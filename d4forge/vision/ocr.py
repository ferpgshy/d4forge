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

# Abaixo disto, as caixas do detector deixaram parte da linha de fora. A
# cobertura agora e' por uniao de intervalos, e os vaos ENTRE palavras (que as
# caixas legitimamente nao cobrem) consomem uns 5-10% - por isso o limiar e'
# mais folgado que os 0.92 da versao por extremos.
COVERAGE_OK = 0.85

# Threads do onnxruntime. Poucas de proposito - ver comentario em _ensure().
DEFAULT_OCR_THREADS = 2

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


@dataclass(frozen=True, slots=True)
class Reading:
    """Uma leitura do backend, com o que precisamos para julga-la."""

    text: str
    score: float
    coverage: float  # fracao da tinta que as caixas do detector cobriram

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
        return (self.structural_ok, self.complete, self.coverage, self.score)


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
        return self._engine

    def read(self, image: np.ndarray, span: tuple[int, int] | None = None) -> Reading:
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
            return Reading("", 0.0, 0.0)

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
            return Reading("", 0.0, 0.0)

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
        return Reading(text, score, coverage)


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
        self.backend = backend if backend is not None else RapidOcrBackend()
        self._dirty = False

    # -- persistencia -----------------------------------------------------
    def _load_cache(self) -> dict[str, str]:
        if not self._cache_path.exists():
            return {}
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("cache de OCR ilegivel (%s); comecando vazio", exc)
            return {}

    def save(self) -> None:
        if not self._dirty:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self.cache, indent=0, ensure_ascii=False), encoding="utf-8"
        )
        self._dirty = False

    # -- leitura ----------------------------------------------------------
    def read(self, bgr: np.ndarray, verify: Verifier | None = None) -> OcrResult:
        """Le uma ROI que contem uma linha de texto."""
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

        # 2. backend, subindo a escada de renderizacoes ate' uma leitura que o
        # dominio aceite. Quem julga cada degrau e' o `verify` do chamador
        # (parse contra o catalogo) - e' um juiz muito mais forte do que
        # qualquer heuristica de imagem. Sem verify, valem as checagens
        # estruturais (comeca com numero + cobertura sem buracos).
        width = mask.shape[1]
        backend_start = time.perf_counter()

        best: Reading | None = None
        best_text = ""
        accepted = False
        attempts = 0
        for spec in RENDER_LADDER:
            reading = self.backend.read(render_for_ocr(mask, spec), spec.span(width))
            attempts += 1
            text = normalize_text(reading.text)
            if verify is not None and text and verify(text):
                best, best_text, accepted = reading, text, True
                break
            if best is None or reading.rank > best.rank:
                best, best_text = reading, text
            if verify is None and reading.structural_ok and reading.complete:
                break

        self.stats.backend_calls += 1
        self.stats.retries += attempts - 1
        backend_ms = (time.perf_counter() - backend_start) * 1000

        # 3. so' memoriza leitura aceita; duvida se resolve de novo na proxima
        if best_text and self.learn and (accepted or (verify is None)):
            self.cache[line_key] = best_text
            self._dirty = True

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
