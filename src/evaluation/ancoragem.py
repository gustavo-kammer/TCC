from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

ATRIBUTOS = ("placeholder", "title", "aria-label", "alt", "value")
STATUS = ("ancorado", "nao_ancorado", "visual", "sem_citacao", "sem_campo")


def _compacto(texto: str) -> str:
    t = unicodedata.normalize("NFKC", texto).casefold()
    return re.sub(r"[\W_]+", "", t)


def texto_da_pagina(html_path: Path | None) -> str:
    if html_path is None or not Path(html_path).exists():
        return ""
    soup = BeautifulSoup(Path(html_path).read_text(encoding="utf-8", errors="ignore"), "html.parser")
    attrs = " ".join(str(t.attrs[a]) for t in soup.find_all(True) for a in ATRIBUTOS if a in t.attrs)
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return _compacto(soup.get_text(" ") + " " + attrs)


def classificar(evidence: dict | None, texto_compacto: str) -> str:
    if not evidence:
        return "sem_campo"
    if evidence.get("kind") == "visual":
        return "visual"
    citacao = _compacto(evidence.get("quote") or "")
    if not citacao:
        return "sem_citacao"
    return "ancorado" if citacao in texto_compacto else "nao_ancorado"


def verificar_execucao(run: dict, textos: dict[int, str]) -> list[dict]:
    registros, n = [], 0
    for est in run["estados"]:
        for v in est["relatorio"]["violations"]:
            n += 1
            if v["source"] != "llm":
                continue
            ev = v.get("evidence")
            registros.append({
                "finding_id": n, "estado": est["nome"], "heuristica": v["heuristic"],
                "descricao": v["description"], "evidencia_tipo": (ev or {}).get("kind", ""),
                "evidencia": ((ev or {}).get("quote") or (ev or {}).get("region") or ""),
                "status": classificar(ev, textos.get(est["ordem"], "")),
            })
    return registros


def resumo(registros: list[dict]) -> dict:
    c = {s: sum(r["status"] == s for r in registros) for s in STATUS}
    verificaveis = c["ancorado"] + c["nao_ancorado"] + c["sem_citacao"]
    return {**c, "total": len(registros), "verificaveis": verificaveis,
            "taxa_nao_ancorado": (c["nao_ancorado"] + c["sem_citacao"]) / verificaveis if verificaveis else None,
            "fracao_visual": c["visual"] / len(registros) if registros else None}


def verificar_tudo(output: Path, fluxos: dict[str, dict[int, Path | None]], configs=("hibrido", "llm"),
                   destino: Path | None = None) -> dict:
    saida: dict = {}
    todos: list[dict] = []
    for cfg in configs:
        saida[cfg] = {}
        for fid, htmls in fluxos.items():
            textos = {o: texto_da_pagina(h) for o, h in htmls.items()}
            for arq in sorted((output / "runs" / cfg / fid).glob("run_*.json")):
                k = int(arq.stem.split("_")[1])
                regs = verificar_execucao(json.loads(arq.read_text(encoding="utf-8")), textos)
                saida[cfg][f"{fid}/run_{k}"] = resumo(regs)
                todos += [{"config": cfg, "fluxo": fid, "run": k, **r} for r in regs]
    por_cfg = {}
    for cfg in configs:
        regs = [r for r in todos if r["config"] == cfg]
        por_cfg[cfg] = resumo(regs)
    saida["total_por_config"] = por_cfg
    if destino is not None:
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "ancoragem.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
        if todos:
            with open(destino / "ancoragem_achados.csv", "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(todos[0]), delimiter=";")
                w.writeheader(); w.writerows(todos)
    return saida
