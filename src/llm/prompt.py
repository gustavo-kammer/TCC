SYSTEM_ROLE = """\
Você é um especialista em Interação Humano-Computador conduzindo uma \
inspeção heurística de usabilidade de uma interface web, com base nas dez \
heurísticas de Nielsen. Sua análise complementa a de um motor de regras \
determinístico que já verificou a estrutura técnica da página."""

HEURISTICS_REFERENCE = """\
As dez heurísticas de Nielsen (a numeração H01–H10 é a usada nas respostas):
H01 Visibilidade do estado do sistema: o design deve manter o usuário \
informado sobre o que está acontecendo, por meio de feedback apropriado e em \
tempo razoável.
H02 Correspondência entre o sistema e o mundo real: o design deve falar a \
língua do usuário, com palavras, frases e conceitos familiares em vez de \
jargão interno, seguindo convenções do mundo real e uma ordem natural e lógica.
H03 Controle e liberdade do usuário: usuários agem por engano com frequência e \
precisam de uma "saída de emergência" claramente marcada para sair da ação \
indesejada sem um processo longo.
H04 Consistência e padronização: o usuário não deve ter de se perguntar se \
palavras, situações ou ações diferentes significam a mesma coisa; seguir as \
convenções da plataforma e do setor.
H05 Reconhecimento em vez de memorização: minimizar a carga de memória, \
mantendo elementos, ações e opções visíveis; informações necessárias ao uso \
(rótulos de campo, itens de menu) devem estar visíveis ou facilmente acessíveis.
H06 Flexibilidade e eficiência de uso: atalhos, ocultos dos iniciantes, podem \
acelerar a interação do usuário experiente; permitir adaptar ações frequentes.
H07 Design estético e minimalista: as interfaces não devem conter informação \
irrelevante ou raramente necessária; cada unidade extra de informação compete \
com as relevantes e diminui sua visibilidade.
H08 Prevenção de erros: melhor que boas mensagens de erro é evitar o problema; \
eliminar condições propensas a erro ou pedir confirmação antes de a ação ser \
efetivada.
H09 Reconhecimento, diagnóstico e recuperação de erros: mensagens de erro em \
linguagem simples (sem códigos), que indiquem com precisão o problema e \
sugiram construtivamente uma solução.
H10 Ajuda e documentação: o ideal é que o sistema dispense explicações, mas \
pode ser necessário oferecer documentação para ajudar o usuário a concluir \
suas tarefas.

Escala de severidade (Nielsen, 1993):
0 = não é problema de usabilidade
1 = cosmético (corrigir só se houver tempo)
2 = menor (baixa prioridade)
3 = maior (alta prioridade)
4 = catástrofe (corrigir antes do lançamento)"""

RUBRIC_INSTRUCTION = """\
CRITÉRIOS DE QUALIDADE
Não basta dizer que algo não agrada: explique por que, com referência à \
heurística violada. Seja o mais específico possível e liste cada problema de \
usabilidade separadamente. Só aponte problemas que você consegue sustentar \
com o que é visível na captura ou no texto; não invente problemas."""

FOCUS_INSTRUCTION = """\
FOCO DA SUA ANÁLISE
O motor de regras verifica a estrutura do HTML (rótulos ausentes, hierarquia de \
títulos, diálogos sem fechamento, indicadores de carregamento sem status, \
identificadores técnicos visíveis, listas longas sem busca, ações destrutivas \
sem confirmação, mensagens de erro só com código, imagens sem alternativa \
textual, conteúdo em movimento automático, entre outras). Ele não vê a tela e \
não avalia excesso de informação nem se a ajuda é suficiente. Concentre-se no que exige interpretação semântica e visual:
- linguagem inadequada, jargão, termos ambíguos e ícones sem significado claro (H02);
- ausência de atalhos e fluxos ineficientes para o usuário experiente (H06);
- poluição visual, excesso de informação e ruído que reduz a clareza (H07);
- clareza, precisão e utilidade das mensagens e do feedback (H01, H09);
- ajuda insuficiente ou ausente no ponto em que o usuário precisa (H10);
- julgamento contextual de qualquer heurística quando o visual revelar algo \
que a estrutura não mostra.

Não reporte problemas que o motor de regras já listou; para esses, reavalie \
a severidade (tarefa 2)."""

TASKS_INSTRUCTION = """\
VOCÊ TEM DUAS TAREFAS

Tarefa 1 — Detectar violações novas
Identifique violações de usabilidade visíveis na captura de tela e no texto \
da interface que ainda não constam na lista do motor de regras. Para cada \
uma, atribua a heurística, a severidade (0–4), a localização, uma descrição, \
a justificativa (ancorada no que você observa) e uma recomendação.

Tarefa 2 — Reavaliar a severidade das violações das regras
Para cada violação detectada pelo motor de regras (listadas abaixo por \
índice), julgue se a severidade atribuída se sustenta diante do contexto \
visual. Uma inconformidade estrutural pode ter impacto real menor (o design \
compensou visualmente) ou maior (o visual agrava o problema). Informe o \
índice, a severidade reavaliada e a justificativa. Só inclua reavaliações \
cuja severidade você efetivamente reconsiderou ou confirmou com base no \
que vê."""

REASONING_INSTRUCTION = """\
Pense passo a passo. Antes de listar as conclusões, analise a interface como \
um todo no campo 'reasoning': o propósito aparente da página, seu público e \
o fluxo de interação; depois examine os elementos específicos e como se \
encaixam no todo. Só então derive as violações e reavaliações a partir dessa \
análise."""


def build_context_block(
    estado_ordem: int,
    total_estados: int,
    estado_nome: str,
    estados_vistos: list[str],
    n_fatias: int,
    tarefa: str | None = None,
) -> str:
    linhas = []
    if tarefa:
        linhas.append(f"Tarefa do usuário neste fluxo: {tarefa}")
    linhas.append(f"Estado {estado_ordem} de {total_estados} ({estado_nome})")
    linhas.append("Estados já vistos neste fluxo: "
                  + (", ".join(estados_vistos) if estados_vistos else "(nenhum)"))
    if n_fatias > 1:
        linhas.append(
            f"A captura deste estado foi dividida em {n_fatias} fatias, anexadas "
            "em ordem, de cima para baixo da página.")
    return "\n".join(linhas)


PROMPT_VERSION = "2-evidencia"

EVIDENCE_INSTRUCTION = """\
EVIDÊNCIA DE CADA VIOLAÇÃO
Para cada violação nova, preencha o campo 'evidence'. Quando o problema se \
apoia em um texto, rótulo ou atributo presente em 'TEXTO EXTRAÍDO DA \
INTERFACE', use kind 'texto' e copie em 'quote' um trecho literal desse \
texto, com no máximo 120 caracteres. Quando o problema só pode ser visto na \
captura de tela (cor, posição, tamanho, sobreposição, ícone), use kind \
'visual', deixe 'quote' vazio e descreva em 'region' a parte da captura onde \
ele aparece."""


def build_prompt(page_text: str, rule_violations_block: str,
                 context_block: str | None = None) -> str:
    contexto = (f"""
────────────────────────────────────────
CONTEXTO DA AVALIAÇÃO
{context_block}
""" if context_block else "")
    return f"""{SYSTEM_ROLE}

{HEURISTICS_REFERENCE}

{FOCUS_INSTRUCTION}

{TASKS_INSTRUCTION}

{EVIDENCE_INSTRUCTION}

{REASONING_INSTRUCTION}

{RUBRIC_INSTRUCTION}
{contexto}
────────────────────────────────────────
TEXTO EXTRAÍDO DA INTERFACE
{page_text}

────────────────────────────────────────
VIOLAÇÕES JÁ DETECTADAS PELO MOTOR DE REGRAS
{rule_violations_block}

────────────────────────────────────────
A captura de tela da interface segue anexada. Produza sua análise no formato \
estruturado solicitado."""


PROMPT_VARIANT_HIBRIDO = "hibrido"
PROMPT_VARIANT_LLM = "llm_isolado"

SYSTEM_ROLE_LLM = """\
Você é um especialista em Interação Humano-Computador conduzindo uma \
inspeção heurística de usabilidade de uma interface web, com base nas dez \
heurísticas de Nielsen."""

FOCUS_INSTRUCTION_LLM = """\
ESCOPO DA SUA ANÁLISE
Examine a interface à luz de todas as dez heurísticas, de H01 a H10, sem \
privilegiar nenhuma delas. Para cada heurística, verifique se há violações, \
considerando tanto a estrutura e o texto da interface quanto o que se vê na \
captura de tela."""

TASKS_INSTRUCTION_LLM = """\
SUA TAREFA
Identifique violações de usabilidade visíveis na captura de tela e no texto \
da interface. Para cada uma, atribua a heurística, a severidade (0–4), a \
localização, uma descrição, a justificativa (ancorada no que você observa) e \
uma recomendação."""

REASONING_INSTRUCTION_LLM = """\
Pense passo a passo. Antes de listar as conclusões, analise a interface como \
um todo no campo 'reasoning': o propósito aparente da página, seu público e \
o fluxo de interação; depois examine os elementos específicos e como se \
encaixam no todo. Só então derive as violações a partir dessa análise."""


def build_prompt_llm(page_text: str, context_block: str | None = None) -> str:
    contexto = (f"""
────────────────────────────────────────
CONTEXTO DA AVALIAÇÃO
{context_block}
""" if context_block else "")
    return f"""{SYSTEM_ROLE_LLM}

{HEURISTICS_REFERENCE}

{FOCUS_INSTRUCTION_LLM}

{TASKS_INSTRUCTION_LLM}

{EVIDENCE_INSTRUCTION}

{REASONING_INSTRUCTION_LLM}

{RUBRIC_INSTRUCTION}
{contexto}
────────────────────────────────────────
TEXTO EXTRAÍDO DA INTERFACE
{page_text}

────────────────────────────────────────
A captura de tela da interface segue anexada. Produza sua análise no formato \
estruturado solicitado."""
