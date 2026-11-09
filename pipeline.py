import argparse
import contextlib
import hashlib
import json
import platform
import runpy
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops
from bs4 import BeautifulSoup

import capturar_paginas as CAP
import main as MN
from src.frozen import _pasta_mais_recente

RAIZ = Path(__file__).resolve().parent
IMPEDITIVOS = ("BLOQUEIO", "HTML muito pequeno", "FALHA")
LIMIAR_BRANCO = 0.995
LIMIAR_MUDANCA_FALHA = 0.001
LIMIAR_MUDANCA_AVISO = 0.005
MIN_TEXTO = 80
CONFIGS = ("hibrido", "regras", "llm")


def caminhos(versao: str) -> dict[str, Path]:
    suf = "" if versao == "v1" else f"_{versao}"
    return {"coletas": RAIZ / f"coletas{suf}", "output": RAIZ / f"output{suf}",
            "resultados": RAIZ / f"resultados{suf}"}


def aplicar_versao(versao: str, sites: str) -> dict[str, Path]:
    p = caminhos(versao)
    MN.SITES_JSON = (RAIZ / sites).resolve()
    MN.COLETAS, MN.OUTPUT, MN.RESULTADOS = p["coletas"], p["output"], p["resultados"]
    CAP.RAIZ_SAIDA = p["coletas"]
    return p


def _texto_visivel(html: Path) -> str:
    soup = BeautifulSoup(html.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return " ".join(soup.get_text(" ").split())


def _fracao_branco(png: Path) -> float:
    im = Image.open(png).convert("L")
    im.thumbnail((480, 480))
    h = im.histogram()
    return sum(h[248:]) / sum(h)


def _fracao_mudanca(a: Path, b: Path) -> float:
    ia = Image.open(a).convert("RGB").resize((480, 270))
    ib = Image.open(b).convert("RGB").resize((480, 270))
    h = ImageChops.difference(ia, ib).convert("L").histogram()
    return sum(h[25:]) / sum(h)


def validar_capturas(sites_json: Path, coletas: Path, ids: list[str], orcamento: int | None):
    sites = json.loads(sites_json.read_text(encoding="utf-8"))
    if ids:
        sites = [s for s in sites if s["id"] in ids]
    linhas: list[dict] = []
    resumo_sites: dict[str, dict] = {}
    for site in sites:
        sid = site["id"]
        try:
            pasta = _pasta_mais_recente(coletas, sid)
            meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
        except Exception as e:
            linhas.append({"site": sid, "estado": "(site)", "status": "FALHA", "notas": [f"sem captura legível: {e}"]})
            resumo_sites[sid] = {"validos": 0, "pasta": None}
            continue
        if meta.get("erro"):
            linhas.append({"site": sid, "estado": "(site)", "status": "FALHA", "notas": [f"erro geral na captura: {meta['erro']}"]})
        por_nome = {e["nome"]: e for e in meta["estados"]}
        anterior_png = None
        validos = 0
        for esperado in site["estados"]:
            nome = esperado["nome"]
            notas: list[str] = []
            status = "OK"
            est = por_nome.get(nome)
            if est is None:
                linhas.append({"site": sid, "estado": nome, "status": "FALHA", "notas": ["estado ausente no meta.json"]})
                continue
            alertas = est.get("alertas", [])
            imped = [a for a in alertas if any(a.startswith(p) for p in IMPEDITIVOS)]
            if imped:
                status = "FALHA"; notas += imped
            elif alertas:
                status = "AVISO"; notas += alertas
            arquivos = [pasta / f for f in est.get("fatias", [])] + ([pasta / est["html"]] if est.get("html") else [])
            faltando = [p.name for p in arquivos if not p.exists()]
            if not arquivos or faltando:
                status = "FALHA"; notas.append(f"arquivos ausentes: {faltando or 'nenhum arquivo registrado'}")
            else:
                completo = pasta / est["completo"]
                texto = _texto_visivel(pasta / est["html"])
                if len(texto) < MIN_TEXTO:
                    status = "FALHA"; notas.append(f"texto visível insuficiente ({len(texto)} caracteres)")
                html_bruto = (pasta / est["html"]).read_text(encoding="utf-8", errors="ignore").lower()
                ausentes = [t for t in esperado.get("exigir_texto", []) if t.lower() not in html_bruto]
                if ausentes:
                    status = "FALHA"; notas.append(f"conteúdo esperado ausente no HTML (página incompleta?): {ausentes}")
                branco = _fracao_branco(completo)
                if branco > LIMIAR_BRANCO:
                    status = "FALHA"; notas.append(f"imagem praticamente em branco ({branco:.1%})")
                base_nome = esperado.get("comparar_com")
                base = por_nome.get(base_nome) if base_nome else None
                if base_nome and base is None:
                    status = "FALHA" if status != "FALHA" else status
                    notas.append(f"estado de comparação '{base_nome}' ausente")
                elif base is not None:
                    dif = _fracao_mudanca(pasta / base["completo"], completo)
                    if dif < LIMIAR_MUDANCA_FALHA:
                        status = "FALHA"; notas.append(f"quase idêntico a '{base_nome}' ({dif:.2%} de pixels diferentes): a ação pode não ter surtido efeito")
                    elif dif < LIMIAR_MUDANCA_AVISO:
                        status = "AVISO" if status == "OK" else status
                        notas.append(f"mudança pequena em relação a '{base_nome}' ({dif:.2%} de pixels): confira a imagem")
                    else:
                        notas.append(f"{dif:.1%} de pixels diferem de '{base_nome}'")
                elif anterior_png is not None and _fracao_mudanca(anterior_png, completo) < 0.001:
                    status = "AVISO" if status == "OK" else status
                    notas.append("idêntico ao estado anterior")
                anterior_png = completo
                notas.append(f"{len(est['fatias'])} fatia(s), {len(texto)} caracteres de texto")
            if status != "FALHA":
                validos += 1
            linhas.append({"site": sid, "estado": nome, "status": status, "notas": notas,
                           "url": est.get("url_no_momento", "")})
        resumo_sites[sid] = {"validos": validos, "esperados": len(site["estados"]), "pasta": str(pasta),
                             "coletado_em": meta.get("coletado_em")}
        if orcamento is not None and validos != orcamento:
            linhas.append({"site": sid, "estado": "(orçamento)", "status": "FALHA",
                           "notas": [f"{validos} estados válidos; o orçamento definido é {orcamento}"]})
    ok = all(l["status"] != "FALHA" for l in linhas) and bool(linhas)
    return linhas, resumo_sites, ok


def relatorio_validacao(linhas, resumo_sites, ok, destino: Path) -> None:
    md = ["# Validação das capturas", "", f"Gerado em {datetime.now().astimezone().isoformat(timespec='seconds')}", ""]
    print("\n=== VALIDAÇÃO DAS CAPTURAS ===")
    for l in linhas:
        marca = {"OK": "OK   ", "AVISO": "AVISO", "FALHA": "FALHA"}[l["status"]]
        print(f"  [{marca}] {l['site']:<4} {l['estado']:<22} " + " | ".join(l["notas"]))
        md.append(f"- **{l['status']}** `{l['site']}/{l['estado']}`: " + "; ".join(l["notas"]))
    for sid, r in resumo_sites.items():
        print(f"  {sid}: {r['validos']} estado(s) válido(s) de {r.get('esperados', '?')} | coletado em {r.get('coletado_em')}")
        md.append(f"\n{sid}: {r['validos']} válido(s) de {r.get('esperados', '?')}; pasta `{r['pasta']}`")
    print("  RESULTADO:", "APROVADO" if ok else "REPROVADO")
    md.append(f"\n**Resultado: {'APROVADO' if ok else 'REPROVADO'}**")
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "validacao_capturas.md").write_text("\n".join(md) + "\n", encoding="utf-8")


@contextlib.contextmanager
def etapa(manifesto: dict, nome: str):
    print(f"\n>>> {nome}")
    t0 = time.time()
    reg = {"etapa": nome, "inicio": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        yield
        reg["status"] = "ok"
    except BaseException as e:
        reg["status"] = f"erro: {type(e).__name__}: {str(e)[:200]}"
        raise
    finally:
        reg["duracao_s"] = round(time.time() - t0, 1)
        manifesto["etapas"].append(reg)


def capturar(sites: str, ids: list[str]) -> None:
    CAP.main(str((RAIZ / sites).resolve()), ids)


def estimar(coletas: Path, ids: list[str], runs: int) -> dict:
    n_estados = n_fatias = 0
    fluxos = 0
    for sid in ids:
        meta = json.loads((_pasta_mais_recente(coletas, sid) / "meta.json").read_text(encoding="utf-8"))
        validos = [e for e in meta["estados"] if not any(a.startswith(IMPEDITIVOS) for a in e.get("alertas", []))]
        n_estados += len(validos); n_fatias += sum(len(e["fatias"]) for e in validos); fluxos += 1
    return {"fluxos": fluxos, "estados": n_estados, "fatias": n_fatias,
            "chamadas_inspecao": 2 * runs * n_estados,
            "chamadas_juiz": len(CONFIGS) * runs * fluxos,
            "imagens_enviadas_inspecao": 2 * runs * n_fatias}


def _checar_chave() -> None:
    env = RAIZ / ".env"
    txt = env.read_text(encoding="utf-8", errors="ignore") if env.exists() else ""
    linha = next((l for l in txt.splitlines() if l.startswith("ANTHROPIC_API_KEY=")), "")
    if len(linha.split("=", 1)[-1].strip()) < 10:
        raise SystemExit("ANTHROPIC_API_KEY ausente ou vazia no .env.")


def _hash_arquivo(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _ids(sites_json: Path, ids: list[str]) -> list[str]:
    todos = [s["id"] for s in json.loads(sites_json.read_text(encoding="utf-8"))]
    return [i for i in todos if not ids or i in ids]


def cmd_validar(a: argparse.Namespace) -> None:
    p = aplicar_versao(a.versao, a.sites)
    ids = _ids(MN.SITES_JSON, a.ids)
    if not a.sem_captura:
        capturar(a.sites, ids)
    linhas, resumo, ok = validar_capturas(MN.SITES_JSON, p["coletas"], ids, a.orcamento)
    relatorio_validacao(linhas, resumo, ok, p["coletas"])
    if not ok:
        raise SystemExit(1)


def cmd_oficial(a: argparse.Namespace) -> None:
    p = aplicar_versao(a.versao, a.sites)
    ids = _ids(MN.SITES_JSON, a.ids)
    if list((p["output"] / "runs").glob("*/*/run_*.json")) and not a.continuar:
        raise SystemExit(f"{p['output']} já contém execuções. Use --continuar para retomar a mesma coleta, "
                         f"ou renomeie a pasta para iniciar uma execução nova.")
    _checar_chave()
    manifesto = {"versao": a.versao, "inicio": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "argumentos": vars(a), "python": sys.version.split()[0], "sistema": platform.platform(),
                 "sites_json": str(MN.SITES_JSON.name), "sites_json_sha256": _hash_arquivo(MN.SITES_JSON), "etapas": []}
    p["resultados"].mkdir(parents=True, exist_ok=True)
    try:
        if not a.sem_captura:
            with etapa(manifesto, "1/7 captura congelada"):
                capturar(a.sites, ids)
        with etapa(manifesto, "2/7 validação das capturas"):
            linhas, resumo, ok = validar_capturas(MN.SITES_JSON, p["coletas"], ids, a.orcamento)
            relatorio_validacao(linhas, resumo, ok, p["coletas"])
            manifesto["capturas"] = resumo
            if not ok:
                raise SystemExit("Capturas reprovadas: corrija e rode 'validar' antes do teste oficial. Nenhuma chamada à API foi feita.")
        with etapa(manifesto, "3/7 estimativa e confirmação"):
            est = estimar(p["coletas"], ids, a.runs)
            manifesto["estimativa"] = est
            print(f"  {est['fluxos']} fluxos, {est['estados']} estados, {est['fatias']} fatias.\n"
                  f"  Chamadas de inspeção (híbrido + LLM, {a.runs} execuções): {est['chamadas_inspecao']}\n"
                  f"  Chamadas do juiz (3 configurações x {a.runs} execuções x {est['fluxos']} fluxos): {est['chamadas_juiz']} "
                  f"(não executadas aqui; rodam depois, no comando 'juiz')")
            if not a.sim and input("  Digite SIM para iniciar as etapas com custo de API: ").strip() != "SIM":
                raise SystemExit("Cancelado antes de qualquer chamada à API.")
        with etapa(manifesto, "4/7 inspeção (3 configurações x execuções)"):
            MN.cmd_externa(argparse.Namespace(runs=a.runs))
    finally:
        manifesto["fim"] = datetime.now().astimezone().isoformat(timespec="seconds")
        (p["resultados"] / "manifesto_pipeline.json").write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nManifesto: {p['resultados'] / 'manifesto_pipeline.json'}")
    print("\nInspeção concluída. O juiz LLM NÃO foi executado. Para casar os achados com o gabarito, gerar as análises "
          "e a confiabilidade, rode:\n"
          f"  python pipeline.py juiz --sites {a.sites} --versao {a.versao}")


def cmd_juiz(a: argparse.Namespace) -> None:
    p = aplicar_versao(a.versao, a.sites)
    ids = _ids(MN.SITES_JSON, a.ids)
    arq = p["resultados"] / "manifesto_pipeline.json"
    manifesto = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {"etapas": []}
    manifesto.setdefault("etapas", [])
    manifesto["juiz_inicio"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _checar_chave()
    n_runs = len(list((p["output"] / "runs").glob("*/*/run_*.json")))
    n_cache = len(list((p["output"] / "matching").glob("*/*/run_*.json")))
    print(f"  {n_runs} execuções gravadas; {n_cache} casamentos já em cache. "
          f"Chamadas do juiz pendentes: até {max(n_runs - n_cache, 0)}.")
    if not a.sim and input("  Digite SIM para iniciar o juiz LLM: ").strip() != "SIM":
        raise SystemExit("Cancelado antes de qualquer chamada à API.")
    try:
        with etapa(manifesto, "5/7 (juiz) casamento por juiz LLM"):
            MN.cmd_casamento(argparse.Namespace(runs=0))
        with etapa(manifesto, "6/7 análises e planilha consolidada"):
            runpy.run_path(str(RAIZ / "analisar_resultados.py"), run_name="__main__")
            runpy.run_path(str(RAIZ / "consolidar_resultados.py"), run_name="__main__")
        with etapa(manifesto, "7/7 confiabilidade, amostra de auditoria e relatórios"):
            etapa_confiabilidade(p, ids)
            etapa_relatorios(p, ids, pdf=False)
    finally:
        manifesto["juiz_fim"] = datetime.now().astimezone().isoformat(timespec="seconds")
        p["resultados"].mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    an = json.loads((p["resultados"] / "analises.json").read_text(encoding="utf-8"))
    print("\n=== MEDIANAS DAS EXECUÇÕES (p12 + p13) ===")
    for cfg in CONFIGS:
        m = an["metricas"][cfg]["mediana"]
        print(f"  {cfg:<8} revocação pond. {m['recall_ponderado']:.3f} | precisão pond. {m['precisao_ponderada']:.3f} | F1 pond. {m['f1_ponderado']:.3f}")


def _fluxos_capturados(p: dict[str, Path], ids: list[str]):
    from src.frozen import load_flow
    return {i: load_flow(i, p["coletas"], MN.SITES_JSON) for i in ids}


def etapa_confiabilidade(p: dict[str, Path], ids: list[str]) -> None:
    from src.evaluation import ancoragem, auditoria, estabilidade
    fluxos = _fluxos_capturados(p, ids)
    htmls = {i: {e.ordem: e.html for e in f.estados} for i, f in fluxos.items()}
    pngs = {i: {e.ordem: (str(e.fatias[0].with_name(e.fatias[0].name.replace("_fatia_1", "_completo"))) if e.fatias else "")
                for e in f.estados} for i, f in fluxos.items()}
    dest = p["resultados"]
    ancoragem.verificar_tudo(p["output"], htmls, ("hibrido", "llm"), dest)
    estabilidade.estabilidade_tudo(p["output"], ids, CONFIGS, destino=dest)
    textos = {i: {o: ancoragem.texto_da_pagina(h) for o, h in hs.items()} for i, hs in htmls.items()}
    itens, totais = auditoria.populacao(RAIZ, p["output"], ids, textos, pngs)
    if itens:
        arq = auditoria.gravar(auditoria.sortear(itens, n=172, igualitaria=True), totais, dest / "auditoria")
        print(f"  amostra de auditoria: {arq['planilha']}")
    else:
        print("  nenhum achado do LLM sem par; amostra de auditoria não gerada.")


def etapa_relatorios(p: dict[str, Path], ids: list[str], pdf: bool) -> None:
    from src import relatorio_html
    fluxos = _fluxos_capturados(p, ids)
    saidas = relatorio_html.gerar_todos(p["output"], p["resultados"] / "relatorios",
                                        lambda fid: fluxos[fid].pasta if fid in fluxos else None, pdf=pdf)
    print(f"  {len(saidas)} arquivos em {p['resultados'] / 'relatorios'}")


def cmd_confiabilidade(a: argparse.Namespace) -> None:
    p = aplicar_versao(a.versao, a.sites)
    etapa_confiabilidade(p, _ids(MN.SITES_JSON, a.ids))


def cmd_relatorios(a: argparse.Namespace) -> None:
    p = aplicar_versao(a.versao, a.sites)
    etapa_relatorios(p, _ids(MN.SITES_JSON, a.ids), a.pdf)


def cmd_auditoria_calcular(a: argparse.Namespace) -> None:
    from src.evaluation import auditoria
    d = aplicar_versao(a.versao, a.sites)["resultados"] / "auditoria"
    res = auditoria.calcular(d / "auditoria_amostra.xlsx", d / "auditoria_chave.csv", d / "auditoria_populacao.json")
    (d / "auditoria_resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_explorar(a: argparse.Namespace) -> None:
    from src.exploracao import explorar
    p = aplicar_versao(a.versao, a.sites)
    sites = {x["id"]: x for x in json.loads(MN.SITES_JSON.read_text(encoding="utf-8"))}
    dest = RAIZ / f"exploracao_{a.versao}"
    for i in _ids(MN.SITES_JSON, a.ids):
        print(f"\n>>> explorando {i}")
        r = explorar(sites[i], dest, limite_segundos=a.limite, max_estados=a.max_estados, max_profundidade=a.profundidade)
        print(f"  parada: {r['parada']} | {len(r['estados'])} estados | {r['duracao_s']} s | roteiro: {dest / ('roteiro_' + i + '.json')}")
    juntos = [x for f in sorted(dest.glob("roteiro_*.json")) for x in json.loads(f.read_text(encoding="utf-8"))]
    alvo = RAIZ / f"sites_{a.versao}_explorado.json"
    alvo.write_text(json.dumps(juntos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRoteiro unificado: {alvo.name} ({sum(len(x['estados']) for x in juntos)} estados). "
          f"Use --sites {alvo.name} em validar/oficial (sem --orcamento, ou com o total de estados).")


def cmd_curar(a: argparse.Namespace) -> None:
    from src.curadoria import curar
    aplicar_versao(a.versao, a.sites)
    dest = RAIZ / f"exploracao_{a.versao}"
    for i in _ids(MN.SITES_JSON, a.ids):
        r = curar(dest / f"roteiro_{i}.json", dest, a.limiar, a.max_estados, dest / f"exploracao_{i}.json",
                  limiar_visual=a.limiar_visual, visual=not a.so_texto)
        print(f"  {i}: {r['antes']} -> {r['depois']} estados (limiar {a.limiar})")
    saidas = []
    for i in _ids(MN.SITES_JSON, None):
        f = dest / f"curado_{i}.json"
        if f.exists():
            saidas += json.loads(f.read_text(encoding="utf-8"))
    alvo = RAIZ / f"sites_{a.versao}_curado.json"
    alvo.write_text(json.dumps(saidas, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRoteiro curado: {alvo.name} ({sum(len(x['estados']) for x in saidas)} estados)")


def cmd_concordancia(a: argparse.Namespace) -> None:
    from src.evaluation import matching as M
    p = aplicar_versao(a.versao, a.sites)
    _checar_chave()
    n = len(list((p["output"] / "runs").glob("*/*/run_*.json")))
    print(f"  Juiz principal: {M.modelo_juiz_padrao()} | juiz alternativo: {a.modelo} | até {n} chamadas")
    if not a.sim and input("  Digite SIM para iniciar: ").strip() != "SIM":
        raise SystemExit("Cancelado antes de qualquer chamada à API.")
    r = M.concordancia_juizes(RAIZ, p["output"], a.modelo)
    destino = p["resultados"] / f"concordancia_juizes_{a.modelo}.json"
    destino.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"\nGravado em {destino}")


def cmd_amostra_juiz(a: argparse.Namespace) -> None:
    p = aplicar_versao(a.versao, a.sites)
    n_runs = len(list((p["output"] / "runs").glob("*/*/run_*.json")))
    n_cache = len(list((p["output"] / "matching").glob("*/*/run_*.json")))
    if n_cache < n_runs:
        raise SystemExit(f"Cache do juiz incompleto ({n_cache} de {n_runs}); abortado para não chamar a API. "
                         "Confira JUIZ_MODEL no .env (o cache depende do modelo do juiz).")
    from src.evaluation import matching as M
    print(f"  {n_cache} casamentos em cache (modelo do juiz: {M.modelo_juiz_padrao()}); sem chamadas à API.")
    MN.cmd_casamento(argparse.Namespace(runs=0))


def cmd_conferir_juiz(a: argparse.Namespace) -> None:
    aplicar_versao(a.versao, a.sites)
    MN.cmd_conferir(argparse.Namespace(planilha=a.planilha))


def cmd_status(a: argparse.Namespace) -> None:
    p = caminhos(a.versao)
    print(f"Versão {a.versao}")
    for k, v in p.items():
        print(f"  {k}: {v} ({'existe' if v.exists() else 'não existe'})")
    for cfg in CONFIGS:
        n = len(list((p["output"] / "runs" / cfg).glob("*/run_*.json")))
        m = len(list((p["output"] / "matching" / cfg).glob("*/run_*.json")))
        print(f"  {cfg:<8} execuções: {n} | casamentos: {m}")
    print("  analises.json:", "sim" if (p["resultados"] / "analises.json").exists() else "não")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome, fn in (("validar", cmd_validar), ("oficial", cmd_oficial)):
        s = sub.add_parser(nome)
        s.add_argument("ids", nargs="*")
        s.add_argument("--sites", default="sites_v2.json")
        s.add_argument("--versao", default="v2")
        s.add_argument("--orcamento", type=int, default=None, help="número exigido de estados válidos por site")
        s.add_argument("--sem-captura", action="store_true", help="usa as capturas já gravadas")
        if nome == "oficial":
            s.add_argument("--runs", type=int, default=3)
            s.add_argument("--sim", action="store_true", help="não pede confirmação antes das etapas pagas")
            s.add_argument("--continuar", action="store_true", help="retoma uma execução em output_<versao> existente")
        s.set_defaults(func=fn)
    s = sub.add_parser("juiz"); s.add_argument("ids", nargs="*")
    s.add_argument("--sites", default="sites_v2.json"); s.add_argument("--versao", default="v2")
    s.add_argument("--sim", action="store_true", help="não pede confirmação antes do juiz")
    s.set_defaults(func=cmd_juiz)
    for nome, fn in (("confiabilidade", cmd_confiabilidade), ("relatorios", cmd_relatorios), ("auditoria-calcular", cmd_auditoria_calcular)):
        s = sub.add_parser(nome); s.add_argument("ids", nargs="*")
        s.add_argument("--sites", default="sites_v2.json"); s.add_argument("--versao", default="v2")
        if nome == "relatorios":
            s.add_argument("--pdf", action="store_true", help="gera também PDF (requer Chromium do Playwright)")
        s.set_defaults(func=fn)
    s = sub.add_parser("explorar"); s.add_argument("ids", nargs="*")
    s.add_argument("--sites", default="sites_v2.json"); s.add_argument("--versao", default="v2")
    s.add_argument("--limite", type=int, default=None, help="teto de tempo em segundos (padrão 7200)")
    s.add_argument("--max-estados", type=int, default=None); s.add_argument("--profundidade", type=int, default=None)
    s.set_defaults(func=cmd_explorar)
    s = sub.add_parser("curar"); s.add_argument("ids", nargs="*")
    s.add_argument("--sites", default="sites_v2.json"); s.add_argument("--versao", default="v2")
    s.add_argument("--limiar", type=float, default=0.9, help="similaridade (Jaccard) a partir da qual o estado é considerado repetido")
    s.add_argument("--max-estados", type=int, default=None)
    s.add_argument("--limiar-visual", type=float, default=0.005, help="fração de pixels alterados abaixo da qual a imagem é considerada igual")
    s.add_argument("--so-texto", action="store_true", help="não reproduz os estados para comparar imagens (mais rápido; ignora mudanças só visuais)")
    s.set_defaults(func=cmd_curar)
    s = sub.add_parser("concordancia"); s.add_argument("--modelo", required=True, help="modelo do segundo juiz, ex.: claude-sonnet-5-5")
    s.add_argument("--sites", default="sites_v2.json"); s.add_argument("--versao", default="v2")
    s.add_argument("--sim", action="store_true"); s.set_defaults(func=cmd_concordancia)
    s = sub.add_parser("amostra-juiz"); s.add_argument("--sites", default="sites_v2.json"); s.add_argument("--versao", default="v2")
    s.set_defaults(func=cmd_amostra_juiz)
    s = sub.add_parser("conferir-juiz"); s.add_argument("--sites", default="sites_v2.json"); s.add_argument("--versao", default="v2")
    s.add_argument("--planilha", default=None); s.set_defaults(func=cmd_conferir_juiz)
    s = sub.add_parser("status"); s.add_argument("--versao", default="v2"); s.set_defaults(func=cmd_status)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
