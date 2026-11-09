import json
from pathlib import Path
from .models import Violation
from .prioritization import criticality_index


SEVERITY_LABEL = {
    0: "não é problema",
    1: "cosmético",
    2: "menor",
    3: "maior",
    4: "catástrofe",
}


def _effective_severity(v: Violation) -> int:
    return v.severity_revised.value if v.severity_revised is not None else v.severity.value


def _violation_to_dict(v: Violation, rank: int) -> dict:
    return {
        "rank": rank,
        "heuristic": v.heuristic.value,
        "severity_effective": _effective_severity(v),
        "criticality_index": round(criticality_index(v), 4),
        "severity_original": v.severity.value,
        "severity_revised": v.severity_revised.value if v.severity_revised is not None else None,
        "source": v.source.value,
        "confidence": v.confidence,
        "location": v.location,
        "description": v.description,
        "justification": v.justification,
        "recommendation": v.recommendation,
        "revision_rationale": v.revision_rationale,
        "evidence": v.evidence.model_dump() if v.evidence is not None else None,
    }


def build_report(url: str, prioritized: list[Violation]) -> dict:
    violations = [_violation_to_dict(v, i)
                  for i, v in enumerate(prioritized, 1)]

    by_severity: dict[int, int] = {}
    for v in prioritized:
        s = _effective_severity(v)
        by_severity[s] = by_severity.get(s, 0) + 1

    return {
        "url": url,
        "total_violations": len(prioritized),
        "count_by_severity": {str(k): by_severity[k] for k in sorted(by_severity, reverse=True)},
        "violations": violations,
    }


def save_json(report: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False,
                    indent=2), encoding="utf-8")
    return path
