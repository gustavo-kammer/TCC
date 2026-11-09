# Inspeção heurística híbrida de interfaces web

Código e dados do Trabalho de Conclusão de Curso em Ciência da Computação (Universidade do Extremo Sul Catarinense, UNESC, 2026).

O sistema detecta violações das dez heurísticas de usabilidade de Nielsen em interfaces web, classifica a severidade (escala de 0 a 4) e ordena os achados por um índice de criticidade. Um modelo em cascata combina um motor de 27 regras determinísticas, aplicado ao HTML e aos estilos renderizados, e um modelo de linguagem multimodal (Claude, via API) que recebe o conteúdo e as capturas de tela. Três configurações são comparadas: `hibrido`, `regras` (sem chamada ao modelo) e `llm` (sem o motor de regras).

## Requisitos

- Python 3.10 ou superior (o experimento foi executado com Python 3.13.2 no Windows 11; os testes também foram verificados com Python 3.10 no Linux).
- Chromium do Playwright, usado na captura e na extração dos estilos.
- Chave de API da Anthropic, necessária apenas para as etapas que chamam o modelo (inspeção nas configurações `hibrido` e `llm` e juiz de casamento). As demais etapas não usam a API.

## Instalação

```
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell/CMD): .venv\Scripts\activate; Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env               # Windows: copy .env.example .env
```

Preencher o `.env`:

| Variável | Função |
|---|---|
| `ANTHROPIC_API_KEY` | Chave da API. |
| `ANTHROPIC_MODEL` | Modelo da inspeção (experimento: `claude-sonnet-5-5`). |
| `JUIZ_MODEL` | Modelo do juiz de casamento (experimento: `claude-opus-5-5`). Se omitido, usa `ANTHROPIC_MODEL`. |

O `.env` não deve ser versionado.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `main.py` | Comandos avulsos: `inspecionar`, `calibracao`, `externa`, `casamento`, `conferir`, `metricas`. |
| `pipeline.py` | Orquestrador do experimento externo: exploração, curadoria, captura, validação, inspeção, juiz, confiabilidade, relatórios e auditoria. |
| `avaliar_url.py` | Fluxo guiado para avaliar uma URL: exploração, curadoria, captura, validação, regras e, opcionalmente, análise com o modelo. |
| `capturar_paginas.py` | Captura congelada (HTML, imagens e metadados) a partir de um roteiro `sites*.json`. |
| `analisar_resultados.py`, `consolidar_resultados.py` | Análises complementares (`resultados*/analises.json`) e planilha consolidada. |
| `src/rules/` | Motor de regras determinístico. |
| `src/llm/` | Prompt, esquema de saída, cliente e analisador do modelo de linguagem. |
| `src/extractor.py`, `src/frozen.py` | Extração do DOM e leitura das capturas congeladas. |
| `src/exploracao.py`, `src/curadoria.py` | Exploração determinística da interface e remoção de estados repetidos. |
| `src/orchestrator.py`, `src/prioritization.py`, `src/report.py`, `src/relatorio_html.py` | Cascata, priorização, relatório JSON e relatório visual. |
| `src/evaluation/` | Gabarito, casamento, métricas, estatística, ancoragem, estabilidade e auditoria. |
| `gabarito/`, `classificacao_104.csv` | Referência dos especialistas (Capeleti, 2024) e classificação dos 104 problemas. |
| `interfaces/calibracao/` | As dez interfaces de calibração, com um defeito plantado cada. Em `prints/`, as capturas de tela de cada uma (`calib_01.png` a `calib_10.png`). |
| `sites.json`, `sites_v2.json`, `sites_v2_curado.json` | Roteiros dos sistemas externos (v1, exploração da v2 e roteiro curado usado na execução oficial). |
| `prompts_exemplo.md` | Exemplo dos prompts enviados ao modelo. |
| `scripts/` | `verificar_isolamento.py`, verificação usada pelos testes. |
| `tests/` | Testes automatizados. |
| `dados_experimento/` | Resultados das execuções relatadas no trabalho (ver `dados_experimento/README.md`). |

## Como executar

Todos os comandos são executados na raiz do projeto. As etapas que chamam a API geram custo; o `pipeline.py` pede a confirmação `SIM` antes delas, salvo com `--sim`.

### Testes

```
python -m pytest
```

Testes que dependem de capturas em `coletas/` ou da chave de API são ignorados quando esses recursos não existem.

### Calibração (dez interfaces com defeito conhecido)

```
python main.py calibracao --runs 3
```

Executa as três configurações, três vezes cada, sobre `interfaces/calibracao/` e grava em `output/` e `resultados/calibracao/`.

### Inspeção de uma interface

```
python main.py inspecionar <alvo> --config hibrido --runs 1
```

`<alvo>` é um identificador de fluxo ou uma URL. `--config` aceita `hibrido`, `regras` e `llm`.

### Avaliar uma URL (fluxo guiado)

```
python avaliar_url.py
```

O comando solicita o endereço a avaliar (também aceito como argumento: `python avaliar_url.py https://exemplo.com`) e executa as mesmas etapas do pipeline do experimento, sobre um único sistema:

1. exploração determinística em largura (`src/exploracao.py`);
2. curadoria dos estados repetidos, por similaridade de texto e mudança visual (`src/curadoria.py`);
3. captura congelada (`capturar_paginas.py`);
4. validação das capturas (`pipeline.py`);
5. inspeção pelo motor de regras, sem chamada à API, e geração do relatório HTML.

Ao final, o programa pergunta se a análise com o modelo de linguagem (configuração `hibrido`) também deve ser executada. Nesse caso é exibida a estimativa de chamadas e pedida uma confirmação antes de qualquer custo de API; a chave deve estar no `.env`. Sem a chave, as etapas de 1 a 5 funcionam normalmente.

Os resultados ficam em `analises_url/<endereço>_<data>/` (`resultados/relatorios/index.html` é o ponto de entrada). Principais opções:

| Opção | Efeito |
|---|---|
| `--tarefa` | Descrição da tarefa informada ao modelo de linguagem (padrão: "Explorar livremente as seções públicas do sistema."). |
| `--limite` | Teto de tempo da exploração, em segundos. O padrão é 900; no experimento foi usado 7200. |
| `--espera` | Espera, em milissegundos, após abrir a página (padrão 3000, como no experimento). Aumentar em páginas que carregam devagar. |
| `--cookies`, `--fechar` | Seletores CSS do botão do aviso de cookies e de janelas a fechar em cada estado (`--fechar` pode ser repetido). Sem eles, avisos que cobrem a página podem impedir os cliques da exploração. |
| `--max-estados`, `--profundidade` | Limitam a exploração. |
| `--limiar`, `--limiar-visual`, `--so-texto` | Parâmetros da curadoria (padrões do experimento: 0,9 e 0,005). |
| `--runs` | Execuções da análise com o modelo (padrão 3, como no experimento). |
| `--llm` | Executa a análise com o modelo sem perguntar. |

Se a validação das capturas reprovar a página (HTML pequeno, texto insuficiente ou imagem em branco), nenhuma inspeção é feita e o motivo é gravado em `coletas/validacao_capturas.md`. Isso ocorre, por exemplo, em páginas que carregam o conteúdo depois de muito tempo, que exibem verificação anti-robô ou que respondem de forma diferente ao navegador automatizado. Nesses casos, `--espera` com valor maior (por exemplo, `--espera 15000`) pode resolver; caso contrário, o sistema não se aplica à página.

Este fluxo é uma interface de uso do repositório. Os parâmetros do experimento relatado no trabalho foram os de `pipeline.py` e `sites_v2.json`; o roteiro explorado aqui parte de uma URL sem os ajustes manuais feitos para os dois sistemas externos (seletores de fechamento de avisos, textos excluídos), de modo que o resultado em sites com avisos ou áreas autenticadas pode diferir.

### Validação externa (Observatório da Agropecuária e SIOUT SC)

```
python pipeline.py explorar --sites sites_v2.json --versao v2
python pipeline.py curar    --sites sites_v2.json --versao v2
python pipeline.py oficial  --sites sites_v2_curado.json --versao v2 --runs 3
python pipeline.py juiz     --sites sites_v2_curado.json --versao v2
python pipeline.py confiabilidade --sites sites_v2_curado.json --versao v2
python pipeline.py relatorios     --sites sites_v2_curado.json --versao v2 [--pdf]
python pipeline.py status --versao v2
```

- `explorar` percorre as interfaces com o Playwright, sem modelo, e grava `exploracao_v2/roteiro_<id>.json`.
- `curar` remove estados quase idênticos e grava `sites_v2_curado.json`.
- `oficial` captura e valida os estados, estima as chamadas e executa a inspeção nas três configurações. Não chama o juiz. A opção `--continuar` retoma uma execução interrompida, e `--sem-captura` usa capturas já gravadas.
- `juiz` executa o casamento entre achados e problemas dos especialistas, as análises e a planilha consolidada. Os casamentos já calculados ficam em cache.
- `confiabilidade` calcula a ancoragem textual das evidências e a estabilidade entre execuções, e gera a amostra de auditoria. Depois de preenchida a planilha, `python pipeline.py auditoria-calcular --versao v2` calcula os indicadores.
- `relatorios` gera um relatório HTML (e PDF, com `--pdf`) por configuração e sistema.

Cada versão grava em pastas próprias (`coletas_<versao>/`, `output_<versao>/`, `resultados_<versao>/`). Os sites públicos mudam com o tempo, de modo que uma nova captura pode diferir da usada no trabalho.

### Recalcular métricas sem chamar a API

Os arquivos de `dados_experimento/` permitem refazer as métricas sem novas chamadas ao modelo. O cache do juiz depende do modelo, portanto o `.env` deve conter `JUIZ_MODEL=claude-opus-5-5`; a chave de API pode ser qualquer valor, pois não é usada quando o cache é aproveitado.

```
mkdir -p output
cp -r dados_experimento/validacao_externa/execucoes output/runs
cp -r dados_experimento/validacao_externa/casamento output/matching
cp -r dados_experimento/validacao_externa/agregado  output/agregado
for c in hibrido llm regras; do
  cp -r dados_experimento/calibracao/execucoes/$c/* output/runs/$c/
  cp dados_experimento/calibracao/agregado/$c/* output/agregado/$c/
done
python main.py metricas
python analisar_resultados.py
```

`main.py metricas` regrava `resultados/calibracao/` e `resultados/externa/`, e `analisar_resultados.py` grava `resultados/analises.json`. Os valores coincidem com os de `dados_experimento/` (diferenças apenas na 16ª casa decimal em alguns coeficientes). A ancoragem, a estabilidade e a auditoria dependem das capturas originais e não são refeitas por esse caminho.

## Limitações do repositório

- As capturas congeladas (HTML e imagens dos sistemas externos) não estão incluídas por tamanho (cerca de 400 MB). Elas são necessárias para refazer a ancoragem, a estabilidade, a amostra de auditoria e os relatórios.
- O modelo de linguagem é acessado por API e não permite fixar temperatura nem semente; por isso cada configuração foi executada três vezes e novas execuções não reproduzem exatamente os mesmos achados.
