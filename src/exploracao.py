from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

EXCLUIR_TEXTO = re.compile(
    r"\b(sair|logout|encerrar sess|excluir|apagar|remover|deletar|enviar|submeter|salvar|cadastrar-se|"
    r"login|entrar|baixar|download|imprimir|print|delete|remove|sign ?out|log ?out|submit)\b", re.I)
MAX_CANDIDATOS = 60
ESPERA_APOS_CLIQUE_MS = 800
TIMEOUT_CLIQUE_MS = 8000
LIMIAR_VISUAL_NOVO = 0.02

JS_CANDIDATOS = r"""
() => {
  const cssPath = el => {
    const parts = []; let e = el;
    while (e && e.nodeType === 1 && e !== document.body) {
      if (e.id && !/(\d{3,}|react-|^:r|[0-9a-f]{8,})/i.test(e.id) && document.querySelectorAll('#' + CSS.escape(e.id)).length === 1) { parts.unshift('#' + CSS.escape(e.id)); return parts.join(' > '); }
      let i = 1, s = e; while ((s = s.previousElementSibling)) if (s.tagName === e.tagName) i++;
      parts.unshift(e.tagName.toLowerCase() + ':nth-of-type(' + i + ')'); e = e.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  };
  const visivel = el => {
    const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const base = 'button, a[href], [role=button], [role=tab], [role=menuitem], [role=switch], [onclick], summary, select, input[type=checkbox], input[type=radio]';
  const vistos = new Set(), lista = [];
  const add = el => {
    if (vistos.has(el) || !visivel(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
    vistos.add(el);
    lista.push({sel: cssPath(el), tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase(),
      texto: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 80),
      href: el.getAttribute('href') || '', target: el.getAttribute('target') || '', download: el.hasAttribute('download'),
      emForm: !!el.closest('form'), classe: (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/)[0] || ''});
  };
  document.querySelectorAll(base).forEach(add);
  document.querySelectorAll('div, span, li, img, svg, i, td').forEach(el => {
    if (getComputedStyle(el).cursor === 'pointer' && el.parentElement && getComputedStyle(el.parentElement).cursor !== 'pointer') add(el);
  });
  return lista;
}
"""
JS_ASSINATURA = "() => ({texto: (document.body.innerText || '').replace(/\\s+/g, ' ').trim().toLowerCase(), rota: location.pathname + location.hash.split('?')[0]})"


def _motivo_exclusao(c: dict, origem: str) -> str | None:
    if c["type"] in ("submit", "password", "file", "reset", "image"):
        return "tipo"
    if c["download"]:
        return "download"
    if c["tag"] == "a":
        h = c["href"].strip()
        if re.match(r"^(mailto:|tel:|javascript:|sms:)", h, re.I):
            return "esquema"
        if h.startswith("http") and urlparse(h).netloc != urlparse(origem).netloc:
            return "origem_externa"
        if c["target"] == "_blank":
            return "nova_aba"
    if EXCLUIR_TEXTO.search(c["texto"]):
        return "texto_de_risco"
    return None


def _assinatura(page) -> tuple[str, dict]:
    d = page.evaluate(JS_ASSINATURA)
    return hashlib.sha1(d["texto"].encode("utf-8")).hexdigest(), d


def _alternativa(c: dict) -> str | None:
    if c["texto"] and c["tag"] in ("button", "a", "summary", "label"):
        t = c["texto"][:40].replace("\\", " ").replace('"', " ").strip()
        return f'{c["tag"]}:visible:has-text("{t}") >> nth=0'
    return None


def _miniatura(page):
    import io
    from PIL import Image
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB").resize((480, 270))


def _mudanca(a, b) -> float:
    from PIL import ImageChops
    h = ImageChops.difference(a, b).convert("L").histogram()
    return sum(h[25:]) / sum(h)


def _slug(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t[:24] or "item"


def _explorar_ponto(site: dict, cfg: dict, limite_segundos: int | None = None, max_estados: int | None = None,
                    max_profundidade: int | None = None, headless: bool = True, silencioso: bool = False,
                    parcial: Path | None = None) -> tuple[dict, dict]:
    import capturar_paginas as CAP
    from playwright.sync_api import sync_playwright

    limite_s = limite_segundos or cfg.get("limite_segundos", 7200)
    max_est = max_estados or cfg.get("max_estados")
    max_prof = max_profundidade or cfg.get("max_profundidade", 4)
    excluir = {t.strip().lower() for t in cfg.get("excluir_textos", [])}
    tokens_vistos: list[set] = []
    miniaturas: dict[str, list] = {}
    limiar_vis = cfg.get("limiar_visual", LIMIAR_VISUAL_NOVO)
    inicio = cfg.get("inicio") or [{"tipo": "ir", "url": site["url"]}, {"tipo": "esperar", "ms": 3000}]
    log = print if not silencioso else (lambda *_: None)
    t0 = time.time()
    estados: list[dict] = []
    assinaturas: set[str] = set()
    tentados: set[tuple[str, str]] = set()
    exclusoes: dict[str, int] = {}
    falhas = tentativas = 0
    parada = "saturacao"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(viewport=CAP.VIEWPORT, device_scale_factor=1, locale=site.get("locale", "pt-BR"))
        page = ctx.new_page()
        novas_abas: list = []
        ctx.on("page", lambda pg: (novas_abas.append(pg), pg.close()) if pg != page else None)
        page.on("dialog", lambda d: d.dismiss())

        def reiniciar():
            for a in inicio:
                CAP._aplicar_acao(page, a)
                page.wait_for_timeout(CAP.ESPERA_APOS_ACAO_MS)
            CAP._esperar_ociosidade(page)
            CAP._clicar_se_visivel(page, site.get("cookies"))
            CAP._fechar_overlays(page, site.get("fechar", []))

        def reproduzir(caminho: list[dict]):
            reiniciar()
            for passo in caminho:
                try:
                    page.locator(passo["seletor"]).first.click(timeout=TIMEOUT_CLIQUE_MS)
                except Exception:
                    if not passo.get("alternativa"):
                        raise
                    page.locator(passo["alternativa"]).first.click(timeout=TIMEOUT_CLIQUE_MS)
                page.wait_for_timeout(ESPERA_APOS_CLIQUE_MS)
                CAP._esperar_ociosidade(page)

        fila: list[list[dict]] = [[]]
        while fila:
            if time.time() - t0 > limite_s:
                parada = "teto_de_tempo"; break
            if max_est and len(estados) >= max_est:
                parada = "max_estados"; break
            caminho = fila.pop(0)
            erro = None
            for _tentativa in range(3 if not caminho else 2):
                try:
                    reproduzir(caminho); erro = None; break
                except Exception as e:
                    erro = e
            if erro is not None:
                falhas += 1; log(f"  [falha ao reproduzir caminho {[c['texto'] for c in caminho]}]: {str(erro).splitlines()[0][:80]}")
                continue
            sig, d = _assinatura(page)
            mini = _miniatura(page)
            if sig in assinaturas and any(_mudanca(mini, m) < limiar_vis for m in miniaturas[sig]):
                continue
            assinaturas.add(sig)
            miniaturas.setdefault(sig, []).append(mini)
            nome = f"x{len(estados) + 1:02d}_" + (_slug(caminho[-1]["texto"]) if caminho else "inicial")
            tk = set(d["texto"].split())
            sim = max((len(tk & o) / len(tk | o) for o in tokens_vistos if tk | o), default=0.0)
            tokens_vistos.append(tk)
            estados.append({"nome": nome, "caminho": caminho, "assinatura": sig, "rota": d["rota"], "caracteres": len(d["texto"]),
                            "profundidade": len(caminho), "t_s": round(time.time() - t0, 1),
                            "similaridade_max": round(sim, 3), "texto": d["texto"]})
            if parcial is not None:
                parcial.parent.mkdir(parents=True, exist_ok=True)
                parcial.write_text(json.dumps({"inicio": inicio, "estados": estados}, ensure_ascii=False), encoding="utf-8")
            log(f"  estado {len(estados)}: {nome} (prof. {len(caminho)}, {len(d['texto'])} car., {round(time.time() - t0)}s)")
            if len(caminho) >= max_prof:
                continue
            origem = page.url
            cands = page.evaluate(JS_CANDIDATOS)
            for c in cands:
                m = _motivo_exclusao(c, origem) or ("configurado" if c["texto"].strip().lower() in excluir else None)
                if m:
                    exclusoes[m] = exclusoes.get(m, 0) + 1
                    continue
                if (sig, c["sel"]) in tentados:
                    continue
                tentados.add((sig, c["sel"]))
                if len([1 for x in fila if x[:-1] == caminho]) >= MAX_CANDIDATOS:
                    exclusoes["excedeu_candidatos"] = exclusoes.get("excedeu_candidatos", 0) + 1
                    continue
                fila.append(caminho + [{"seletor": c["sel"], "texto": c["texto"] or c["classe"], "alternativa": _alternativa(c)}])
                tentativas += 1
        browser.close()

    def acoes(est):
        return list(inicio) + [x for passo in est["caminho"] for x in (
            {k: v for k, v in {"tipo": "clicar", "seletor": passo["seletor"], "alternativa": passo.get("alternativa"), "ms": TIMEOUT_CLIQUE_MS}.items() if v},
            {"tipo": "esperar", "ms": 1000})]
    roteiro = {k: v for k, v in site.items() if k not in ("estados", "exploracao")}
    roteiro["estados"] = [{"nome": e["nome"], "acoes": acoes(e)} for e in estados]
    roteiro["_nota"] = (f"Roteiro gerado por exploração determinística em largura (parada: {parada}; {len(estados)} estados; "
                        f"{round(time.time() - t0)} s).")
    registro = {"site": site["id"], "parada": parada, "estados": estados, "tentativas_enfileiradas": tentativas,
                "caminhos_irreproduziveis": falhas, "exclusoes_por_motivo": exclusoes, "duracao_s": round(time.time() - t0, 1),
                "limite_segundos": limite_s, "max_profundidade": max_prof, "abas_novas_fechadas": len(novas_abas)}
    return roteiro, registro


def explorar(site: dict, destino: Path, limite_segundos: int | None = None, max_estados: int | None = None,
             max_profundidade: int | None = None, headless: bool = True, silencioso: bool = False) -> dict:
    cfg = site.get("exploracao", {})
    pontos = cfg if isinstance(cfg, list) else [cfg]
    estados_rot, estados_reg, registros = [], [], []
    for k, ponto in enumerate(pontos, 1):
        rot, reg = _explorar_ponto(site, ponto, limite_segundos, max_estados, max_profundidade, headless, silencioso,
                                   parcial=destino / f"parcial_{site['id']}_{k}.json")
        pre = f"{ponto['nome']}_" if len(pontos) > 1 and ponto.get("nome") else (f"p{k}_" if len(pontos) > 1 else "")
        for e in rot["estados"]:
            estados_rot.append({**e, "nome": pre + e["nome"]})
        for e in reg["estados"]:
            estados_reg.append({**e, "nome": pre + e["nome"], "ponto": ponto.get("nome", k)})
        registros.append({k_: v for k_, v in reg.items() if k_ != "estados"} | {"ponto": ponto.get("nome", k)})
    roteiro = {k_: v for k_, v in site.items() if k_ not in ("estados", "exploracao")}
    roteiro["estados"] = estados_rot
    roteiro["_nota"] = (f"Roteiro gerado por exploração determinística em largura; {len(estados_rot)} estados em "
                        f"{len(pontos)} ponto(s) de partida; paradas: {[r['parada'] for r in registros]}.")
    registro = {"site": site["id"], "pontos": registros, "estados": estados_reg,
                "duracao_s": round(sum(r["duracao_s"] for r in registros), 1),
                "parada": registros[0]["parada"] if len(registros) == 1 else "/".join(r["parada"] for r in registros)}
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"roteiro_{site['id']}.json").write_text(json.dumps([roteiro], ensure_ascii=False, indent=1), encoding="utf-8")
    (destino / f"exploracao_{site['id']}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    return registro
