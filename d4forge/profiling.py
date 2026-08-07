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

# Suba junto com CACHE_VERSION quando o pipeline mudar de custo. Comparar
# medicao de antes e depois de uma otimizacao na mesma janela so' confunde.
PIPELINE_VERSION = 4


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
        blob = {
            "pipeline": PIPELINE_VERSION,
            "timings": {name: t.samples for name, t in self.timings.items()},
        }
        path.write_text(json.dumps(blob, indent=0), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Profiler":
        """Carrega as medicoes, descartando as de um pipeline anterior.

        Medicao velha nao e' so' inutil: engana. Depois de corrigir o detector
        (1951 ms -> 70 ms por linha), a aba Desempenho continuava mostrando
        p50 de 1,4 s porque as amostras antigas dominavam a janela - dava a
        impressao de que a correcao nao tinha surtido efeito.
        """
        prof = cls()
        if not path.exists():
            return prof
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return prof
        if not isinstance(blob, dict) or blob.get("pipeline") != PIPELINE_VERSION:
            return prof
        for name, samples in blob.get("timings", {}).items():
            timing = Timing(name)
            timing.samples = [float(s) for s in samples][-MAX_SAMPLES:]
            prof.timings[name] = timing
        return prof

    # -- ajuste automatico ------------------------------------------------
    def _reaction_samples(self) -> list[float]:
        reactions = [t for name, t in self.timings.items() if name.startswith("reação")]
        return [s for t in reactions for s in t.samples]

    def suggested_retry_after(self, default: float = 1.2) -> float:
        """Quanto esperar pela tela antes de concluir que o clique se perdeu.

        Nao e' o mesmo que desistir da sessao. E' so' o ponto a partir do qual
        vale mais clicar de novo do que continuar esperando - e depois desse
        ponto, esperar nao resolve nada, porque o clique nao chegou.

        O numero sai da propria maquina do usuario: quatro vezes a reacao mais
        lenta ja' medida, com um piso de 0,8 s. Numa sessao real de 111 rodadas
        a reacao maxima foi 173 ms, entao a janela fica em 0,8 s - contra os 8 s
        de `state_timeout` que se gastavam parado antes de tentar de novo.
        """
        samples = self._reaction_samples()
        if len(samples) < 5:
            return default
        return max(0.8, min(default * 3, max(samples) / 1000 * 4))

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
