from __future__ import annotations

import html as _html
import re
from typing import Callable
from urllib.parse import urljoin

_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = r"""{nome}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""


def _attr(tag: str, nome: str) -> str | None:
    m = re.search(_ATTR.format(nome=nome), tag, re.I)
    return None if not m else next(g for g in m.groups() if g is not None)


def folhas_externas(html: str, base_url: str) -> list[str]:
    urls = []
    for tag in _LINK.findall(html):
        if "stylesheet" in (_attr(tag, "rel") or "").lower() and _attr(tag, "href"):
            urls.append(urljoin(base_url, _html.unescape(_attr(tag, "href"))))
    return urls


_IMPORT = re.compile(
    r"""@import\s+(?:url\(\s*(["']?)(?P<u1>[^)]*?)\1\s*\)|(["'])(?P<u2>.*?)\3)[^;{}]*;""", re.I)
_STYLE = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.I | re.S)


def _resolver_imports_css(css: str, base: str, buscar, cache: dict, profundidade: int = 2) -> str:
    def trocar(m: re.Match) -> str:
        url = urljoin(base, _html.unescape((m.group("u1") or m.group("u2") or "").strip()))
        if profundidade <= 0:
            return m.group(0)
        if url not in cache:
            try:
                cache[url] = buscar(url)
            except Exception:
                cache[url] = None
        conteudo = cache[url]
        if conteudo is None:
            return m.group(0)
        if conteudo == "":
            return f"/* @import ausente no servidor: {url} */"
        return f"/* @import {url} */\n" + _resolver_imports_css(conteudo, url, buscar, cache, profundidade - 1)
    return _IMPORT.sub(trocar, css)


def resolver_imports(html: str, base_url: str, buscar, cache: dict | None = None) -> str:
    cache = {} if cache is None else cache

    def bloco(m: re.Match) -> str:
        origem = re.search(r'data-origem="([^"]*)"', m.group(1))
        base = _html.unescape(origem.group(1)) if origem else base_url
        return m.group(1) + _resolver_imports_css(m.group(2), base, buscar, cache) + m.group(3)

    return _STYLE.sub(bloco, html) if "@import" in html else html


def embutir(html: str, base_url: str, buscar: Callable[[str], str | None],
            cache: dict[str, str | None] | None = None) -> tuple[str, dict]:
    cache = {} if cache is None else cache
    resumo = {"embutidas": 0, "ausentes": [], "falhas": []}

    def trocar(m: re.Match) -> str:
        tag = m.group(0)
        if "stylesheet" not in (_attr(tag, "rel") or "").lower() or not _attr(tag, "href"):
            return tag
        url = urljoin(base_url, _html.unescape(_attr(tag, "href")))
        if url not in cache:
            try:
                cache[url] = buscar(url)
            except Exception:
                cache[url] = None
        css = cache[url]
        if css is None:
            resumo["falhas"].append(url)
            return tag
        if css == "":
            resumo["ausentes"].append(url)
            return f'<style data-origem="{_html.escape(url, quote=True)}" data-status="ausente"></style>'
        resumo["embutidas"] += 1
        media = _attr(tag, "media")
        atributos = f' data-origem="{_html.escape(url, quote=True)}"' + (f' media="{_html.escape(media, quote=True)}"' if media else "")
        seguro = css.replace("</style", "<\\/style")
        return f"<style{atributos}>\n{seguro}\n</style>"

    novo = _LINK.sub(trocar, html)
    return resolver_imports(novo, base_url, buscar, cache), resumo
