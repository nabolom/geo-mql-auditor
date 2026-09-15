# GEO: Generative Engine Optimization (Aggarwal et al., KDD 2024)

Lectura corregida del paper. Verificado el 2026-09-10 contra https://arxiv.org/abs/2311.09735 (HTML y PDF) y Crossref (DOI 10.1145/3637528.3671900, KDD '24, Barcelona, pp. 5-16).

## Qué evaluó

- Un motor generativo **simulado**: los cinco primeros resultados de Google como fuentes y `gpt-3.5-turbo` como generador (2023). Validación adicional en Perplexity.ai subiendo las fuentes como archivos porque no permite fijar URLs.
- GEO-bench: 10,000 consultas (8k/1k/1k) de nueve fuentes; 80% informacionales, 10% transaccionales, 10% navegacionales.
- Métricas: **Position-Adjusted Word Count** (palabras de las oraciones atribuidas a una cita, ponderadas por una función exponencial decreciente de la posición) y **Subjective Impression** (siete submétricas juzgadas por GPT-3.5).

## Los nueve métodos, con nombre exacto

| Método | Resultado (PAWC overall / SI) | Grupo |
|---|---|---|
| Keyword Stuffing | 17.7 / 20.2 (línea base 19.3 / 19.3): peor | Non-Performing |
| Unique Words | sin mejora relevante | Non-Performing |
| Easy-to-Understand | +15-30% | High-Performing |
| Authoritative | mejora; destaca en debate, historia y ciencia | High-Performing |
| Technical Terms | mejora moderada | High-Performing |
| Fluency Optimization | 24.7 / 21.9 | High-Performing |
| Cite Sources | 24.6 / 21.9 | High-Performing |
| Quotation Addition | 27.2 / 24.7 | High-Performing |
| Statistics Addition | 25.2 / 23.7 | High-Performing |

Texto del paper: "our top-performing methods, Cite Sources, Quotation Addition, and Statistics Addition, achieved a relative improvement of 30-40% on the Position-Adjusted Word Count metric and 15-30% on the Subjective Impression metric". El abstract resume "up to 40%".

## El 115.1% y lo que no dice

La cifra aparece en la Tabla 2, que optimiza todas las fuentes a la vez y desglosa por posición en el SERP: "the Cite Sources method led to a substantial 115.1% increase in visibility for websites ranked fifth in SERP, while on average, the visibility of the top-ranked website decreased by 30.3%". Es un efecto para sitios en quinta posición, con pérdida para el primero. **No es un efecto general** y no debe citarse así.

## Hallazgos por dominio (Tabla 3)

- Authoritative: debate, historia, ciencia.
- Fluency Optimization: negocios, ciencia, salud.
- Cite Sources: statement, facts, ley y gobierno.
- Quotation Addition: people and society, explicación, historia.
- Statistics Addition: ley y gobierno, debate, opinión.

## Lo que NO está en el paper

- "Flesch 8-10" o cualquier objetivo de legibilidad numérico: cero menciones de Flesch.
- "Topic relevance" y "length optimization" como métodos: no existen; "relevance" solo es una submétrica subjetiva y "length" solo aparece como longitud de contexto.
- "Autoría anónima −60%", "frescura 3.2x", "listas +14%": no están en el paper ni en ninguna fuente primaria localizada.

## Limitaciones que el propio paper reconoce

Motor simulado, posible deriva de los motores reales, sin evaluación del efecto en rankings de búsqueda, experimentos de combinación sobre 200 ejemplos. Además, **C-SEO Bench (Puerto et al., NeurIPS Datasets and Benchmarks 2025, arXiv:2506.11097)** evaluó los mismos ocho métodos en GPT-4o-mini, Claude 3.5 Haiku, o3 y o4-mini y concluyó que "most current C-SEO methods are not only largely ineffective but also frequently have a negative impact on document ranking", y que ser el primer documento del contexto pesa mucho más que cualquier método.

## Cómo lo usa este skill

- Las reglas X-04 a X-07 citan el paper con fuerza **B · efecto experimental** y la nota de motor simulado. Conservan fuerza A solo cuando Bing o Google documentan la práctica.
- Ninguna cifra del paper se presenta como efecto esperado en un reporte.
- Trabajo posterior relacionado: AutoGEO (Wu, Zhong, Kim y Xiong, ICLR 2026, arXiv:2510.11438), que extrae reglas de preferencia con modelos frontera; el ID 2502.13392 que circula en algunos repos es un paper de robotaxis.
