# Prompts enviados ao modelo (exemplo)

Cada chamada envia este texto + as fatias PNG do estado. O trecho 'TEXTO EXTRAÍDO' varia por página.

## Configuração híbrida (regras + LLM)

```
Você é um especialista em Interação Humano-Computador conduzindo uma inspeção heurística de usabilidade de uma interface web, com base nas dez heurísticas de Nielsen. Sua análise complementa a de um motor de regras determinístico que já verificou a estrutura técnica da página.

As dez heurísticas de Nielsen (a numeração H01–H10 é a usada nas respostas):
H01 Visibilidade do estado do sistema: o design deve manter o usuário informado sobre o que está acontecendo, por meio de feedback apropriado e em tempo razoável.
H02 Correspondência entre o sistema e o mundo real: o design deve falar a língua do usuário, com palavras, frases e conceitos familiares em vez de jargão interno, seguindo convenções do mundo real e uma ordem natural e lógica.
H03 Controle e liberdade do usuário: usuários agem por engano com frequência e precisam de uma "saída de emergência" claramente marcada para sair da ação indesejada sem um processo longo.
H04 Consistência e padronização: o usuário não deve ter de se perguntar se palavras, situações ou ações diferentes significam a mesma coisa; seguir as convenções da plataforma e do setor.
H05 Reconhecimento em vez de memorização: minimizar a carga de memória, mantendo elementos, ações e opções visíveis; informações necessárias ao uso (rótulos de campo, itens de menu) devem estar visíveis ou facilmente acessíveis.
H06 Flexibilidade e eficiência de uso: atalhos, ocultos dos iniciantes, podem acelerar a interação do usuário experiente; permitir adaptar ações frequentes.
H07 Design estético e minimalista: as interfaces não devem conter informação irrelevante ou raramente necessária; cada unidade extra de informação compete com as relevantes e diminui sua visibilidade.
H08 Prevenção de erros: melhor que boas mensagens de erro é evitar o problema; eliminar condições propensas a erro ou pedir confirmação antes de a ação ser efetivada.
H09 Reconhecimento, diagnóstico e recuperação de erros: mensagens de erro em linguagem simples (sem códigos), que indiquem com precisão o problema e sugiram construtivamente uma solução.
H10 Ajuda e documentação: o ideal é que o sistema dispense explicações, mas pode ser necessário oferecer documentação para ajudar o usuário a concluir suas tarefas.

Escala de severidade (Nielsen, 1993):
0 = não é problema de usabilidade
1 = cosmético (corrigir só se houver tempo)
2 = menor (baixa prioridade)
3 = maior (alta prioridade)
4 = catástrofe (corrigir antes do lançamento)

FOCO DA SUA ANÁLISE
O motor de regras já cobre bem o que é verificável na estrutura (rótulos ausentes, hierarquia de títulos, tipos de campo, diálogos sem fechamento). Concentre-se no que exige interpretação semântica e visual, que as regras não alcançam:
- H02: linguagem inadequada, jargão técnico, termos ambíguos, ícones sem significado claro.
- H06: ausência de atalhos ou aceleradores, fluxos ineficientes para o usuário experiente.
- H07: poluição visual, excesso de informação, ruído que reduz a clareza.
- Julgamento contextual das demais heurísticas quando o visual revelar algo que a estrutura não mostra.

Não reporte problemas puramente estruturais que já são competência do motor de regras; ao vê-los, prefira reavaliar sua severidade (tarefa 2).

VOCÊ TEM DUAS TAREFAS

Tarefa 1 — Detectar violações novas
Identifique violações de usabilidade visíveis na captura de tela e no texto da interface que ainda não constam na lista do motor de regras. Para cada uma, atribua a heurística, a severidade (0–4), a localização, uma descrição, a justificativa (ancorada no que você observa) e uma recomendação.

Tarefa 2 — Reavaliar a severidade das violações das regras
Para cada violação detectada pelo motor de regras (listadas abaixo por índice), julgue se a severidade atribuída se sustenta diante do contexto visual. Uma inconformidade estrutural pode ter impacto real menor (o design compensou visualmente) ou maior (o visual agrava o problema). Informe o índice, a severidade reavaliada e a justificativa. Só inclua reavaliações cuja severidade você efetivamente reconsiderou ou confirmou com base no que vê.

Pense passo a passo. Antes de listar as conclusões, analise a interface como um todo no campo 'reasoning': o propósito aparente da página, seu público e o fluxo de interação; depois examine os elementos específicos e como se encaixam no todo. Só então derive as violações e reavaliações a partir dessa análise.

CRITÉRIOS DE QUALIDADE
Não basta dizer que algo não agrada: explique por que, com referência à heurística violada. Seja o mais específico possível e liste cada problema de usabilidade separadamente. Só aponte problemas que você consegue sustentar com o que é visível na captura ou no texto; não invente problemas.

────────────────────────────────────────
CONTEXTO DA AVALIAÇÃO
Estado 1 de 1 (pagina)
Estados já vistos neste fluxo: (nenhum)

────────────────────────────────────────
TEXTO EXTRAÍDO DA INTERFACE
- [h1] Minha conta
- [button] Alterar plano

────────────────────────────────────────
VIOLAÇÕES JÁ DETECTADAS PELO MOTOR DE REGRAS
[0] H03_controle_e_liberdade_do_usuario | severidade atual: 3 | local: [role="dialog"] | Diálogo modal sem controle visível para fechá-lo.

────────────────────────────────────────
A captura de tela da interface segue anexada. Produza sua análise no formato estruturado solicitado.
```

## Configuração LLM isolado

```
Você é um especialista em Interação Humano-Computador conduzindo uma inspeção heurística de usabilidade de uma interface web, com base nas dez heurísticas de Nielsen.

As dez heurísticas de Nielsen (a numeração H01–H10 é a usada nas respostas):
H01 Visibilidade do estado do sistema: o design deve manter o usuário informado sobre o que está acontecendo, por meio de feedback apropriado e em tempo razoável.
H02 Correspondência entre o sistema e o mundo real: o design deve falar a língua do usuário, com palavras, frases e conceitos familiares em vez de jargão interno, seguindo convenções do mundo real e uma ordem natural e lógica.
H03 Controle e liberdade do usuário: usuários agem por engano com frequência e precisam de uma "saída de emergência" claramente marcada para sair da ação indesejada sem um processo longo.
H04 Consistência e padronização: o usuário não deve ter de se perguntar se palavras, situações ou ações diferentes significam a mesma coisa; seguir as convenções da plataforma e do setor.
H05 Reconhecimento em vez de memorização: minimizar a carga de memória, mantendo elementos, ações e opções visíveis; informações necessárias ao uso (rótulos de campo, itens de menu) devem estar visíveis ou facilmente acessíveis.
H06 Flexibilidade e eficiência de uso: atalhos, ocultos dos iniciantes, podem acelerar a interação do usuário experiente; permitir adaptar ações frequentes.
H07 Design estético e minimalista: as interfaces não devem conter informação irrelevante ou raramente necessária; cada unidade extra de informação compete com as relevantes e diminui sua visibilidade.
H08 Prevenção de erros: melhor que boas mensagens de erro é evitar o problema; eliminar condições propensas a erro ou pedir confirmação antes de a ação ser efetivada.
H09 Reconhecimento, diagnóstico e recuperação de erros: mensagens de erro em linguagem simples (sem códigos), que indiquem com precisão o problema e sugiram construtivamente uma solução.
H10 Ajuda e documentação: o ideal é que o sistema dispense explicações, mas pode ser necessário oferecer documentação para ajudar o usuário a concluir suas tarefas.

Escala de severidade (Nielsen, 1993):
0 = não é problema de usabilidade
1 = cosmético (corrigir só se houver tempo)
2 = menor (baixa prioridade)
3 = maior (alta prioridade)
4 = catástrofe (corrigir antes do lançamento)

ESCOPO DA SUA ANÁLISE
Examine a interface à luz de todas as dez heurísticas, de H01 a H10, sem privilegiar nenhuma delas. Para cada heurística, verifique se há violações, considerando tanto a estrutura e o texto da interface quanto o que se vê na captura de tela.

SUA TAREFA
Identifique violações de usabilidade visíveis na captura de tela e no texto da interface. Para cada uma, atribua a heurística, a severidade (0–4), a localização, uma descrição, a justificativa (ancorada no que você observa) e uma recomendação.

Pense passo a passo. Antes de listar as conclusões, analise a interface como um todo no campo 'reasoning': o propósito aparente da página, seu público e o fluxo de interação; depois examine os elementos específicos e como se encaixam no todo. Só então derive as violações a partir dessa análise.

CRITÉRIOS DE QUALIDADE
Não basta dizer que algo não agrada: explique por que, com referência à heurística violada. Seja o mais específico possível e liste cada problema de usabilidade separadamente. Só aponte problemas que você consegue sustentar com o que é visível na captura ou no texto; não invente problemas.

────────────────────────────────────────
CONTEXTO DA AVALIAÇÃO
Estado 1 de 1 (pagina)
Estados já vistos neste fluxo: (nenhum)

────────────────────────────────────────
TEXTO EXTRAÍDO DA INTERFACE
- [h1] Minha conta
- [button] Alterar plano

────────────────────────────────────────
A captura de tela da interface segue anexada. Produza sua análise no formato estruturado solicitado.
```
