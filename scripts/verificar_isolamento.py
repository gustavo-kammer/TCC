import glob, json, re, sys
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from src.models import Heuristic

HTML = RAIZ / "interfaces" / "calibracao"
GAB = RAIZ / "gabarito" / "calibracao"
ENUM = {h.value for h in Heuristic}
ESPERADO = {"salto": {"calib_04"}, "sem_label": {"calib_05"}}


class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.h = []; s.fields = []; s.labels = set(); s.lang = None; s.title = False; s.imgs = []; s.inline = 0
    def handle_starttag(s, t, a):
        a = dict(a)
        if t == "html": s.lang = a.get("lang")
        if t in ("h1", "h2", "h3", "h4", "h5", "h6"): s.h.append(int(t[1]))
        if t in ("input", "select", "textarea"): s.fields.append((a.get("id"), "aria-label" in a or "aria-labelledby" in a))
        if t == "label" and a.get("for"): s.labels.add(a["for"])
        if t == "img": s.imgs.append(a.get("alt"))
        if t == "title": s.title = True
        if "style" in a: s.inline += 1


def shell(html):
    n = lambda x: x.replace(' aria-current="page"', "")
    return n(re.search(r"<header.*?</header>", html, re.S).group(0)), n(re.search(r"<footer.*?</footer>", html, re.S).group(0))


erros = []
ref = None
saltos, sem = set(), set()
for f in sorted(glob.glob(str(HTML / "calib_*.html"))):
    cid = Path(f).stem
    html = Path(f).read_text(encoding="utf-8"); p = P(); p.feed(html)
    if p.lang != "pt-BR" or not p.title: erros.append(f"{cid}: falta lang/title")
    if p.h.count(1) != 1: erros.append(f"{cid}: h1 != 1")
    if any(b - a > 1 for a, b in zip(p.h, p.h[1:])): saltos.add(cid)
    if [i for i, aria in p.fields if i not in p.labels and not aria]: sem.add(cid)
    if any(not a for a in p.imgs): erros.append(f"{cid}: img sem alt")
    if p.inline: erros.append(f"{cid}: style inline")
    sh = shell(html); ref = ref or sh
    if sh != ref: erros.append(f"{cid}: shell diferente")
if saltos != ESPERADO["salto"]: erros.append(f"salto de heading em {sorted(saltos)} (esperado {sorted(ESPERADO['salto'])})")
if sem != ESPERADO["sem_label"]: erros.append(f"campo sem label em {sorted(sem)} (esperado {sorted(ESPERADO['sem_label'])})")

hs = []
for f in sorted(glob.glob(str(GAB / "calib_*.json"))):
    g = json.loads(Path(f).read_text(encoding="utf-8")); v = g["violacoes_gabarito"]
    if len(v) != 1: erros.append(f"{Path(f).stem}: esperado 1 violação")
    for x in v:
        if x["heuristic"] not in ENUM: erros.append(f"{Path(f).stem}: heuristic fora do enum")
        if not 0 <= x["severity"] <= 4: erros.append(f"{Path(f).stem}: severity inválida")
        hs.append(x["heuristic"])
if len(set(hs)) != 10: erros.append("gabaritos não cobrem as 10 heurísticas")

print("OK — isolamento verificado." if not erros else "FALHAS:\n- " + "\n- ".join(erros))
sys.exit(1 if erros else 0)
