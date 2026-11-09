import json
from pathlib import Path
from pydantic import BaseModel
from src.models import Heuristic, Severity


class GabaritoViolation(BaseModel):
    id: str
    heuristic: Heuristic
    severity: Severity
    location: str
    description: str
    n_apontaram: int | None = None
    severidades_individuais: list[int] | None = None
    papel: str | None = None
    racional_coocorrencia: str | None = None


class Gabarito(BaseModel):
    interface_id: str
    fase: str
    fonte: str
    descricao: str
    arquivo_ou_url: str
    violacoes_gabarito: list[GabaritoViolation]
    n_avaliadores: int | None = None
    concordancia_kappa: float | None = None


def load_gabarito(path: str | Path) -> Gabarito:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Gabarito.model_validate(raw)


def load_all(pasta: str | Path) -> list[Gabarito]:
    pasta = Path(pasta)
    return [load_gabarito(p) for p in sorted(pasta.glob("*.json"))]
