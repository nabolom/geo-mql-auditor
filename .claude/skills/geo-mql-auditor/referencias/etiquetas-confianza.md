# Etiquetas de confianza y priorización

Cada hallazgo lleva **dos etiquetas independientes** y un bloque de prioridad. Nunca lleva impacto proyectado numérico.

## Etiqueta 1: evidencia de la observación

| Etiqueta | Cuándo | Ejemplos |
|---|---|---|
| Confirmado | Un colector lo observó directamente en el HTML, las cabeceras, robots.txt o el sitemap | código HTTP, noindex, JSON-LD inválido, canonical ausente, dato sin enlace de fuente |
| Probable | Dos colectores coinciden, o una heurística con alta especificidad | HTML casi vacío más marcadores de framework (dependencia de JavaScript sin render); apertura que no comparte términos con el H1 |
| Hipótesis | Juicio del modelo o de un subagente; requiere revisión humana antes de actuar | claridad de redacción, aporte propio, presencia externa de la marca, precisión de la descripción de la marca en una respuesta de IA |

Las observaciones `Hipótesis` no entran en el puntaje de cumplimiento.

## Etiqueta 2: fuerza de la regla con tipo de evidencia

| Fuerza | Definición |
|---|---|
| A | Documentación oficial del motor (Google, Bing, OpenAI, Anthropic, Perplexity, Apple, Meta), estándar (RFC 9309, W3C) o estudio revisado por pares |
| B | Estudio de industria con metodología publicada (muestra, periodo, método) |
| C | Consenso de practicantes o hipótesis del skill |

| Tipo de evidencia | Significado |
|---|---|
| requisito_oficial | Lo pide o lo documenta el motor |
| efecto_experimental | Medido con diseño experimental o cuasi-experimental (Princeton en motor simulado; Ahrefs con grupo de control) |
| correlacional | Asociación observada, sin causalidad |
| consenso | Práctica compartida sin medición |

En los reportes se muestran juntas: `A · requisito oficial`, `B · experimental`, `B · correlacional`, `C · consenso`. Una fuente verificada solo por snippet o resumen de terceros vale como máximo C hasta leer la página.

## Prioridad

- Impacto esperado: alto, medio, bajo (definido por regla en el rulebook; los subagentes pueden ajustarlo con motivo).
- Esfuerzo: bajo, medio, alto.
- Dependencia: propio, contenido, desarrollo, analítica, crm, legal o dirección, terceros.
- Horizonte: 30 días (esfuerzo bajo, impacto al menos medio, sin dependencia externa), 90 días (esfuerzo medio o depende de otro equipo), largo plazo (capacidades: contenido original, autoridad externa, programa de autoría).

Orden en el reporte: impacto, esfuerzo, evidencia de la observación, fuerza de la regla, número de URL afectadas.

## Puntaje de cumplimiento

`100 × Σ peso de reglas superadas / Σ peso de reglas aplicables`, con peso A=3, B=2, C=1, por vector y global. Excluye reglas de ámbito principio, método y anti-patrón, resultados no aplicables o sin evidencia y observaciones `Hipótesis`. Se presenta siempre con la leyenda "cumplimiento de verificaciones, no predicción de visibilidad", en su propia sección y nunca en el titular. En `monitor` es alerta secundaria (cambios mayores a ±3) detrás de la regresión por regla y URL y de las caídas en métricas de visibilidad.
