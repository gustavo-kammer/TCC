# Avaliação por violação (externa)

Juiz: LLM, cego à configuração. Recall = problemas dos especialistas encontrados; precisão = achados com par (limite inferior). *Ponderado*: parcial = 0,5; *estrito*: só casamento completo. Valores = mediana das execuções.

| Configuração | Fluxo | Execuções | Problemas | Achados | Recall (pond.) | Recall (estr.) | Precisão (pond.) | Precisão (estr.) | F1 (pond.) | F1 (estr.) | Pares | Kappa sev. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hibrido | p12 | 3 | 52 | 1426 | 0.269 | 0.135 | 0.010 | 0.005 | 0.019 | 0.009 | 21 | 0.013 |
| hibrido | p13 | 3 | 52 | 252 | 0.221 | 0.115 | 0.038 | 0.020 | 0.065 | 0.034 | 16 | 0.106 |
| hibrido | p12+p13 | 3 | 104 | 1678 | 0.240 | 0.135 | 0.013 | 0.008 | 0.025 | 0.015 | 36 | 0.103 |
| regras | p12 | 3 | 52 | 794 | 0.067 | 0.000 | 0.004 | 0.000 | 0.008 | 0.000 | 7 | 0.117 |
| regras | p13 | 3 | 52 | 165 | 0.058 | 0.000 | 0.012 | 0.000 | 0.020 | 0.000 | 6 | -0.030 |
| regras | p12+p13 | 3 | 104 | 959 | 0.062 | 0.000 | 0.005 | 0.000 | 0.010 | 0.000 | 13 | 0.000 |
| llm | p12 | 3 | 52 | 741 | 0.231 | 0.135 | 0.016 | 0.009 | 0.030 | 0.018 | 17 | -0.083 |
| llm | p13 | 3 | 52 | 108 | 0.231 | 0.077 | 0.093 | 0.037 | 0.133 | 0.050 | 17 | 0.180 |
| llm | p12+p13 | 3 | 104 | 851 | 0.221 | 0.106 | 0.025 | 0.013 | 0.044 | 0.023 | 34 | 0.090 |
