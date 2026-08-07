"""Coletor de tempos e o efeito da subamostragem na detecção de estado."""

import time

from d4forge.geometry import Rect
from d4forge.profiling import MAX_SAMPLES, Profiler
from d4forge.vision.states import ScreenState, detect_state, ink


def test_estatisticas():
    p = Profiler()
    for ms in (10, 20, 30, 40, 100):
        p.record("etapa", ms)
    t = p.timings["etapa"]
    assert t.count == 5
    assert t.mean == 40
    assert t.percentile(50) == 30
    assert t.maximum == 100
    assert t.total == 200


def test_measure_cronometra():
    p = Profiler()
    with p.measure("dormida"):
        time.sleep(0.02)
    assert p.timings["dormida"].mean >= 18


def test_mede_mesmo_com_excecao():
    """Falha no meio não pode perder a medição nem engolir o erro."""
    p = Profiler()
    try:
        with p.measure("quebra"):
            raise ValueError("x")
    except ValueError:
        pass
    assert p.timings["quebra"].count == 1


def test_limita_amostras():
    p = Profiler()
    for i in range(MAX_SAMPLES + 50):
        p.record("etapa", i)
    assert p.timings["etapa"].count == MAX_SAMPLES


def test_rows_ordena_por_tempo_total():
    p = Profiler()
    p.record("barato", 1)
    p.record("barato", 1)
    p.record("caro", 500)
    assert [t.name for t in p.rows()] == ["caro", "barato"]


def test_persiste(tmp_path):
    p = Profiler()
    p.record("captura de tela", 1.5)
    path = tmp_path / "timings.json"
    p.save(path)
    again = Profiler.load(path)
    assert again.timings["captura de tela"].samples == [1.5]


def test_medicao_de_pipeline_antigo_e_descartada(tmp_path):
    """Depois de corrigir o detector (1951 ms -> 70 ms por linha), a aba
    Desempenho continuava mostrando p50 de 1,4 s: as amostras antigas dominavam
    a janela e davam a impressão de que nada tinha melhorado."""
    import json

    from d4forge.profiling import PIPELINE_VERSION

    path = tmp_path / "timings.json"
    path.write_text(
        json.dumps({
            "pipeline": PIPELINE_VERSION - 1,
            "timings": {"ler afixo (OCR)": [1951.0, 1800.0]},
        }),
        encoding="utf-8",
    )
    assert Profiler.load(path).timings == {}


def test_formato_antigo_sem_versao_e_descartado(tmp_path):
    import json

    path = tmp_path / "timings.json"
    path.write_text(json.dumps({"ler afixo (OCR)": [1951.0]}), encoding="utf-8")
    assert Profiler.load(path).timings == {}


def test_espera_sugerida_ignora_amostra_insuficiente():
    p = Profiler()
    p.record("reação: a → b", 50)
    assert p.suggested_settle(default=0.25) == 0.25


def test_espera_sugerida_usa_reacao_medida():
    p = Profiler()
    for _ in range(20):
        p.record("reação: a → b", 100)  # jogo responde em 100 ms
    assert p.suggested_settle(default=0.25) < 0.25


# ---------------------------------------------------------------- vision

def test_subamostragem_nao_muda_o_estado(shots, profiles):
    """A subamostragem de `ink` corta 15 ms por leitura; não pode custar acerto."""
    for name, img in shots.items():
        assert detect_state(img, profiles[name]).state is ScreenState(name)


def test_subamostragem_aproxima_o_valor_cheio(shots):
    img = shots["replace"]
    roi = Rect(40, 60, 640, 960)
    aproximado = ink(img, roi)
    exato = ink(img, roi, max_samples=0)
    assert abs(aproximado - exato) < 0.005


def test_deteccao_e_rapida(shots, profiles):
    """Regressão de desempenho: varrer o painel inteiro custava 16 ms."""
    img, prof = shots["replace"], profiles["replace"]
    for _ in range(3):
        detect_state(img, prof)
    start = time.perf_counter()
    for _ in range(20):
        detect_state(img, prof)
    media_ms = (time.perf_counter() - start) / 20 * 1000
    assert media_ms < 6.0, f"detectar estado levou {media_ms:.1f} ms"
