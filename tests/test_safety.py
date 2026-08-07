"""Trava de mouse: abortar por mão humana, não por salto espúrio do cursor.

Regressão de sessão real: o bot parava com "mouse movido manualmente" sem o
usuário ter tocado no mouse — uma única amostra deslocada bastava. O critério
correto é movimento CONTÍNUO entre checagens consecutivas.
"""

import pytest

from d4forge.automation.safety import Guard, Limits, StopReason
from d4forge.geometry import Point


@pytest.fixture
def guard(monkeypatch):
    g = Guard(
        limits=Limits(max_attempts=1000, max_minutes=None),
        require_foreground=False,
        abort_on_mouse_move=True,
    )
    g.note_click(Point(500, 500))

    positions: list[Point] = []

    def feed(*points: tuple[int, int]) -> None:
        positions.extend(Point(*p) for p in points)

    monkeypatch.setattr(
        "d4forge.automation.safety.cursor_position", lambda: positions.pop(0)
    )
    # Desliga a tecla de parada para o teste não depender do teclado real.
    monkeypatch.setattr("d4forge.automation.safety.key_is_down", lambda vk: False)
    return g, feed


def test_cursor_parado_no_lugar_nao_aborta(guard):
    g, feed = guard
    feed((500, 500), (501, 499), (500, 500))
    for _ in range(3):
        g.check()


def test_salto_unico_nao_aborta(guard):
    """O cursor apareceu longe (jogo/OS o moveu) mas está imóvel: não é mão
    humana. Antes isso derrubava a sessão."""
    g, feed = guard
    feed((900, 300), (901, 300), (900, 301), (901, 301))
    for _ in range(4):
        g.check()


def test_movimento_continuo_aborta(guard):
    g, feed = guard
    feed((700, 500), (760, 520))  # longe do clique E ainda andando
    g.check()
    with pytest.raises(StopReason, match="movimento"):
        g.check()


def test_movimento_apos_salto_aborta(guard):
    """Salto único é tolerado, mas mexer a partir do novo ponto aborta."""
    g, feed = guard
    feed((900, 300), (901, 300), (960, 340))
    g.check()
    g.check()
    with pytest.raises(StopReason):
        g.check()


def test_clique_zera_a_referencia(guard):
    g, feed = guard
    feed((900, 300))
    g.check()  # anota o desvio
    g.note_click(Point(900, 300))  # o bot clicou ali: nova referência
    feed((901, 301))
    g.check()  # sem desvio, sem abortar


def test_volta_ao_lugar_esquece_o_desvio(guard):
    g, feed = guard
    feed((900, 300), (500, 500), (900, 300), (901, 300), (900, 300))
    g.check()   # desvio anotado
    g.check()   # voltou: âncora limpa
    g.check()   # novo salto único…
    g.check()   # …parado: tolera
    g.check()
