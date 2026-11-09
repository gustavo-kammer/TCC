from collections.abc import Callable
from ..models import ExtractionResult, Violation

Rule = Callable[[ExtractionResult], list[Violation]]

_REGISTRY: list[Rule] = []


def rule(func: Rule) -> Rule:
    _REGISTRY.append(func)
    return func


def all_rules() -> list[Rule]:
    return list(_REGISTRY)
