"""ROIs do painel de Tempering do Ferreiro.

Coordenadas em pixels de uma tela de referencia 1920x1080, medidas nos prints de
`Funcionalidade Tempering/PRINTS INTEIROS/` - nao estimadas. O metodo foi
binarizar o painel e deixar as bandas de tinta apontarem onde o texto esta',
depois conferir cada banda passando OCR nela.

Layout medido:

  IDLE       BLACKSMITH y 56..129 | aba TEMPERING y 135..182
             item y 198..371 com o botao circular de recarga em x 419..441
             categorias em duas linhas, y 374..588 e y 610..711
             "Note: Existing affix..." y 732..757
             "Temper Rerolls Remaining: N" y 757..791
             botao Temper Item y 878..944
  RECIPES    titulo TEMPERING RECIPES y 100..168 | "DEFENSIVE (10)" y 188..222
             lista y 183..826 | Close y 918..964
  ANIMACAO   titulo TEMPERING y 221..275 | Skip y 798..840
  RESULTADO  TEMPER COMPLETE y 282..342 | afixo y 660..736 | Close y 798..840

Skip e Close ocupam o MESMO retangulo - o que separa as duas telas e' o texto
"TEMPER COMPLETE", nao o botao.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Rect
from ..profile import ResolvedProfile


@dataclass(frozen=True)
class TemperProfile:
    """ROIs em pixels de referencia (1920x1080)."""

    # -- tela IDLE (aba Tempering aberta) ---------------------------------
    # Só fica aceso quando nenhum modal está por cima: é o teste que separa a
    # tela normal das outras três (medido: 0.352 contra 0.000).
    blacksmith_header: Rect = Rect(44, 56, 659, 45)
    tempering_tab: Rect = Rect(39, 135, 665, 47)

    # Botao circular que recarrega os Temper Rerolls, a' direita do item.
    # Fica CINZA quando nao ha' o que recarregar: ou os rerolls ja' estao no
    # maximo do item, ou os Pergaminhos acabaram. Medido: 0.2736 de tinta aceso
    # contra 0.0000 apagado - separacao total.
    recharge_button: Rect = Rect(408, 304, 48, 48)

    note_line: Rect = Rect(210, 730, 366, 28)
    # "Temper Rerolls Remaining: N".
    #
    # O NUMERO e' informativo; quem conduz o ciclo e' o estado dos botoes, que
    # custa ~0,1 ms e nao erra digito. A PRESENCA desta linha e' consultada num
    # caso so': quando o Temper Item esta' cinza E nao da' para recarregar, ela
    # separa "voce ainda nao escolheu a receita" de "os Pergaminhos acabaram".
    #
    # Ela NAO significa "ha' receita escolhida". Num slot livre o jogo escreve
    # "Adds your selected affix" e nao mostra contador, com o botao aceso.
    rerolls_remaining: Rect = Rect(210, 757, 360, 34)

    # Botao "Temper Item / Temper Rerolls: N". Cinza quando nao da' para
    # temperar - sem receita escolhida ou sem rerolls.
    temper_button: Rect = Rect(340, 878, 320, 66)

    # -- tela TEMPERING RECIPES -------------------------------------------
    recipes_title: Rect = Rect(85, 100, 620, 68)
    recipes_category: Rect = Rect(85, 188, 260, 34)
    recipes_close: Rect = Rect(285, 918, 135, 46)

    # -- telas de animacao e resultado ------------------------------------
    modal_header: Rect = Rect(23, 217, 681, 63)
    # Larga o bastante para o "TEMPER COMPLETE" inteiro caber: com a ROI
    # apertada o OCR devolvia "MPER COMPLETE", e comparar texto cortado obriga
    # a inventar regra de tolerancia - que e' justamente o que queremos evitar.
    complete_title: Rect = Rect(190, 326, 440, 38)
    # Regiao onde o afixo sorteado aparece. E' varrida em busca de bandas de
    # texto em vez de ter uma ROI por linha: o resultado tem uma ou duas linhas
    # conforme o afixo, e uma ROI unica cobrindo as duas nao e' lida pelo
    # detector (medido - ver result.read_text_lines).
    result_text: Rect = Rect(20, 656, 660, 84)
    # Skip (durante a animacao) e Close (no resultado) sao o mesmo retangulo.
    skip_or_close: Rect = Rect(283, 796, 133, 46)

    # Onde largar o cursor depois de cada clique.
    #
    # NAO e' cosmetico. O Diablo IV desenha o proprio cursor DENTRO do quadro
    # renderizado, entao ele nao da' para excluir da captura. Parado sobre o
    # botao circular, o cursor acrescenta pixels acesos justamente na regiao que
    # decide "da' para recarregar" - o botao apagava ao encher o item e a
    # leitura seguinte continuava dizendo "aceso" por causa do cursor, entao o
    # ciclo clicava sem parar, gastando um Pergaminho por volta.
    #
    # Este ponto mede tinta 0.000 em sete das oito telas de referencia e nao
    # encosta em nenhuma ROI lida.
    cursor_park: Rect = Rect(40, 770, 70, 60)

    # -- sondagem de estado -----------------------------------------------
    # O painel escurece quando o modal de tempering abre por cima.
    panel_probe: Rect = Rect(40, 60, 640, 900)

    def scaled(self, client: Rect) -> ResolvedProfile:
        """Converte para a tela real, com a mesma regra do perfil do Occultist.

        O painel do Ferreiro fica colado na borda esquerda, igual ao do
        Occultist, entao a ancora padrao (esquerda) vale para todas as ROIs
        daqui - nenhuma e' centrada.
        """
        return ResolvedProfile(self, client)


DEFAULT_TEMPER_PROFILE = TemperProfile()
