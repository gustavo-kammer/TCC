import json

import pytest

import src.frozen as frozen
import src.llm.analyzer as analyzer
from src.llm.schemas import IsolatedAnalysis, SemanticAnalysis
from src.frozen import FrozenState, Flow, extract_frozen_state, load_flow
from src.llm.prompt import build_context_block, build_prompt
from src.models import ExtractionResult, Heuristic, Severity, Source, Violation
from src.orchestrator import aggregate_cells, aggregate_runs, inspect_flow
from src.prioritization import criticality_index, prioritize

H = Heuristic


def _v(h: Heuristic, s: int, source: Source = Source.REGRAS, loc: str = "x",
       revisada: int | None = None, conf: float | None = 1.0) -> Violation:
    return Violation(heuristic=h, severity=Severity(s), location=loc, description="d",
                     justification="j", recommendation="r", source=source, confidence=conf,
                     severity_revised=Severity(revisada) if revisada is not None else None)


def test_celula_recebe_o_maximo_entre_estados_e_zero_quando_ausente():
    estados = [
        (1, "home", [_v(H.H03_CONTROLE, 3), _v(H.H07_ESTETICA, 1, Source.LLM)]),
        (2, "lista", [_v(H.H03_CONTROLE, 1, loc="y"), _v(H.H07_ESTETICA, 2, Source.LLM)]),
        (3, "item", [_v(H.H05_RECONHECIMENTO, 3, revisada=2)]),
    ]
    c = aggregate_cells(estados)
    assert c[H.H03_CONTROLE.value].nota == 3
    assert c[H.H07_ESTETICA.value].nota == 2
    assert c[H.H05_RECONHECIMENTO.value].nota == 2
    assert all(c[h.value].nota == 0 for h in H
               if h not in (H.H03_CONTROLE, H.H07_ESTETICA, H.H05_RECONHECIMENTO))
    assert c[H.H07_ESTETICA.value].nota_por_origem == {"motor_de_regras": 0, "llm": 2}
    vs = c[H.H03_CONTROLE.value].violacoes
    assert [(v["estado_ordem"], v["estado_nome"], v["source"]) for v in vs] \
        == [(1, "home", "motor_de_regras"), (2, "lista", "motor_de_regras")]
    assert c[H.H05_RECONHECIMENTO.value].violacoes[0]["severity_original"] == 3


def test_agregacao_das_execucoes_por_mediana():
    def rep(run_id: int, notas: dict) -> object:
        from src.models import FlowReport
        estados = [(1, "e", [_v(h, n) for h, n in notas.items()])]
        return FlowReport(metadata={"run_id": run_id, "modelo": "m", "temperatura": 0.0,
                                    "seed": 1, "prompt_sha256": "h", "regras_versao": "r",
                                    "configuracao": "hibrido"},
                          flow_id="p01", site="s", tarefa="t", pasta=None, estados=[],
                          celulas=aggregate_cells(estados))
    reps = [rep(0, {H.H01_VISIBILIDADE: 1, H.H02_CORRESPONDENCIA: 1}),
            rep(1, {H.H01_VISIBILIDADE: 3}),
            rep(2, {H.H01_VISIBILIDADE: 2, H.H02_CORRESPONDENCIA: 2})]
    ag = aggregate_runs(reps)
    assert ag["celulas"][H.H01_VISIBILIDADE.value]["nota"] == 2
    assert ag["celulas"][H.H01_VISIBILIDADE.value]["notas_execucoes"] == [1, 3, 2]
    assert ag["celulas"][H.H02_CORRESPONDENCIA.value]["nota"] == 1
    ag2 = aggregate_runs(reps[:2])
    assert ag2["celulas"][H.H01_VISIBILIDADE.value]["nota"] == 2
    assert ag2["celulas"][H.H02_CORRESPONDENCIA.value]["nota"] == 1
    assert ag["metadata"]["n_execucoes"] == 3 and ag["metadata"]["run_ids"] == [0, 1, 2]


def test_prioritize_descarta_severidade_efetiva_zero():
    regra = _v(H.H05_RECONHECIMENTO, 3, loc="campo")
    revisada = _v(H.H05_RECONHECIMENTO, 3, loc="campo", revisada=0)
    nova_zero = _v(H.H07_ESTETICA, 0, Source.LLM)
    assert prioritize([regra], [nova_zero], [revisada]) == []


def test_indice_de_criticidade_e_ordenacao():
    a = _v(H.H01_VISIBILIDADE, 4, conf=0.4)
    b = _v(H.H02_CORRESPONDENCIA, 2, conf=1.0)
    c = _v(H.H03_CONTROLE, 3, conf=0.75)
    d = _v(H.H04_CONSISTENCIA, 2, conf=None)
    assert criticality_index(a) == pytest.approx(1.6)
    assert criticality_index(d) == pytest.approx(2.0)
    ordem = prioritize([a, b, c, d], [], [])
    assert [v.heuristic for v in ordem][:1] == [H.H03_CONTROLE]
    assert [v.heuristic for v in ordem][1:] == [H.H02_CORRESPONDENCIA, H.H04_CONSISTENCIA,
                                                H.H01_VISIBILIDADE]


schemas: list[type] = []
HTML_SEM_LABEL ="<html><head><title>t</title></head><body><input id='q'></body></html>"


@pytest.fixture
def llm_falso(monkeypatch):
    chamadas: list[list[dict]] = []
    schemas.clear()

    def fake_analyze(client, input_blocks, schema):
        chamadas.append(input_blocks)
        schemas.append(schema)
        return json.dumps({
            "reasoning": "r",
            "new_violations": [{"heuristic": H.H07_ESTETICA.value, "severity": 2,
                                "location": "topo", "description": "d",
                                "justification": "j", "recommendation": "r",
                                "evidence": {"kind": "visual", "quote": "", "region": "topo"}}],
            "severity_revisions": [{"rule_index": 0, "revised_severity": 1,
                                    "rationale": "visual compensa"}],
        })
    monkeypatch.setattr(analyzer, "analyze", fake_analyze)
    return chamadas


def _flow_e_extracao(n_fatias: int = 3) -> tuple[Flow, list[ExtractionResult]]:
    flow = Flow(id="tx", site="s", tarefa="Achar X.", locale="pt-BR", pasta=None,
                estados=[FrozenState(ordem=1, nome="home", url_no_momento="u1"),
                         FrozenState(ordem=2, nome="lista", url_no_momento="u2")])
    ex = [ExtractionResult(url=f"u{i}", html=HTML_SEM_LABEL, screenshots=["AA=="] * n_fatias)
          for i in (1, 2)]
    return flow, ex


def test_regras_nao_chama_llm(llm_falso):
    flow, ex = _flow_e_extracao()
    rep = inspect_flow(flow, "regras", extractions=ex, verbose=False)
    assert llm_falso == []
    assert rep.metadata["modelo"] is None and rep.metadata["prompt_sha256"] is None
    assert rep.metadata["prompt_variante"] is None
    assert rep.celulas[H.H05_RECONHECIMENTO.value].nota == 3


def test_llm_so_nao_tem_regras_nem_revisao(llm_falso):
    flow, ex = _flow_e_extracao()
    rep = inspect_flow(flow, "llm", client=object(), extractions=ex, verbose=False)
    assert len(llm_falso) == 2
    prompt = llm_falso[1][0]["text"]
    assert "regra" not in prompt.lower()
    assert "todas as dez heurísticas" in prompt
    assert "Estado 2 de 2 (lista)" in prompt
    assert schemas[-1] is IsolatedAnalysis
    assert "regra" not in json.dumps(IsolatedAnalysis.model_json_schema(),
                                     ensure_ascii=False).lower()
    assert [b["type"] for b in llm_falso[1]] == ["text", "image", "image", "image"]
    assert rep.metadata["prompt_variante"] == "llm_isolado"
    assert rep.celulas[H.H05_RECONHECIMENTO.value].nota == 0
    assert rep.celulas[H.H07_ESTETICA.value].nota == 2
    assert all(v["severity_revised"] is None
               for c in rep.celulas.values() for v in c.violacoes)
    assert rep.metadata["regras_versao"] is None


def test_hibrido_envia_todas_as_fatias_e_contexto(llm_falso):
    flow, ex = _flow_e_extracao(n_fatias=3)
    rep = inspect_flow(flow, "hibrido", run_id=7, client=object(), extractions=ex,
                       verbose=False)
    blocos = llm_falso[1]
    assert [b["type"] for b in blocos] == ["text", "image", "image", "image"]
    prompt = blocos[0]["text"]
    assert "Tarefa do usuário neste fluxo: Achar X." in prompt
    assert "Estado 2 de 2 (lista)" in prompt
    assert "Estados já vistos neste fluxo: home" in prompt
    h05 = rep.celulas[H.H05_RECONHECIMENTO.value]
    assert h05.nota == 1 and h05.violacoes[0]["severity_revised"] == 1
    assert rep.metadata["run_id"] == 7 and len(rep.metadata["prompt_sha256"]) == 64
    assert rep.metadata["temperatura"] is None
    assert rep.metadata["prompt_variante"] == "hibrido"
    assert schemas[-1] is SemanticAnalysis
    assert "VIOLAÇÕES JÁ DETECTADAS PELO MOTOR DE REGRAS" in prompt


def test_prompt_sem_contexto_mantem_o_texto_base():
    sem = build_prompt("T", "R")
    assert "CONTEXTO DA AVALIAÇÃO" not in sem
    com = build_prompt("T", "R", build_context_block(1, 3, "home", [], 1, None))
    assert com.replace(com[com.index("\n────────────────────────────────────────\nCONTEXTO"):
                           com.index("\n────────────────────────────────────────\nTEXTO")],
                       "") == sem


def test_load_flow_p12():
    flow = load_flow("p12")
    assert flow.tarefa
    assert [e.nome for e in flow.estados][:2] == ["modal_temas", "mapa_inicial"]
    assert all(e.fatias for e in flow.estados)
    assert all(p.exists() for e in flow.estados for p in [*e.fatias, e.html])


@pytest.mark.parametrize("fid,n_estados", [("p12", 7), ("p13", 3)])
def test_fluxos_externos_carregam_sem_bloqueio(fid, n_estados):
    assert len(load_flow(fid).estados) == n_estados


def test_load_flow_rejeita_alerta_de_bloqueio(tmp_path):
    pasta = tmp_path / "px" / "20260101"
    pasta.mkdir(parents=True)
    (pasta / "meta.json").write_text(json.dumps({"estados": [
        {"ordem": 1, "nome": "home", "alertas": ["BLOQUEIO: anti-robô"]}]}), encoding="utf-8")
    sites = tmp_path / "sites.json"
    sites.write_text('[{"id": "px", "site": "s", "tarefa": "t"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="bloqueio"):
        load_flow("px", base=tmp_path, sites_json=sites)


def test_extracao_congelada_sem_rede():
    est = load_flow("p12").estados[1]
    ex = extract_frozen_state(est)
    assert len(ex.screenshots) == len(est.fatias) >= 1
    assert ex.html == est.html.read_text(encoding="utf-8")
    assert ex.computed_styles and ex.warnings == []


def test_extracao_congelada_fallback_beautifulsoup(monkeypatch):
    def falha(html, base_url):
        raise RuntimeError("sem navegador")
    monkeypatch.setattr(frozen, "_render_computed_styles", falha)
    ex = extract_frozen_state(load_flow("p12").estados[1])
    assert ex.warnings and "BeautifulSoup" in ex.warnings[0]
    assert any(el["text"] for el in ex.computed_styles)


def test_texto_da_pagina_usa_texto_proprio_sem_duplicar_e_mantem_repeticoes():
    from src.llm.analyzer import _format_page_text
    ex = ExtractionResult(url="u", html="", computed_styles=[
        {"tag": "div", "text": "Oi Aproveitar", "own_text": "", "attrs": ""},
        {"tag": "p", "text": "Oi", "own_text": "Oi", "attrs": ""},
        {"tag": "button", "text": "Aproveitar", "own_text": "Aproveitar", "attrs": ""},
        {"tag": "button", "text": "Aproveitar", "own_text": "Aproveitar", "attrs": ""},
        {"tag": "input", "text": "", "own_text": "", "attrs": "(48) 99999-0000"},
    ])
    linhas = _format_page_text(ex).splitlines()
    assert linhas[0] == "- [p] Oi"
    assert linhas.count("- [button] Aproveitar") == 2
    assert any("atributos: (48) 99999-0000" in l for l in linhas)
    assert len(linhas) == 4


def test_prompts_hibrido_e_llm_compartilham_definicoes_e_rubrica():
    from src.llm.prompt import (
        HEURISTICS_REFERENCE, RUBRIC_INSTRUCTION, build_prompt, build_prompt_llm)
    for prompt in (build_prompt("T", "R"), build_prompt_llm("T")):
        assert HEURISTICS_REFERENCE in prompt and RUBRIC_INSTRUCTION in prompt
    assert "motor de regras" not in build_prompt_llm("T").lower()
    for n in range(1, 11):
        assert f"H{n:02d} " in HEURISTICS_REFERENCE


def test_evidencia_chega_ao_relatorio(llm_falso):
    from src.llm.analyzer import analyze_isolated
    flow, ex = _flow_e_extracao(1)
    achados = analyze_isolated(ex[0])
    assert achados[0].evidence is not None and achados[0].evidence.kind == "visual"
    from src.report import build_report
    rel = build_report("u", achados)
    assert rel["violations"][0]["evidence"]["region"] == "topo"


def test_prompt_pede_evidencia_nas_duas_variantes():
    from src.llm.analyzer import build_isolated_prompt, build_semantic_prompt
    ex = ExtractionResult(url="u", html=HTML_SEM_LABEL, screenshots=["AA=="])
    assert "EVIDÊNCIA DE CADA VIOLAÇÃO" in build_isolated_prompt(ex)
    assert "EVIDÊNCIA DE CADA VIOLAÇÃO" in build_semantic_prompt(ex, [])


def test_run_com_outra_versao_de_prompt_e_invalidado(tmp_path):
    from src.orchestrator import _carregar_run_valida
    import inspect
    assert "prompt_versao" in inspect.getsource(_carregar_run_valida)
