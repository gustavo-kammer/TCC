from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import ancoragem
from .matching import casar
from .stats import wilson

VEREDITOS = ("procedente", "não procedente", "inconclusivo")
TIPOS_ERRO = ("inexistente na captura", "suposição de interação", "generalização", "discordância (preferência ou escopo)")
CAB = ["id", "fluxo", "estado", "heurística", "severidade", "local", "descrição", "justificativa",
       "evidência (tipo)", "evidência (citação ou região)", "captura", "VEREDITO", "TIPO DO ERRO", "COMENTÁRIO"]
LARG = [6, 7, 18, 28, 10, 26, 55, 55, 12, 40, 40, 16, 28, 40]

INSTRUCOES = [
    "Auditoria dos achados do LLM sem par nos especialistas",
    "",
    "Para cada linha da aba Amostra, abra a captura indicada (coluna 'captura') e confira se o achado descreve algo que existe no material.",
    "VEREDITO:",
    "  procedente: o problema descrito existe na captura ou no texto da página e fere a heurística indicada.",
    "  não procedente: o achado descreve algo inexistente, errado, genérico demais para ser verificado ou que depende de interação não observável na captura.",
    "  inconclusivo: não é possível decidir com o material disponível.",
    "TIPO DO ERRO (só para 'não procedente'), segundo a tipologia de Guerino et al. (2025):",
    "  inexistente na captura: o elemento ou texto citado não aparece.",
    "  suposição de interação: afirma comportamento (hover, clique, feedback) que uma captura estática não permite observar.",
    "  generalização: descrição ampla demais para ser confirmada.",
    "  discordância (preferência ou escopo): o elemento existe, mas o avaliador não considera problema.",
    "A configuração que gerou cada achado não é informada, de propósito.",
]


def populacao(raiz: Path, output: Path, fluxos: list[str], textos: dict[str, dict[int, str]],
              capturas: dict[str, dict[int, str]], configs=("hibrido", "llm"), run: int = 0) -> tuple[list[dict], dict]:
    itens, totais = [], {}
    for cfg in configs:
        tot = com_par_n = 0
        for fid in fluxos:
            c = casar(raiz, output, cfg, fid, run)
            rep = json.loads((output / "runs" / cfg / fid / f"run_{run}.json").read_text(encoding="utf-8"))
            com_par = {m["finding_id"] for m in c["matches"] if m["match"] != "none" and m["finding_id"]}
            n = 0
            for est in rep["estados"]:
                for v in est["relatorio"]["violations"]:
                    n += 1
                    if v["source"] != "llm":
                        continue
                    tot += 1
                    if n in com_par:
                        com_par_n += 1
                        continue
                    ev = v.get("evidence")
                    itens.append({
                        "config": cfg, "fluxo": fid, "run": run, "finding_id": n, "estado": est["nome"],
                        "heuristica": v["heuristic"], "severidade": v["severity_effective"], "local": v["location"],
                        "descricao": v["description"], "justificativa": v["justification"],
                        "evidencia_tipo": (ev or {}).get("kind", ""),
                        "evidencia": (ev or {}).get("quote") or (ev or {}).get("region") or "",
                        "captura": capturas.get(fid, {}).get(est["ordem"], ""),
                        "ancoragem": ancoragem.classificar(ev, textos.get(fid, {}).get(est["ordem"], "")),
                    })
        totais[cfg] = {"achados_llm": tot, "com_par": com_par_n, "sem_par": tot - com_par_n}
    return itens, totais


def sortear(itens: list[dict], n: int = 80, semente: int = 2026, minimo_por_config: int = 10,
            igualitaria: bool = False) -> list[dict]:
    rng = random.Random(semente)
    por_cfg: dict[str, list[dict]] = {}
    for it in itens:
        por_cfg.setdefault(it["config"], []).append(it)
    n = min(n, len(itens))
    if igualitaria:
        cotas = {c: min(len(v), n // len(por_cfg)) for c, v in por_cfg.items()}
    else:
        cotas = {c: min(len(v), max(minimo_por_config, round(n * len(v) / len(itens)))) for c, v in por_cfg.items()}
        while sum(cotas.values()) > n:
            maior = max(cotas, key=cotas.get)
            cotas[maior] -= 1
    amostra = [x for c, v in sorted(por_cfg.items()) for x in rng.sample(v, cotas[c])]
    rng.shuffle(amostra)
    return [{"id": i, **x} for i, x in enumerate(amostra, 1)]


def gravar(amostra: list[dict], totais: dict, destino: Path) -> dict[str, Path]:
    destino.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws0 = wb.active; ws0.title = "Instruções"
    for i, linha in enumerate(INSTRUCOES, 1):
        ws0.cell(row=i, column=1, value=linha).font = Font(name="Arial", bold=(i == 1), size=11 if i > 1 else 13)
    ws0.column_dimensions["A"].width = 140
    ws = wb.create_sheet("Amostra")
    ws.append(CAB)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF", name="Arial"); c.fill = PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for a in amostra:
        ws.append([a["id"], a["fluxo"], a["estado"], a["heuristica"], a["severidade"], a["local"], a["descricao"],
                   a["justificativa"], a["evidencia_tipo"], a["evidencia"], a["captura"], "", "", ""])
    for i, w in enumerate(LARG, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top"); c.font = Font(name="Arial", size=10)
    dv1 = DataValidation(type="list", formula1='"' + ",".join(VEREDITOS) + '"', allow_blank=True)
    dv2 = DataValidation(type="list", formula1='"' + ",".join(TIPOS_ERRO) + '"', allow_blank=True)
    ws.add_data_validation(dv1); ws.add_data_validation(dv2)
    dv1.add(f"L2:L{len(amostra) + 1}"); dv2.add(f"M2:M{len(amostra) + 1}")
    ws.freeze_panes = "A2"
    xlsx = destino / "auditoria_amostra.xlsx"; wb.save(xlsx)
    chave = destino / "auditoria_chave.csv"
    with open(chave, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "config", "fluxo", "run", "finding_id", "estado", "ancoragem"], delimiter=";",
                           extrasaction="ignore")
        w.writeheader(); w.writerows(amostra)
    pop = destino / "auditoria_populacao.json"
    pop.write_text(json.dumps({"totais": totais, "amostra": len(amostra)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"planilha": xlsx, "chave": chave, "populacao": pop}


def _veredito(v) -> str | None:
    t = str(v or "").strip().lower()
    if t.startswith("p"):
        return "procedente"
    if t.startswith("n"):
        return "nao_procedente"
    if t.startswith("i"):
        return "inconclusivo"
    return None


def calcular(planilha: Path, chave: Path, populacao_json: Path) -> dict:
    ws = load_workbook(planilha, data_only=True)["Amostra"]
    cab = [c.value for c in ws[1]]
    i_id, i_v, i_t = cab.index("id"), cab.index("VEREDITO"), cab.index("TIPO DO ERRO")
    i_c = cab.index("COMENTÁRIO") if "COMENTÁRIO" in cab else None
    ch = {int(r["id"]): r for r in csv.DictReader(open(chave, encoding="utf-8-sig"), delimiter=";")}
    pop = json.loads(populacao_json.read_text(encoding="utf-8"))["totais"]
    linhas = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        v = _veredito(row[i_v])
        if row[i_id] is None or v is None:
            continue
        com = str(row[i_c] or "").strip().lower() if i_c is not None else ""
        linhas.append({**ch[int(row[i_id])], "veredito": v, "tipo": row[i_t] or "",
                       "ressalva": v == "procedente" and com.startswith("procede com ressalva")})
    saida: dict = {"auditados": len(linhas), "por_config": {}, "ancoragem_vs_veredito": {}}
    for cfg in sorted({r["config"] for r in linhas}):
        rs = [r for r in linhas if r["config"] == cfg]
        proc = sum(r["veredito"] == "procedente" for r in rs)
        nao = sum(r["veredito"] == "nao_procedente" for r in rs)
        inc = sum(r["veredito"] == "inconclusivo" for r in rs)
        n = proc + nao
        ic = wilson(nao, n)
        t = pop[cfg]
        corr = lambda p: (t["com_par"] + t["sem_par"] * p) / t["achados_llm"] if t["achados_llm"] else None
        ic_proc = wilson(proc, n)
        ress = sum(r["ressalva"] for r in rs)
        n_c = proc + nao + inc
        p_c = proc - ress
        ic_c = wilson(p_c, n_c) if n_c else None
        saida["por_config"][cfg] = {
            "auditados": len(rs), "procedentes": proc, "nao_procedentes": nao, "inconclusivos": inc,
            "taxa_nao_procedente": nao / n if n else None, "taxa_nao_procedente_ic95": ic,
            "tipos_de_erro": {k: sum(r["tipo"] == k for r in rs if r["veredito"] == "nao_procedente") for k in TIPOS_ERRO},
            "achados_llm_run": t["achados_llm"], "achados_sem_par_run": t["sem_par"],
            "precisao_estimada": corr(proc / n) if n else None,
            "precisao_estimada_ic95": (corr(ic_proc[0]), corr(ic_proc[1])) if ic_proc else None,
            "cenario_conservador": {
                "procedentes_com_ressalva": ress, "procedentes_sem_ressalva": p_c, "n": n_c,
                "taxa_procedente": p_c / n_c if n_c else None,
                "precisao_estimada": corr(p_c / n_c) if n_c else None,
                "precisao_estimada_ic95": (corr(ic_c[0]), corr(ic_c[1])) if ic_c else None,
            },
        }
    verif = [r for r in linhas if r["ancoragem"] in ("ancorado", "nao_ancorado", "sem_citacao") and r["veredito"] != "inconclusivo"]
    nao_proc = [r for r in verif if r["veredito"] == "nao_procedente"]
    proc = [r for r in verif if r["veredito"] == "procedente"]
    fora = lambda rs: sum(r["ancoragem"] != "ancorado" for r in rs)
    saida["ancoragem_vs_veredito"] = {
        "n_verificaveis": len(verif),
        "sensibilidade": fora(nao_proc) / len(nao_proc) if nao_proc else None,
        "especificidade": (len(proc) - fora(proc)) / len(proc) if proc else None,
        "n_nao_procedentes": len(nao_proc), "n_procedentes": len(proc),
    }
    return saida
