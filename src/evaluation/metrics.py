from dataclasses import dataclass, field
from ..models import Heuristic, Violation
from .gabarito import GabaritoViolation
from .stats import quadratic_weighted_kappa, spearman


@dataclass
class MatchResult:
    true_positives: list[tuple[Violation, GabaritoViolation]] = field(
        default_factory=list)
    false_positives: list[Violation] = field(default_factory=list)
    false_negatives: list[GabaritoViolation] = field(default_factory=list)

    @property
    def vp(self) -> int: return len(self.true_positives)
    @property
    def fp(self) -> int: return len(self.false_positives)
    @property
    def fn(self) -> int: return len(self.false_negatives)


def match_by_heuristic(
    detected: list[Violation],
    gabarito: list[GabaritoViolation],
) -> MatchResult:

    result = MatchResult()
    gab_restante = list(gabarito)
    det_restante = list(detected)

    for det in list(det_restante):
        alvo = next(
            (g for g in gab_restante if g.heuristic == det.heuristic), None)
        if alvo is not None:
            result.true_positives.append((det, alvo))
            gab_restante.remove(alvo)
            det_restante.remove(det)

    result.false_positives = det_restante
    result.false_negatives = gab_restante
    return result


def build_match_from_manual(
    detected: list[Violation],
    gabarito: list[GabaritoViolation],
    confirmed_pairs: list[tuple[int, str]],
) -> MatchResult:

    result = MatchResult()
    det_casadas, gab_casados = set(), set()

    gab_por_id = {g.id: g for g in gabarito}
    for det_idx, gab_id in confirmed_pairs:
        det = detected[det_idx]
        gab = gab_por_id[gab_id]
        result.true_positives.append((det, gab))
        det_casadas.add(det_idx)
        gab_casados.add(gab_id)

    result.false_positives = [d for i, d in enumerate(
        detected) if i not in det_casadas]
    result.false_negatives = [g for g in gabarito if g.id not in gab_casados]
    return result


@dataclass
class DetectionMetrics:
    precision: float
    recall: float
    f1: float
    vp: int
    fp: int
    fn: int


def detection_metrics(match: MatchResult) -> DetectionMetrics:
    vp, fp, fn = match.vp, match.fp, match.fn
    precision = vp / (vp + fp) if (vp + fp) else 0.0
    recall = vp / (vp + fn) if (vp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          ) if (precision + recall) else 0.0
    return DetectionMetrics(precision, recall, f1, vp, fp, fn)


def _effective_severity(v: Violation) -> int:
    return v.severity_revised.value if v.severity_revised is not None else v.severity.value


def weighted_cohen_kappa(match: MatchResult, max_severity: int = 4) -> float | None:

    pares = [
        (_effective_severity(det), gab.severity.value)
        for det, gab in match.true_positives
    ]
    return quadratic_weighted_kappa(pares, max_severity)


@dataclass
class CellPair:
    fluxo: str
    heuristic: Heuristic
    sistema: int
    humano: int
    apontada: bool


@dataclass
class CellMetrics:
    n_celulas: int
    precision: float
    recall: float
    f1: float
    vp: int
    fp: int
    fn: int
    vn: int
    kappa_todas_celulas: float | None
    kappa_somente_vp: float | None
    spearman: float | None


def cell_metrics(pairs: list[CellPair]) -> CellMetrics:
    vp = sum(1 for p in pairs if p.sistema >= 1 and p.apontada)
    fp = sum(1 for p in pairs if p.sistema >= 1 and not p.apontada)
    fn = sum(1 for p in pairs if p.sistema == 0 and p.apontada)
    vn = len(pairs) - vp - fp - fn
    precision = vp / (vp + fp) if (vp + fp) else 0.0
    recall = vp / (vp + fn) if (vp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          ) if (precision + recall) else 0.0
    return CellMetrics(
        n_celulas=len(pairs),
        precision=precision, recall=recall, f1=f1,
        vp=vp, fp=fp, fn=fn, vn=vn,
        kappa_todas_celulas=quadratic_weighted_kappa(
            [(p.sistema, p.humano) for p in pairs]),
        kappa_somente_vp=quadratic_weighted_kappa(
            [(p.sistema, p.humano) for p in pairs if p.sistema >= 1 and p.apontada]),
        spearman=spearman([p.sistema for p in pairs], [p.humano for p in pairs]),
    )
