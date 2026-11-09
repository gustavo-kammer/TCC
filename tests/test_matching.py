import json
from pathlib import Path

from src.evaluation import matching as M


def _juiz_falso(problemas, achados):
    return M.ResultadoCasamento(matches=[
        M.Par(problem_code="X-1", match="full", finding_id=1, rationale="ok"),
        M.Par(problem_code="X-2", match="partial", finding_id=2, rationale="ok"),
        M.Par(problem_code="X-3", match="none", finding_id=0, rationale="-")])


def _montar(tmp_path: Path) -> tuple[Path, Path]:
    raiz, out = tmp_path / "raiz", tmp_path / "out"
    g = raiz / "gabarito" / "observatorio"
    g.mkdir(parents=True)
    (g / "problemas.csv").write_text(
        "code,description,heuristics_raw,severity,pdf_page\n"
        "X-1,Problem one,N1,3,1\nX-2,Problem two,N2,2,1\nX-3,Problem three,N3,4,1\n",
        encoding="utf-8")
    run = out / "runs" / "hibrido" / "p12"
    run.mkdir(parents=True)
    viol = lambda h, s, d: {"heuristic": h, "severity_effective": s, "location": "loc", "description": d}
    (run / "run_0.json").write_text(json.dumps({"estados": [{"nome": "e1", "relatorio": {"violations": [
        viol("H01_x", 3, "a"), viol("H02_y", 1, "b"), viol("H03_z", 2, "c")]}}]}), encoding="utf-8")
    return raiz, out


def test_metricas_por_violacao(tmp_path):
    raiz, out = _montar(tmp_path)
    c = M.casar(raiz, out, "hibrido", "p12", 0, juiz=_juiz_falso)
    m = M.metricas_casamento([c])
    assert m["problemas"] == 3 and m["achados"] == 3
    assert m["recall_estrito"] == 1 / 3
    assert m["recall_ponderado"] == 1.5 / 3
    assert m["precisao_estrita"] == 1 / 3
    assert m["precisao_ponderada"] == 1.5 / 3
    assert m["n_pares_severidade"] == 2


def test_cache_e_validacao_de_indice(tmp_path):
    raiz, out = _montar(tmp_path)
    chamadas = []

    def juiz(p, a):
        chamadas.append(1)
        return M.ResultadoCasamento(matches=[
            M.Par(problem_code="X-1", match="full", finding_id=99, rationale="índice inválido")])
    c = M.casar(raiz, out, "hibrido", "p12", 0, juiz=juiz)
    assert all(m["match"] == "none" for m in c["matches"])
    M.casar(raiz, out, "hibrido", "p12", 0, juiz=juiz)
    assert len(chamadas) == 1


def test_amostra_e_concordancia(tmp_path):
    raiz, out = _montar(tmp_path)
    c = M.casar(raiz, out, "hibrido", "p12", 0, juiz=_juiz_falso)
    pub, chave = M.gerar_amostra([c], n_casou=2, n_nao=1)
    assert len(pub) == 3 and all("config" not in r for r in pub)
    for r in pub:
        r["SEU_VEREDITO"] = "concordo" if r["tipo"] == "casou" else "0"
    r = M.concordancia(pub, chave)
    assert r["acordo"] == 1.0 and r["n"] == 3


def test_cache_do_juiz_depende_do_modelo(tmp_path):
    import json
    from pathlib import Path
    from src.evaluation import matching as M
    chamadas = []

    def fake(modelo):
        def j(problemas, achados):
            chamadas.append(modelo)
            return M.ResultadoCasamento(matches=[M.Par(problem_code=p.code, match="none", finding_id=0, rationale="x") for p in problemas])
        j.modelo = modelo
        return j
    raiz = Path(__file__).resolve().parent.parent
    out = tmp_path / "out"
    (out / "runs" / "hibrido" / "p12").mkdir(parents=True)
    src = next((raiz / "output_v2" / "runs" / "hibrido" / "p12").glob("run_0.json"), None) or next((raiz / "output" / "runs" / "hibrido" / "p12").glob("run_*.json"), None)
    if src is None:
        import pytest; pytest.skip("sem run de exemplo")
    (out / "runs" / "hibrido" / "p12" / "run_0.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    M.casar(raiz, out, "hibrido", "p12", 0, juiz=fake("A"))
    M.casar(raiz, out, "hibrido", "p12", 0, juiz=fake("A"))
    M.casar(raiz, out, "hibrido", "p12", 0, juiz=fake("B"))
    assert chamadas == ["A", "B"]
    assert json.loads((out / "matching" / "hibrido" / "p12" / "run_0.json").read_text(encoding="utf-8"))["juiz_modelo"] == "B"
