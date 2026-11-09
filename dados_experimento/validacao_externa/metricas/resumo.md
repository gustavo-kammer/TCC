# Resultados — Validação externa (sistemas avaliados por especialistas, Capeleti 2024)

- Fluxos no gabarito: 2 (p12, p13)
- Células excluídas das métricas: 0
- Células aplicáveis nas métricas: 20
- `hibrido`: 2 fluxos, 3 execuções, modelo claude-sonnet-5-5, regras 083ac2f2b37f
- `regras`: 2 fluxos, 3 execuções, modelo —, regras 083ac2f2b37f
- `llm`: 2 fluxos, 3 execuções, modelo claude-sonnet-5-5, regras —

## Métricas por configuração (nível da célula fluxo × heurística)

Detectado = nota do sistema ≥ 1; positivo = célula apontada pela maioria. **Kappa (todas)** usa todas as células aplicáveis, zeros incluídos; **Kappa (só VP)** usa apenas as células detectadas e apontadas.

| Configuração | Origem | Células | VP | FP | FN | VN | Precisão | Recall | F1 | Kappa (todas) | Kappa (só VP) | Spearman |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hibrido | todos | 20 | 19 | 1 | 0 | 0 | 0.950 | 1.000 | 0.974 | 0.110 | -0.044 | 0.031 |
| hibrido | llm | 20 | 19 | 1 | 0 | 0 | 0.950 | 1.000 | 0.974 | -0.053 | -0.136 | -0.291 |
| hibrido | motor_de_regras | 20 | 15 | 1 | 4 | 0 | 0.938 | 0.789 | 0.857 | 0.076 | 0.000 | 0.134 |
| regras | todos | 20 | 15 | 1 | 4 | 0 | 0.938 | 0.789 | 0.857 | 0.007 | -0.062 | -0.073 |
| llm | todos | 20 | 19 | 1 | 0 | 0 | 0.950 | 1.000 | 0.974 | -0.029 | -0.128 | -0.264 |

Origem `llm` = só achados visíveis na imagem (camada LLM); `motor_de_regras` = só achados das regras (com a severidade revisada, no híbrido). Na configuração `regras`, `todos` equivale a só regras; em `llm`, a só LLM.
