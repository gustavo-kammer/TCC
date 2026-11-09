import math

import pytest

from src.evaluation.gabarito import GabaritoViolation
from src.evaluation.metrics import (
    CellPair, cell_metrics, detection_metrics, match_by_heuristic, weighted_cohen_kappa)
from src.evaluation.stats import median_severe, quadratic_weighted_kappa, spearman
from src.models import Heuristic, Severity, Source, Violation

H = Heuristic


def _v(h: Heuristic, s: Severity) -> Violation:
    return Violation(heuristic=h, severity=s, location="x", description="d",
                     justification="j", recommendation="r", source=Source.LLM)


def _g(gid: str, h: Heuristic, s: Severity) -> GabaritoViolation:
    return GabaritoViolation(id=gid, heuristic=h, severity=s, location="x", description="d")


def test_match_por_heuristica_e_metricas_de_deteccao():
    gabarito = [_g("g1", H.H07_ESTETICA, Severity.MAIOR),
                _g("g2", H.H05_RECONHECIMENTO, Severity.MENOR),
                _g("g3", H.H08_PREVENCAO_ERROS, Severity.MAIOR)]
    detectado = [_v(H.H07_ESTETICA, Severity.MAIOR),
                 _v(H.H05_RECONHECIMENTO, Severity.COSMETICO),
                 _v(H.H01_VISIBILIDADE, Severity.MENOR)]
    match = match_by_heuristic(detectado, gabarito)
    m = detection_metrics(match)
    assert (m.vp, m.fp, m.fn) == (2, 1, 1)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.f1 == pytest.approx(2 / 3)
    assert weighted_cohen_kappa(match) == pytest.approx(2 / 3)


@pytest.mark.parametrize("valores, esperado", [
    ([2], 2), ([0, 1, 4], 1), ([1, 2], 2), ([1, 3], 2), ([0, 0, 1, 3], 1),
    ([1, 2, 3, 4], 3), ([3, 1, 2], 2),
])
def test_mediana_empate_para_o_mais_severo(valores, esperado):
    assert median_severe(valores) == esperado


def test_kappa_concordancia_perfeita_e_poucos_pares():
    assert quadratic_weighted_kappa([(0, 0), (2, 2), (4, 4)]) == pytest.approx(1.0)
    assert quadratic_weighted_kappa([(1, 1)]) is None
    assert quadratic_weighted_kappa([(0, 0), (0, 0)]) == 1.0


def test_kappa_discordancia_maxima_simetrica():
    assert quadratic_weighted_kappa([(0, 4), (4, 0)]) == pytest.approx(-1.0)


def test_spearman():
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert spearman([1], [1]) is None


def _pares() -> list[CellPair]:
    dados = [(2, 3, True),
             (0, 2, True),
             (1, 0, False),
             (0, 0, False),
             (3, 3, True)]
    return [CellPair("p01", list(H)[i], s, h, a) for i, (s, h, a) in enumerate(dados)]


def test_cell_metrics_valores_a_mao():
    m = cell_metrics(_pares())
    assert (m.vp, m.fp, m.fn, m.vn, m.n_celulas) == (2, 1, 1, 1, 5)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.f1 == pytest.approx(2 / 3)
    assert m.kappa_todas_celulas == pytest.approx(9 / 14)
    assert m.kappa_somente_vp == pytest.approx(0.0)
    assert m.spearman == pytest.approx(6.75 / math.sqrt(85.5))


def test_cell_metrics_sem_deteccao():
    m = cell_metrics([CellPair("p01", H.H01_VISIBILIDADE, 0, 2, True),
                      CellPair("p01", H.H02_CORRESPONDENCIA, 0, 0, False)])
    assert (m.vp, m.fp, m.fn, m.vn) == (0, 0, 1, 1)
    assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0
    assert m.kappa_somente_vp is None
