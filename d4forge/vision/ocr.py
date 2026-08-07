"""Motor de OCR: cache exato por conteudo + backend neural.

    1. cache   ~0.2 ms   linha identica ja' vista antes
    2. backend ~30-90 ms primeira vez que ve' aquela linha

Como o jogo renderiza a mesma linha com exatamente os mesmos pixels, o cache
por hash de conteudo tem zero falso positivo. Os rolls vem de um conjunto
finito, entao o cache satura com o uso.

Duas decisoes tomadas contra medicao, nao por intuicao:

* A imagem vai binarizada e ampliada por repeticao de pixel, com margem branca.
  Variantes em tom de cinza liam a marca d'agua "PUBLIC TEST BUILD" junto com o
  texto ("...Generation 72"); sem margem, o detector cortava as pontas da linha
  e "+151 Dexterity" virava "ext".
* Ler a linha inteira de uma vez, e nao em pedacos. Uma versao que separava
  "valor" e "nome" para cachear cada metade ficou mais rapida e bem menos
  precisa - "+2 to Imbuement Skills" saiu como "to kil". Recortes pequenos
  confundem o detector de caixas.

O OCR nao e' o gargalo do loop de encantamento: as animacoes do jogo custam
segundos. Por isso a prioridade aqui e' acerto, nao microssegundo. Leitura
duvidosa e' marcada como tal e o engine trata duvida como "nao trocar".
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .preprocess import (
    DEFAULT_THRESHOLD,
    RENDER_LADDER,
    content_hash,
    prepare_line,
    render_for_ocr,
)

# Abaixo disto, as caixas do detector deixaram parte da linha de fora.
#
# Calibrado com o trace da escada sobre recortes reais: leitura correta mede
# 0.99-1.00, porque o detector cobre a linha inteira num bloco continuo. Uma
# leitura que perdeu o "+1," de "+1,431 Maximum Life" mede 0.88 - o digito
# comido custa so' ~12% da largura, entao o limiar precisa ser exigente para
# separar os dois casos. Com 0.85 aquela leitura truncada passava valendo 431.
COVERAGE_OK = 0.95

# Threads do onnxruntime. Poucas de proposito - ver comentario em _ensure().
DEFAULT_OCR_THREADS = 2

# Suba este numero sempre que a escada de renderizacoes, o limiar de cobertura
# ou a gramatica do parser mudarem. O cache em disco guarda o veredito de uma
# versao antiga; sem invalidar, uma leitura errada gravada no passado continua
# voltando pronta e escapa de toda correcao posterior.
CACHE_VERSION = 4

# Numero com o digito da frente comido: ".7%", ",425". A linha do jogo nunca
# comeca assim, entao no cache isso e' sempre residuo de leitura estropiada.
_TRUNCATED_NUMBER = re.compile(r"^\s*[.,]\s*\d")


def plausible_line(text: str) -> bool:
    """Uma linha de afixo poderia mesmo ter este texto?"""
    text = (text or "").strip()
    if not text or _TRUNCATED_NUMBER.match(text):
        return False
    return any(ch.isalpha() for ch in text)

_STARTS_WITH_NUMBER = re.compile(r"^\s*(?:[+-]|[x×])?\s*\d")
_NO_CHANGE = re.compile(r"^\s*no\s*change", re.IGNORECASE)
# Familia "Lucky Hit: Up to a X% Chance..." - o valor fica no MEIO da frase.
_LUCKY_HIT = re.compile(r"^\s*lucky\s*hit\b", re.IGNORECASE)

log = logging.getLogger(__name__)

# Recebe o texto montado e diz se ele e' confiavel o bastante para ir ao cache.
Verifier = Callable[[str], bool]

# O jogo usa apostrofo tipografico e tracos longos que confundem o parser.
_NORMALIZE = str.maketrans({"’": "'", "‘": "'", "–": "-", "—": "-"})
_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _WS.sub(" ", text.translate(_NORMALIZE)).strip()


def _box_bounds(box) -> tuple[float, float, float, float]:
    """(esq, dir, topo, base) de uma caixa do detector.

    O formato e' uma lista de 4 pontos [x, y]; alguns backends devolvem numpy
    array. Em caso de duvida devolvemos zeros para nao quebrar a ordenacao.
    """
    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        return min(xs), max(xs), min(ys), max(ys)
    except (TypeError, ValueError, IndexError):
        return 0.0, 0.0, 0.0, 0.0


def order_boxes(items: list[tuple[float, float, float, float, str, float]]):
    """Ordena caixas em ordem de leitura: linha de cima primeiro, depois X.

    Um afixo longo quebra em duas linhas na tela, e o detector devolve as
    caixas em ordem arbitraria. Ordenar so' por X intercalava as linhas:
    "Lucky Hit: Up to a 13% Chance..." saiu como "Lutky ... 13% tne lU ..."
    numa sessao real. Agrupamos por faixa vertical (centros a menos de meia
    altura tipica um do outro = mesma linha) e lemos linha a linha.
    """
    if not items:
        return items
    heights = sorted((b - t) for _l, _r, t, b, _txt, _s in items)
    typical = max(1.0, heights[len(heights) // 2])

    rows: list[list] = []
    centers: list[float] = []
    for item in sorted(items, key=lambda i: (i[2] + i[3]) / 2):
        center = (item[2] + item[3]) / 2
        if rows and abs(center - centers[-1]) < typical * 0.6:
            rows[-1].append(item)
        else:
            rows.append([item])
            centers.append(center)
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda i: i[0]))
    return ordered


# Largura de tinta por caractere acima da qual faltam letras no resultado.
#
# Medido sobre 56 recortes de uma sessao real: leitura inteira fica entre 8,12 e
# 10,47 px/char; as truncadas destoam - "+2 Life Kil" (era "+271 Life on Kill")
# deu 14,33, "+284 Life Kil" deu 11,73. E' o unico sinal que pega omissao do
# RECONHECEDOR: quando ele engole letras mas o detector cobriu a linha toda, a
# cobertura continua 1,00 e nao denuncia nada.
MAX_INK_PER_CHAR = 11.0


@dataclass(frozen=True, slots=True)
class Reading:
    """Uma leitura do backend, com o que precisamos para julga-la."""

    text: str
    score: float
    coverage: float  # fracao da tinta que as caixas do detector cobriram
    ink_width: int = 0  # largura da mascara, para aferir a densidade

    @property
    def density_ok(self) -> bool:
        """O texto lido e' comprido o bastante para a tinta que existe?"""
        chars = len(self.text.replace(" ", ""))
        if not chars or not self.ink_width:
            return True
        return self.ink_width / chars <= MAX_INK_PER_CHAR

    @property
    def structural_ok(self) -> bool:
        """Linha de afixo comeca com numero (com sinal +/-/x), e' "No Change",
        ou pertence a familia "Lucky Hit:", cujo valor fica no meio da frase."""
        return bool(
            _STARTS_WITH_NUMBER.match(self.text)
            or _NO_CHANGE.match(self.text)
            or _LUCKY_HIT.match(self.text)
        )

    @property
    def complete(self) -> bool:
        return self.coverage >= COVERAGE_OK

    @property
    def rank(self) -> tuple:
        """Maior e' melhor. A estrutura pesa mais que a confianca do modelo.

        Confianca sozinha nao serve de arbitro: medido, o modelo leu 'Dexterity'
        (perdendo o '+151') com score 0.90, acima do 0.74 da leitura correta.
        """
        return (self.structural_ok, self.density_ok, self.complete,
                self.coverage, self.score)


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    source: str  # cache | backend | empty
    elapsed_ms: float
    confidence: float = 1.0
    backend_ms: float = 0.0   # tempo gasto dentro do modelo
    retried: bool = False     # precisou da segunda passada?

    @property
    def ok(self) -> bool:
        return bool(self.text)

    @property
    def overhead_ms(self) -> float:
        """Tempo fora do modelo: preparo, cache, disco.

        Medido em bancada o modelo custa ~35 ms, mas o ciclo real acusava 873 ms
        de mediana. Separar as duas coisas e' o que permite achar a diferenca.
        """
        return max(0.0, self.elapsed_ms - self.backend_ms)


@dataclass
class OcrStats:
    cache_hits: int = 0
    backend_calls: int = 0
    retries: int = 0
    empty: int = 0
    total_ms: float = 0.0

    @property
    def reads(self) -> int:
        return self.cache_hits + self.backend_calls + self.empty

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.reads if self.reads else 0.0

    @property
    def hit_ratio(self) -> float:
        served = self.cache_hits + self.backend_calls
        return self.cache_hits / served if served else 0.0

    def summary(self) -> str:
        return (
            f"{self.reads} leituras | cache {self.cache_hits} backend {self.backend_calls} "
            f"repescagem {self.retries} | acerto {self.hit_ratio * 100:.0f}% "
            f"| media {self.avg_ms:.2f} ms"
        )


# Maior lado que o detector processa. Ver _tune_detector().
DET_LIMIT_SIDE = 1280


def _tune_detector(engine) -> bool:
    """Impede o detector de inflar a imagem.

    O RapidOCR vem com `limit_type: min` e `limit_side_len: 736`, ou seja: ele
    redimensiona ate' o MENOR lado alcancar 736. Nossas linhas sao largas e
    baixas - 660x104 -, entao isso multiplicava tudo por 7 e mandava uma imagem
    de 4670x736 (3,4 megapixels) para ler uma unica linha de texto.

    Era a causa da instabilidade: leitura nova custava 1,4-5,5 s, enquanto o
    cache respondia em 1 ms. Trocando para `max`, o maior lado passa a mandar e
    a imagem segue no tamanho original.

    Medido nos recortes reais: 1951 ms -> 70 ms por linha (28x), e a precisao
    subiu de 4/5 para 5/5 - a imagem inflada tambem atrapalhava o modelo.
    """
    try:
        for op in getattr(engine.text_detector, "preprocess_op", []):
            if hasattr(op, "limit_type") and hasattr(op, "limit_side_len"):
                op.limit_type = "max"
                op.limit_side_len = DET_LIMIT_SIDE
                return True
    except Exception as exc:  # noqa: BLE001 - versao nova pode mudar a estrutura
        log.warning("nao consegui ajustar o detector (%s); segue no padrao", exc)
    else:
        log.warning("detector sem limit_type conhecido; segue no padrao")
    return False


class RapidOcrBackend:
    """Backend neural. Carregado sob demanda: inicializar leva ~1-2 s."""

    name = "rapidocr"

    def __init__(self, threads: int = DEFAULT_OCR_THREADS) -> None:
        self._engine = None
        self.threads = threads

    def _ensure(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            # Limitar as threads e' contraintuitivo mas foi o que mediu melhor:
            # o Diablo IV ja' satura os 16 processadores logicos, e deixar o
            # onnxruntime abrir mais threads so' aumenta a disputa. Com 1 thread
            # a inferencia saiu em 32,7 ms; com 8, em 40,4 ms.
            try:
                self._engine = RapidOCR(intra_op_num_threads=self.threads)
            except TypeError:
                self._engine = RapidOCR()
            _tune_detector(self._engine)
        return self._engine

    def read(
        self,
        image: np.ndarray,
        span: tuple[int, int] | None = None,
        ink_width: int = 0,
    ) -> Reading:
        """Le uma imagem que ja' e' UMA linha (texto escuro em fundo claro).

        `span` diz onde a tinta deveria estar na imagem. Comparar isso com o que
        as caixas do detector realmente cobriram denuncia caractere descartado:
        e' assim que pegamos "+1,431" saindo como "431".

        Mantemos a deteccao de caixas ligada: medido nos prints de referencia,
        ficou tanto mais preciso (5/7 contra 4/7) quanto mais rapido (31 ms
        contra 56 ms) do que pular direto para o reconhecimento.
        """
        result, _ = self._ensure()(image)
        if not result:
            return Reading("", 0.0, 0.0, ink_width)

        # (esq, dir, topo, base, texto, score)
        found: list[tuple[float, float, float, float, str, float]] = []
        for item in result:
            if not isinstance(item, (list, tuple)):
                continue
            if len(item) >= 3:       # (caixa, texto, score)
                left, right, top, bottom = _box_bounds(item[0])
                found.append((left, right, top, bottom, str(item[1]), float(item[2])))
            elif len(item) == 2:     # (texto, score)
                found.append((float(len(found)), 0.0, 0.0, 0.0, str(item[0]), float(item[1])))
        if not found:
            return Reading("", 0.0, 0.0, ink_width)

        # Ordem de leitura: linha de cima primeiro, depois X. O detector devolve
        # as caixas em ordem arbitraria - juntar na ordem de chegada ja' fez
        # "+4 Energy" virar "Energy +4", e ordenar so' por X intercalava as
        # duas linhas de um afixo longo.
        found = order_boxes(found)

        text = " ".join(part for _l, _r, _t, _b, part, _s in found)
        score = sum(s for _l, _r, _t, _b, _txt, s in found) / len(found)

        coverage = 1.0
        if span is not None:
            start, end = span
            width = max(1.0, end - start)
            # Uniao dos intervalos X das caixas, nao so' os extremos: quando o
            # detector dropa uma palavra do MEIO ("+2 to Invigorating Strike"
            # virou "-2 to Strike"), os extremos continuam cobertos e so' o
            # buraco central denuncia a perda.
            intervals = sorted(
                (max(float(start), l), min(float(end), r))
                for l, r, _t, _b, _txt, _s in found
                if r > l
            )
            covered = 0.0
            cursor = float(start)
            for left, right in intervals:
                if right <= cursor:
                    continue
                covered += right - max(cursor, left)
                cursor = max(cursor, right)
            coverage = max(0.0, min(1.0, covered / width))
        return Reading(text, score, coverage, ink_width)


class OcrEngine:
    def __init__(
        self,
        data_dir: Path,
        backend: RapidOcrBackend | None = None,
        threshold: int = DEFAULT_THRESHOLD,
        learn: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.threshold = threshold
        self.learn = learn
        self.stats = OcrStats()

        self._cache_path = self.data_dir / "ocr_cache.json"
        self.cache: dict[str, str] = self._load_cache()
        # Leituras que NAO foram aprovadas. Ficam so' em memoria e nunca vao
        # para o disco - mas evitam repetir a escada inteira (3 chamadas ao
        # modelo, ~1,4 s cada sob disputa de CPU) num recorte que ja' sabemos
        # que o modelo le' assim. Como a inferencia e' deterministica, repetir
        # daria exatamente o mesmo resultado.
        self._rejected: dict[str, str] = {}
        self.backend = backend if backend is not None else RapidOcrBackend()
        self._dirty = False

    # -- persistencia -----------------------------------------------------
    def _load_cache(self) -> dict[str, str]:
        """Carrega o cache, descartando o que a versao atual nao aceitaria.

        O cache guarda o que uma versao ANTIGA do pipeline julgou confiavel. Ao
        endurecer o parser, entradas ja' gravadas continuam valendo e voltam
        instantaneamente como se estivessem certas: foi assim que
        ".7% Dodge Chance" (o "7" da frente comido) sobreviveu a correcao e
        seguiu sendo devolvido em 0,7 ms, sem passar pelo modelo de novo.
        """
        if not self._cache_path.exists():
            return {}
        try:
            blob = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("cache de OCR ilegivel (%s); comecando vazio", exc)
            return {}

        if not isinstance(blob, dict):
            return {}
        if blob.get("version") != CACHE_VERSION:
            log.info("cache de OCR e' de outra versao do pipeline; descartado")
            self._dirty = True
            return {}

        entries = blob.get("entries", {})
        clean = {k: v for k, v in entries.items() if plausible_line(v)}
        if len(clean) != len(entries):
            log.info("%d entrada(s) implausivel(is) descartada(s) do cache",
                     len(entries) - len(clean))
            self._dirty = True
        return clean

    def save(self) -> None:
        if not self._dirty:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        blob = {"version": CACHE_VERSION, "entries": self.cache}
        self._cache_path.write_text(
            json.dumps(blob, indent=0, ensure_ascii=False), encoding="utf-8"
        )
        self._dirty = False

    # -- leitura ----------------------------------------------------------
    def read(
        self,
        bgr: np.ndarray,
        verify: Verifier | None = None,
        ui_scale: float = 1.0,
    ) -> OcrResult:
        """Le uma ROI que contem uma linha de texto.

        `ui_scale` e' o quanto a tela do jogo e' maior que a de referencia
        (1.0 em 1080p, 1.33 em 1440p, 2.0 em 4K). Serve para UMA coisa so':
        converter a largura da tinta para pixels de referencia antes da checagem
        de densidade. A escada de render nao muda com a resolucao - medido, o
        detector ja' limita a imagem a 1280 px de lado, entao ler a mesma linha
        custa 22-32 ms em 1080p, 1440p ou 4K indistintamente, e reduzir a
        ampliacao so' fazia "15.0%" sair como "1 5.0%".
        """
        t0 = time.perf_counter()

        def done(
            text: str, source: str, conf: float = 1.0,
            backend_ms: float = 0.0, retried: bool = False,
        ) -> OcrResult:
            elapsed = (time.perf_counter() - t0) * 1000
            self.stats.total_ms += elapsed
            return OcrResult(text, source, elapsed, conf, backend_ms, retried)

        mask, _box = prepare_line(bgr, self.threshold)
        if mask is None:
            self.stats.empty += 1
            return done("", "empty", 0.0)

        # 1. linha inteira ja' vista
        line_key = content_hash(mask)
        cached = self.cache.get(line_key)
        if cached is not None:
            self.stats.cache_hits += 1
            return done(cached, "cache")
        rejected = self._rejected.get(line_key)
        if rejected is not None:
            self.stats.cache_hits += 1
            return done(rejected, "cache")

        # 2. backend, subindo a escada de renderizacoes ate' uma leitura que o
        # dominio aceite. Quem julga cada degrau e' o `verify` do chamador
        # (parse contra o catalogo) - e' um juiz muito mais forte do que
        # qualquer heuristica de imagem. Sem verify, valem as checagens
        # estruturais (comeca com numero + cobertura sem buracos).
        width = mask.shape[1]
        backend_start = time.perf_counter()

        best: Reading | None = None
        best_text = ""
        best_key: tuple = ()
        accepted = False
        attempts = 0
        # A densidade de tinta por caractere foi medida em pixels da tela de
        # referencia; numa tela maior a mesma frase tem mais pixels sem ter mais
        # letras, e sem esta conversao `density_ok` reprovaria toda leitura.
        ink_width = int(round(width / ui_scale)) if ui_scale > 1.02 else width
        for spec in RENDER_LADDER:
            reading = self.backend.read(
                render_for_ocr(mask, spec), spec.span(width), ink_width
            )
            attempts += 1
            text = normalize_text(reading.text)
            recognized = bool(text) and (verify is None or verify(text))

            # A aprovacao exige as DUAS coisas: o dominio reconhecer a linha e
            # ela estar geometricamente completa. So' `verify` nao basta -
            # ".0% Dodgei Chance" casa com "Dodge Chance" no catalogo e passa
            # como confiavel valendo 0.0. E' a cobertura que denuncia o digito
            # perdido e manda subir mais um degrau.
            sound = (
                reading.structural_ok
                and reading.complete
                and reading.density_ok
                and plausible_line(text)
            )
            if sound and recognized:
                best, best_text, accepted = reading, text, True
                break

            # Nenhum degrau aprovado ainda: guarda o menos ruim. Concordar com o
            # catalogo pesa mais que "comeca com digito" - sem isso o lixo
            # "29 70 hance" (valor 2970!) vencia ".2% Dodgei Chance", que errava
            # so' o primeiro digito. Ambos acabam marcados como duvidosos, mas o
            # que sobra no log e no cache tem de ser o mais proximo da verdade.
            key = (recognized, *reading.rank)
            if best is None or key > best_key:
                best, best_text, best_key = reading, text, key

        self.stats.backend_calls += 1
        self.stats.retries += attempts - 1
        backend_ms = (time.perf_counter() - backend_start) * 1000

        # 3. leitura aprovada vai para o cache em disco; a reprovada fica só na
        # memoria da sessao, para nao repetir a escada no mesmo recorte
        if best_text and self.learn:
            if accepted or verify is None:
                self.cache[line_key] = best_text
                self._dirty = True
            else:
                self._rejected[line_key] = best_text

        return done(best_text, "backend", best.score if best else 0.0,
                    backend_ms, attempts > 1)

    def read_many(
        self, images: list[np.ndarray], verify: Verifier | None = None
    ) -> list[OcrResult]:
        return [self.read(img, verify) for img in images]

    # -- correcao manual --------------------------------------------------
    def teach(self, bgr: np.ndarray, text: str) -> bool:
        """Grava uma leitura corrigida a mao (tela de treino da GUI).

        O acerto vale so' para esta linha exata; se o numero mudar, o backend le'
        de novo. Como o texto que aparece na tela e' sempre identico ao pixel,
        uma correcao nunca precisa ser repetida.
        """
        mask, _ = prepare_line(bgr, self.threshold)
        if mask is None:
            return False
        self.cache[content_hash(mask)] = normalize_text(text)
        self._dirty = True
        return True

    def forget(self, text: str) -> int:
        """Esquece toda entrada que produza este texto."""
        keys = [k for k, v in self.cache.items() if v == text]
        for k in keys:
            del self.cache[k]
        if keys:
            self._dirty = True
        return len(keys)

    def reset_learning(self) -> None:
        self.cache.clear()
        self._dirty = True
        self.save()
