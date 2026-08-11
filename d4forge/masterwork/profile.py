"""ROIs do painel de Masterworking do Ferreiro.

Coordenadas em pixels de uma tela de referencia 1920x1080, medidas nos prints
de `Masterworking/PRINTS INTEIROS/` - nao estimadas. Mesmo metodo do Tempering:
binarizar o painel, deixar as bandas de tinta apontarem onde o texto esta', e
conferir cada banda passando OCR nela.

E' a MESMA janela do Ferreiro que o Tempering usa, no mesmo canto da tela, so'
com outra aba aberta. O cabecalho BLACKSMITH e o retangulo do Skip sao os
mesmos - foram medidos de novo aqui mesmo assim, e batem.

Layout medido:

  PASSO       BLACKSMITH y 77..126 | aba MASTERWORKING y 139..179
              "ITEM / To upgrade" y 254..299 | item y 316..407
              "NEXT RANK" y 539..553 | "QUALITY 0/25" y 584..598
              "173 All Resist" + explicacao y 636..725
              REQUIRED MATERIALS y 832..847 | Upgrade y 872..947
  MASTERWORK  igual, MENOS o "NEXT RANK": no lugar dele vem
              "Current Masterwork Affix" y 585..599
              o afixo sorteado y 634..722 (uma ou duas linhas)
              "Reroll for a different Masterwork Affix" y 723..739
  ANIMACAO    titulo MASTERWORKING y 226..274 | Skip y 815..830

O que separa "passou um Masterwork" de "foi so' mais um rank" e' a PRESENCA da
linha "NEXT RANK" (medido: 0.0808 contra 0.0000). Presenca, e nao ausencia -
foi a licao cara do Tempering, onde o sinal de Greater Affix era o jogo NAO
mostrar o intervalo e qualquer digito comido pelo OCR virava um falso positivo.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Rect
from ..profile import ResolvedProfile


@dataclass(frozen=True)
class MasterworkProfile:
    """ROIs em pixels de referencia (1920x1080)."""

    # -- painel (aba Masterworking aberta, sem modal) ----------------------
    # Aceso so' quando nenhum modal esta' por cima: 0.3598 no painel contra
    # 0.0000 durante a animacao. E' o mesmo teste do Tempering.
    blacksmith_header: Rect = Rect(44, 56, 640, 45)
    masterworking_tab: Rect = Rect(39, 135, 640, 47)

    # "NEXT RANK". Existe no passo comum e SOME quando o Masterwork Affix
    # aparece - medido: 0.0808 contra 0.0000, sem meio-termo.
    next_rank: Rect = Rect(180, 533, 340, 26)

    # A linha logo abaixo do NEXT RANK. Ela troca de conteudo conforme o estado,
    # e serve de segunda testemunha para o `next_rank`:
    #     passo comum -> "QUALITY 0/25"
    #     masterwork  -> "Current Masterwork Affix"
    state_line: Rect = Rect(180, 578, 340, 26)

    # Onde o afixo do Masterwork aparece. Varrida em busca de bandas de texto,
    # e nao lida de uma vez: "+80.0% Damage with Two-Handed Slashing Weapons"
    # quebra em duas linhas, e uma ROI unica cobrindo as duas nao e' lida pelo
    # detector - o mesmo comportamento medido no Tempering.
    #
    # Medido linha a linha: y 633..649 e y 656..672. A ROI vai ate' 680 e para
    # ali de proposito - ver `reroll_hint`.
    affix_text: Rect = Rect(20, 628, 660, 52)

    # "Reroll for a different Masterwork Affix", medido em y 698..734 (tambem
    # em duas linhas). E' texto FIXO: se entrar na ROI do afixo, entra em toda
    # leitura e estraga o nome que decide a sessao. Por isso as duas ROIs nao
    # se encostam, e ha' teste garantindo isso.
    reroll_hint: Rect = Rect(180, 694, 340, 46)

    # Botao "Upgrade: N". Cinza quando nao da' para subir - sem ouro, sem
    # material, ou o item ja' no rank maximo.
    upgrade_button: Rect = Rect(340, 866, 320, 84)

    # -- animacao ---------------------------------------------------------
    modal_header: Rect = Rect(23, 217, 660, 63)
    skip_button: Rect = Rect(283, 805, 133, 40)

    # Onde largar o cursor depois de cada clique.
    #
    # O Diablo IV desenha o proprio cursor DENTRO do quadro renderizado, entao
    # ele nao da' para excluir da captura: parado sobre uma ROI lida, ele soma
    # pixels acesos e falseia a medida. No Tempering isso fez o ciclo clicar sem
    # parar sobre o botao de recarga.
    #
    # Este ponto mede tinta zero nas tres telas de referencia e nao encosta em
    # nenhuma ROI lida.
    cursor_park: Rect = Rect(40, 770, 70, 60)

    def scaled(self, client: Rect) -> ResolvedProfile:
        """Converte para a tela real, com a mesma regra dos outros dois perfis.

        O painel do Ferreiro fica colado na borda esquerda, entao a ancora
        padrao (esquerda) vale para todas as ROIs daqui - nenhuma e' centrada.
        """
        return ResolvedProfile(self, client)


DEFAULT_MW_PROFILE = MasterworkProfile()
