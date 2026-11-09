import csv
import json
from dataclasses import asdict
from pathlib import Path

from src.models import Heuristic
from .cells import HumanCell, load_cells_csv
from .gabarito import Gabarito
from .metrics import CellMetrics, CellPair, cell_metrics

CONFIGS = ("hibrido", "regras", "llm")
ORIGENS_POR_CONFIG = {
    "hibrido": ("todos", "llm", "motor_de_regras"),
    "regras": ("todos",),
    "llm": ("todos",),
}


def human_cells_from_calibration(gabaritos: list[Gabarito]) -> list[HumanCell]:
    celulas = []
    for g in gabaritos:
        plantadas = {v.heuristic: v.severity.value for v in g.violacoes_gabarito}
        for h in Heuristic:
            celulas.append(HumanCell(
                fluxo=g.interface_id, heuristic=h,
                consenso=plantadas.get(h, 0), apontada=h in plantadas))
    return celulas


def load_aggregates(config: str, flow_ids: list[str],
                    out_dir: str | Path = "output") -> dict[str, dict]:
    agregados = {}
    for fid in flow_ids:
        path = Path(out_dir) / "agregado" / config / f"{fid}.json"
        if path.exists():
            agregados[fid] = json.loads(path.read_text(encoding="utf-8"))
    return agregados


def _nota(celula: dict, origem: str) -> int:
    return celula["nota"] if origem == "todos" else celula["nota_por_origem"][origem]


def build_pairs(cells: list[HumanCell], agregados: dict[str, dict],
                origem: str = "todos") -> list[CellPair]:
    pares = []
    for c in cells:
        if not c.incluida or c.consenso is None or c.fluxo not in agregados:
            continue
        pares.append(CellPair(
            fluxo=c.fluxo, heuristic=c.heuristic,
            sistema=_nota(agregados[c.fluxo]["celulas"][c.heuristic.value], origem),
            humano=c.consenso, apontada=c.apontada))
    return pares


def _fmt(v: object) -> object:
    if isinstance(v, float):
        return f"{v:.4f}"
    return "" if v is None else v


def _write_csv(path: Path, linhas: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        if not linhas:
            f.write("")
            return
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        for l in linhas:
            w.writerow({k: _fmt(v) for k, v in l.items()})


def evaluate(cells: list[HumanCell], out_dir: str | Path = "output",
             results_dir: str | Path = "resultados",
             titulo: str = "Validação") -> dict[str, CellMetrics]:
    results_dir = Path(results_dir)
    flow_ids = sorted({c.fluxo for c in cells})
    agregados = {cfg: load_aggregates(cfg, flow_ids, out_dir) for cfg in CONFIGS}

    por_config: list[dict] = []
    por_fluxo: list[dict] = []
    resumo: dict[str, CellMetrics] = {}
    for cfg in CONFIGS:
        if not agregados[cfg]:
            continue
        for origem in ORIGENS_POR_CONFIG[cfg]:
            pares = build_pairs(cells, agregados[cfg], origem)
            m = cell_metrics(pares)
            resumo[f"{cfg}/{origem}"] = m
            por_config.append({"configuracao": cfg, "origem": origem,
                               "n_fluxos": len({p.fluxo for p in pares}), **asdict(m)})
            for fid in flow_ids:
                pf = [p for p in pares if p.fluxo == fid]
                if pf:
                    por_fluxo.append({"configuracao": cfg, "origem": origem,
                                      "fluxo": fid, **asdict(cell_metrics(pf))})

    _write_csv(results_dir / "metricas_por_configuracao.csv", por_config)
    _write_csv(results_dir / "metricas_por_fluxo.csv", por_fluxo)
    _write_csv(results_dir / "celulas_sistema_vs_humano.csv",
               _cells_table(cells, agregados))
    (results_dir / "resumo.md").write_text(
        _resumo_md(titulo, cells, agregados, por_config),
        encoding="utf-8")
    return resumo


def _cells_table(cells: list[HumanCell], agregados: dict[str, dict]) -> list[dict]:
    linhas = []
    for c in cells:
        linha: dict = {"fluxo": c.fluxo, "heuristica": c.heuristic.value}
        linha |= {"consenso": c.consenso, "apontada": int(c.apontada),
                  "status": "incluida" if c.incluida else "excluida",
                  "motivo": c.motivo}
        for cfg in CONFIGS:
            cel = agregados[cfg].get(c.fluxo, {}).get("celulas", {}).get(c.heuristic.value)
            linha[f"sistema_{cfg}"] = cel["nota"] if cel else None
            linha[f"origem_{cfg}"] = ";".join(cel["origens"]) if cel else None
            linha[f"execucoes_{cfg}"] = ";".join(map(str, cel["notas_execucoes"])) if cel else None
        cel = agregados["hibrido"].get(c.fluxo, {}).get("celulas", {}).get(c.heuristic.value)
        linha["hibrido_so_llm"] = cel["nota_por_origem"]["llm"] if cel else None
        linha["hibrido_so_regras"] = cel["nota_por_origem"]["motor_de_regras"] if cel else None
        linhas.append(linha)
    return linhas


def _f(v: float | None) -> str:
    return "—" if v is None else f"{v:.3f}"


def _resumo_md(titulo: str, cells: list[HumanCell], agregados: dict[str, dict],
               por_config: list[dict]) -> str:
    fluxos = sorted({c.fluxo for c in cells})
    incluidas = [c for c in cells if c.incluida]
    excluidas = [c for c in cells if not c.incluida]

    md = [f"# Resultados — {titulo}", ""]
    md.append(f"- Fluxos no gabarito: {len(fluxos)} ({', '.join(fluxos)})")
    md.append(f"- Células excluídas das métricas: {len(excluidas)}")
    md.append(f"- Células aplicáveis nas métricas: {len(incluidas)}")
    for cfg in CONFIGS:
        ags = agregados[cfg]
        if ags:
            meta = next(iter(ags.values()))["metadata"]
            md.append(f"- `{cfg}`: {len(ags)} fluxos, {meta['n_execucoes']} execuções, "
                      f"modelo {meta['modelo'] or '—'}, regras {(meta['regras_versao'] or '—')[:12]}")
        else:
            md.append(f"- `{cfg}`: sem saídas agregadas")

    md += ["", "## Métricas por configuração (nível da célula fluxo × heurística)", "",
           "Detectado = nota do sistema ≥ 1; positivo = célula apontada pela maioria. "
           "**Kappa (todas)** usa todas as células aplicáveis, zeros incluídos; "
           "**Kappa (só VP)** usa apenas as células detectadas e apontadas.", "",
           "| Configuração | Origem | Células | VP | FP | FN | VN | Precisão | Recall | F1 "
           "| Kappa (todas) | Kappa (só VP) | Spearman |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in por_config:
        md.append(f"| {r['configuracao']} | {r['origem']} | {r['n_celulas']} | {r['vp']} | "
                  f"{r['fp']} | {r['fn']} | {r['vn']} | {_f(r['precision'])} | "
                  f"{_f(r['recall'])} | {_f(r['f1'])} | {_f(r['kappa_todas_celulas'])} | "
                  f"{_f(r['kappa_somente_vp'])} | {_f(r['spearman'])} |")
    md += ["", "Origem `llm` = só achados visíveis na imagem (camada LLM); "
           "`motor_de_regras` = só achados das regras (com a severidade revisada, "
           "no híbrido). Na configuração `regras`, `todos` equivale a só regras; "
           "em `llm`, a só LLM.", ""]
    return "\n".join(md)


def validation_cells(path: str | Path) -> list[HumanCell]:
    return load_cells_csv(path)
