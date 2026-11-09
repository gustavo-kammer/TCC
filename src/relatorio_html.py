from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

from .evaluation import ancoragem

ROTULO_SEV = {4: "catástrofe", 3: "maior", 2: "menor", 1: "cosmético", 0: "não é problema"}
ROTULO_FONTE = {"motor_de_regras": "regras", "llm": "LLM"}
ROTULO_ANC = {"ancorado": "citação confirmada na página", "nao_ancorado": "citação não encontrada na página",
              "visual": "evidência visual", "sem_citacao": "sem citação", "sem_campo": ""}
LARGURA_IMG = 900


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _heur(h: str) -> str:
    cod, _, resto = h.partition("_")
    return f"{cod} {resto.replace('_', ' ')}"


def _img_b64(png: Path) -> str:
    from PIL import Image
    with Image.open(png) as im:
        im = im.convert("RGB")
        if im.width > LARGURA_IMG:
            im = im.resize((LARGURA_IMG, round(im.height * LARGURA_IMG / im.width)))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _captura(pasta: Path | None, ordem: int) -> Path | None:
    if not pasta or not pasta.exists():
        return None
    achados = sorted(pasta.glob(f"estado_{ordem:02d}_*_completo.png"))
    return achados[0] if achados else None


def _html_estado(est: dict, pasta: Path | None, embutir: bool) -> str:
    rel = est["relatorio"]
    texto = ""
    if pasta:
        h = sorted(pasta.glob(f"estado_{est['ordem']:02d}_*.html"))
        texto = ancoragem.texto_da_pagina(h[0]) if h else ""
    cap = _captura(pasta, est["ordem"]) if embutir else None
    img = f'<img class="cap" alt="captura do estado" src="{_img_b64(cap)}">' if cap else ""
    cards = []
    for v in rel["violations"]:
        sev = v["severity_effective"]; fonte = ROTULO_FONTE.get(v["source"], v["source"])
        ev = v.get("evidence"); badge = ""
        if v["source"] == "llm":
            st = ancoragem.classificar(ev, texto) if texto else "sem_campo"
            if ROTULO_ANC.get(st):
                badge = f'<span class="chip anc-{st}">{_esc(ROTULO_ANC[st])}</span>'
        evid = ""
        if ev:
            alvo = ev.get("quote") or ev.get("region")
            evid = f'<p class="ev"><b>Evidência ({_esc(ev.get("kind"))}):</b> {_esc(alvo)}</p>'
        rev = (f'<p class="rev"><b>Severidade revisada de {v["severity_original"]} para {v["severity_revised"]}:</b> '
               f'{_esc(v["revision_rationale"])}</p>') if v.get("severity_revised") is not None and v.get("revision_rationale") else ""
        cards.append(
            f'<article class="achado" data-sev="{sev}" data-fonte="{_esc(v["source"])}" data-heur="{_esc(v["heuristic"][:3])}">'
            f'<header><span class="chip sev{sev}">{sev} {ROTULO_SEV.get(sev, "")}</span>'
            f'<span class="chip fonte-{_esc(v["source"])}">{fonte}</span>{badge}'
            f'<span class="rank">#{v["rank"]} · índice {v["criticality_index"]}</span></header>'
            f'<h4>{_esc(_heur(v["heuristic"]))}</h4>'
            f'<p class="loc"><b>Local:</b> <code>{_esc(v["location"])}</code></p>'
            f'<p>{_esc(v["description"])}</p><p class="just"><b>Justificativa:</b> {_esc(v["justification"])}</p>'
            f'{evid}{rev}<p class="rec"><b>Recomendação:</b> {_esc(v["recommendation"])}</p></article>')
    corpo = "".join(cards) or "<p>Nenhum achado neste estado.</p>"
    return (f'<section class="estado"><h3>Estado {est["ordem"]}: {_esc(est["nome"])} '
            f'<small>({rel["total_violations"]} achados)</small></h3>'
            f'<p class="url">{_esc(est.get("url_no_momento") or rel.get("url"))}</p>{img}{corpo}</section>')


CSS = """
:root{--bg:#fff;--fg:#1c2330;--mut:#5b6575;--bd:#d9dee7;--card:#f7f9fc;--acc:#1f3864}
@media(prefers-color-scheme:dark){:root{--bg:#12161d;--fg:#e6eaf1;--mut:#9aa5b5;--bd:#2c3442;--card:#1a2029;--acc:#8fb0ee}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.5rem;margin:.2em 0;color:var(--acc)}h3{margin:1.6em 0 .3em;color:var(--acc)}h4{margin:.3em 0}
.sub{color:var(--mut);margin:0 0 1em}.aviso{border-left:4px solid var(--acc);background:var(--card);padding:10px 14px;margin:14px 0;border-radius:4px}
.resumo{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:10px 12px}.kpi b{font-size:1.5rem;display:block}.kpi span{color:var(--mut);font-size:.85rem}
.barras{margin:10px 0}.linha{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:.85rem}.linha .nome{width:230px;color:var(--mut)}
.linha .bar{height:12px;background:var(--acc);border-radius:3px;min-width:2px}.filtros{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--bd);z-index:2;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.filtros label{font-size:.85rem;color:var(--mut)}select{font:inherit;padding:3px 6px;background:var(--card);color:var(--fg);border:1px solid var(--bd);border-radius:4px}
.estado .url{color:var(--mut);font-size:.8rem;word-break:break-all;margin:0 0 8px}.cap{max-width:100%;border:1px solid var(--bd);border-radius:4px;margin:6px 0 12px}
.achado{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:10px 14px;margin:10px 0;break-inside:avoid}.achado header{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.achado p{margin:.35em 0}.rank{margin-left:auto;color:var(--mut);font-size:.8rem}code{font-size:.85em;word-break:break-all}
.chip{font-size:.75rem;padding:1px 8px;border-radius:10px;border:1px solid var(--bd);white-space:nowrap}
.sev4{background:#b3261e;color:#fff;border-color:#b3261e}.sev3{background:#e8710a;color:#fff;border-color:#e8710a}.sev2{background:#f2c94c;color:#222;border-color:#f2c94c}.sev1{background:#9bb7d4;color:#222}.sev0{background:var(--card)}
.fonte-llm{border-style:dashed}.anc-ancorado{color:#1e7b34;border-color:#1e7b34}.anc-nao_ancorado{color:#b3261e;border-color:#b3261e}
.oculto{display:none}@media print{.filtros{display:none}.achado{background:#fff}.estado{break-before:auto}body{font-size:12px}}
"""
JS = """
const f=()=>{const s=document.getElementById('fs').value,o=document.getElementById('fo').value;
document.querySelectorAll('.achado').forEach(a=>{const ok=(s==='todas'||a.dataset.sev>=s)&&(o==='todas'||a.dataset.fonte===o);a.classList.toggle('oculto',!ok)})};
document.getElementById('fs').onchange=f;document.getElementById('fo').onchange=f;
"""


def gerar_html(run_json: Path, destino: Path, pasta_capturas: Path | None = None, embutir_imagens: bool = True) -> Path:
    run = json.loads(Path(run_json).read_text(encoding="utf-8"))
    md = run["metadata"]
    todos = [v for e in run["estados"] for v in e["relatorio"]["violations"]]
    por_sev = {s: sum(v["severity_effective"] == s for v in todos) for s in (4, 3, 2, 1)}
    por_fonte = {k: sum(v["source"] == k for v in todos) for k in ("motor_de_regras", "llm")}
    heur: dict[str, int] = {}
    for v in todos:
        heur[v["heuristic"][:3]] = heur.get(v["heuristic"][:3], 0) + 1
    nomes_h = {v["heuristic"][:3]: _heur(v["heuristic"]) for v in todos}
    maximo = max(heur.values(), default=1)
    barras = "".join(f'<div class="linha"><span class="nome">{_esc(nomes_h[k])}</span><span class="bar" style="width:{220 * n / maximo:.0f}px"></span>{n}</div>'
                     for k, n in sorted(heur.items()))
    kpis = "".join(f'<div class="kpi"><b>{n}</b><span>{_esc(t)}</span></div>' for t, n in
                   [("achados", len(todos)), ("catástrofe (4)", por_sev[4]), ("maior (3)", por_sev[3]), ("menor (2)", por_sev[2]),
                    ("cosmético (1)", por_sev[1]), ("regras", por_fonte["motor_de_regras"]), ("LLM", por_fonte["llm"])])
    estados = "".join(_html_estado(e, pasta_capturas, embutir_imagens) for e in run["estados"])
    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório de inspeção {_esc(run['flow_id'])}</title><style>{CSS}</style></head><body><main>
<h1>Relatório de inspeção heurística: {_esc(run['flow_id'])}</h1>
<p class="sub">{_esc(run.get('site'))} · configuração {_esc(md.get('configuracao'))} · execução {_esc(md.get('run_id'))} · modelo {_esc(md.get('modelo'))} · {_esc(md.get('data_hora'))}</p>
<div class="aviso">Os achados de origem <b>LLM</b> são hipóteses geradas por modelo de linguagem e devem ser conferidos por um avaliador antes de qualquer decisão. Os achados de <b>regras</b> são determinísticos. A etiqueta de citação indica apenas se o trecho citado pelo modelo existe na página capturada; não substitui a validação humana.</div>
<div class="resumo">{kpis}</div><h3>Achados por heurística</h3><div class="barras">{barras}</div>
<div class="filtros"><label>Severidade mínima <select id="fs"><option value="todas">todas</option><option value="2">2 menor</option><option value="3">3 maior</option><option value="4">4 catástrofe</option></select></label>
<label>Origem <select id="fo"><option value="todas">todas</option><option value="motor_de_regras">regras</option><option value="llm">LLM</option></select></label></div>
{estados}</main><script>{JS}</script></body></html>"""
    destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(doc, encoding="utf-8")
    return destino


def para_pdf(html_path: Path, pdf_path: Path) -> Path | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page()
            pg.goto(Path(html_path).resolve().as_uri()); pg.emulate_media(media="print")
            pg.pdf(path=str(pdf_path), format="A4", print_background=True, margin={"top": "14mm", "bottom": "14mm", "left": "10mm", "right": "10mm"})
            b.close()
        return Path(pdf_path)
    except Exception as e:
        print(f"[aviso] PDF não gerado: {e}")
        return None


def gerar_todos(output: Path, destino: Path, pasta_capturas_de: callable = lambda fid: None, pdf: bool = False) -> list[Path]:
    saidas = []
    for rj in sorted(Path(output).glob("runs/*/*/run_0.json")):
        cfg, fid = rj.parent.parent.name, rj.parent.name
        h = gerar_html(rj, Path(destino) / cfg / f"{fid}.html", pasta_capturas_de(fid))
        saidas.append(h)
        if pdf:
            para_pdf(h, h.with_suffix(".pdf"))
    links = "".join(f'<li><a href="{_esc(p.relative_to(destino).as_posix())}">{_esc(p.parent.name)} / {_esc(p.stem)}</a></li>' for p in saidas)
    ind = Path(destino) / "index.html"
    ind.write_text(f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Relatórios</title><style>{CSS}</style><body><main><h1>Relatórios de inspeção</h1><ul>{links}</ul></main></body></html>', encoding="utf-8")
    return saidas + [ind]
