# Resultados — Calibração (10 interfaces, 1 violação plantada cada)

- Fluxos no gabarito: 10 (calib_01, calib_02, calib_03, calib_04, calib_05, calib_06, calib_07, calib_08, calib_09, calib_10)
- Células excluídas das métricas: 0
- Células aplicáveis nas métricas: 100
- `hibrido`: 10 fluxos, 3 execuções, modelo claude-sonnet-5-5, regras 083ac2f2b37f
- `regras`: 10 fluxos, 3 execuções, modelo —, regras 083ac2f2b37f
- `llm`: 10 fluxos, 3 execuções, modelo claude-sonnet-5-5, regras —

## Métricas por configuração (nível da célula fluxo × heurística)

Detectado = nota do sistema ≥ 1; positivo = célula apontada pela maioria. **Kappa (todas)** usa todas as células aplicáveis, zeros incluídos; **Kappa (só VP)** usa apenas as células detectadas e apontadas.

| Configuração | Origem | Células | VP | FP | FN | VN | Precisão | Recall | F1 | Kappa (todas) | Kappa (só VP) | Spearman |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hibrido | todos | 100 | 10 | 30 | 0 | 60 | 0.250 | 1.000 | 0.400 | 0.405 | 0.466 | 0.531 |
| hibrido | llm | 100 | 7 | 30 | 3 | 60 | 0.189 | 0.700 | 0.298 | 0.143 | 0.000 | 0.264 |
| hibrido | motor_de_regras | 100 | 8 | 0 | 2 | 90 | 1.000 | 0.800 | 0.889 | 0.890 | 0.600 | 0.892 |
| regras | todos | 100 | 8 | 0 | 2 | 90 | 1.000 | 0.800 | 0.889 | 0.909 | 0.833 | 0.892 |
| llm | todos | 100 | 10 | 34 | 0 | 56 | 0.227 | 1.000 | 0.370 | 0.380 | 0.505 | 0.499 |

Origem `llm` = só achados visíveis na imagem (camada LLM); `motor_de_regras` = só achados das regras (com a severidade revisada, no híbrido). Na configuração `regras`, `todos` equivale a só regras; em `llm`, a só LLM.
