from __future__ import annotations

import json
from pathlib import Path


def _tokens(texto: str) -> set[str]:
    return set(texto.split())


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def fracao_mudanca(a: Path, b: Path) -> float:
    from PIL import Image, ImageChops
    ia = Image.open(a).convert("RGB").resize((480, 270))
    ib = Image.open(b).convert("RGB").resize((480, 270))
    h = ImageChops.difference(ia, ib).convert("L").histogram()
    return sum(h[25:]) / sum(h)


def selecionar(estados: list[dict], limiar: float, max_estados: int | None = None,
               limiar_visual: float = 0.005) -> list[dict]:
    ordem = sorted(range(len(estados)), key=lambda i: (estados[i]["profundidade"], i))
    mantidos: list[int] = []
    toks: dict[int, set] = {}

    def repetido(i: int, j: int) -> bool:
        if jaccard(toks[i], toks[j]) < limiar:
            return False
        a, b = estados[i].get("png"), estados[j].get("png")
        if bool(a) != bool(b):
            return False
        return not (a and b and fracao_mudanca(Path(a), Path(b)) >= limiar_visual)

    for i in ordem:
        toks[i] = _tokens(estados[i]["texto"])
        if not any(repetido(i, j) for j in mantidos):
            mantidos.append(i)
            if max_estados and len(mantidos) >= max_estados:
                break
    return [estados[i] for i in sorted(mantidos)]


def replay_estados(roteiro_site: dict, pasta_png: Path, silencioso: bool = False) -> dict[str, tuple[str, str]]:
    import capturar_paginas as CAP
    from playwright.sync_api import sync_playwright
    pasta_png.mkdir(parents=True, exist_ok=True)
    saida: dict[str, tuple[str, str]] = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(viewport=CAP.VIEWPORT, locale=roteiro_site.get("locale", "pt-BR")).new_page()
        pg.on("dialog", lambda d: d.dismiss())
        for e in roteiro_site["estados"]:
            ultimo = ""
            for tentativa in (1, 2):
                try:
                    for a in e["acoes"]:
                        if a["tipo"].startswith("clicar"):
                            CAP._clicar_se_visivel(pg, roteiro_site.get("cookies"))
                            CAP._fechar_overlays(pg, roteiro_site.get("fechar", []))
                        CAP._aplicar_acao(pg, a); pg.wait_for_timeout(CAP.ESPERA_APOS_ACAO_MS)
                        if a["tipo"].startswith("clicar"):
                            CAP._esperar_ociosidade(pg)
                    CAP._esperar_ociosidade(pg)
                    CAP._clicar_se_visivel(pg, roteiro_site.get("cookies"))
                    CAP._fechar_overlays(pg, roteiro_site.get("fechar", []))
                    pg.wait_for_timeout(1000)
                    png = pasta_png / f"{e['nome']}.png"
                    pg.screenshot(path=str(png))
                    saida[e["nome"]] = (pg.evaluate("(document.body.innerText||'').replace(/\\s+/g,' ').trim().toLowerCase()"), str(png))
                    break
                except Exception as ex:
                    ultimo = str(ex).splitlines()[0][:100]
                    if tentativa == 2:
                        try:
                            pg.screenshot(path=str(pasta_png / f"_FALHA_{e['nome']}.png"))
                        except Exception:
                            pass
            else:
                if not silencioso:
                    print(f"  [replay falhou em {e['nome']}]: {ultimo} (captura da tela em _FALHA_{e['nome']}.png)")
        b.close()
    return saida


def curar(roteiro_json: Path, destino: Path, limiar: float = 0.9, max_estados: int | None = None,
          registro_json: Path | None = None, limiar_visual: float = 0.005, visual: bool = True) -> dict:
    site = json.loads(Path(roteiro_json).read_text(encoding="utf-8"))[0]
    textos: dict[str, str] = {}
    pngs: dict[str, str] = {}
    if registro_json and Path(registro_json).exists():
        textos = {e["nome"]: e["texto"] for e in json.loads(Path(registro_json).read_text(encoding="utf-8"))["estados"] if e.get("texto")}
    if visual or len(textos) < len(site["estados"]):
        alvo = site["estados"] if visual else [e for e in site["estados"] if e["nome"] not in textos]
        print(f"  reproduzindo {len(alvo)} estados ({'texto e imagem' if visual else 'texto'})")
        for nome, (t, png) in replay_estados({**site, "estados": alvo}, Path(destino) / f"_curadoria_{site['id']}").items():
            textos[nome] = t
            pngs[nome] = png
    est = [{"nome": e["nome"], "profundidade": sum(a["tipo"] == "clicar" for a in e["acoes"]), "texto": textos[e["nome"]],
            "png": pngs.get(e["nome"]), "_e": e} for e in site["estados"] if e["nome"] in textos]
    sem_img = sum(1 for e in est if not e["png"])
    if visual and sem_img:
        print(f"  ATENÇÃO: {sem_img} de {len(est)} estados sem imagem (replay falhou); comparados só por texto.")
    mant = selecionar(est, limiar, max_estados, limiar_visual)
    site["estados"] = [m["_e"] for m in mant]
    site["_nota"] = (site.get("_nota", "") + f" Curadoria: similaridade de texto >= {limiar}"
                     + (f" e mudança visual < {limiar_visual}" if visual else "") + f" = repetido; {len(mant)} de {len(est)} estados mantidos.").strip()
    Path(destino).mkdir(parents=True, exist_ok=True)
    saida = Path(destino) / f"curado_{site['id']}.json"
    saida.write_text(json.dumps([site], ensure_ascii=False, indent=1), encoding="utf-8")
    return {"site": site["id"], "limiar": limiar, "antes": len(est), "depois": len(mant), "arquivo": str(saida)}
