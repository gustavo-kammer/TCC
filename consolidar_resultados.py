import csv, collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import main as MN
from src.evaluation import matching as M

NOME = {"hibrido": "Híbrido", "regras": "Regras", "llm": "LLM"}
RES = {"full": "Casou", "partial": "Parcial", "none": "Não casou"}
RANK = {"Casou": 0, "Parcial": 1, "Não casou": 2}
cat = {r["code"]: r for r in csv.DictReader(open("classificacao_104.csv", encoding="utf-8-sig"), delimiter=";")}
fluxos = list(M.PASTA_GABARITO)
ordem = [c for p in fluxos for c in sorted(k for k in cat if cat[k]["fluxo"] == p)]
HDR = PatternFill("solid", fgColor="1F3864")
COR = {"Casou": "C6EFCE", "Parcial": "FFEB9C", "Não casou": "F8CBAD"}


def aba(wb, nome, cab, linhas, larg, col_res=None):
    ws = wb.create_sheet(nome[:31]); ws.append(cab)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF", name="Arial"); c.fill = HDR
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for l in linhas: ws.append(l)
    for i, w in enumerate(larg, 1): ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top"); c.font = Font(name="Arial", size=10)
        if col_res is not None:
            v = row[col_res].value
            if v in COR: row[col_res].fill = PatternFill("solid", fgColor=COR[v])
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    return ws


linhas_run, casaram, nao = {}, [], []
achados_run, achados_todos = {}, []
for cfg in M.CONFIGS:
    runs = sorted(set.intersection(*[set(M.runs_disponiveis(MN.OUTPUT, cfg, x)) for x in fluxos]))
    for k in runs:
        por, A = {}, []
        for x in fluxos:
            c = M.casar(MN.RAIZ, MN.OUTPUT, cfg, x, k)
            ach = {a["id"]: a for a in c["achados"]}
            for m in c["matches"]: por[m["problem_code"]] = (m, ach.get(m["finding_id"]), x)
            st, cods = {}, collections.defaultdict(list)
            for m in c["matches"]:
                if m["match"] == "none" or not m["finding_id"]: continue
                s = RES[m["match"]]
                if m["finding_id"] not in st or RANK[s] < RANK[st[m["finding_id"]]]: st[m["finding_id"]] = s
                cods[m["finding_id"]].append(f'{m["problem_code"]} ({s.lower()})')
            for a in c["achados"]:
                s = st.get(a["id"], "Não casou")
                A.append([x, a["id"], a["estado"], a["heuristica"], a["severidade"],
                          a["local"], a["descricao"], s, "; ".join(cods.get(a["id"], []))])
        A.sort(key=lambda r: (RANK[r[7]], r[0], r[2], r[1]))
        achados_run[(cfg, k)] = A
        achados_todos += [[NOME[cfg], k + 1] + r for r in A]
        L = []
        for code in ordem:
            m, a, x = por[code]; r = cat[code]
            res = RES[m["match"]]
            achado = (a["descricao"] + (f' ({a["local"]})' if a["local"] else "")) if a else ""
            base = [code, x, int(r["severidade"]), r["categoria"], r["descricao"], res,
                    m["finding_id"] or "", a["estado"] if a else "", achado,
                    a["heuristica"] if a else "", a["severidade"] if a else "", m["rationale"]]
            L.append(base)
            (nao if m["match"] == "none" else casaram).append([NOME[cfg], k + 1] + base)
        linhas_run[(cfg, k)] = L

CAB = ["Código", "Fluxo", "Severidade (especialista)", "Categoria", "Problema do especialista", "Resultado",
       "Nº do achado", "Estado", "Achado do sistema que casou", "Heurística", "Severidade do achado", "Justificativa do juiz"]
LARG = [10, 7, 11, 24, 50, 11, 8, 18, 60, 9, 10, 50]
CABA = ["Fluxo", "Nº do achado", "Estado", "Heurística", "Severidade", "Local", "Descrição do achado do sistema",
        "Resultado", "Problema(s) do especialista com que casou"]
LARGA = [7, 8, 20, 9, 10, 35, 70, 11, 40]

wb = Workbook(); wb.remove(wb.active)
hits = collections.Counter()
for L in linhas_run.values():
    for l in L:
        if l[5] != "Não casou": hits[l[0]] += 1
av = [[c, cat[c]["fluxo"], int(cat[c]["severidade"]), cat[c]["categoria"], cat[c]["motivo"], cat[c]["descricao"],
       hits[c], len(linhas_run)] for c in ordem]
aba(wb, "Avaliadores", ["Código", "Fluxo", "Severidade", "Categoria", "Motivo da classificação",
                         "Problema do especialista", "Rodadas em que casou (qualquer par)", "Total de rodadas"],
    av, [10, 7, 10, 28, 40, 70, 14, 10])

resumo = []
for (cfg, k), A in achados_run.items():
    n = collections.Counter(r[7] for r in A)
    resumo.append([NOME[cfg], k + 1, len(A), n["Casou"], n["Parcial"], n["Não casou"],
                   round((n["Casou"] + n["Parcial"]) / len(A), 3) if A else None])
aba(wb, "Resumo_achados", ["Configuração", "Execução", "Total de achados", "Casou", "Parcial", "Não casou",
                            "Fração que casou (limite inferior da precisão)"], resumo, [14, 10, 12, 10, 10, 11, 22])

for (cfg, k), L in linhas_run.items():
    aba(wb, f"{NOME[cfg]}_exec{k+1}", CAB, L, LARG, col_res=5)
for (cfg, k), A in achados_run.items():
    aba(wb, f"Achados_{NOME[cfg]}_{k+1}", CABA, A, LARGA, col_res=7)

aba(wb, "Achados_todos", ["Configuração", "Execução"] + CABA, achados_todos, [13, 9] + LARGA, col_res=9)
aba(wb, "Casaram", ["Configuração", "Execução"] + CAB, casaram, [13, 9] + LARG, col_res=7)
aba(wb, "Nao_casaram", ["Configuração", "Execução"] + CAB, nao, [13, 9] + LARG, col_res=7)

dest = MN.RESULTADOS / "externa_problemas" / "resultados_consolidados_v2.xlsx"
wb.save(dest)
print(dest, "| abas:", len(wb.sheetnames))
print("problemas: casaram", len(casaram), "| não casaram", len(nao))
print("achados:", len(achados_todos), "| casou", sum(r[9] == "Casou" for r in achados_todos),
      "| parcial", sum(r[9] == "Parcial" for r in achados_todos), "| não casou", sum(r[9] == "Não casou" for r in achados_todos))
