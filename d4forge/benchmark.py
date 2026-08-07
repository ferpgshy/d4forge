"""Teste de tempo de resposta.

Mede cada etapa do ciclo na maquina e na tela do usuario, para que a decisao de
onde otimizar venha de numero e nao de intuicao. Nao clica em nada.

O que ja' saiu daqui: varrer o painel inteiro para detectar o estado custava
15,8 ms dos 16,2 ms totais, e a subamostragem derrubou isso para ~1,1 ms sem
mudar o resultado.
"""

from __future__ import annotations

import time

from .automation.sendinput import PROFILES
from .capture import ScreenCapture
from .geometry import Rect
from .profiling import Profiler
from .vision.states import detect_state
from .window import find_game_window

REPEATS = 30


def _bench(profiler: Profiler, name: str, fn, repeats: int = REPEATS) -> None:
    try:
        fn()  # aquece: a primeira chamada carrega modelo/buffer
    except Exception:  # noqa: BLE001
        return
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        profiler.record(name, (time.perf_counter() - start) * 1000)


def measure_pipeline(app_state) -> tuple[Profiler, list[str]]:
    """Cronometra captura, deteccao de estado e OCR na tela atual.

    Devolve (medicoes, avisos). Funciona com o jogo aberto em qualquer tela do
    Occultist; sem o jogo, mede so' o que nao depende dele.
    """
    profiler = Profiler()
    notes: list[str] = []

    win = find_game_window()
    if win is None:
        notes.append("Diablo IV não está aberto — medi apenas o que não depende dele.")
        client = Rect(0, 0, 1920, 1080)
    else:
        client = win.client

    capture = ScreenCapture(prefer=app_state.settings.capture_backend)
    notes.append(f"captura via {capture.backend_name}")
    try:
        prof = app_state.profile.scaled(client)

        _bench(profiler, "captura de tela", lambda: capture.grab(client))

        frame = capture.grab(client)
        if frame is None:
            notes.append("a captura não retornou imagem; o resto foi pulado.")
            return profiler, notes

        _bench(profiler, "detectar estado", lambda: detect_state(frame, prof))
        state = detect_state(frame, prof).state
        notes.append(f"tela reconhecida agora: {state.value}")

        # OCR: só faz sentido onde há texto de afixo na tela.
        rois = []
        if state.value == "replace":
            rois = list(prof.replace_options)
        elif state.value == "enchant_select":
            rois = list(prof.affix_rows)
        elif state.value == "enchant_locked":
            rois = [prof.locked_affix]

        if rois:
            crop = rois[0].crop(frame)
            # Primeira leitura pode cair no modelo; as seguintes vêm do cache.
            start = time.perf_counter()
            app_state.ocr.read(crop)
            profiler.record("ler afixo (1ª vez)", (time.perf_counter() - start) * 1000)
            _bench(profiler, "ler afixo (em cache)", lambda: app_state.ocr.read(crop))
        else:
            notes.append("nenhum afixo visível: abra a tela Replace Affix para medir o OCR.")
    finally:
        capture.close()

    # Custo do mouse por perfil - é a maior fatia controlável do ciclo.
    for label, ip in PROFILES.items():
        profiler.record(f"clique estimado: {label}", ip.estimate_ms())

    return profiler, notes


def cycle_estimate(profiler: Profiler, clicks_per_cycle: int = 4) -> float:
    """Estimativa de quanto uma volta custa, em milissegundos.

    Soma o que o app controla (cliques, leitura, deteccao) com o que o jogo
    impoe (tempo de reacao medido).
    """
    def mean_of(prefix: str) -> float:
        rows = [t for name, t in profiler.timings.items() if name.startswith(prefix)]
        return sum(t.mean for t in rows) / len(rows) if rows else 0.0

    click = mean_of("clique:") or mean_of("clique estimado: rápido")
    reaction = mean_of("reação")
    ocr = mean_of("ler afixo (em cache)")
    stable = mean_of("esperar tela estabilizar")
    return clicks_per_cycle * (click + reaction) + 2 * ocr + 3 * stable
