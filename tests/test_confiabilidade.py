import json

import pytest
from openpyxl import load_workbook

from src.evaluation import ancoragem, auditoria, estabilidade
from src.evaluation.stats import wilson


def test_wilson_valores_conhecidos():
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.237, abs=0.002) and hi == pytest.approx(0.763, abs=0.002)
    assert wilson(0, 0) is None and wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == 1.0


def test_ancoragem_classifica():
    texto = ancoragem._compacto("Buscar por: Uso de água. Termos pesquisáveis: Número do cadastro")
    assert ancoragem.classificar({"kind": "texto", "quote": "Uso de ÁGUA", "region": ""}, texto) == "ancorado"
    assert ancoragem.classificar({"kind": "texto", "quote": "Limpar filtros", "region": ""}, texto) == "nao_ancorado"
    assert ancoragem.classificar({"kind": "texto", "quote": "  ", "region": ""}, texto) == "sem_citacao"
    assert ancoragem.classificar({"kind": "visual", "quote": "", "region": "topo"}, texto) == "visual"
    assert ancoragem.classificar(None, texto) == "sem_campo"


def test_ancoragem_texto_da_pagina_inclui_atributos(tmp_path):
    h = tmp_path / "e.html"
    h.write_text("<html><body><p>Olá</p><input placeholder='Pesquisar por nome do local'><script>var x='oculto'</script></body></html>",
                 encoding="utf-8")
    t = ancoragem.texto_da_pagina(h)
    assert ancoragem._compacto("pesquisar por nome do local") in t and "oculto" not in t


def _run(descricoes):
    return {"estados": [{"nome": "home", "ordem": 1, "relatorio": {"violations": [
        {"source": "llm", "heuristic": "H04", "description": d, "evidence": None} for d in descricoes]}}]}


def test_estabilidade_agrupa_achados_parecidos():
    r0 = estabilidade.achados_do_run(_run(["O botão Limpar fica escondido no canto inferior", "Rótulo ambíguo no campo Termo"]))
    r1 = estabilidade.achados_do_run(_run(["O botão Limpar está escondido no canto inferior da tela"]))
    r2 = estabilidade.achados_do_run(_run(["O botão Limpar fica escondido no canto inferior", "Ícone sem legenda no menu"]))
    grupos = estabilidade.agrupar([r0, r1, r2], limiar=0.5)
    tamanhos = sorted(len(g) for g in grupos)
    assert tamanhos == [1, 1, 3]
    res = estabilidade.resumo_grupos(grupos, 3)
    assert res["achados"] == 5 and res["achados_reproduzidos"] == pytest.approx(3 / 5)


def _itens():
    return [{"config": c, "fluxo": "p12", "run": 0, "finding_id": i, "estado": "e", "heuristica": "H01", "severidade": 2,
             "local": "l", "descricao": f"d{c}{i}", "justificativa": "j", "evidencia_tipo": "texto", "evidencia": "q",
             "captura": "x.png", "ancoragem": "ancorado" if i % 2 else "nao_ancorado"}
            for c, n in (("hibrido", 30), ("llm", 50)) for i in range(n)]


def test_sorteio_e_deterministico_e_cego():
    a = auditoria.sortear(_itens(), n=40, semente=7)
    b = auditoria.sortear(_itens(), n=40, semente=7)
    assert [x["descricao"] for x in a] == [x["descricao"] for x in b] and len(a) == 40
    assert {x["config"] for x in a} == {"hibrido", "llm"} and [x["id"] for x in a] == list(range(1, 41))


def test_sorteio_igualitario_divide_n_entre_configuracoes():
    a = auditoria.sortear(_itens(), n=40, semente=3, igualitaria=True)
    assert len(a) == 40 and sum(x["config"] == "hibrido" for x in a) == 20 and sum(x["config"] == "llm" for x in a) == 20


def test_gravar_e_calcular_ciclo_completo(tmp_path):
    amostra = auditoria.sortear(_itens(), n=40, semente=1)
    totais = {"hibrido": {"achados_llm": 60, "com_par": 30, "sem_par": 30}, "llm": {"achados_llm": 80, "com_par": 30, "sem_par": 50}}
    arq = auditoria.gravar(amostra, totais, tmp_path)
    assert "Amostra" in load_workbook(arq["planilha"]).sheetnames
    wb = load_workbook(arq["planilha"]); ws = wb["Amostra"]
    cab = [c.value for c in ws[1]]; iv = cab.index("VEREDITO") + 1; it = cab.index("TIPO DO ERRO") + 1
    chave = {a["id"]: a for a in amostra}
    for r in range(2, ws.max_row + 1):
        i = ws.cell(row=r, column=1).value
        nao = chave[i]["ancoragem"] == "nao_ancorado"
        ws.cell(row=r, column=iv, value="não procedente" if nao else "procedente")
        if nao:
            ws.cell(row=r, column=it, value="inexistente na captura")
    wb.save(arq["planilha"])
    res = auditoria.calcular(arq["planilha"], arq["chave"], arq["populacao"])
    assert res["auditados"] == 40
    assert res["ancoragem_vs_veredito"]["sensibilidade"] == 1.0 and res["ancoragem_vs_veredito"]["especificidade"] == 1.0
    for cfg, t in totais.items():
        p = res["por_config"][cfg]
        assert 0 <= p["precisao_estimada"] <= 1 and p["taxa_nao_procedente_ic95"][0] <= p["taxa_nao_procedente"] <= p["taxa_nao_procedente_ic95"][1]


def test_relatorio_html_autocontido(tmp_path):
    from src import relatorio_html
    run = {"metadata": {"configuracao": "hibrido", "run_id": 0, "modelo": "m", "data_hora": "d"}, "flow_id": "f", "site": "s",
           "estados": [{"ordem": 1, "nome": "home", "url_no_momento": "u", "relatorio": {"url": "u", "total_violations": 2, "violations": [
               {"rank": 1, "heuristic": "H01_visibilidade_do_estado_do_sistema", "severity_effective": 4, "criticality_index": 2.4,
                "severity_original": 3, "severity_revised": 4, "source": "motor_de_regras", "location": "div.x", "description": "<b>d</b>",
                "justification": "j", "recommendation": "r", "revision_rationale": "porque", "evidence": None},
               {"rank": 2, "heuristic": "H04_consistencia_e_padronizacao", "severity_effective": 2, "criticality_index": 1.0,
                "severity_original": 2, "severity_revised": None, "source": "llm", "location": "l", "description": "d", "justification": "j",
                "recommendation": "r", "revision_rationale": None, "evidence": {"kind": "texto", "quote": "Olá", "region": ""}}]}}]}
    rj = tmp_path / "run_0.json"; rj.write_text(json.dumps(run), encoding="utf-8")
    h = tmp_path / "e.html"; (tmp_path / "estado_01_home.html").write_text("<body>Olá mundo</body>", encoding="utf-8")
    out = relatorio_html.gerar_html(rj, h, tmp_path)
    t = out.read_text(encoding="utf-8")
    assert "&lt;b&gt;d&lt;/b&gt;" in t and "citação confirmada" in t and "hipóteses geradas" in t and "src=\"http" not in t


def _chromium_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_ok(), reason="Chromium do Playwright indisponível")
def test_exploracao_respeita_exclusoes(tmp_path):
    from src.exploracao import explorar
    (tmp_path / "i.html").write_text(
        "<body><button onclick=\"c.textContent='A'\">Opção A</button><a href='mailto:a@b.c'>Contato</a><a href='/sair'>Sair</a>"
        "<a href='https://externo.example.com'>Externo</a><form><button type='submit'>Enviar</button></form><div id=c>início</div></body>",
        encoding="utf-8")
    url = (tmp_path / "i.html").as_uri()
    r = explorar({"id": "t", "url": url, "site": "t", "exploracao": {"max_profundidade": 1}}, tmp_path / "saida", silencioso=True)
    assert r["parada"] == "saturacao" and len(r["estados"]) == 2
    assert {"origem_externa", "esquema", "texto_de_risco"} <= set(r["pontos"][0]["exclusoes_por_motivo"])
    roteiro = json.loads((tmp_path / "saida" / "roteiro_t.json").read_text(encoding="utf-8"))[0]
    assert roteiro["estados"][1]["acoes"][-2]["tipo"] == "clicar"


def test_curadoria_remove_quase_duplicados():
    from src.curadoria import selecionar
    base = " ".join(f"p{i}" for i in range(40))
    est = [{"nome": "a", "profundidade": 0, "texto": base},
           {"nome": "b", "profundidade": 1, "texto": base + " novo"},
           {"nome": "c", "profundidade": 1, "texto": base + " " + " ".join(f"q{i}" for i in range(30))}]
    assert [e["nome"] for e in selecionar(est, 0.9)] == ["a", "c"]
    assert [e["nome"] for e in selecionar(est, 0.9, max_estados=1)] == ["a"]


def test_css_embutido():
    from src.css_embutido import embutir, folhas_externas
    h = '<head><link rel="stylesheet" href="/a.css"><link rel="icon" href="i.png"><link href=b.css rel=stylesheet></head>'
    assert folhas_externas(h, "https://s.com/x/#/") == ["https://s.com/a.css", "https://s.com/x/b.css"]
    novo, r = embutir(h, "https://s.com/x/#/", lambda u: "p{color:red}" if u.endswith("a.css") else None)
    assert "<style data-origem=" in novo and "p{color:red}" in novo
    assert r["embutidas"] == 1 and r["falhas"] == ["https://s.com/x/b.css"]
    assert 'rel="icon"' in novo


def test_css_embutido_folha_ausente():
    from src.css_embutido import embutir
    h = '<head><link rel="stylesheet" href="x.css"></head>'
    novo, r = embutir(h, "https://s.com/", lambda u: "")
    assert 'data-status="ausente"' in novo and "<link" not in novo
    assert r["ausentes"] == ["https://s.com/x.css"] and r["embutidas"] == 0 and not r["falhas"]


def test_css_embutido_resolve_import():
    from src.css_embutido import embutir
    h = ('<head><style data-origem="https://s.com/css/a.css">@import url(https://f.com/css2?family=X:wght@0,300;1,500&display=swap);'
         'p{color:red}</style></head>')
    novo, _ = embutir(h, "https://s.com/", lambda u: "@font-face{font-family:X}" if u.startswith("https://f.com/") else None)
    assert "@import url" not in novo and "@font-face{font-family:X}" in novo and "p{color:red}" in novo
    novo2, _ = embutir(h, "https://s.com/", lambda u: "")
    assert "@import ausente no servidor" in novo2


def test_tem_css_externo_ignora_import_comentado():
    from src.frozen import _tem_css_externo
    assert not _tem_css_externo("<style>/* @import https://f.com/x */ p{color:red}</style>")
    assert _tem_css_externo("<style>@import url(https://f.com/x);</style>")
    assert _tem_css_externo('<link rel="stylesheet" href="a.css">')
