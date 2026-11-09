import csv, json, statistics as st, collections
import main as MN
from src.evaluation import matching as M

fluxos = list(M.PASTA_GABARITO)
cats = {r["code"]: r["categoria"] for r in csv.DictReader(open("classificacao_104.csv", encoding="utf-8-sig"), delimiter=";")}
CATS = sorted(set(cats.values()))
PESO = M.PESO
out = {"cfgs": list(M.CONFIGS)}
runs_cfg = {cfg: sorted(set.intersection(*[set(M.runs_disponiveis(MN.OUTPUT, cfg, x)) for x in fluxos])) for cfg in M.CONFIGS}
out["runs"] = runs_cfg

def med(v): return st.median(v) if v else None
def faixa(v): return [min(v), max(v)] if v else None

C = {}
SRC = {}
for cfg in M.CONFIGS:
    for k in runs_cfg[cfg]:
        for x in fluxos:
            C[cfg, k, x] = M.casar(MN.RAIZ, MN.OUTPUT, cfg, x, k)
            d = json.load(open(MN.OUTPUT / "runs" / cfg / x / f"run_{k}.json", encoding="utf-8"))
            ids, n = {}, 0
            for est in d["estados"]:
                for v in est["relatorio"]["violations"]:
                    n += 1; ids[n] = v["source"]
            SRC[cfg, k, x] = ids

CH = ["recall_estrito", "recall_ponderado", "precisao_estrita", "precisao_ponderada", "f1_estrito", "f1_ponderado", "kappa_severidade"]
out["metricas"] = {}
for cfg in M.CONFIGS:
    por_run = {k: M.metricas_casamento([C[cfg, k, x] for x in fluxos]) for k in runs_cfg[cfg]}
    por_flx = {x: {k: M.metricas_casamento([C[cfg, k, x]]) for k in runs_cfg[cfg]} for x in fluxos}
    out["metricas"][cfg] = {
        "por_run": {k: {h: por_run[k][h] for h in CH + ["problemas", "achados", "casou", "parcial", "n_pares_severidade"]} for k in por_run},
        "mediana": {h: med([por_run[k][h] for k in por_run if por_run[k][h] is not None]) for h in CH + ["achados", "n_pares_severidade"]},
        "faixa": {h: faixa([por_run[k][h] for k in por_run if por_run[k][h] is not None]) for h in CH + ["achados"]},
        "por_fluxo": {x: {h: med([por_flx[x][k][h] for k in por_flx[x] if por_flx[x][k][h] is not None]) for h in CH + ["achados"]} for x in fluxos},
        "por_fluxo_faixa": {x: {h: faixa([por_flx[x][k][h] for k in por_flx[x] if por_flx[x][k][h] is not None]) for h in ["recall_ponderado", "recall_estrito", "precisao_ponderada"]} for x in fluxos},
    }

def melhor(cfg, k, code):
    for x in fluxos:
        for m in C[cfg, k, x]["matches"]:
            if m["problem_code"] == code: return m
    return None

codes = list(cats)
out["uniao"], out["freq"], out["categoria"] = {}, {}, {}
bestw = {}
for cfg in M.CONFIGS:
    freq = collections.Counter(); pool_any = set(); pool_full = set(); w_pool = 0.0
    per_cat_run = {c: [] for c in CATS}; per_cat_run_w = {c: [] for c in CATS}; pool_cat = {c: set() for c in CATS}
    for code in codes:
        ms = [melhor(cfg, k, code) for k in runs_cfg[cfg]]
        n_any = sum(m["match"] != "none" for m in ms); freq[n_any] += 1
        if n_any: pool_any.add(code)
        if any(m["match"] == "full" for m in ms): pool_full.add(code)
        w_pool += max(PESO[m["match"]] for m in ms)
        if n_any: pool_cat[cats[code]].add(code)
        bestw[cfg, code] = max(PESO[m["match"]] for m in ms)
    for k in runs_cfg[cfg]:
        for c in CATS:
            cs = [code for code in codes if cats[code] == c]
            ms = [melhor(cfg, k, code) for code in cs]
            per_cat_run[c].append(sum(m["match"] != "none" for m in ms) / len(cs))
            per_cat_run_w[c].append(sum(PESO[m["match"]] for m in ms) / len(cs))
    out["uniao"][cfg] = {"recall_qualquer_par": len(pool_any) / 104, "recall_estrito": len(pool_full) / 104, "recall_ponderado": w_pool / 104,
                         "n_qualquer_par": len(pool_any), "n_estrito": len(pool_full)}
    out["freq"][cfg] = {str(i): freq.get(i, 0) for i in range(len(runs_cfg[cfg]) + 1)}
    out["categoria"][cfg] = {c: {"n": sum(1 for code in codes if cats[code] == c),
                                 "qualquer_par_med": med(per_cat_run[c]), "qualquer_par_faixa": faixa(per_cat_run[c]),
                                 "ponderado_med": med(per_cat_run_w[c]), "uniao": len(pool_cat[c]) / sum(1 for code in codes if cats[code] == c)}
                             for c in CATS}

sets = {}
for cfg in M.CONFIGS:
    sets[cfg] = {code for code in codes if any(melhor(cfg, k, code)["match"] != "none" for k in runs_cfg[cfg])}
out["complementar"] = {
    "regras": len(sets["regras"]), "llm": len(sets["llm"]), "hibrido": len(sets["hibrido"]),
    "llm_e_hibrido": len(sets["llm"] & sets["hibrido"]), "so_hibrido": len(sets["hibrido"] - sets["llm"]), "so_llm": len(sets["llm"] - sets["hibrido"]),
    "regras_nao_llm_nem_hibrido": len(sets["regras"] - sets["llm"] - sets["hibrido"]),
    "regras_dentro_llm_ou_hibrido": len(sets["regras"] & (sets["llm"] | sets["hibrido"])),
    "nenhuma": len(set(codes) - sets["regras"] - sets["llm"] - sets["hibrido"]),
    "alguma": len(sets["regras"] | sets["llm"] | sets["hibrido"]),
}

out["volume"] = {}
for cfg in M.CONFIGS:
    v = {}
    for x in fluxos:
        v[x] = {"achados_med": med([len(C[cfg, k, x]["achados"]) for k in runs_cfg[cfg]]),
                "achados_por_run": [len(C[cfg, k, x]["achados"]) for k in runs_cfg[cfg]]}
    out["volume"][cfg] = v
comp = {}
for k in runs_cfg["hibrido"]:
    tot = collections.Counter(); casados = collections.Counter(); prob_origem = collections.Counter()
    for x in fluxos:
        src = SRC["hibrido", k, x]
        for a in C["hibrido", k, x]["achados"]: tot[src[a["id"]]] += 1
        best = {}
        for m in C["hibrido", k, x]["matches"]:
            if m["match"] == "none": continue
            fid = m["finding_id"]; best[fid] = max(best.get(fid, 0), PESO[m["match"]])
            prob_origem[src[fid]] += 1
        for fid, w in best.items(): casados[src[fid]] += 1
    comp[k] = {"achados": dict(tot), "achados_com_par": dict(casados), "pares_por_origem": dict(prob_origem)}
out["hibrido_composicao"] = comp

sev = {}
for cfg in M.CONFIGS:
    dif = []
    for k in runs_cfg[cfg]:
        for x in fluxos:
            c = C[cfg, k, x]
            se = {p["code"]: p["severity"] for p in c["problemas"]}; ss = {a["id"]: a["severidade"] for a in c["achados"]}
            for m in c["matches"]:
                if m["match"] != "none": dif.append((ss[m["finding_id"]], se[m["problem_code"]]))
    n = len(dif)
    sev[cfg] = {"pares": n, "igual": sum(a == b for a, b in dif) / n if n else None,
                "sistema_maior": sum(a > b for a, b in dif) / n if n else None,
                "sistema_menor": sum(a < b for a, b in dif) / n if n else None,
                "media_sistema": sum(a for a, b in dif) / n if n else None, "media_especialista": sum(b for a, b in dif) / n if n else None}
out["severidade"] = sev
out["sev_especialistas"] = dict(collections.Counter(str(p["severity"]) for x in fluxos for p in C["hibrido", runs_cfg["hibrido"][0], x]["problemas"]))

cal = list(csv.DictReader(open("resultados/calibracao/celulas_sistema_vs_humano.csv", encoding="utf-8-sig")))
plant = [r for r in cal if r["apontada"] == "1"]
out["calibracao"] = {"plantadas": []}
for r in plant:
    out["calibracao"]["plantadas"].append({
        "fluxo": r["fluxo"], "heuristica": r["heuristica"][:3], "consenso": r["consenso"],
        **{cfg: {"nota": r[f"sistema_{cfg}"], "origem": r[f"origem_{cfg}"], "execucoes": r[f"execucoes_{cfg}"]} for cfg in M.CONFIGS}})
extras = {}
for cfg in M.CONFIGS:
    por_fluxo = collections.defaultdict(int)
    for r in cal:
        if r["apontada"] != "1" and r["status"] == "incluida" and int(r[f"sistema_{cfg}"] or 0) >= 1: por_fluxo[r["fluxo"]] += 1
    extras[cfg] = sum(por_fluxo.values()) / 10
out["calibracao"]["heuristicas_extras_por_interface"] = extras
cm = list(csv.DictReader(open("resultados/calibracao/metricas_por_configuracao.csv", encoding="utf-8-sig")))
out["calibracao"]["metricas"] = cm

MN.RESULTADOS.mkdir(parents=True, exist_ok=True)
json.dump(out, open(MN.RESULTADOS / "analises.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", MN.RESULTADOS / "analises.json")
