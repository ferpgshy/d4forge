"""Caminhos e preferencias persistentes.

Tudo fica em data/ dentro do projeto, e nao no perfil do usuario, para que
cache de OCR, catalogo e regras sejam faceis de inspecionar, versionar e apagar.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


log = logging.getLogger(__name__)


def _dirs() -> tuple[Path, Path]:
    """(pasta gravavel, pasta de recursos).

    Congelado pelo PyInstaller, `__file__` aponta para uma pasta temporaria que
    e' recriada a cada execucao: gravar catalogo e configuracoes ali significa
    perde-los ao fechar. O que o usuario edita fica ao lado do executavel; os
    recursos empacotados vem de sys._MEIPASS.
    """
    if getattr(sys, "frozen", False):
        gravavel = Path(sys.executable).resolve().parent
        recursos = Path(getattr(sys, "_MEIPASS", gravavel))
        return gravavel, recursos
    raiz = Path(__file__).resolve().parent.parent
    return raiz, raiz


PROJECT_DIR, RESOURCE_DIR = _dirs()
DATA_DIR = PROJECT_DIR / "data"
CAPTURES_DIR = PROJECT_DIR / "captures"

SETTINGS_PATH = DATA_DIR / "settings.json"
CATALOG_PATH = DATA_DIR / "affixes.json"
RULES_PATH = DATA_DIR / "rules.json"
TIMINGS_PATH = DATA_DIR / "timings.json"


@dataclass
class Settings:
    # -- interface --------------------------------------------------------
    language: str = "pt-BR"

    # -- seguranca --------------------------------------------------------
    # Simulacao continua existindo no engine (e os testes usam), mas saiu da
    # interface: servia para conferir calibracao antes de confiar no clique, e
    # isso ja' foi feito.
    dry_run: bool = False
    max_attempts: int = 200
    max_gold: int | None = None
    max_minutes: float | None = 60.0
    require_foreground: bool = True
    abort_on_mouse_move: bool = True

    # -- captura e visao --------------------------------------------------
    capture_backend: str = "dxcam"   # dxcam | mss
    monitor_index: int = 0
    text_threshold: int = 120

    # -- ritmo ------------------------------------------------------------
    # 20 ms entre leituras: detectar o estado passou a custar ~1,5 ms depois da
    # subamostragem, entao pesquisar mais rapido praticamente nao custa CPU e
    # corta o atraso de reagir a cada troca de tela.
    poll_interval: float = 0.02
    state_timeout: float = 8.0
    input_speed: str = "instantâneo"  # humano | rápido | instantâneo

    # Tempo entre apertar Iniciar e o engine comecar a agir, para dar chance de
    # voltar o foco para o jogo. Sem isso o guard aborta na hora, porque quem
    # esta' em primeiro plano e' a janela do proprio app.
    start_delay_s: float = 4.0
    focus_game_on_start: bool = True

    def to_json(self) -> dict:
        return asdict(self)

    # `path=None` e nao `path=SETTINGS_PATH`: um default no cabecalho fixa o
    # caminho na hora do import, e a partir dai nao ha' como redireciona-lo -
    # nem nos testes, que acabavam lendo e sobrescrevendo os ajustes de verdade.
    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or SETTINGS_PATH
        if not path.exists():
            return cls()
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in blob.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")


TEMPER_PATH = DATA_DIR / "temper.json"


def load_temper_goal(path: Path | None = None):
    """Meta do Tempering salva. Devolve o padrao se nao houver arquivo."""
    from .temper.rules import Recharge, TemperGoal

    # Resolvido na chamada, nunca no cabecalho: um default no `def` fixa o
    # caminho no import e deixa de ser redirecionavel - o mesmo descuido que
    # fazia os testes de GUI sobrescreverem os ajustes de verdade.
    caminho = path or TEMPER_PATH
    if not caminho.exists():
        return TemperGoal()
    # Qualquer defeito no arquivo vira "usa o padrao", NUNCA excecao.
    #
    # Isto roda na montagem da janela, entao um valor inesperado aqui nao
    # estraga uma preferencia: impede o app de ABRIR. Foi o que aconteceu quando
    # `max_recharges` passou a aceitar None - o arquivo ja' salvo trazia `null`,
    # `int(None)` estourou, e o programa parou de subir. Um arquivo de ajustes
    # jamais deveria ter esse poder.
    try:
        blob = json.loads(caminho.read_text(encoding="utf-8"))
        if not isinstance(blob, dict):
            return TemperGoal()

        teto = blob.get("max_recharges")
        return TemperGoal(
            require_greater=bool(blob.get("require_greater", True)),
            min_fraction=_optional_float(blob.get("min_fraction")),
            min_value=_optional_float(blob.get("min_value")),
            affix_contains=str(blob.get("affix_contains") or ""),
            # A politica de recarga NAO volta do arquivo: ela gasta Pergaminhos
            # e a escolha e' por sessao. Reabrir o app ja' gastando seria uma
            # surpresa cara.
            recharge=Recharge.STOP,
            max_recharges=int(teto) if teto else None,
        )
    except Exception:  # noqa: BLE001 - ver o comentario acima
        log.warning("temper.json ilegível; usando o padrão", exc_info=True)
        return TemperGoal()


def _optional_float(valor):
    """Numero, ou None se o arquivo trouxer qualquer outra coisa."""
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def save_temper_goal(goal, path: Path | None = None) -> None:
    caminho = path or TEMPER_PATH
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps({
            "require_greater": goal.require_greater,
            "min_fraction": goal.min_fraction,
            "min_value": goal.min_value,
            "affix_contains": goal.affix_contains,
            "max_recharges": goal.max_recharges,
        }, indent=2),
        encoding="utf-8",
    )


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)


PREVIOUS_SESSION_DIR = "sessao_anterior"


def clear_captures() -> int:
    """Esvazia captures/ por completo. Devolve quantos arquivos sairam.

    Chamada ao fechar a janela normalmente. Se o app cair, nao passa por aqui -
    as evidencias sobrevivem justamente quando importam.

    A pasta so' guarda material descartavel de depuracao (recortes do OCR e
    quadros de erro), entao levar tudo e' o comportamento pedido. Se voce
    guardar algo ali que queira manter, tire antes de fechar o app.
    """
    if not CAPTURES_DIR.is_dir():
        return 0

    removed = 0
    for path in sorted(CAPTURES_DIR.rglob("*"), key=lambda p: -len(p.parts)):
        try:
            if path.is_file():
                path.unlink()
                removed += 1
            elif path.is_dir():
                path.rmdir()
        except OSError:
            continue
    return removed
