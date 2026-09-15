# geo-mql-auditor

Skill de Claude Code, en español, para auditar y medir la visibilidad de un sitio en motores de respuesta con IA (ChatGPT, Perplexity, Gemini, Claude, Copilot y Google AI Overviews) y conectar esa visibilidad con la generación de leads calificados (MQL). Produce reportes con hallazgos etiquetados por evidencia y priorizados por impacto, esfuerzo, dependencia y horizonte. Nunca modifica el sitio auditado.

## Qué problema resuelve

Los equipos de marketing reciben recomendaciones de "GEO" o "AEO" sin distinguir entre lo que documenta un motor, lo que midió un estudio y lo que opina un practicante. Tampoco distinguen entre lo que un script observó y lo que un modelo de lenguaje supuso. Este proyecto separa esas cosas:

- Colectores deterministas en Python (solo biblioteca estándar) observan HTML, cabeceras, robots.txt, sitemap y JSON-LD.
- Un rulebook en YAML con 73 reglas, cada una con fuente, fuerza y fecha de verificación, decide qué se evalúa y en qué tipo de página.
- Subagentes de Claude Code aportan el juicio que un colector no puede dar, siempre marcado como tal.
- El módulo de visibilidad mide menciones y citas de la marca en un panel fijo de prompts, con repeticiones y sin mezclar capturas manuales con capturas por API.

## Arquitectura

```
.claude/skills/geo-mql-auditor/
  SKILL.md                 flujo que sigue Claude Code al activarse el skill
  reglas/rulebook.yaml     73 reglas con fuentes, fuerza y tipo de evidencia
  referencias/             bots de IA, etiquetas, fuentes verificadas, tipos de página, paper de Princeton
  plantillas/              reporte Markdown y JSON-LD por tipo de página
  scripts/
    contexto.py            módulo 0: valida contexto/negocio.md
    audit.py               módulo audit: una URL, una lista o un sitemap
    visibilidad.py         módulo visibilidad: panel, captura, análisis, métricas, calibración
    geomql/                paquete con colectores, verificaciones, reporte y motores
.claude/agents/            subagentes que juzgan sobre los vectores del audit y la visibilidad
contexto/negocio.md        plantilla vacía del contexto de negocio
tests/                     164 pruebas con fixturas HTML inventadas
```

### Los seis módulos

Solo tres módulos tienen CLI funcional: contexto, audit y visibilidad. Los otros cuatro no tienen código ejecutable: mql existe solo como ocho reglas en el rulebook; compare, fix y monitor no existen.

| Módulo | Qué hace | Estado |
|---|---|---|
| contexto (módulo 0) | Lee y valida `contexto/negocio.md`; lista campos críticos faltantes y las preguntas para pedirlos | CLI funcional |
| audit | Descarga hasta 100 URL, detecta el tipo de página, corre los colectores, evalúa las reglas aplicables, escribe un reporte y un archivo por vector para los subagentes; fusiona sus salidas | CLI funcional |
| visibilidad | Genera un panel de prompts desde el contexto, produce hojas de captura manual, consulta motores por API con costo estimado, analiza respuestas, calcula share of answers, tasa de citación y share of voice, calibra manual contra API | CLI funcional |
| mql | Journey, CTA, formularios, tracking GA4, scoring y campos de CRM | Sin CLI ni subagente. Solo existen las reglas M-01 a M-08 en el rulebook, que ningún colector evalúa |
| compare | Mismas verificaciones contra los competidores del contexto | No existe. `audit --comparar-reglas` cubre solo la comparación regla por regla entre dos corridas de audit |
| fix | Propuestas de cambio con verificador de cifras inventadas | No existe |
| monitor | Regresiones por regla y URL entre corridas | No existe. `audit --comparar` cubre solo la comparación de hallazgos con una corrida anterior |

### Subagentes

Hay cinco subagentes, no seis. Los cinco están escritos en `.claude/agents/`; el sexto, `geo-mql`, estaba previsto para el módulo mql y no se escribió. Ninguna parte del código lo invoca. Cada uno recibe únicamente la ruta de un archivo JSON de vector y devuelve un JSON con `hallazgos`, `ajustes` y `notas`.

| Subagente | Vector | Tipo de trabajo |
|---|---|---|
| geo-tecnico | tecnico.json | Mecánico: interpreta robots.txt, bots, HTTP, canonical, snippet, hreflang, JavaScript, sitemap |
| geo-schema | schema.json | Mecánico: JSON-LD por tipo de página, coherencia con lo visible, referencias `@id` |
| geo-extractabilidad | extractabilidad.json | Juicio: respuesta directa, jerarquía, tablas, datos con fuente, citas atribuidas, fecha, aporte propio |
| geo-entidad | entidad.json | Juicio: nombre de marca, sameAs, autoría con credenciales, acerca de y contacto, NAP |
| geo-visibilidad | visibilidad.json | Juicio: precisión de la descripción de la marca en cada respuesta, siempre como Hipótesis |

SKILL.md menciona `geo-mql` como subagente del módulo mql; es una previsión, no algo que exista. El módulo mql tampoco tiene CLI.

### Colectores del audit

Cada URL pasa por `tipo_pagina` (home, solución, artículo, comparativa, FAQ, glosario, landing, local, perfil, programa, institucional u otra) y después por los colectores `tecnico`, `schema`, `extractabilidad`, `estadisticas`, `citas`, `frescura` y `entidad`. A nivel de sitio corren `robots`, `bots`, `sitemap` y `llmstxt`. Las verificaciones en `verificaciones.py` traducen la salida de cada colector en un resultado por regla (`pasa`, `falla`, `no_aplica`, `sin_evidencia`) con evidencia y extractos. El reporte agrupa hallazgos sistémicos y puntuales, por tipo de página y por área responsable.

## Instalación

Requiere Python 3.11 o superior. Los colectores no tienen dependencias externas.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # opcional: solo para el modo API de visibilidad
.venv/bin/python -m pytest -q
```

`pyyaml` es opcional: el paquete trae un parser mínimo para el formato restringido del rulebook. Playwright es opcional y solo se usa con `--render`.

## Cómo correr cada módulo

Todos los comandos se ejecutan desde la raíz del repositorio. En Claude Code basta con pedir "audita la visibilidad GEO de https://dominio.com" y el skill sigue el flujo de SKILL.md; los comandos siguientes son los que el skill ejecuta.

### Módulo 0: contexto

```bash
C=.claude/skills/geo-mql-auditor/scripts/contexto.py
.venv/bin/python $C validar                 # imprime válido o los campos críticos que faltan
.venv/bin/python $C validar --modulo mql    # el CRM solo es crítico para mql
.venv/bin/python $C faltantes               # preguntas para pedir cada campo faltante
```

### Módulo audit

```bash
A=.claude/skills/geo-mql-auditor/scripts/audit.py
.venv/bin/python $A correr --url https://dominio.com/pagina
.venv/bin/python $A correr --sitemap https://dominio.com/sitemap.xml --max-urls 100 --sufijo sitemap
.venv/bin/python $A correr --urls https://dominio.com/a https://dominio.com/b --render
.venv/bin/python $A correr --url https://dominio.com/ --anexo-tecnico --sin-negocio
.venv/bin/python $A correr --url https://dominio.com/ --comparar salidas/<corrida-anterior>.json
.venv/bin/python $A resumen salidas/tmp/<corrida>/tecnico.json
.venv/bin/python $A fusionar --reporte salidas/<archivo>.json --hallazgos salidas/tmp/<corrida>/subagente_*.json
```

`correr` escribe `salidas/AAAA-MM-DD_<dominio>_audit.md` y `.json`, más un archivo por vector en `salidas/tmp/<corrida>/`. Los subagentes leen esos archivos y devuelven JSON; `fusionar` valida cada salida (rechaza impacto proyectado numérico y hallazgos sobre reglas que pasan) y regenera el reporte.

### Módulo visibilidad

```bash
V=.claude/skills/geo-mql-auditor/scripts/visibilidad.py
.venv/bin/python $V prompts                                   # panel desde contexto/negocio.md
.venv/bin/python $V importar-gsc --csv export_gsc.csv --aplicar
.venv/bin/python $V config                                    # modelos, repeticiones, user_location, idioma
.venv/bin/python $V captura --corrida m1 --motores chatgpt,perplexity,gemini,claude,aio
.venv/bin/python $V importar-txt --archivo captura_aio.txt --motor aio
.venv/bin/python $V importar-captura --csv respuestas_externas.csv
.venv/bin/python $V analizar --respuestas datos/visibilidad/respuestas_<fecha>_m1.csv
.venv/bin/python $V metricas --corrida m1
.venv/bin/python $V correr --corrida a1 --solo-costo          # modo API: imprime el costo y no consulta
.venv/bin/python $V correr --corrida a1                       # modo API: requiere llaves en .env
.venv/bin/python $V calibrar --manual m1 --api a1
.venv/bin/python $V fusionar --corrida m1 --salida salidas/tmp/m1/subagente_visibilidad.json
```

Cada corrida lleva `modo` (`manual` o `api`) y los modos no se mezclan en una serie. Los archivos de datos viven en `datos/visibilidad/`, que se crea al primer uso.

## Cómo está estructurado el rulebook

`reglas/rulebook.yaml` es una lista de 73 reglas en un subconjunto restringido de YAML (cadenas entre comillas dobles, listas simples) que `geomql/reglas.py` puede leer sin dependencias. Cada regla tiene:

- `id` con prefijo por categoría: T (técnico, 15), X (extractabilidad, 17), S (schema, 14), E (entidad, 8), M (mql, 8), V (visibilidad, 5), N (antipatrón, 6).
- `ambito`: `pagina`, `sitio`, `metodo`, `principio`, `analitica`, `crm`, `offpage` o `antipatron`. Las reglas de método, principio y antipatrón no puntúan.
- `tipos_pagina`: a qué tipos aplica; `[todas]` o una lista.
- `enunciado`, `titulo_hallazgo`, `recomendacion`.
- `fuerza` (A, B, C) y `tipo_evidencia` (`requisito_oficial`, `efecto_experimental`, `correlacional`, `consenso`).
- `fuentes`: cada una con `titulo`, `url`, su propia fuerza y tipo de evidencia, y una `nota` con lo que la fuente dice y lo que no dice.
- `verificado_el`: fecha en que se leyó la fuente.
- `colector`: función determinista que produce la evidencia, cuando existe. Las reglas sin colector solo las evalúan los subagentes.
- `impacto_esperado`, `esfuerzo`, `dependencia`, `horizonte`: los ejes de priorización.

Distribución de fuerza: 53 reglas A, 7 B, 13 C. Las 44 reglas de ámbito `pagina` se evalúan por URL; las 9 de ámbito `sitio` una vez por dominio.

### Las dos etiquetas de evidencia

Cada hallazgo lleva dos etiquetas independientes, explicadas en `referencias/etiquetas-confianza.md`.

**Etiqueta 1, evidencia de la observación.** Dice quién vio el problema.

| Etiqueta | Significado |
|---|---|
| Confirmado | Un colector lo observó directamente en el HTML, las cabeceras, robots.txt o el sitemap |
| Probable | Dos colectores coinciden, o una heurística de alta especificidad |
| Hipótesis | Juicio del modelo o de un subagente; requiere revisión humana antes de actuar y no entra en el puntaje |

**Etiqueta 2, fuerza de la regla con su tipo de evidencia.** Dice qué tan bien respaldada está la regla que se aplicó, independientemente de la observación.

| Fuerza | Definición |
|---|---|
| A | Documentación oficial del motor, un estándar (RFC 9309, W3C) o un estudio revisado por pares |
| B | Estudio de industria con metodología publicada |
| C | Consenso de practicantes o hipótesis del proyecto |

En los reportes se muestran juntas, por ejemplo `Confirmado · A · requisito oficial` o `Hipótesis · B · correlacional`. Un hallazgo puede ser Confirmado sobre una regla C (se observó con certeza algo cuya importancia no está probada) o Hipótesis sobre una regla A (la regla es firme pero el modelo no pudo verificar el hecho).

El puntaje de cumplimiento pondera A=3, B=2, C=1 sobre las reglas aplicables con evidencia. Mide verificaciones superadas, no visibilidad, y nunca va en el titular del reporte.

## Limitaciones conocidas

- **AI Overviews requiere captura humana.** No hay API oficial. Una captura por navegador automatizado devuelve "sin resumen" en la mayoría de los prompts donde una persona en ventana de incógnito sí ve el resumen. Por eso solo la captura manual cuenta como evidencia de ausencia (nota de método en la regla V-04).
- **Las citaciones de ChatGPT y Perplexity no se recuperan con captura automatizada.** El texto de la respuesta sí, pero la lista de fuentes que muestra la interfaz no llega de forma fiable a una captura por script. El modo API devuelve citas estructuradas, pero es un proxy con otro comportamiento de búsqueda, y por eso las series manual y API se comparan solo en `calibrar`.
- **Las citas de AI Overviews son redirecciones opacas.** Las fuentes llegan como enlaces de `google.com/goto` que responden 403 al resolverse. La citación de AI Overviews queda como desconocida, no como cero; la mención de marca sí se mide sobre el texto.
- La dependencia de JavaScript se detecta por heurística (HTML casi vacío más marcadores de framework o placeholders de plantilla) y se confirma solo con `--render`, que requiere Playwright instalado.
- La detección del tipo de página es heurística por ruta, JSON-LD y contenido; `--tipo` permite forzarla.
- Las cifras del paper de Princeton (KDD 2024) se citan con su alcance real: motor simulado con GPT-3.5 en 2023. C-SEO Bench (2025) no replica esos efectos. Ver `referencias/princeton-kdd-2024.md` y `referencias/fuentes-verificadas.md`.
- Las fuentes fueron verificadas el 2026-09-10. Los motores cambian sus bots, directivas y comportamiento; cada regla lleva `verificado_el` para saber cuándo revisar.

## Qué NO hace

- **No aplica cambios en producción.** Solo genera propuestas en `salidas/`. No toca el CMS, el CRM ni la analítica del cliente (regla N-05).
- **No proyecta impacto numérico.** Ningún hallazgo dice "+18 puntos" o "+40% de citas"; el validador de `fusionar` rechaza salidas de subagentes que lo hagan (regla N-01).
- **No sustituye la medición de negocio.** Share of answers, tasa de citación y puntaje de cumplimiento son proxies. Los MQL, el pipeline y el ingreso se miden en GA4 y el CRM, no aquí.
- No inventa cifras, citas ni nombres en propuestas de contenido; donde falte un dato escribe `[DATO REQUERIDO: qué falta]` (regla N-03).
- No recomienda FAQPage con preguntas sintéticas ni trata llms.txt como palanca (reglas N-02 y N-04).
- No decide por el usuario si bloquear bots de entrenamiento: es una decisión de política que no afecta la aparición en respuestas según los proveedores (regla T-04).

## Pruebas

```bash
.venv/bin/python -m pytest -q
```

Las fixturas de `tests/fixturas/` son HTML, robots.txt y sitemaps inventados para dos empresas ficticias (un software de nómina y una universidad). Ninguna proviene de un sitio real. Una prueba se omite cuando no existe `datos/historial`, un directorio que solo aparece después de correr auditorías.

## Licencia y atribución

Este proyecto se distribuye bajo la licencia MIT (ver `LICENSE`).

Parte del código de `scripts/geomql/` deriva de [metawhisp/best-aeo-skill](https://github.com/metawhisp/best-aeo-skill), publicado bajo licencia MIT. `NOTICE` lista archivo por archivo qué se reutilizó y qué se descartó por decisión de diseño: el rulebook "The 100 Rules", sus estadísticas y pesos, los frameworks CORE-EEAT y CITE, y sus afirmaciones sobre el paper de Princeton, AutoGEO, C-SEO Bench, FAQPage y llms.txt.
