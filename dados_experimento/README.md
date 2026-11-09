# Dados das execuções

Resultados brutos e consolidados das execuções relatadas no trabalho. Os caminhos locais dos arquivos originais foram substituídos por `RAIZ_DO_PROJETO`.

Identificadores: `calib_01` a `calib_10` são as interfaces de calibração; `p12` é o Observatório da Agropecuária e `p13` é o SIOUT SC. As configurações são `hibrido`, `regras` e `llm`, e cada uma teve três execuções (`run_0`, `run_1`, `run_2`).

## calibracao/

| Pasta | Conteúdo |
|---|---|
| `execucoes/<configuracao>/calib_NN/run_K.json` | Relatório bruto de cada execução. |
| `agregado/<configuracao>/calib_NN.json` | Execuções agregadas por interface, com metadados (modelo, prompt, versão das regras). |
| `metricas/` | Métricas por configuração e por fluxo, células sistema versus autor e `resumo.md`. |

## validacao_externa/

| Pasta | Conteúdo |
|---|---|
| `execucoes/<configuracao>/<sistema>/run_K.json` | Achados brutos de cada execução, por estado da interface. |
| `agregado/<configuracao>/<sistema>.json` | Execuções agregadas por sistema. |
| `casamento/<configuracao>/<sistema>/run_K.json` | Decisões do juiz (`claude-opus-5-5`) entre os achados e os 104 problemas dos especialistas. |
| `metricas/` | `analises.json` (revocação, precisão, F1, severidade, categorias e complementaridade), `estabilidade.json`, `ancoragem.json`, `ancoragem_achados.csv`, métricas por configuração e por fluxo, células por heurística e `manifesto_pipeline.json` (datas, parâmetros e hashes da execução). |
| `resultados_por_violacao/` | Planilha consolidada, métricas por violação, amostra de conferência do juiz (`amostra_conferencia_abas.xlsx`, preenchida pelo autor), sua chave (`amostra_gabarito_oculto.csv`) e `concordancia.json`. |
| `auditoria/` | Amostra de auditoria dos achados sem par (`auditoria_amostra.xlsx`, preenchida pelo autor), chave, população e resultado. |
| `relatorios/` | Relatório visual (HTML e PDF) por configuração e sistema. |

## roteiros_exploracao/

Roteiros gerados pela exploração determinística (`roteiro_*`), registro da exploração (`exploracao_*`) e roteiros após a curadoria (`curado_*`).

Não estão incluídas as capturas congeladas (HTML e imagens) nem as imagens intermediárias da curadoria.
