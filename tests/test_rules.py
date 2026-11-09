import json
from pathlib import Path

import pytest

from src.models import ExtractionResult, Heuristic
from src.rules.base import all_rules
from src.rules.engine import run_rules
import src.rules.checks

RAIZ = Path(__file__).resolve().parents[1]
HTML = RAIZ / "interfaces" / "calibracao"
GAB = RAIZ / "gabarito" / "calibracao"


def _regras(html: str):
    return run_rules(ExtractionResult(url="t", html=html))


SEM_REGRA_NA_CALIBRACAO = {Heuristic.H07_ESTETICA, Heuristic.H10_AJUDA}


def test_toda_regra_tem_fundamentacao_conforme_os_criterios():
    from src.rules.fundamentacao import AXE, FONTE_PARCIAL, FUNDAMENTACAO
    nomes = {r.__name__ for r in all_rules()}
    assert nomes == set(FUNDAMENTACAO) == set(AXE), nomes ^ set(FUNDAMENTACAO)
    for nome, (h, que, fonte, dec, obj, lim, veredito) in FUNDAMENTACAO.items():
        assert fonte and que and veredito in ("Conforme", "Parcial"), nome
        assert (veredito == "Conforme") == (dec == "Sim" and obj == "Sim" and nome not in FONTE_PARCIAL), nome
        if veredito == "Parcial":
            assert lim != "—", f"{nome}: regra parcial precisa declarar a limitação"


@pytest.mark.parametrize("n", range(1, 11))
def test_calibracao_aciona_so_a_heuristica_plantada(n):
    gab = json.loads((GAB / f"calib_{n:02d}.json").read_text(encoding="utf-8"))
    plantada = Heuristic(gab["violacoes_gabarito"][0]["heuristic"])
    vs = _regras((HTML / f"calib_{n:02d}.html").read_text(encoding="utf-8"))
    if plantada in SEM_REGRA_NA_CALIBRACAO:
        assert vs == []
    else:
        assert vs and {v.heuristic for v in vs} == {plantada}


def test_elementos_ocultos_nao_geram_violacao():
    html = ('<html><head><title>t</title></head><body><h1>x</h1>'
            '<div style="display: none"><div class="spinner"></div>'
            '<button>Excluir conta</button><input type="text"></div></body></html>')
    assert [v.heuristic for v in _regras(html)
            if v.heuristic in (Heuristic.H01_VISIBILIDADE, Heuristic.H08_PREVENCAO_ERROS,
                               Heuristic.H05_RECONHECIMENTO)] == []


def test_acao_destrutiva_com_confirmacao_nao_dispara():
    html = ('<html><head><title>t</title></head><body><h1>x</h1>'
            '<button data-confirm="Tem certeza?">Excluir conta</button></body></html>')
    assert not any(v.heuristic == Heuristic.H08_PREVENCAO_ERROS for v in _regras(html))


def test_mensagem_de_erro_com_orientacao_nao_dispara():
    html = ('<html><head><title>t</title></head><body><h1>x</h1>'
            '<div role="alert">Erro 500. Tente novamente em alguns minutos.</div></body></html>')
    assert not any(v.heuristic == Heuristic.H09_RECUPERACAO_ERROS for v in _regras(html))


def test_toda_heuristica_tem_ao_menos_uma_regra():
    from src.rules.fundamentacao import FUNDAMENTACAO
    heuristicas = {h for h, *_ in FUNDAMENTACAO.values()}
    assert heuristicas == {f"H{n:02d}" for n in range(1, 11)}


def test_conteudo_em_movimento_automatico():
    base = '<html lang="pt"><head><title>t</title></head><body><h1>x</h1>{}</body></html>'
    dispara = _regras(base.format("<marquee>promo</marquee>"))
    assert [v.heuristic for v in dispara if v.heuristic == Heuristic.H07_ESTETICA]
    com_pausa = _regras(base.format('<marquee>promo</marquee><button>Pausar animação</button>'))
    assert not any(v.heuristic == Heuristic.H07_ESTETICA for v in com_pausa)
    css = _regras('<html lang="pt"><head><title>t</title><style>.a{animation: x 2s infinite}</style></head>'
                  '<body><h1>x</h1><div class="a">oi</div></body></html>')
    assert any(v.heuristic == Heuristic.H07_ESTETICA for v in css)
    definida_e_nao_usada = _regras('<html lang="pt"><head><title>t</title><style>.a{animation: x 2s infinite}</style></head>'
                                   '<body><h1>x</h1><div>oi</div></body></html>')
    assert not any(v.heuristic == Heuristic.H07_ESTETICA for v in definida_e_nao_usada)
    estatico = _regras(base.format("<p>texto</p>"))
    assert not any(v.heuristic == Heuristic.H07_ESTETICA for v in estatico)
