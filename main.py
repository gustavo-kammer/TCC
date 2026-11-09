import argparse
import json
import re
import sys
from pathlib import Path

from src.evaluation.experiment import (
    CONFIGS, evaluate, human_cells_from_calibration, validation_cells)
from src.evaluation.gabarito import load_all
from src.frozen import Flow, flow_from_url, load_flow
from src.orchestrator import extract_flow, run_flow

RAIZ = Path(__file__).resolve().parent
SITES_JSON = RAIZ / "sites.json"
COLETAS = RAIZ / "coletas"
OUTPUT = RAIZ / "output"
RESULTADOS = RAIZ / "resultados"
GAB_CALIBRACAO = RAIZ / "gabarito" / "calibracao"


def _ids_validacao() -> list[str]:
    return [s["id"] for s in json.loads(SITES_JSON.read_text(encoding="utf-8"))]


def _flow_do_alvo(alvo: str) -> Flow:
    if alvo in _ids_validacao():
        return load_flow(alvo, base=COLETAS, sites_json=SITES_JSON)
    caminho = Path(alvo)
    if caminho.exists():
        return flow_from_url(caminho.stem, caminho.resolve().as_uri())
    if re.match(r"^(https?|file)://", alvo):
        slug = re.sub(r"[^\w]+", "_", re.sub(r"^\w+://", "", alvo)).strip("_")[:60]
        return flow_from_url(slug, alvo)
    raise SystemExit(f"Alvo não reconhecido: {alvo!r} (use um id do sites.json, URL ou arquivo)")


def _imprimir_celulas(agregado: dict) -> None:
    print(f"\n{agregado['flow_id']} [{agregado['metadata']['configuracao']}]")
    for h, c in agregado["celulas"].items():
        extra = f"  origem: {', '.join(c['origens'])}" if c["origens"] else ""
        print(f"  {h:<45} nota {c['nota']}  execuções {c['notas_execucoes']}{extra}")


def _rodar(flow: Flow, configs: tuple[str, ...], runs: int) -> None:
    print(f"[{flow.id}] {flow.site}")
    extracoes = extract_flow(flow)
    for cfg in configs:
        agregado = run_flow(flow, cfg, runs=runs, out_dir=OUTPUT,
                            extractions=extracoes)
        _imprimir_celulas(agregado)


def cmd_inspecionar(args: argparse.Namespace) -> None:
    flow = _flow_do_alvo(args.alvo)
    _rodar(flow, (args.config,), args.runs)
    print(f"\nAgregado: {OUTPUT / 'agregado' / args.config / (flow.id + '.json')}")


def _metricas_calibracao() -> None:
    cells = human_cells_from_calibration(load_all(GAB_CALIBRACAO))
    evaluate(cells, out_dir=OUTPUT, results_dir=RESULTADOS / "calibracao",
             titulo="Calibração (10 interfaces, 1 violação plantada cada)")
    print(f"Calibração: {RESULTADOS / 'calibracao' / 'resumo.md'}")


def cmd_calibracao(args: argparse.Namespace) -> None:
    for g in load_all(GAB_CALIBRACAO):
        url = (RAIZ / g.arquivo_ou_url).resolve().as_uri()
        _rodar(flow_from_url(g.interface_id, url), CONFIGS, args.runs)
    _metricas_calibracao()


def cmd_externa(args: argparse.Namespace) -> None:
    pasta_gabarito = {"p12": "observatorio", "p13": "siout"}
    ids = _ids_validacao()
    sem_gabarito = [i for i in ids if i not in pasta_gabarito]
    if sem_gabarito:
        raise SystemExit(f"Sem gabarito externo para: {sem_gabarito}")
    celulas = []
    for fid in ids:
        _rodar(load_flow(fid, base=COLETAS, sites_json=SITES_JSON), CONFIGS, args.runs)
        celulas += validation_cells(RAIZ / "gabarito" / pasta_gabarito[fid] / "_celulas.csv")
    evaluate(celulas, out_dir=OUTPUT, results_dir=RESULTADOS / "externa",
             titulo="Validação externa (sistemas avaliados por especialistas, Capeleti 2024)")
    print(f"Validação externa: {RESULTADOS / 'externa' / 'resumo.md'}")


def cmd_casamento(args: argparse.Namespace) -> None:
    import csv
    from src.evaluation import matching as M
    saida = RESULTADOS / "externa_problemas"
    saida.mkdir(parents=True, exist_ok=True)
    fluxos = list(M.PASTA_GABARITO)
    todos: list[dict] = []
    linhas, md = [], ["# Avaliação por violação (externa)", "",
        "Juiz: LLM, cego à configuração. Recall = problemas dos especialistas encontrados; "
        "precisão = achados com par (limite inferior). *Ponderado*: parcial = 0,5; "
        "*estrito*: só casamento completo. Valores = mediana das execuções.", "",
        "| Configuração | Fluxo | Execuções | Problemas | Achados | Recall (pond.) | Recall (estr.) | Precisão (pond.) | Precisão (estr.) | F1 (pond.) | F1 (estr.) | Pares | Kappa sev. |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda v: "—" if v is None else f"{v:.3f}"
    for cfg in M.CONFIGS:
        for alvo in [[x] for x in fluxos] + [fluxos]:
            runs = sorted(set.intersection(*[set(M.runs_disponiveis(OUTPUT, cfg, x)) for x in alvo]))
            if args.runs:
                runs = runs[:args.runs]
            if not runs:
                continue
            por_run = []
            for k in runs:
                cas = [M.casar(RAIZ, OUTPUT, cfg, x, k) for x in alvo]
                if len(alvo) == len(fluxos):
                    todos += cas
                por_run.append(M.metricas_casamento(cas))
            m = M.mediana_metricas(por_run)
            nome = "+".join(alvo) if len(alvo) > 1 else alvo[0]
            linhas.append({"configuracao": cfg, "fluxo": nome, "execucoes": len(runs), **m})
            md.append(f"| {cfg} | {nome} | {len(runs)} | {m['problemas']:.0f} | {m['achados']:.0f} | "
                      f"{f(m['recall_ponderado'])} | {f(m['recall_estrito'])} | {f(m['precisao_ponderada'])} | "
                      f"{f(m['precisao_estrita'])} | {f(m['f1_ponderado'])} | {f(m['f1_estrito'])} | "
                      f"{m['n_pares_severidade']:.0f} | {f(m['kappa_severidade'])} |")
    with open(saida / "metricas_por_violacao.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0])); w.writeheader(); w.writerows(linhas)
    (saida / "resumo.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    base = [c for c in todos if c["run"] == min(r["run"] for r in todos)]
    pub, chave = M.gerar_amostra(base)
    pop = {"casou": sum(m["match"] != "none" for c in base for m in c["matches"]),
           "nao_casou": sum(m["match"] == "none" for c in base for m in c["matches"])}
    (saida / "amostra_populacao.json").write_text(json.dumps(pop, ensure_ascii=False, indent=1), encoding="utf-8")
    _amostra_xlsx(pub, saida / "amostra_conferencia_abas.xlsx")
    for nome, dados in (("amostra_conferencia.csv", pub), ("amostra_gabarito_oculto.csv", chave)):
        try:
            with open(saida / nome, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(dados[0]), delimiter=";"); w.writeheader(); w.writerows(dados)
        except PermissionError:
            print(f"Aviso: {nome} está aberto em outro programa; feche-o para regravar.")
    print(f"Resumo: {saida / 'resumo.md'}\nPlanilha para você preencher: {saida / 'amostra_conferencia_abas.xlsx'}")


def _amostra_xlsx(pub: list[dict], destino: Path) -> None:
    import re
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    F = lambda **k: Font(name="Arial", size=10, **k)
    wb = Workbook()

    ins = wb.active; ins.title = "Instruções"
    texto = [
        ("COMO PREENCHER", True),
        ("Objetivo: conferir se o juiz automático casou corretamente os problemas dos especialistas com os achados do sistema.", False),
        ("", False),
        ("Aba A_casou — o juiz disse que o achado do sistema É o mesmo problema do especialista.", True),
        ("  Leia as colunas C e D. Na coluna E escolha: concordo (mesmo elemento e mesmo tipo de problema) ou discordo.", False),
        ("", False),
        ("Aba B_nao_casou — o juiz disse que NENHUM achado corresponde ao problema do especialista.", True),
        ("  Leia o problema (coluna C). Abra a aba Achados_B, filtre a coluna A pelo mesmo id, e veja se algum achado descreve o mesmo problema.", False),
        ("  Na coluna D escreva o número (coluna B de Achados_B) desse achado, ou 0 se nenhum corresponder.", False),
        ("", False),
        ("Critério: mesmo elemento ou região da interface E mesmo tipo de problema. Mesma heurística de Nielsen não basta.", False),
        ("Os problemas estão em inglês; ignore o idioma. Em caso de dúvida, consulte o screenshot em coletas/.", False),
        ("A ordem é embaralhada e a configuração (híbrido, regras, LLM) não é mostrada de propósito.", False),
    ]
    for i, (t, neg) in enumerate(texto, 1):
        c = ins.cell(i, 1, t); c.font = F(bold=neg); c.alignment = Alignment(wrap_text=True, vertical="top")
    ins.column_dimensions["A"].width = 120

    def cab(ws, cols, larg):
        ws.append(cols)
        for i, w in enumerate(larg, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        for c in ws[1]:
            c.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
            c.fill = PatternFill("solid", fgColor="305496")
            c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.freeze_panes = "A2"

    def corpo(ws):
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = F(); c.alignment = Alignment(vertical="top", wrap_text=True)

    A = wb.create_sheet("A_casou")
    cab(A, ["id", "fluxo", "problema_do_especialista", "achado_do_sistema", "SEU_VEREDITO"], [6, 8, 55, 70, 18])
    B = wb.create_sheet("B_nao_casou")
    cab(B, ["id", "fluxo", "problema_do_especialista", "SEU_VEREDITO (nº do achado ou 0)"], [6, 8, 70, 24])
    L = wb.create_sheet("Achados_B")
    cab(L, ["id", "nº do achado", "achado do sistema"], [6, 12, 120])
    for r in pub:
        if r["tipo"] == "casou":
            A.append([r["id"], r["fluxo"], r["problema_do_especialista"], r["achado_do_sistema"], ""])
        else:
            B.append([r["id"], r["fluxo"], r["problema_do_especialista"], ""])
            for linha in r["lista_de_achados"].split("\n"):
                m = re.match(r"^(\d+)\.\s*(.*)$", linha)
                if m:
                    L.append([r["id"], int(m.group(1)), m.group(2)])
    for ws in (A, B, L):
        corpo(ws)
    L.auto_filter.ref = f"A1:C{L.max_row}"
    dv = DataValidation(type="list", formula1='"concordo,discordo"', allow_blank=True)
    A.add_data_validation(dv)
    for i in range(2, A.max_row + 1):
        A.cell(i, 5).fill = PatternFill("solid", fgColor="FFF2CC"); dv.add(A.cell(i, 5))
    dn = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    B.add_data_validation(dn)
    for i in range(2, B.max_row + 1):
        B.cell(i, 4).fill = PatternFill("solid", fgColor="FFF2CC"); dn.add(B.cell(i, 4))
    wb.save(destino)


def cmd_conferir(args: argparse.Namespace) -> None:
    import csv
    from src.evaluation import matching as M
    saida = RESULTADOS / "externa_problemas"
    def lê(p) -> list[dict]:
        p = Path(p)
        if p.suffix.lower() == ".xlsx":
            from openpyxl import load_workbook
            wb = load_workbook(p, data_only=True)
            saida_l = []
            for aba, tipo, col in (("A_casou", "casou", 4), ("B_nao_casou", "nao_casou", 3)):
                for l in list(wb[aba].values)[1:]:
                    v = l[col]
                    saida_l.append({"id": str(l[0]), "tipo": tipo,
                                    "SEU_VEREDITO": "" if v is None else str(v).replace(".0", "")})
            return saida_l
        txt = p.read_text(encoding="utf-8-sig")
        delim = ";" if txt.split("\n", 1)[0].count(";") >= txt.split("\n", 1)[0].count(",") else ","
        return list(csv.DictReader(txt.splitlines(), delimiter=delim))
    padrao = saida / "amostra_conferencia_abas.xlsx"
    arq_pop = saida / "amostra_populacao.json"
    pop = json.loads(arq_pop.read_text(encoding="utf-8")) if arq_pop.exists() else None
    r = M.concordancia(lê(args.planilha or padrao), lê(saida / "amostra_gabarito_oculto.csv"), pop)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    (saida / "concordancia.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_metricas(args: argparse.Namespace) -> None:
    feito = False
    if list(OUTPUT.glob("agregado/*/calib_*.json")):
        _metricas_calibracao()
        feito = True
    if list(OUTPUT.glob("agregado/*/p1[0-9].json")):
        celulas = []
        for fid, pasta in {"p12": "observatorio", "p13": "siout"}.items():
            celulas += validation_cells(RAIZ / "gabarito" / pasta / "_celulas.csv")
        evaluate(celulas, out_dir=OUTPUT, results_dir=RESULTADOS / "externa",
                 titulo="Validação externa (sistemas avaliados por especialistas, Capeleti 2024)")
        print(f"Validação externa: {RESULTADOS / 'externa' / 'resumo.md'}")
        feito = True
    if not feito:
        raise SystemExit("Nada a medir: rode 'calibracao' ou 'externa' antes.")


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("inspecionar", help="roda uma configuração em um fluxo ou URL")
    p.add_argument("alvo")
    p.add_argument("--config", choices=CONFIGS, default="hibrido")
    p.add_argument("--runs", type=int, default=1)
    p.set_defaults(func=cmd_inspecionar)

    p = sub.add_parser("calibracao", help="roda as 3 configurações nas 10 páginas de calibração")
    p.add_argument("--runs", type=int, default=3)
    p.set_defaults(func=cmd_calibracao)

    p = sub.add_parser("externa", help="roda as 3 configurações nos sites externos e mede contra o gabarito de especialistas")
    p.add_argument("--runs", type=int, default=3)
    p.set_defaults(func=cmd_externa)

    p = sub.add_parser("casamento", help="avaliação por violação nas externas (juiz LLM)")
    p.add_argument("--runs", type=int, default=0, help="limita as execuções usadas (0 = todas)")
    p.set_defaults(func=cmd_casamento)

    p = sub.add_parser("conferir", help="concordância do seu veredito com o juiz")
    p.add_argument("planilha", nargs="?", default=None)
    p.set_defaults(func=cmd_conferir)

    p = sub.add_parser("metricas", help="recalcula as métricas a partir de output/agregado")
    p.set_defaults(func=cmd_metricas)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
