import hashlib
from pathlib import Path
from ..models import ExtractionResult, Violation
from .base import all_rules
from . import checks


def run_rules(extraction: ExtractionResult) -> list[Violation]:
    violations: list[Violation] = []
    for rule in all_rules():
        try:
            violations.extend(rule(extraction))
        except Exception as e:
            print(f"[motor de regras] regra '{rule.__name__}' falhou: {e}")
    return violations


def ruleset_version() -> str:
    codigo = Path(checks.__file__).read_text(encoding="utf-8").replace("\r\n", "\n")
    nomes = sorted(r.__name__ for r in all_rules())
    return hashlib.sha256((codigo + "\n" + "\n".join(nomes)).encode("utf-8")).hexdigest()
