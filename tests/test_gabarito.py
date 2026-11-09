import json
import os
import subprocess
import sys
from pathlib import Path

from src.evaluation.experiment import evaluate, human_cells_from_calibration
from src.evaluation.gabarito import load_all
from src.models import Heuristic

RAIZ = Path(__file__).resolve().parents[1]


def test_carrega_os_10_gabaritos_de_calibracao():
    gabs = load_all(RAIZ / "gabarito" / "calibracao")
    assert len(gabs) == 10
    assert {g.violacoes_gabarito[0].heuristic for g in gabs} == set(Heuristic)
    assert all(len(g.violacoes_gabarito) == 1 for g in gabs)


def test_h02_usa_o_nome_curto():
    assert Heuristic.H02_CORRESPONDENCIA.value == "H02_correspondencia_sistema_mundo_real"


def test_verificar_isolamento():
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "verificar_isolamento.py")],
                       cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_evaluate_calibracao_com_saidas_simuladas(tmp_path):
    gabs = load_all(RAIZ / "gabarito" / "calibracao")
    cells = human_cells_from_calibration(gabs)
    assert len(cells) == 100 and sum(c.apontada for c in cells) == 10

    for i, g in enumerate(gabs):
        alvo = g.violacoes_gabarito[0]
        celulas = {h.value: {"nota": (alvo.severity.value if h == alvo.heuristic and i < 5 else 0),
                             "nota_por_origem": {"llm": 0, "motor_de_regras": 0},
                             "notas_execucoes": [0], "origens": []}
                   for h in Heuristic}
        agregado = {"metadata": {"n_execucoes": 1, "modelo": None, "regras_versao": "r"},
                    "celulas": celulas}
        destino = tmp_path / "out" / "agregado" / "regras" / f"{g.interface_id}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(agregado), encoding="utf-8")

    res = evaluate(cells, out_dir=tmp_path / "out", results_dir=tmp_path / "res")
    m = res["regras/todos"]
    assert (m.vp, m.fp, m.fn, m.vn) == (5, 0, 5, 90)
    assert m.precision == 1.0 and m.recall == 0.5
    assert m.kappa_somente_vp == 1.0
    for nome in ["metricas_por_configuracao.csv", "metricas_por_fluxo.csv",
                 "celulas_sistema_vs_humano.csv", "resumo.md"]:
        assert (tmp_path / "res" / nome).exists()
