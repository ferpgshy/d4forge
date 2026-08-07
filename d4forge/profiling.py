"""Medicao de tempo das interacoes.

Existe para trocar chute por numero. Os atrasos do ciclo eram constantes que eu
escrevi no codigo; com isto d'a para ver quanto o jogo realmente leva em cada
transicao e ajustar as esperas ao que a maquina do usuario faz.

Guarda tudo em data/timings.json, entao as medicoes se acumulam entre sessoes.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

# Amostras por metrica. Segurar as ultimas N mantem o relatorio representativo
# do estado atual da maquina em vez da media de todos os tempos ja' vistos.
MAX_SAMPLES = 200


@dataclass
class Timing:
    name: str
    samples: list[float] = field(default_factory=list)

    def add(self, ms: float) -> None:
        self.samples.append(ms)
        if len(self.samples) > MAX_SAMPLES:
            del self.samples[: len(self.samples) - MAX_SAMPLES]

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def mean(self) -> float:
        return sum(self.samples) / len(self.samples) if self.samples else 0.0

    def percentile(self, pct: float) -> float:
        if not self.samples:
            return 0.0
        ordered = sorted(self.samples)
        idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
        return ordered[idx]

    @property
    def minimum(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def maximum(self) -> float:
        return max(self.samples) if self.samples else 0.0

    @property
    def total(self) -> float:
        return sum(self.samples)


@dataclass
class Profiler:
    """Coletor de tempos, indexado por nome de etapa."""

    timings: dict[str, Timing] = field(default_factory=dict)
    enabled: bool = True

    def record(self, name: str, ms: float) -> None:
        if not self.enabled:
            return
        self.timings.setdefault(name, Timing(name)).add(ms)

    @contextmanager
    def measure(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.record(name, (time.perf_counter() - start) * 1000)

    def clear(self) -> None:
        self.timings.clear()

    def rows(self) -> list[Timing]:
        """Etapas ordenadas pelo tempo total gasto - o topo e' onde otimizar."""
        return sorted(self.timings.values(), key=lambda t: t.total, reverse=True)

    def report(self) -> str:
        lines = [f"{'etapa':<32}{'n':>5}{'média':>9}{'p50':>9}{'p95':>9}{'máx':>9}"]
        lines.append("-" * 73)
        for t in self.rows():
            lines.append(
                f"{t.name:<32}{t.count:>5}{t.mean:>8.1f}m{t.percentile(50):>8.1f}m"
                f"{t.percentile(95):>8.1f}m{t.maximum:>8.1f}m"
            )
        return "\n".join(lines)

    # -- persistencia -----------------------------------------------------
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = {name: t.samples for name, t in self.timings.items()}
        path.write_text(json.dumps(blob, indent=0), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Profiler":
        prof = cls()
        if not path.exists():
            return prof
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return prof
        for name, samples in blob.items():
            timing = Timing(name)
            timing.samples = [float(s) for s in samples][-MAX_SAMPLES:]
            prof.timings[name] = timing
        return prof

    # -- ajuste automatico ------------------------------------------------
    def suggested_settle(self, default: float = 0.25) -> float:
        """Espera segura depois de um clique, em segundos.

        Usa o p95 do tempo de reacao medido do jogo, com uma folga de 30%. Se
        ainda nao ha' medicao suficiente, mantem o padrao conservador.
        """
        reactions = [t for name, t in self.timings.items() if name.startswith("reação")]
        samples = [s for t in reactions for s in t.samples]
        if len(samples) < 5:
            return default
        ordered = sorted(samples)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))]
        return max(0.05, min(default, p95 / 1000 * 1.3))
