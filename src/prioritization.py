from .models import Violation, Severity


def _final_severity(v: Violation) -> int:

    if v.severity_revised is not None:
        return v.severity_revised.value
    return v.severity.value


def _dedup_key(v: Violation) -> tuple:

    return (v.heuristic.value, v.location.strip().lower())


def _merge_duplicates(violations: list[Violation]) -> list[Violation]:

    grupos: dict[tuple, Violation] = {}
    for v in violations:
        k = _dedup_key(v)
        atual = grupos.get(k)
        if atual is None:
            grupos[k] = v
            continue
        if (_final_severity(v), v.confidence or 0) > (_final_severity(atual), atual.confidence or 0):
            grupos[k] = v
    return list(grupos.values())


def criticality_index(v: Violation) -> float:
    confianca = v.confidence if v.confidence is not None else 1.0
    return _final_severity(v) * confianca


def _sort_key(v: Violation) -> tuple[float, int, float]:

    return (criticality_index(v), _final_severity(v), v.confidence or 0.0)


def prioritize(
    rule_violations: list[Violation],
    llm_new: list[Violation],
    llm_revised: list[Violation],
) -> list[Violation]:
    revised_keys = {_dedup_key(v) for v in llm_revised}
    regras_finais = [
        v for v in rule_violations if _dedup_key(v) not in revised_keys]

    combinadas = regras_finais + llm_revised + llm_new
    unicas = _merge_duplicates(combinadas)
    problemas = [v for v in unicas
                 if _final_severity(v) > Severity.NAO_E_PROBLEMA.value]

    return sorted(problemas, key=_sort_key, reverse=True)
