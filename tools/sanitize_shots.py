"""Gera as telas de referência dos testes sem nada pessoal.

As capturas originais mostram nome de conta, personagem, ouro, e o nome de
outros jogadores no mundo. Nada disso é lido pelo app — só o painel do
Occultist e o diálogo central importam. Este script preserva exatamente essas
regiões e apaga o resto, para que a suíte continue completa num repositório
público.

    .venv\\Scripts\\python.exe tools\\sanitize_shots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from d4forge.geometry import Rect  # noqa: E402
from d4forge.imageio import imread, imwrite  # noqa: E402

ORIGEM = ROOT / "PRINTS SEM CORTE (DIMENSAO)"
DESTINO = ROOT / "tests" / "fixtures" / "telas"

TELAS = {
    "enchant_select": "image 5.png",
    "confirm": "image 6.png",
    "replace": "image 7.png",
    "result": "image 8.png",
    "enchant_locked": "image 9.png",
}

# O Ferreiro usa o mesmo canto da tela que o Occultist, então a mesma máscara
# serve. Estes prints têm nome de conta, de personagem e o total de ouro — nada
# disso é lido pelo app, e o repositório é público.
ORIGEM_TEMPER = ROOT / "Funcionalidade Tempering" / "PRINTS INTEIROS"
TELAS_TEMPER = {
    "temper_idle": "image.png",            # receita escolhida, dá para temperar
    "temper_recipes": "image copy.png",    # lista TEMPERING RECIPES
    "temper_no_recipe": "image copy 2.png",  # sem receita: Temper Item cinza
    "temper_result": "image copy 3.png",   # TEMPER COMPLETE
    "temper_animation": "image copy 4.png",  # animação com Skip
    # Par casado do MESMO afixo, que é o que prova o sinal de Greater Affix:
    # o roll normal traz o intervalo na linha, o GA vem só com o valor.
    "temper_result_normal": "image copy 5.png",  # +4.6% Attack Speed [4.0 - 8.0]%
    "temper_result_ga": "image copy 6.png",      # +10.0% Attack Speed
    # Rerolls zerados: Temper Item cinza e o botão circular ACESO. É o par que
    # calibra a recarga — sem ele o limiar do circular seria chute, e é esse
    # botão que gasta Pergaminhos.
    "temper_no_rerolls": "image copy 7.png",
    # Afixo NOVO num slot livre: "Adds your selected affix", sem contador de
    # rerolls, e o botão diz só "Temper Item" — mas está ativo. Uma receita
    # está escolhida; o que não existe é reroll a contar.
    "temper_new_affix": "image copy 8.png",
}

# Preview do item durante a animação: o tooltip aparece à direita do painel, e
# aqui ele É a região lida — por isso estas telas usam um recorte próprio.
ORIGEM_PREVIEW = ROOT / "Funcionalidade Tempering" / "ESTRATEGIA"
TELAS_PREVIEW = {
    # Magnum Opus: o afixo temperado é o Lucky Hit, e ele quebra em três linhas.
    "preview_lucky_hit": "image.png",
    "preview_lucky_hit_2": "image copy 2.png",
    "preview_lucky_hit_daze": "image copy 3.png",
    # Wildbolt Greaves: o temperado virou GA (+31% Movement Speed, sem
    # intervalo) e o item JÁ TINHA um "+24% Movement Speed" normal — o mesmo
    # nome duas vezes, que é o caso que derruba casar por nome.
    "preview_movement_ga": "image copy 4.png",
}
TOOLTIP = Rect(676, 60, 400, 820)

# Regiões que o app realmente lê, em pixels de referência (1920x1080).
PAINEL = Rect(0, 0, 700, 968)          # Occultist; termina antes da linha de ouro
DIALOGO = Rect(676, 370, 580, 320)     # janela Accept / Cancel


def sanitizar(img: np.ndarray, regioes=(PAINEL, DIALOGO)) -> np.ndarray:
    limpo = np.zeros_like(img)
    for regiao in regioes:
        r = regiao.clip_to(Rect(0, 0, img.shape[1], img.shape[0]))
        limpo[r.top:r.bottom, r.left:r.right] = img[r.top:r.bottom, r.left:r.right]
    return limpo


def gerar(origem: Path, telas: dict[str, str], regioes=(PAINEL, DIALOGO)) -> None:
    if not origem.is_dir():
        print(f"origem não encontrada: {origem} — pulando")
        return
    for estado, arquivo in telas.items():
        img = imread(origem / arquivo)
        if img is None:
            print(f"!! não consegui ler {arquivo}")
            continue
        destino = DESTINO / f"{estado}.jpg"
        imwrite(destino, sanitizar(img, regioes))
        print(f"{destino.relative_to(ROOT)}  {destino.stat().st_size // 1024} KB")


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    gerar(ORIGEM, TELAS)
    # O Ferreiro não tem diálogo central: só o painel esquerdo é lido, e manter
    # o resto só exporia o personagem e o cenário à toa.
    gerar(ORIGEM_TEMPER, TELAS_TEMPER, regioes=(PAINEL,))
    gerar(ORIGEM_PREVIEW, TELAS_PREVIEW, regioes=(PAINEL, TOOLTIP))

    if not ORIGEM.is_dir():
        print("\norigem do Occultist ausente; pulando a conferência de estado")
        return 0

    print("\nConferindo se a detecção de estado continua correta:")
    from d4forge.profile import DEFAULT_PROFILE
    from d4forge.vision.states import ScreenState, detect_state

    erros = 0
    for estado in TELAS:
        img = imread(DESTINO / f"{estado}.jpg")
        prof = DEFAULT_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))
        lido = detect_state(img, prof).state
        ok = lido is ScreenState(estado)
        erros += not ok
        print(f"  {'ok  ' if ok else 'ERRO'} {estado:<16} -> {lido.value}")
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
