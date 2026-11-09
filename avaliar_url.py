import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import capturar_paginas as CAP
import main as MN
import pipeline as PL
from src import relatorio_html
from src.curadoria import curar
from src.exploracao import explorar
from src.frozen import load_flow
from src.orchestrator import extract_flow, run_flow

RAIZ = Path(__file__).resolve().parent
BASE = RAIZ / "analises_url"
TAREFA_PADRAO = "Explorar livremente as seções públicas do sistema."


def _slug(url: str) -> str:
    p = urlparse(url)
    bruto = f"{p.netloc}{p.path}".strip("/")
    return re.sub(r"[^\w]+", "_", bruto).strip("_").lower()[:50] or "pagina"


def _normalizar(url: str) -> str:
    url = url.strip()
    if not re.match(r"^(https?|file)://", url):
        url = "https://" + url
    return url


def _preparar(pasta: Path) -> dict[str, Path]:
    p = {"coletas": pasta / "coletas", "output": pasta / "output",
         "resultados": pasta / "resultados", "exploracao": pasta / "exploracao",
         "sites": pasta / "sites.json"}
    for k, v in p.items():
        if k != "sites":
            v.mkdir(parents=True, exist_ok=True)
    MN.SITES_JSON = p["sites"]
    MN.COLETAS, MN.OUTPUT, MN.RESULTADOS = p["coletas"], p["output"], p["resultados"]
    CAP.RAIZ_SAIDA = p["coletas"]
    return p


def _perguntar(texto: str, padrao: str = "") -> str:
    try:
        resposta = input(texto).strip()
    except EOFError:
        resposta = ""
    return resposta or padrao


def _confirmar(texto: str) -> bool:
    return _perguntar(texto + " [s/N] ").lower() in ("s", "sim")


def _preparar_estados(site: dict, p: dict[str, Path], a: argparse.Namespace) -> dict:
    print("\n[1/5] Exploração determinística em largura")
    reg = explorar(site, p["exploracao"], limite_segundos=a.limite,
                   max_estados=a.max_estados, max_profundidade=a.profundidade)
    print(f"  {len(reg['estados'])} estados, parada: {reg['parada']}")
    print("\n[2/5] Curadoria dos estados")
    r = curar(p["exploracao"] / f"roteiro_{site['id']}.json", p["exploracao"], a.limiar,
              None, p["exploracao"] / f"exploracao_{site['id']}.json",
              limiar_visual=a.limiar_visual, visual=not a.so_texto)
    print(f"  {r['antes']} -> {r['depois']} estados")
    curado = json.loads(Path(r["arquivo"]).read_text(encoding="utf-8"))
    p["sites"].write_text(json.dumps(curado, ensure_ascii=False, indent=1), encoding="utf-8")
    return curado[0]


def _capturar_e_validar(site: dict, p: dict[str, Path]) -> None:
    print("\n[3/5] Captura congelada")
    CAP.main(str(p["sites"]), [site["id"]])
    print("\n[4/5] Validação das capturas")
    linhas, resumo, ok = PL.validar_capturas(p["sites"], p["coletas"], [site["id"]], None)
    PL.relatorio_validacao(linhas, resumo, ok, p["coletas"])
    if not ok:
        raise SystemExit("Capturas reprovadas na validação. Veja o relatório em "
                         f"{p['coletas']}. Nenhuma inspeção foi executada.")


def _relatorios(site_id: str, p: dict[str, Path], flow) -> Path:
    relatorio_html.gerar_todos(p["output"], p["resultados"] / "relatorios",
                               lambda fid: flow.pasta if fid == site_id else None, pdf=False)
    return p["resultados"] / "relatorios" / "index.html"


def _inspecionar(flow, config: str, runs: int, p: dict[str, Path], extracoes) -> None:
    run_flow(flow, config, runs=runs, out_dir=p["output"], extractions=extracoes)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Fluxo guiado: URL, exploração, curadoria, captura, regras, relatório e análise opcional com LLM.")
    ap.add_argument("url", nargs="?", help="endereço a avaliar (se omitido, será solicitado)")
    ap.add_argument("--tarefa", default=TAREFA_PADRAO, help="tarefa informada ao modelo de linguagem")
    ap.add_argument("--limite", type=int, default=900, help="teto de tempo da exploração, em segundos (o experimento usou 7200)")
    ap.add_argument("--espera", type=int, default=None, help="espera, em milissegundos, após abrir a página antes de explorar (padrão do experimento: 3000); aumentar em páginas que carregam devagar")
    ap.add_argument("--cookies", default="", help="seletor CSS do botão do aviso de cookies, clicado ao abrir a página (ex.: \"button.cookie-btn\")")
    ap.add_argument("--fechar", action="append", default=[], help="seletor CSS de janela ou aviso a fechar em cada estado; pode ser repetido")
    ap.add_argument("--max-estados", type=int, default=None, help="máximo de estados explorados")
    ap.add_argument("--profundidade", type=int, default=None, help="profundidade máxima da exploração")
    ap.add_argument("--limiar", type=float, default=0.9, help="similaridade de texto da curadoria")
    ap.add_argument("--limiar-visual", type=float, default=0.005, help="fração de pixels da curadoria visual")
    ap.add_argument("--so-texto", action="store_true", help="curadoria apenas por texto (mais rápida)")
    ap.add_argument("--runs", type=int, default=3, help="execuções da análise com o modelo de linguagem")
    ap.add_argument("--llm", action="store_true", help="executa também a análise híbrida, sem perguntar")
    a = ap.parse_args(argv)

    url = _normalizar(a.url or _perguntar("URL a avaliar: "))
    if url in ("https://", ""):
        raise SystemExit("URL não informada.")
    slug = _slug(url)
    pasta = BASE / f"{slug}_{datetime.now():%Y%m%d_%H%M%S}"
    p = _preparar(pasta)
    site = {"id": slug, "site": urlparse(url).netloc or url, "tarefa": a.tarefa, "url": url,
            "cookies": a.cookies, "locale": "pt-BR", "exploracao": {}}
    if a.fechar:
        site["fechar"] = a.fechar
    if a.espera:
        site["exploracao"]["inicio"] = [{"tipo": "ir", "url": url}, {"tipo": "esperar", "ms": a.espera}]

    print(f"Alvo: {url}\nSaída: {pasta}")
    site = _preparar_estados(site, p, a)
    _capturar_e_validar(site, p)

    flow = load_flow(site["id"], p["coletas"], p["sites"])
    print("\n[5/5] Inspeção determinística (motor de regras, sem API)")
    extracoes = extract_flow(flow)
    _inspecionar(flow, "regras", 1, p, extracoes)
    indice = _relatorios(site["id"], p, flow)
    print(f"\nRelatório das regras: {indice}")

    if a.llm or _confirmar("\nExecutar também a análise com o modelo de linguagem (configuração híbrida)? Gera custo de API."):
        PL._checar_chave()
        est = PL.estimar(p["coletas"], [site["id"]], a.runs)
        print(f"  {est['estados']} estados, {est['fatias']} fatias, "
              f"{est['chamadas_inspecao']} chamadas de inspeção ({a.runs} execuções, híbrido e LLM).")
        print("  Será executada apenas a configuração híbrida: "
              f"{est['chamadas_inspecao'] // 2} chamadas.")
        if not a.llm and not _confirmar("  Confirmar?"):
            raise SystemExit("Análise com o modelo de linguagem cancelada.")
        _inspecionar(flow, "hibrido", a.runs, p, extracoes)
        indice = _relatorios(site["id"], p, flow)
        print(f"\nRelatórios (regras e híbrido): {indice}")


if __name__ == "__main__":
    main(sys.argv[1:])
