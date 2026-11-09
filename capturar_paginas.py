import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

from src.css_embutido import embutir as embutir_css
from playwright.sync_api import Page, sync_playwright

VIEWPORT = {"width": 1920, "height": 1080}
ALTURA_FATIA = 1080
MAX_FATIAS = 4
ESPERA_APOS_ACAO_MS = 800
TIMEOUT_NAVEGACAO_MS = 30_000
TIMEOUT_OCIOSIDADE_MS = 8_000
ESPERA_ELEMENTO_MS = 2_500
RAIZ_SAIDA = Path("coletas")

SINAIS_DE_BLOQUEIO = [
    "confirmar que você é humano", "confirmar que voce e humano",
    "verify you are human", "are you a robot", "captcha",
    "access denied", "erro 403", "error 403", "(erro 403)",
    "não é possível acessar a página", "just a moment",
    "attention required", "unusual traffic", "pardon our interruption",
]


def _ir(page: Page, url: str) -> None:
    page.goto(url, wait_until="load", timeout=TIMEOUT_NAVEGACAO_MS)
    _esperar_ociosidade(page)


def _esperar_ociosidade(page: Page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_OCIOSIDADE_MS)
    except Exception:
        pass


def _rolar_para_carregar(page: Page) -> None:
    altura = page.evaluate("document.body.scrollHeight")
    posicao = 0
    while posicao < altura:
        page.evaluate(f"window.scrollTo(0, {posicao})")
        page.wait_for_timeout(300)
        posicao += VIEWPORT["height"]
        altura = page.evaluate("document.body.scrollHeight")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)


def _clicar_se_visivel(page: Page, seletor: str | None) -> bool:
    if not seletor:
        return False
    limite = ESPERA_ELEMENTO_MS // 250
    for _ in range(limite):
        for frame in page.frames:
            try:
                alvo = frame.locator(seletor).first
                if alvo.is_visible():
                    alvo.click(timeout=3_000)
                    page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        page.wait_for_timeout(250)
    return False


def _fechar_overlays(page: Page, seletores: list[str]) -> list[str]:
    fechados = []
    for sel in seletores:
        if _clicar_se_visivel(page, sel):
            fechados.append(sel)
    return fechados


def _aplicar_acao(page: Page, acao: dict) -> None:
    tipo = acao["tipo"]
    if tipo == "ir":
        _ir(page, acao["url"])
    elif tipo == "clicar":
        loc = page.locator(acao["seletor"]).first
        t_ms = int(acao.get("ms", 30000))
        if acao.get("opcional"):
            try:
                loc.click(timeout=min(t_ms, 4000))
            except Exception:
                print(f"[captura] clique opcional ignorado: {acao['seletor']}")
        elif acao.get("alternativa"):
            try:
                loc.click(timeout=t_ms)
            except Exception:
                page.locator(acao["alternativa"]).first.click(timeout=t_ms)
        elif acao.get("js_se_falhar"):
            try:
                loc.click(timeout=5000)
            except Exception as e:
                print(f"[captura] clique normal falhou em {acao['seletor']} "
                      f"({str(e).splitlines()[0][:80]}); usando clique via DOM")
                loc.evaluate("el => el.click()")
        else:
            loc.click(timeout=t_ms)
    elif tipo == "clicar_mesma_aba":
        loc = page.locator(acao["seletor"]).first
        loc.evaluate("el => el.removeAttribute('target')")
        try:
            loc.click(timeout=int(acao.get("ms", 15000)))
        except Exception as e:
            print(f"[captura] clique normal falhou em {acao['seletor']} "
                  f"({str(e).splitlines()[0][:80]}); usando clique via DOM")
            loc.evaluate("el => el.click()")
    elif tipo == "esperar_elemento":
        page.locator(acao["seletor"]).first.wait_for(
            state=acao.get("estado", "attached"), timeout=int(acao.get("ms", 60000)))
    elif tipo == "preencher":
        page.locator(acao["seletor"]).first.fill(acao["valor"])
    elif tipo == "esperar":
        page.wait_for_timeout(int(acao["ms"]))
    elif tipo == "rolar":
        page.evaluate(f"window.scrollBy(0, {int(acao['px'])})")
    else:
        raise ValueError(f"Ação não permitida: {tipo}")


def _fatiar(png_completo: Path, prefixo: Path) -> list[str]:
    img = Image.open(png_completo)
    largura, altura = img.size
    arquivos: list[str] = []
    for i in range(MAX_FATIAS):
        topo = i * ALTURA_FATIA
        if topo >= altura:
            break
        fatia = img.crop((0, topo, largura, min(topo + ALTURA_FATIA, altura)))
        destino = Path(f"{prefixo}_fatia_{i + 1}.png")
        fatia.save(destino)
        arquivos.append(destino.name)
    return arquivos


def _alertas(page: Page, html: str, hash_png: str, anterior: dict | None,
             url_pedida: str | None) -> list[str]:
    alertas: list[str] = []
    try:
        texto = (page.inner_text("body") or "")[:3000].lower()
    except Exception:
        texto = ""
    titulo = (page.title() or "").lower()
    if any(s in texto or s in titulo for s in SINAIS_DE_BLOQUEIO):
        alertas.append(
            "BLOQUEIO: página de verificação anti-robô ou acesso negado. Troque o site.")
    if len(html) < 5_000:
        alertas.append(
            "HTML muito pequeno (<5 KB): provável página de erro/bloqueio.")
    if anterior and anterior["_hash_png"] == hash_png:
        alertas.append(
            "Captura idêntica à do estado anterior: o fluxo não avançou.")
    if url_pedida and anterior and page.url.rstrip("/") == anterior["url_no_momento"].rstrip("/") \
            and anterior["_hash_png"] != hash_png:
        alertas.append(
            "URL não mudou entre os estados (ok se for SPA/menu; confira visualmente).")
    return alertas


def capturar_site(site: dict, pasta_site: Path) -> dict:
    pasta_site.mkdir(parents=True, exist_ok=True)
    locale = site.get("locale", "pt-BR")
    meta: dict = {
        "id": site["id"],
        "url_solicitada": site["url"],
        "coletado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "viewport": VIEWPORT,
        "locale": locale,
        "estados": [],
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport=VIEWPORT, device_scale_factor=1, locale=locale)
                page = context.new_page()
                _ir(page, site["url"])
                meta["user_agent"] = page.evaluate("navigator.userAgent")
                meta["cookies_tratados"] = _clicar_se_visivel(
                    page, site.get("cookies"))

                anterior: dict | None = None
                cache_css: dict = {}
                for idx, estado in enumerate(site["estados"], 1):
                    try:
                        for tentativa in (1, 2):
                            try:
                                for acao in estado.get("acoes", []):
                                    _aplicar_acao(page, acao)
                                    page.wait_for_timeout(ESPERA_APOS_ACAO_MS)
                                    if acao["tipo"].startswith("clicar"):
                                        _esperar_ociosidade(page)
                                break
                            except Exception as e1:
                                if tentativa == 2:
                                    raise
                                print(f"[captura] {estado['nome']}: tentativa 1 falhou "
                                      f"({str(e1).splitlines()[0][:70]}); repetindo o caminho")
                        _esperar_ociosidade(page)
                        _clicar_se_visivel(page, site.get("cookies"))
                        fechados = _fechar_overlays(
                            page, site.get("fechar", []))
                        _rolar_para_carregar(page)

                        prefixo = pasta_site / \
                            f"estado_{idx:02d}_{estado['nome']}"
                        completo = Path(f"{prefixo}_completo.png")
                        page.screenshot(path=str(completo), full_page=True)
                        fatias = _fatiar(completo, prefixo)
                        html = page.content()
                        css_resumo = None
                        if site.get("embutir_css", True):
                            def _buscar(u, _ctx=context):
                                r = _ctx.request.get(u, timeout=30000)
                                if r.status in (404, 410):
                                    return ""
                                return r.text() if r.ok else None
                            html, css_resumo = embutir_css(html, page.url, _buscar, cache_css)
                        Path(f"{prefixo}.html").write_text(
                            html, encoding="utf-8")
                        hash_png = hashlib.md5(
                            completo.read_bytes()).hexdigest()

                        registro = {
                            "ordem": idx,
                            "nome": estado["nome"],
                            "url_no_momento": page.url,
                            "completo": completo.name,
                            "fatias": fatias,
                            "html": f"{prefixo.name}.html",
                            "overlays_fechados": fechados,
                            "css_embutido": css_resumo,
                            "_hash_png": hash_png,
                        }
                        registro["alertas"] = _alertas(
                            page, html, hash_png, anterior, site["url"])
                        meta["estados"].append(registro)
                        anterior = registro
                    except Exception as e:
                        meta["estados"].append({
                            "ordem": idx, "nome": estado["nome"],
                            "alertas": [f"FALHA no estado: {str(e)[:700]}"],
                            "_hash_png": "",
                        })
                        acoes = estado.get("acoes") or []
                        if acoes and acoes[0].get("tipo") == "ir":
                            continue
                        break
            finally:
                browser.close()
    except Exception as e:
        meta["erro"] = str(e)[:300]
    finally:
        for est in meta["estados"]:
            est.pop("_hash_png", None)
        (pasta_site / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(caminho_sites: str, ids: list[str]) -> None:
    sites = json.loads(Path(caminho_sites).read_text(encoding="utf-8"))
    if ids:
        sites = [s for s in sites if s["id"] in ids]
    data = datetime.now().strftime("%Y%m%d")
    resumo: list[str] = []
    for site in sites:
        pasta = RAIZ_SAIDA / site["id"] / data
        if "PREENCHER" in json.dumps(site, ensure_ascii=False):
            print(
                f"[captura] {site['id']} PULADO: há URLs 'PREENCHER_URL' no sites.json")
            resumo.append(f"  PENDENTE {site['id']}: preencha as URLs marcadas em sites.json "
                          f"({site.get('_pendente', '')})")
            continue
        print(f"[captura] {site['id']} → {pasta}")
        meta = capturar_site(site, pasta)
        alertas = [f"{e['nome']}: {a}" for e in meta["estados"]
                   for a in e.get("alertas", [])]
        if meta.get("erro"):
            alertas.insert(0, f"ERRO GERAL: {meta['erro']}")
        resumo.append(f"  {'OK   ' if not alertas else 'ATENÇÃO'} {site['id']}" +
                      ("" if not alertas else "\n      - " + "\n      - ".join(alertas)))
    print("\n=== RESUMO ===")
    print("\n".join(resumo))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Uso: python capturar_paginas.py sites.json [id1 id2 ...]")
    main(sys.argv[1], sys.argv[2:])
