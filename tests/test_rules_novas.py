from src.models import ExtractionResult
from src.rules.engine import run_rules, ruleset_version
import src.rules.checks as checks


def _nomes(html="<html lang='pt'><title>t</title><body></body></html>", facts=None):
    r = ExtractionResult(url="t", html=html, render_facts=facts or [], render_facts_status="ok")
    return [v for v in run_rules(r)]


def _desc(vs):
    return " ".join(v.description for v in vs)


def _no(i, p=-1, **kw):
    base = dict(i=i, p=p, tag="p", sel="p", text="", fg=[0, 0, 0, 1], bg=[0, 0, 0, 0], bgimg=False,
                op=1, fs=16, fw=400, dis=False, inter=False, inl=False, x=0, y=0, w=100, h=20)
    base.update(kw)
    return base


def test_viewport_bloqueia_zoom():
    ruim = "<html lang='pt'><title>t</title><meta name='viewport' content='width=device-width, user-scalable=no'>"
    bom = "<html lang='pt'><title>t</title><meta name='viewport' content='width=device-width, initial-scale=1'>"
    assert "zoom" in _desc(_nomes(ruim))
    assert "zoom" not in _desc(_nomes(bom))


def test_autocomplete_exige_declaracao():
    sem = "<html lang='pt'><title>t</title><label>E-mail <input type='email' name='email'></label>"
    com = "<html lang='pt'><title>t</title><label>E-mail <input type='email' name='email' autocomplete='email'></label>"
    assert "autocomplete" in _desc(_nomes(sem))
    assert "autocomplete" not in _desc(_nomes(com))


def test_contraste_insuficiente_e_suficiente():
    raiz = _no(0, tag="body", text="", bg=[255, 255, 255, 1])
    claro = _no(1, p=0, text="texto cinza", fg=[170, 170, 170, 1])
    escuro = _no(2, p=0, text="texto preto", fg=[0, 0, 0, 1])
    assert "Contraste insuficiente" in _desc(_nomes(facts=[raiz, claro]))
    assert "Contraste insuficiente" not in _desc(_nomes(facts=[raiz, escuro]))


def test_contraste_ignora_fundo_com_imagem():
    raiz = _no(0, tag="body", bg=[255, 255, 255, 1], bgimg=True)
    claro = _no(1, p=0, text="texto cinza", fg=[170, 170, 170, 1])
    assert "Contraste insuficiente" not in _desc(_nomes(facts=[raiz, claro]))


def test_contraste_texto_grande_usa_limiar_menor():
    raiz = _no(0, tag="body", bg=[255, 255, 255, 1])
    normal = _no(1, p=0, text="normal", fg=[119, 119, 119, 1])
    grande = _no(2, p=0, text="grande", fg=[119, 119, 119, 1], fs=24)
    assert "Contraste insuficiente" in _desc(_nomes(facts=[raiz, normal]))
    assert "Contraste insuficiente" not in _desc(_nomes(facts=[raiz, grande]))


def test_alvo_pequeno_e_junto_dispara_e_isolado_nao():
    a = _no(1, tag="button", inter=True, x=0, y=0, w=16, h=16)
    b = _no(2, tag="button", inter=True, x=18, y=0, w=16, h=16)
    longe = _no(3, tag="button", inter=True, x=500, y=500, w=16, h=16)
    assert "Alvo interativo pequeno" in _desc(_nomes(facts=[a, b]))
    assert "Alvo interativo pequeno" not in _desc(_nomes(facts=[longe]))


def test_limite_de_ocorrencias_por_regra():
    campos = "".join(f"<input type='text' name='c{i}' value='x'>" for i in range(8))
    vs = _nomes(f"<html lang='pt'><title>t</title><body>{campos}</body></html>")
    sem_label = [v for v in vs if "sem rótulo" in v.description]
    assert 1 <= len(sem_label) <= 3
    assert "omitida" in _desc(sem_label)


def test_versao_muda_com_o_codigo():
    assert len(ruleset_version()) >= 8
