"""Ajuste do detector do RapidOCR.

Regressão de desempenho, achada medindo uma sessão real: o `! repescagem de
OCR` aparecia em 199 de 200 leituras, com p50 de 1,4 s e picos de 5,5 s,
enquanto o cache respondia em 1 ms — era essa alternância que fazia o bot
parecer que travava e voltava.

Causa: o RapidOCR vem com `limit_type: min`, que redimensiona até o MENOR lado
alcançar 736. Nossas linhas são largas e baixas (660x104), então a imagem era
multiplicada por 7 e o detector processava 4670x736 para ler uma linha.
"""

import pytest

from d4forge.vision.ocr import DET_LIMIT_SIDE, RapidOcrBackend, _tune_detector


@pytest.fixture(scope="module")
def engine():
    backend = RapidOcrBackend()
    return backend._ensure()


def test_detector_nao_infla_a_imagem(engine):
    ops = [op for op in engine.text_detector.preprocess_op if hasattr(op, "limit_type")]
    assert ops, "detector sem operação de resize reconhecível"
    for op in ops:
        assert op.limit_type == "max"
        assert op.limit_side_len == DET_LIMIT_SIDE


def test_ajuste_e_idempotente(engine):
    assert _tune_detector(engine)
    assert _tune_detector(engine)


def test_nossa_linha_passa_sem_redimensionar():
    """Com 'max' e 1280, uma linha típica (660x104) não é tocada; com o padrão
    'min' 736 ela viraria 4670x736 — 3,4 megapixels."""
    w, h = 660, 104
    escala_max = min(1.0, DET_LIMIT_SIDE / max(w, h))
    escala_min = 736 / min(w, h)
    assert escala_max == 1.0
    assert escala_min > 7


def test_ajuste_nao_quebra_com_estrutura_desconhecida():
    """Versão nova do RapidOCR pode mudar tudo de lugar: falhar é aceitável,
    derrubar o app não."""

    class Fake:
        text_detector = object()

    assert _tune_detector(Fake()) is False
