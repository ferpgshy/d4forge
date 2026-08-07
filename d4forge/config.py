"""Caminhos e preferencias persistentes.

Tudo fica em data/ dentro do projeto, e nao no perfil do usuario, para que
cache de OCR, catalogo e regras sejam faceis de inspecionar, versionar e apagar.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


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

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        if not path.exists():
            return cls()
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in blob.items() if k in known})

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")


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
