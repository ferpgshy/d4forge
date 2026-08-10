"""Threads de trabalho da GUI.

O engine e o monitor de tela rodam fora da thread da interface: qualquer captura
ou OCR na thread do Qt congelaria a janela, e uma janela congelada e' exatamente
onde voce nao consegue apertar "parar".
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from ..engine import EnchantEngine, EngineEvent, Outcome
from ..profile import EnchantProfile
from ..vision.states import StateReading


class EngineWorker(QThread):
    """Roda o ciclo de encantamento e repassa eventos para a interface."""

    event = Signal(object)     # EngineEvent
    finished_run = Signal(object)  # Outcome

    def __init__(self, engine: EnchantEngine, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._engine._listener = self._on_event

    def _on_event(self, evt: EngineEvent) -> None:
        self.event.emit(evt)

    def run(self) -> None:
        outcome: Outcome = self._engine.run()
        self.finished_run.emit(outcome)

    def stop(self) -> None:
        self._engine.cancel()


class TemperWorker(QThread):
    """Roda o ciclo do Tempering fora da thread da interface."""

    event = Signal(object)         # EngineEvent
    finished_run = Signal(object)  # TemperOutcome

    def __init__(self, engine, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._engine._listener = self.event.emit

    def run(self) -> None:
        self.finished_run.emit(self._engine.run())

    def stop(self) -> None:
        self._engine.cancel()


class WarmupWorker(QThread):
    """Carrega o modelo de OCR em segundo plano assim que a janela abre.

    Medido: construir o RapidOCR custa ~330 ms e a primeira inferencia ~140 ms.
    Sem isto, essa meia dezena de decimos cai em cima da primeira leitura do
    ciclo - justo quando o usuario esta' olhando para ver se funcionou.
    """

    ready = Signal(float)

    def __init__(self, app_state, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app_state

    def run(self) -> None:
        import time

        import numpy as np

        start = time.perf_counter()
        try:
            # Uma linha sintetica basta para instanciar tudo e rodar um passe.
            branco = np.full((26, 300, 3), 255, dtype=np.uint8)
            branco[8:18, 20:120] = 0
            self._app.ocr.read(branco)
        except Exception:  # noqa: BLE001 - aquecimento nunca pode derrubar a GUI
            pass
        self.ready.emit((time.perf_counter() - start) * 1000)


class BenchWorker(QThread):
    """Roda o teste de tempo de resposta fora da thread da interface."""

    done = Signal(object, object)  # Profiler, list[str]

    def __init__(self, app_state, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app_state

    def run(self) -> None:
        from ..benchmark import measure_pipeline

        try:
            profiler, notes = measure_pipeline(self._app)
        except Exception as exc:  # noqa: BLE001
            from ..profiling import Profiler

            profiler, notes = Profiler(), [f"falha ao medir: {exc}"]
        self.done.emit(profiler, notes)


class MonitorWorker(QThread):
    """Le' a tela continuamente so' para mostrar diagnostico, sem clicar nada.

    E' o que permite conferir calibracao e OCR com o jogo aberto sem ligar a
    automacao.
    """

    reading = Signal(object, object, object)  # StateReading, list[str], dict

    def __init__(self, app_state, interval_ms: int = 400, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app_state
        self._interval = interval_ms
        self._running = False

    def run(self) -> None:
        from ..capture import ScreenCapture
        from ..vision.states import ScreenState, detect_state

        self._running = True
        capture = ScreenCapture(prefer=self._app.settings.capture_backend)
        try:
            while self._running:
                try:
                    payload = self._sample(capture, detect_state, ScreenState)
                except Exception as exc:  # noqa: BLE001
                    payload = (StateReading(ScreenState.UNKNOWN, {}), [f"erro: {exc}"], {})
                self.reading.emit(*payload)
                self.msleep(self._interval)
        finally:
            capture.close()

    def _sample(self, capture, detect_state, ScreenState):
        from ..affixes import parse_affix
        from ..window import find_game_window

        win = find_game_window()
        if win is None:
            return StateReading(ScreenState.UNKNOWN, {}), ["Diablo IV nao esta' aberto"], {}

        prof = self._app.profile.scaled(win.client)
        frame = capture.grab(win.client)
        if frame is None:
            return StateReading(ScreenState.UNKNOWN, {}), ["captura falhou"], {}

        reading = detect_state(frame, prof)
        lines: list[str] = []
        rois = []
        if reading.state is ScreenState.REPLACE:
            rois = [("atual", prof.replace_current)]
            rois += [(f"opcao {i}", r) for i, r in enumerate(prof.replace_options, 1)]
        elif reading.state is ScreenState.ENCHANT_SELECT:
            rois = [(f"afixo {i}", r) for i, r in enumerate(prof.affix_rows, 1)]
        elif reading.state is ScreenState.ENCHANT_LOCKED:
            rois = [("afixo", prof.locked_affix), ("custo", prof.enchant_cost)]

        for label, roi in rois:
            res = self._app.ocr.read(roi.crop(frame))
            parsed = parse_affix(res.text, self._app.catalog)
            mark = "" if parsed.confident else "  <duvidoso>"
            lines.append(f"{label:>9}: {parsed.describe()}{mark}   [{res.source} {res.elapsed_ms:.1f}ms]")

        return reading, lines, {"client": win.client.as_tuple()}

    def stop(self) -> None:
        self._running = False
