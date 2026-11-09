import csv
from dataclasses import dataclass
from pathlib import Path

from src.models import Heuristic


@dataclass
class HumanCell:
    fluxo: str
    heuristic: Heuristic
    consenso: int | None = None
    apontada: bool = False
    incluida: bool = True
    motivo: str = ""


def load_cells_csv(path: str | Path) -> list[HumanCell]:
    with Path(path).open(encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    return [HumanCell(
        fluxo=l["fluxo"],
        heuristic=Heuristic(l["heuristica"]),
        consenso=int(l["consenso"]) if l["consenso"] != "" else None,
        apontada=l["apontada"] == "1",
        incluida=l["status"] == "incluida",
        motivo=l["motivo"],
    ) for l in linhas]
