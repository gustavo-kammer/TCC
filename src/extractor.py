import base64
from playwright.sync_api import sync_playwright
from .models import ExtractionResult

RELEVANT_STYLE_PROPS = [
    "color", "background-color", "font-size", "font-family", "font-weight", "text-decoration", "border", "border-radius", "box-shadow", "padding", "margin", "width", "height", "display", "visibility", "cursor"
]


def _extract_computed_styles(page) -> list[dict]:
    js = """
   (props) => {
        const SKIP = new Set(['script', 'style', 'noscript', 'template', 'svg', 'path']);
        const nodes = Array.from(document.querySelectorAll('body *'))
            .filter((el) => !SKIP.has(el.tagName.toLowerCase()) && !el.closest('svg')
                && !(el.checkVisibility && !el.checkVisibility({visibilityProperty: true})));
        return nodes.slice(0, 1500).map((el) => {
            const ownText = Array.from(el.childNodes)
                .filter((n) => n.nodeType === 3)
                .map((n) => n.textContent.trim()).filter(Boolean).join(' ').slice(0, 200);
            const attrs = ['placeholder', 'aria-label', 'alt', 'title']
                .map((a) => el.getAttribute(a)).filter(Boolean).join(' | ').slice(0, 200);
            const cs = window.getComputedStyle(el);
            const styles = {};
            for (const p of props) styles[p] = cs.getPropertyValue(p);
            return {
                tag: el.tagName.toLowerCase(),
                selector: el.id ? '#' + el.id
                          : (el.className && typeof el.className === 'string'
                             ? el.tagName.toLowerCase() + '.' + el.className.trim().split(/\\s+/).join('.')
                             : el.tagName.toLowerCase()),
                text: (el.innerText || '').slice(0, 100),
                own_text: ownText,
                attrs: attrs,
                styles: styles,
            };
        });
    }
    """
    return page.evaluate(js, RELEVANT_STYLE_PROPS)


_RENDER_FACTS_JS = """
() => {
    const SKIP = new Set(['script', 'style', 'noscript', 'template', 'svg', 'path',
                          'head', 'meta', 'link', 'title']);
    const parseColor = (v) => {
        const m = (v || '').match(/^rgba?\\(([^)]+)\\)$/);
        if (!m) return null;
        const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number);
        if (p.length < 3 || p.slice(0, 3).some(Number.isNaN)) return null;
        return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const INTER = 'a[href], button, input:not([type=hidden]), select, textarea, summary, ' +
        '[role=button], [role=link], [role=checkbox], [role=radio], [role=switch], [role=tab], [role=menuitem]';
    const els = [document.documentElement, document.body, ...document.querySelectorAll('body *')]
        .filter((el) => el && !SKIP.has(el.tagName.toLowerCase()) && !el.closest('svg')
            && !(el.checkVisibility && !el.checkVisibility({visibilityProperty: true})))
        .slice(0, 3000);
    const idx = new Map();
    els.forEach((el, i) => idx.set(el, i));
    return els.map((el, i) => {
        let p = el.parentElement;
        while (p && !idx.has(p)) p = p.parentElement;
        const cs = window.getComputedStyle(el);
        const r = el.getBoundingClientRect();
        const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3)
            .map((n) => n.textContent.trim()).filter(Boolean).join(' ').slice(0, 80);
        return {
            i: i, p: p ? idx.get(p) : -1, tag: el.tagName.toLowerCase(),
            sel: el.id ? '#' + el.id : el.tagName.toLowerCase(),
            text: own, fg: parseColor(cs.color), bg: parseColor(cs.backgroundColor),
            bgimg: cs.backgroundImage !== 'none', op: parseFloat(cs.opacity),
            fs: parseFloat(cs.fontSize), fw: parseInt(cs.fontWeight) || 400,
            dis: el.disabled === true || el.getAttribute('aria-disabled') === 'true'
                 || !!el.closest('fieldset[disabled]'),
            inter: el.matches(INTER), inl: cs.display === 'inline',
            x: Math.round(r.x * 10) / 10, y: Math.round(r.y * 10) / 10,
            w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10,
        };
    });
}
"""


def _extract_render_facts(page) -> list[dict]:
    return page.evaluate(_RENDER_FACTS_JS)


def _capture_screenshot(page, max_shots: int = 3) -> list[str]:
    shots = []
    viewport_height = page.viewport_size["height"]
    total_height = page.evaluate("document.body.scrollHeight")

    offset = 0
    while offset < total_height and len(shots) < max_shots:
        page.evaluate(f"window.scrollTo(0, {offset})")
        page.wait_for_timeout(500)
        png_bytes = page.screenshot(type="png")
        shots.append(base64.b64encode(png_bytes).decode("utf-8"))
        offset += viewport_height

    return shots


def extract(url: str, headless: bool = True) -> ExtractionResult:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(url, wait_until="networkidle", timeout=30_000)
        html = page.content()
        computed_styles = _extract_computed_styles(page)
        try:
            render_facts, facts_status = _extract_render_facts(page), "ok"
        except Exception:
            render_facts, facts_status = [], "falha"
        screenshots = _capture_screenshot(page)
        browser.close()

    return ExtractionResult(
        url=url,
        html=html,
        screenshots=screenshots,
        computed_styles=computed_styles,
        render_facts=render_facts,
        render_facts_status=facts_status,
    )
