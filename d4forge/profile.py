"""Perfil de ROIs do Occultist.

Todas as coordenadas sao em pixels de uma tela de referencia 1920x1080 e vem de
medicao direta nos prints em PRINTS SEM CORTE/ (image 5 a 9), nao de estimativa.
Em runtime o perfil e' escalado para o client rect real do jogo.

Como o perfil viaja entre resolucoes
------------------------------------
A escala e' UNIFORME e sai da altura (`client.h / 1080`), nao de dois fatores
independentes. Esticar x por `w/1920` e y por `h/1080` so' funciona quando a
tela e' 16:9; numa ultrawide 3440x1440 os fatores seriam 1,79 e 1,33 e toda ROI
sairia deformada.

Com escala unica sobra a pergunta horizontal: onde a interface fica quando a
tela e' mais larga que 16:9. Cada ROI declara sua ancora:

  ANCHOR_LEFT     colada na borda esquerda - o painel do Occultist
  ANCHOR_CENTER   centrada na tela - o dialogo de confirmacao

Em 16:9 as duas ancoras dao exatamente o mesmo resultado que a conta antiga
(demonstrado em tests/test_resolution.py), entao nada muda para quem ja' rodava.
A diferenca so' aparece fora de 16:9.

Layout medido (1920x1080):

  ENCHANT      titulo OCCULTIST y 78..125 | 4 afixos em y 496/545/596/644
               orbes em x~210  | botao Enchant y 862..964 x 277..659
  CONFIRM      Accept x 824..946 / Cancel x 972..1094, ambos y 620..659
  REPLACE      titulo y 103..146 | afixo atual y 369..382
               opcoes y 558 e 632, No Change y 709 | orbes em x~145
               botao Replace Affix y ~900..948
  RESULT       titulo ITEM y 398..438 | botao Close y 638..660 x 289..411
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import Rect

REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080
REFERENCE_ASPECT = REFERENCE_WIDTH / REFERENCE_HEIGHT

ANCHOR_LEFT = "left"
ANCHOR_CENTER = "center"

# ROIs que o jogo centraliza na tela em vez de prender no painel esquerdo.
#
# Nao e' palpite: nos prints de 1920x1080 o par Accept/Cancel ocupa x 824..1094,
# cujo meio e' 959 - a um pixel do centro da tela (960). O mesmo vale para o
# texto do dialogo (726..1190, meio 958). Todo o resto vive no painel do
# Occultist, entre x 40 e x 680.
CENTERED_ROIS = frozenset({"confirm_accept", "confirm_cancel", "confirm_text"})

# Passo vertical entre linhas de afixo na tela de selecao (medido: 48/51/48).
AFFIX_ROW_PITCH = 49.3
AFFIX_ROW_TOP = 496  # centro da primeira linha


def _row(cy: int, x: int = 228, w: int = 306, h: int = 26) -> Rect:
    """ROI de uma linha de texto centrada verticalmente em `cy`.

    A largura cobre ate' a borda da caixa de afixos (x~534), e nao apenas o
    texto medido nos prints: nome de afixo longo passaria do recorte e sairia
    cortado no OCR.
    """
    return Rect(x, cy - h // 2, w, h)


@dataclass(frozen=True)
class EnchantProfile:
    """ROIs em pixels de referencia (1920x1080)."""

    # -- tela ENCHANT (Occultist) ----------------------------------------
    occultist_title: Rect = Rect(258, 80, 196, 36)
    enchant_button: Rect = Rect(277, 862, 382, 102)
    enchant_cost: Rect = Rect(396, 916, 190, 26)
    gold_total: Rect = Rect(58, 974, 268, 30)

    # Variante SELECT: item ainda nao encantado, 4 afixos para escolher.
    affix_rows: tuple[Rect, ...] = tuple(
        _row(int(round(AFFIX_ROW_TOP + i * AFFIX_ROW_PITCH))) for i in range(4)
    )
    affix_orbs: tuple[Rect, ...] = tuple(
        Rect(196, int(round(AFFIX_ROW_TOP + i * AFFIX_ROW_PITCH)) - 14, 30, 28)
        for i in range(4)
    )

    # Variante LOCKED: afixo ja' escolhido, mostra so' ele + explicacao.
    # ROI com altura para DUAS linhas: afixo longo ("Lucky Hit: Up to...")
    # quebra, e uma ROI de linha unica fatiava o texto ao meio - o OCR devolvia
    # metade de cada linha misturada. O aparo por bbox ignora a folga quando o
    # afixo e' de uma linha so'.
    locked_affix: Rect = Rect(184, 482, 340, 44)
    locked_hint: Rect = Rect(180, 556, 340, 78)

    # -- dialogo CONFIRM --------------------------------------------------
    confirm_accept: Rect = Rect(824, 620, 122, 40)
    confirm_cancel: Rect = Rect(972, 620, 122, 40)
    confirm_text: Rect = Rect(726, 455, 464, 70)

    # -- tela REPLACE AFFIX -----------------------------------------------
    replace_title: Rect = Rect(238, 106, 224, 38)
    replace_current: Rect = Rect(150, 352, 404, 44)
    # Largura ate' x~578 (a caixa termina em x 600) e altura para DUAS linhas:
    # afixo longo ("Lucky Hit: Up to...") quebra, e a ROI de linha unica
    # fatiava o texto ao meio - o OCR devolvia metade de cada linha misturada.
    # As ROIs nao podem se tocar: opcao 1 termina em y 600, opcao 2 comeca 610.
    replace_options: tuple[Rect, ...] = (
        Rect(174, 536, 404, 64),   # opcao 1, texto de 1 linha no centro y 558
        Rect(174, 610, 404, 64),   # opcao 2, texto de 1 linha no centro y 632
    )
    replace_orbs: tuple[Rect, ...] = (
        Rect(131, 544, 30, 28),    # opcao 1
        Rect(131, 618, 30, 28),    # opcao 2
        Rect(131, 696, 30, 28),    # No Change (marcado por padrao)
    )
    replace_no_change: Rect = Rect(174, 688, 310, 24)
    replace_button: Rect = Rect(186, 898, 330, 50)

    # -- dialogo RESULT ---------------------------------------------------
    result_title: Rect = Rect(276, 398, 148, 42)
    result_close: Rect = Rect(286, 634, 128, 30)

    # Onde largar o cursor depois de cada clique.
    #
    # Nao e' cosmetico: o Diablo IV desenha o proprio cursor DENTRO do quadro
    # renderizado, entao ele nao da' para excluir da captura. Parado sobre a
    # lista de afixos, o cursor acende a ROI e a tela "enchant_locked" era lida
    # como "enchant_select"; parado sobre um texto, corrompe o OCR; e parado
    # sobre um item, o jogo abre tooltip por cima da interface.
    #
    # Este ponto fica na borda escura do painel, vazia nas cinco telas.
    cursor_park: Rect = Rect(36, 762, 70, 58)

    # -- regioes de sondagem para classificar o estado --------------------
    # O painel esquerdo escurece quando um dialogo modal abre: isso sozinho
    # ja' separa CONFIRM/RESULT das telas normais.
    panel_probe: Rect = Rect(40, 60, 640, 960)

    def scaled(self, client: Rect) -> "ResolvedProfile":
        return ResolvedProfile(self, client)


@dataclass
class ResolvedProfile:
    """Perfil convertido para coordenadas de tela do client rect atual."""

    base: EnchantProfile
    client: Rect
    scale: float = field(init=False)
    _dx: float = field(init=False)

    def __post_init__(self) -> None:
        # Escala unica, tirada da altura: a interface do jogo cresce junto com a
        # altura da tela e nao se estica na horizontal.
        self.scale = self.client.h / REFERENCE_HEIGHT
        # Quanto a tela e' mais larga que a moldura 16:9 correspondente. Zero em
        # 16:9, ~677 px numa 3440x1440. E' o unico termo que separa as ancoras.
        self._dx = self.client.w - REFERENCE_WIDTH * self.scale

    @property
    def widescreen(self) -> bool:
        """Tela mais larga que 16:9 (ultrawide), onde a ancora importa."""
        return abs(self._dx) > 1.0

    def rect(self, ref: Rect, anchor: str = ANCHOR_LEFT) -> Rect:
        """Converte um Rect de referencia para coordenadas de tela."""
        x = ref.x * self.scale
        if anchor == ANCHOR_CENTER:
            x += self._dx / 2
        return Rect(
            self.client.x + int(round(x)),
            self.client.y + int(round(ref.y * self.scale)),
            max(1, int(round(ref.w * self.scale))),
            max(1, int(round(ref.h * self.scale))),
        )

    def rects(self, refs, anchor: str = ANCHOR_LEFT) -> list[Rect]:
        return [self.rect(r, anchor) for r in refs]

    def __getattr__(self, name: str):
        """Espelha os campos do perfil base ja' convertidos."""
        if name.startswith("_"):
            raise AttributeError(name)
        value = getattr(self.base, name)
        anchor = ANCHOR_CENTER if name in CENTERED_ROIS else ANCHOR_LEFT
        if isinstance(value, Rect):
            return self.rect(value, anchor)
        if isinstance(value, tuple) and value and isinstance(value[0], Rect):
            return self.rects(value, anchor)
        return value


DEFAULT_PROFILE = EnchantProfile()
