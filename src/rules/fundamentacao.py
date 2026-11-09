from .base import all_rules
from . import checks

H = {1: "H01", 2: "H02", 3: "H03", 4: "H04", 5: "H05", 6: "H06", 7: "H07",
     8: "H08", 9: "H09", 10: "H10"}

FUNDAMENTACAO: dict[str, tuple[str, str, str, str, str, str, str]] = {
    "titulo_ausente": ("H01", "<title> ausente ou vazio", "WCAG 2.4.2 (A)",
                       "Sim", "Sim", "—", "Conforme"),
    "indicador_de_carregamento_sem_status": (
        "H01", "indicador de carregamento sem texto, nome acessível ou região de status",
        "WCAG 4.1.3 (AA), 1.1.1 (A)", "Parcial", "Sim",
        "indicador reconhecido por nome de classe (spinner, loader…); se o site o oculta por "
        "CSS externo ou JavaScript, o HTML estático não permite saber", "Parcial"),
    "valor_nao_tratado_visivel": ("H02", "textos 'undefined', 'NaN', '[object Object]', 'null' ou lorem ipsum visíveis",
                                  "Nielsen H02 (linguagem do usuário)", "Sim", "Sim",
                                  "cadeias literais fixas; tolera pontuação ao redor, mas o texto deve ser só o valor", "Conforme"),
    "identificador_tecnico_visivel": ("H02", "identificadores snake_case visíveis em rótulos, opções e textos",
                                      "Nielsen H02 (jargão interno)", "Sim", "Sim",
                                      "só detecta identificadores de código; jargão em linguagem natural fica com o LLM",
                                      "Conforme"),
    "lang_ausente": ("H02", "atributo lang ausente em <html>", "WCAG 3.1.1 (A)", "Sim", "Sim", "—", "Conforme"),
    "dialogo_sem_fechar": ("H03", "diálogo modal visível sem controle para fechar",
                           "Nielsen H03 (saída de emergência); WAI-ARIA APG (diálogo modal)", "Sim", "Parcial",
                           "controle de fechar identificado por léxico fixo (×, fechar, close, data-dismiss)",
                           "Parcial"),
    "conteudo_automatico_sem_controle": ("H03", "mídia com autoplay sem controls; <meta refresh> com tempo",
                                         "WCAG 1.4.2 (A), 2.2.1 (A)", "Sim", "Sim", "—", "Conforme"),
    "hierarquia_de_titulos": ("H04", "salto de nível entre títulos (ex.: h1 → h4)",
                              "axe heading-order (boa prática); WCAG técnica G141 (advisória)", "Sim", "Sim",
                              "o axe classifica como boa prática, sem critério WCAG de conformidade", "Parcial"),
    "pagina_sem_titulos": ("H04", "página sem nenhum título h1–h6", "WCAG 2.4.10 (AAA)",
                           "Sim", "Sim",
                           "critério de nível AAA; sem regra equivalente no axe", "Parcial"),
    "imagem_sem_alternativa": ("H04", "<img> sem atributo alt", "WCAG 1.1.1 (A)", "Sim", "Sim",
                               "mapeamento para H04 (padrões da plataforma) é escolha do autor", "Conforme"),
    "input_sem_label": ("H05", "campo de formulário sem rótulo acessível", "WCAG 1.3.1, 3.3.2, 4.1.2 (A)",
                        "Sim", "Sim", "—", "Conforme"),
    "controle_so_com_icone_sem_nome": ("H05", "botão/link sem texto nem nome acessível",
                                       "WCAG 4.1.2, 2.4.4, 1.1.1 (A)", "Sim", "Sim", "—", "Conforme"),
    "link_texto_ambiguo": ("H05", "mesmo texto de link com destinos diferentes",
                           "WCAG 2.4.9 (AAA); axe identical-links-same-purpose", "Sim", "Sim",
                           "critério de nível AAA (fora do alvo A/AA)", "Parcial"),
    "tabela_sem_cabecalhos": ("H05", "tabela de dados sem <th>", "WCAG 1.3.1 (A), técnica H43",
                              "Sim", "Sim", "—", "Conforme"),
    "conteudo_em_movimento_automatico": (
        "H07", "<marquee>, <blink>, carrossel automático ou animação CSS infinita sem controle de pausa",
        "WCAG 2.2.2 (A); Nielsen H07 (o extra compete com o relevante)", "Parcial", "Sim",
        "só enxerga movimento declarado no HTML ou em <style>/style inline; animações de CSS externo ou "
        "JavaScript não aparecem; o mapeamento distração → H07 é escolha do autor", "Parcial"),
    "lista_longa_sem_busca_ou_filtro": (
        "H06", "tabela com ≥ 10 linhas ou lista com ≥ 15 itens sem busca, filtro ou ordenação",
        "Nielsen H06 (aceleradores); WCAG 2.4.5 apenas por analogia", "Sim", "Parcial",
        "limiares 10 e 15 são convenção do autor (análise de sensibilidade); busca/filtro por léxico",
        "Parcial"),
    "blocos_repetidos_sem_atalho": ("H06", "navegação sem link de pular nem marco <main>", "WCAG 2.4.1 (A)",
                                    "Sim", "Sim", "—", "Conforme"),
    "acao_destrutiva_sem_protecao": (
        "H08", "ação destrutiva (excluir, apagar, remover…) sem confirmação nem aviso de irreversibilidade",
        "WCAG 3.3.4 (AA); Nielsen H08", "Parcial", "Parcial",
        "confirmação feita por JavaScript não aparece no HTML estático; verbos destrutivos por léxico",
        "Parcial"),
    "campo_sem_tipo_semantico": ("H08", "campo type=text que aparenta coletar e-mail, telefone ou URL",
                                 "WCAG 1.3.5 (AA); HTML (tipos de input); Nielsen H08", "Sim", "Parcial",
                                 "finalidade do campo inferida por léxico em name/id/placeholder", "Parcial"),
    "campo_obrigatorio_sem_marcacao": ("H08", "rótulo indica obrigatório (*, 'obrigatório') mas o campo não tem required",
                                       "WCAG 3.3.2 (A), 4.1.2 (A)", "Sim", "Parcial",
                                       "indicação de obrigatório por léxico fixo (*, obrigat, required)", "Parcial"),
    "mensagem_de_erro_so_com_codigo": ("H09", "mensagem de erro com código técnico e sem orientação",
                                       "Nielsen H09 (sem códigos); WCAG 3.3.1, 3.3.3", "Sim", "Parcial",
                                       "contêiner de erro e palavras de orientação por léxico", "Parcial"),
    "campo_invalido_sem_mensagem": ("H09", "aria-invalid sem mensagem associada", "WCAG 3.3.1 (A)",
                                    "Sim", "Sim", "—", "Conforme"),
    "ausencia_de_ajuda_ou_busca": ("H10", "nenhum link de ajuda/FAQ nem campo de busca",
                                   "Nielsen H10", "Sim", "Parcial",
                                   "a presença é objetiva, mas se o sistema precisa de ajuda é julgamento "
                                   "(WCAG 3.2.6 só exige consistência quando a ajuda existe); severidade 1, confiança 0,4",
                                   "Parcial"),
    "viewport_bloqueia_zoom": ("H03", "<meta viewport> com user-scalable=no ou maximum-scale < 2",
                               "WCAG 1.4.4 (AA); Nielsen H03 (controle do usuário)", "Sim", "Sim",
                               "limiar de maximum-scale segue o axe meta-viewport", "Conforme"),
    "campo_sem_autocomplete": ("H08", "campo de dado pessoal (e-mail, telefone, nome, endereço) sem autocomplete",
                               "WCAG 1.3.5 (AA), técnica H98; Nielsen H08", "Sim", "Parcial",
                               "finalidade do campo inferida por type e léxico em name/id/placeholder; "
                               "não distingue dado do próprio usuário de dado de terceiro", "Parcial"),
    "contraste_insuficiente": ("H05", "contraste texto/fundo abaixo de 4,5:1 (3:1 para texto grande)",
                               "WCAG 1.4.3 (AA); axe color-contrast", "Parcial", "Sim",
                               "exige CSS carregado na extração; ignora fundo com imagem, gradiente, "
                               "sobreposição ou opacidade de ancestral; mapeamento para H05 é escolha do autor",
                               "Parcial"),
    "alvo_de_toque_pequeno": ("H08", "alvo interativo < 24x24 px sem espaçamento suficiente em relação a outros",
                              "WCAG 2.5.8 (AA); axe target-size", "Parcial", "Sim",
                              "exige CSS e layout renderizados; links em linha de texto são exceção; "
                              "mapeamento para H08 é escolha do autor", "Parcial"),
}

AXE: dict[str, str] = {
    "titulo_ausente": "document-title", "indicador_de_carregamento_sem_status": "—",
    "valor_nao_tratado_visivel": "—", "identificador_tecnico_visivel": "—", "lang_ausente": "html-has-lang",
    "dialogo_sem_fechar": "— (aria-dialog-name trata só do nome)",
    "conteudo_automatico_sem_controle": "meta-refresh; no-autoplay-audio (experimental)",
    "hierarquia_de_titulos": "heading-order", "pagina_sem_titulos": "—", "imagem_sem_alternativa": "image-alt",
    "input_sem_label": "label", "controle_so_com_icone_sem_nome": "button-name; link-name",
    "link_texto_ambiguo": "identical-links-same-purpose", "tabela_sem_cabecalhos": "td-has-header; th-has-data-cells",
    "lista_longa_sem_busca_ou_filtro": "—", "blocos_repetidos_sem_atalho": "bypass",
    "conteudo_em_movimento_automatico": "marquee; blink (carrossel e CSS: sem equivalente)",
    "acao_destrutiva_sem_protecao": "—", "campo_sem_tipo_semantico": "autocomplete-valid (relacionada)",
    "campo_obrigatorio_sem_marcacao": "—", "mensagem_de_erro_so_com_codigo": "—",
    "campo_invalido_sem_mensagem": "—", "ausencia_de_ajuda_ou_busca": "—",
    "viewport_bloqueia_zoom": "meta-viewport", "campo_sem_autocomplete": "autocomplete-valid (só valida o valor)",
    "contraste_insuficiente": "color-contrast", "alvo_de_toque_pequeno": "target-size",
}

FONTE_PARCIAL = {"hierarquia_de_titulos", "pagina_sem_titulos", "link_texto_ambiguo"}

SEM_REGRA = {
    "H07 (excesso de informação e poluição visual)": "WCAG não define critério de excesso; indicadores por "
        "contagem (botões, avisos) exigiriam limiares sem fonte. A regra de H07 cobre só o movimento "
        "automático (WCAG 2.2.2); o restante fica com a camada LLM.",
    "H10 (suficiência da ajuda)": "a regra de H10 verifica só a presença de ajuda ou busca; avaliar se a "
        "ajuda é suficiente ou contextual depende de julgamento e fica com a camada LLM.",
}


def matriz_markdown() -> str:
    linhas = ["# Matriz de rastreabilidade das regras determinísticas", "",
              "Critérios: (1) decidível pelo HTML; (2) operacionalização objetiva; "
              "(3) fonte em Nielsen ou padrão aberto (WCAG 2.x).", "",
              "| Regra | Heurística | O que verifica | Fonte | Equivalente axe-core | (1) Decidível | (2) Objetiva | Limitação | Veredito |",
              "|---|---|---|---|---|---|---|---|---|"]
    for nome in sorted(FUNDAMENTACAO, key=lambda n: (FUNDAMENTACAO[n][0], n)):
        h, que, fonte, d, o, lim, v = FUNDAMENTACAO[nome]
        linhas.append(f"| `{nome}` | {h} | {que} | {fonte} | {AXE[nome]} | {d} | {o} | {lim} | {v} |")
    linhas += ["", "## Aspectos de H07 e H10 que as regras não cobrem", ""]
    linhas += [f"- **{h}**: {m}" for h, m in SEM_REGRA.items()]
    n_conf = sum(1 for t in FUNDAMENTACAO.values() if t[-1] == "Conforme")
    linhas += ["", f"Total: {len(FUNDAMENTACAO)} regras ({n_conf} conformes, "
               f"{len(FUNDAMENTACAO) - n_conf} parciais).", ""]
    return "\n".join(linhas)


if __name__ == "__main__":
    print(matriz_markdown())
