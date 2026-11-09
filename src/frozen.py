import base64
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

from .extractor import _extract_computed_styles, _extract_render_facts
from .models import ExtractionResult

TIMEOUT_RENDER_MS = 10_000
VIEWPORT = {"width": 1920, "height": 1080}

ALERTAS_IMPEDITIVOS = ("BLOQUEIO", "HTML muito pequeno", "FALHA")


class FrozenState(BaseModel):
    ordem: int
    nome: str
    url_no_momento: str
    fatias: list[Path] = []
    html: Path | None = None


class Flow(BaseModel):
    id: str
    site: str
    tarefa: str | None
    locale: str
    pasta: Path | None
    estados: list[FrozenState]


def _pasta_mais_recente(base: Path, site_id: str) -> Path:
    datas = sorted(p for p in (base / site_id).glob("*")
                   if p.is_dir() and re.fullmatch(r"\d{8}", p.name))
    if not datas:
        raise FileNotFoundError(
            f"Nenhuma captura em {base / site_id}/<AAAAMMDD>/")
    return datas[-1]


def _validar_meta(meta: dict, pasta: Path) -> None:
    if meta.get("erro"):
        raise ValueError(f"{pasta}: captura com erro geral: {meta['erro']}")
    for est in meta["estados"]:
        impeditivos = [a for a in est.get("alertas", [])
                       if any(a.startswith(p) for p in ALERTAS_IMPEDITIVOS)]
        if impeditivos:
            raise ValueError(
                f"{pasta}: estado {est.get('ordem')} ({est.get('nome')}) "
                f"tem alertas de bloqueio: {impeditivos}")
        for a in est.get("alertas", []):
            if a not in impeditivos:
                print(f"[frozen] aviso em {pasta.name}/{est['nome']}: {a}")


def load_flow(site_id: str, base: str | Path = "coletas",
              sites_json: str | Path = "sites.json") -> Flow:
    sites = json.loads(Path(sites_json).read_text(encoding="utf-8"))
    site = next((s for s in sites if s["id"] == site_id), None)
    if site is None:
        raise KeyError(f"Fluxo '{site_id}' não existe em {sites_json}")

    pasta = _pasta_mais_recente(Path(base), site_id)
    meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
    _validar_meta(meta, pasta)

    estados = []
    for est in sorted(meta["estados"], key=lambda e: e["ordem"]):
        fatias = [pasta / f for f in est["fatias"]]
        html = pasta / est["html"]
        faltando = [str(p) for p in [*fatias, html] if not p.exists()]
        if faltando:
            raise FileNotFoundError(f"Arquivos ausentes: {faltando}")
        estados.append(FrozenState(
            ordem=est["ordem"],
            nome=est["nome"],
            url_no_momento=est["url_no_momento"],
            fatias=fatias,
            html=html,
        ))

    return Flow(
        id=site_id,
        site=site["site"],
        tarefa=site.get("tarefa"),
        locale=meta.get("locale", site.get("locale", "pt-BR")),
        pasta=pasta,
        estados=estados,
    )


def flow_from_url(flow_id: str, url: str, tarefa: str | None = None) -> Flow:
    return Flow(
        id=flow_id, site=url, tarefa=tarefa, locale="pt-BR", pasta=None,
        estados=[FrozenState(ordem=1, nome="pagina", url_no_momento=url)],
    )


def _com_base_href(html: str, base_url: str) -> str:
    tag = f'<base href="{base_url}">'
    m = re.search(r"<head[^>]*>", html, re.I)
    if m:
        return html[:m.end()] + tag + html[m.end():]
    return tag + html


def _sem_noscript(html: str) -> str:
    return re.sub(r"<noscript\b.*?</noscript>", "", html, flags=re.S | re.I)


def _render_computed_styles(html: str, base_url: str) -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport=VIEWPORT, java_script_enabled=False)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(_com_base_href(_sem_noscript(html), base_url),
                             wait_until="domcontentloaded",
                             timeout=TIMEOUT_RENDER_MS)
            return _extract_computed_styles(page)
        finally:
            browser.close()


def _tem_css_externo(html: str) -> bool:
    sem_comentarios = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    return bool(re.search(r"<link\b[^>]*rel=[\"']?stylesheet", sem_comentarios, re.I)
                or re.search(r"@import\b", sem_comentarios, re.I))


def _render_render_facts(html: str, base_url: str) -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport=VIEWPORT, java_script_enabled=False)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(_com_base_href(_sem_noscript(html), base_url),
                             wait_until="domcontentloaded",
                             timeout=TIMEOUT_RENDER_MS)
            return _extract_render_facts(page)
        finally:
            browser.close()


def _styles_from_soup(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    itens = []
    for el in body.find_all(True)[:1500]:
        if el.name in ("script", "style", "noscript", "template"):
            continue
        classes = el.get("class") or []
        seletor = (f"#{el['id']}" if el.get("id")
                   else el.name + "".join(f".{c}" for c in classes))
        itens.append({
            "tag": el.name,
            "selector": seletor,
            "text": el.get_text(" ", strip=True)[:100],
            "own_text": " ".join(t.strip() for t in el.find_all(string=True, recursive=False)
                                 if t.strip())[:200],
            "attrs": " | ".join(el.get(a) for a in ("placeholder", "aria-label", "alt", "title")
                                if el.get(a))[:200],
            "styles": {},
        })
    return itens


def extract_frozen_state(state: FrozenState) -> ExtractionResult:
    if state.html is None:
        raise ValueError(
            "Estado sem HTML congelado: use extractor.extract(url).")

    html = state.html.read_text(encoding="utf-8")
    screenshots = [base64.b64encode(f.read_bytes()).decode("utf-8")
                   for f in state.fatias]

    warnings: list[str] = []
    try:
        computed_styles = _render_computed_styles(html, state.url_no_momento)
    except Exception as e:
        aviso = (f"computed_styles indisponível ({type(e).__name__}: "
                 f"{str(e)[:120]}); texto extraído do HTML com BeautifulSoup")
        print(f"[frozen] {state.nome}: {aviso}")
        warnings.append(aviso)
        computed_styles = _styles_from_soup(html)

    render_facts: list[dict] = []
    facts_status = "css_externo"
    if not _tem_css_externo(html):
        try:
            render_facts, facts_status = _render_render_facts(html, state.url_no_momento), "ok"
        except Exception:
            facts_status = "falha"

    return ExtractionResult(
        url=state.url_no_momento,
        html=html,
        screenshots=screenshots,
        computed_styles=computed_styles,
        render_facts=render_facts,
        render_facts_status=facts_status,
        warnings=warnings,
    )
