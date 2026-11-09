from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", t).casefold()).strip()


def achados_do_run(run: dict) -> list[dict]:
    return [{"estado": e["nome"], "heuristica": v["heuristic"], "descricao": _norm(v["description"]), "run": None}
            for e in run["estados"] for v in e["relatorio"]["violations"]]


def agrupar(runs: list[list[dict]], limiar: float = 0.5, mesma_heuristica: bool = True) -> list[list[dict]]:
    grupos: list[list[dict]] = []
    for k, achados in enumerate(runs):
        for a in achados:
            melhor, melhor_s = None, limiar
            for gi, g in enumerate(grupos):
                if any(m["run"] == k for m in g):
                    continue
                rep = g[0]
                if rep["estado"] != a["estado"] or (mesma_heuristica and rep["heuristica"] != a["heuristica"]):
                    continue
                s = SequenceMatcher(None, rep["descricao"], a["descricao"]).ratio()
                if s >= melhor_s:
                    melhor, melhor_s = gi, s
            a = {**a, "run": k}
            if melhor is None:
                grupos.append([a])
            else:
                grupos[melhor].append(a)
    return grupos


def resumo_grupos(grupos: list[list[dict]], n_runs: int) -> dict:
    tamanhos = Counter(len(g) for g in grupos)
    achados = sum(len(g) for g in grupos)
    reproduzidos = sum(len(g) for g in grupos if len(g) >= 2)
    return {"execucoes": n_runs, "achados": achados, "grupos": len(grupos),
            "distribuicao_tamanho": {str(k): tamanhos.get(k, 0) for k in range(1, n_runs + 1)},
            "achados_reproduzidos": reproduzidos / achados if achados else None,
            "grupos_em_todas_execucoes": tamanhos.get(n_runs, 0) / len(grupos) if grupos else None}


def estabilidade_tudo(output: Path, fluxos: list[str], configs=("hibrido", "regras", "llm"),
                      limiares=(0.4, 0.5, 0.6), destino: Path | None = None) -> dict:
    saida: dict = {"limiar_principal": 0.5, "por_config": {}}
    for cfg in configs:
        saida["por_config"][cfg] = {}
        for lim in limiares:
            grupos_total, n_runs = [], 0
            for fid in fluxos:
                arqs = sorted((output / "runs" / cfg / fid).glob("run_*.json"))
                if len(arqs) < 2:
                    continue
                runs = [achados_do_run(json.loads(a.read_text(encoding="utf-8"))) for a in arqs]
                n_runs = max(n_runs, len(runs))
                grupos_total += agrupar(runs, limiar=lim)
            if grupos_total:
                saida["por_config"][cfg][str(lim)] = resumo_grupos(grupos_total, n_runs)
    if destino is not None:
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "estabilidade.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    return saida
