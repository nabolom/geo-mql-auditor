---
name: geo-mql-auditor
description: Usar cuando el usuario pida auditar, medir, comparar o mejorar la visibilidad de un sitio en motores de respuesta con IA (ChatGPT, Perplexity, Gemini, Google AI Overviews o AI Mode, Claude, Copilot), hable de GEO, AEO, share of answers, citaciones por IA, llms.txt, robots.txt para bots de IA, datos estructurados para IA, o quiera conectar esa visibilidad con MQLs, scoring de leads, tracking de tráfico referido por IA o campos del CRM.
---

# geo-mql-auditor

Audita y mide la visibilidad en motores de respuesta con IA. Incluye reglas y KPIs exploratorios relacionados con MQL, pero no implementa generación, scoring o atribución de leads ni integraciones de CRM; si el usuario lo pide, aclara ese límite. Todo en español. Nunca aplica cambios en producción: solo genera propuestas en `salidas/`.

## Principios que no se negocian

- Cada hallazgo lleva dos etiquetas: evidencia de la observación (`Confirmado` lo vio un colector, `Probable` coinciden dos colectores, `Hipótesis` juicio del modelo que requiere revisión humana) y fuerza de la regla con su tipo de evidencia (`A · requisito oficial`, `B · experimental`, `B · correlacional`, `C · consenso`).
- Nunca presentes un impacto proyectado numérico ("+18 puntos", "+40% de citas"). Prioriza por impacto esperado, esfuerzo, dependencia y horizonte (30 días, 90 días, largo plazo).
- No inventes cifras, citas ni nombres. En una reescritura, donde falte un dato escribe `[DATO REQUERIDO: qué falta]`.
- Bloquear bots de entrenamiento (GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, Meta-ExternalAgent) es decisión de política del usuario, no un error de visibilidad. Solo los bots de búsqueda (OAI-SearchBot, Claude-SearchBot, PerplexityBot, Googlebot, bingbot, Applebot, Meta-WebIndexer) y los fetchers por usuario afectan la aparición en respuestas.
- Las cifras del paper de Princeton (KDD 2024) se citan con su alcance real: motor simulado con GPT-3.5 en 2023, hasta 40% en Position-Adjusted Word Count, y el 115.1% solo para Cite Sources en sitios en posición 5. C-SEO Bench 2025 no replica esos efectos. Ver `referencias/princeton-kdd-2024.md`.
- FAQPage no es palanca (Google retiró el rich result el 7 de mayo de 2026); llms.txt es prioridad baja (Google no lo usa y ningún proveedor confirma consumirlo). Los datos estructurados son higiene, no palanca.
- El puntaje de cumplimiento nunca va en el titular; mide verificaciones superadas, no visibilidad.
- La visibilidad medida por API es un proxy; cada corrida lleva `modo` (manual o api) y los modos no se mezclan.
- Todo diagnóstico que vaya a audiencia no técnica tiene una versión aparte en lenguaje llano. Cada hallazgo se explica con un ejemplo concreto: qué hace una persona o un buscador, a dónde llega y qué ve. Se distingue siempre lo que era antes de lo que es ahora. Los términos técnicos se traducen. La versión técnica, con evidencia, es la fuente y no se mezcla con la no técnica.
- Los entregables a otras áreas son diagnósticos con rutas sugeridas, dirigidos al área dueña del sitio que declare el contexto. Siempre en positivo: hallazgos como áreas de oportunidad, sin lenguaje de falla ni de petición. Horas en la zona horaria del contexto.

## Flujo

0. Confirma que los subagentes geo-tecnico, geo-extractabilidad, geo-schema, geo-entidad y geo-visibilidad están registrados (Claude Code abierto desde la raíz del proyecto que contiene .claude/agents). Si no lo están, detente antes de auditar.
1. Valida el contexto: `python3 .claude/skills/geo-mql-auditor/scripts/contexto.py validar [--modulo mql]` (el CRM solo es crítico para mql). Si faltan campos críticos, pregunta al usuario lo que imprime `contexto.py faltantes` antes de recomendar. Si el usuario decide seguir sin ellos, cada supuesto queda escrito en el reporte.
2. Elige el módulo según la petición. Solo existen tres CLI: `contexto` (módulo 0), `audit` (una URL, una lista o un sitemap, hasta 100 URLs) y `visibilidad` (panel de prompts; ver sección propia). Cada CLI vive en `scripts/` y explica sus opciones con `--help`. Los módulos `mql` (journey, CTA, formularios, tracking, scoring, CRM), `compare` (contra competidores del contexto), `fix` (propuestas) y `monitor` (regresiones) no están implementados: si el usuario los pide, díselo y ofrece lo parcial que sí existe en audit: `--comparar`, `--comparar-reglas`, `--anexo-tecnico` y `--sin-negocio`.
3. Corre el CLI. Para audit:

   ```bash
   .venv/bin/python .claude/skills/geo-mql-auditor/scripts/audit.py correr --url https://dominio.com/pagina
   .venv/bin/python .claude/skills/geo-mql-auditor/scripts/audit.py correr --sitemap https://dominio.com/sitemap.xml --max-urls 100
   ```

   Opciones útiles: `--render` (Playwright, si está instalado), `--resolver-sameas`, `--tipo` para forzar el tipo de página, `--urls` para una lista explícita, y además:

   - `--comparar <json>`: JSON de una corrida anterior para comparar hallazgos (patrón del sitio vs exclusivos).
   - `--comparar-reglas <json>`: JSON de otra corrida para la tabla regla por regla (X de N en cada dominio).
   - `--anexo-tecnico`: auditoría técnica comparativa: sin contexto de negocio ni visibilidad; los hallazgos de negocio quedan como no evaluables.
   - `--sin-negocio`: ignora contexto/negocio.md (corre con contexto vacío).

   El CLI escribe el reporte base en `salidas/AAAA-MM-DD_<dominio>_audit.md` y `.json`, y un archivo por vector en `salidas/tmp/<corrida>/{tecnico,extractabilidad,schema,entidad}.json` con resumen agregado (reglas × tipos de página y ejemplos), pensado para los subagentes.
4. Lanza los cuatro subagentes de audit en paralelo, en un solo mensaje con cuatro llamadas a Agent: `geo-tecnico`, `geo-extractabilidad`, `geo-schema`, `geo-entidad`. A cada uno pásale solo la ruta de su archivo de vector: dentro van las reglas completas de su categoría con fuentes y extractos de referencia, el resultado por URL, la guía de etiquetas y (en extractabilidad) las muestras de texto. No les pases el reporte ni otras rutas. Devuelven un JSON con `hallazgos`, `ajustes` y `notas`. Guarda cada salida en `salidas/tmp/<corrida>/subagente_<vector>.json`.
5. Fusiona y regenera el reporte:

   ```bash
   .venv/bin/python .claude/skills/geo-mql-auditor/scripts/audit.py fusionar --reporte salidas/<archivo>.json --hallazgos salidas/tmp/<corrida>/subagente_*.json
   ```

   Si `fusionar` rechaza una salida (por ejemplo, contiene impacto proyectado numérico), corrige la salida, no el validador.
6. Entrega al usuario: la ruta del reporte, el titular (métricas de visibilidad si existen; si no, los tres hallazgos prioritarios), los supuestos y el roadmap. No pegues el reporte completo en el chat salvo que lo pidan.

## Módulo visibilidad

El CLI es `scripts/visibilidad.py`; los datos viven en `datos/visibilidad/` (`prompts.csv`, `config.json`, `historial.csv`, `resumen.csv`, `calibracion.csv`, `raw/`). Reglas que no se negocian: cada corrida lleva `modo` (`manual` | `api`) y los modos nunca se mezclan en una serie; `config.json` deriva `user_location` e idioma de `contexto/negocio.md`; `search_context_size` es `medium` y las repeticiones son 3 por defecto; AI Overviews solo por captura manual; la precisión de la descripción de marca es Hipótesis hasta revisión humana.

1. Panel: `visibilidad.py prompts` crea `datos/visibilidad/prompts.csv` con las preguntas de descubrimiento, consideración y decisión del contexto (`origen=contexto`). **Muéstrale el panel al usuario antes de medir** y deja que agregue o quite preguntas. Cualquier fila que añadas por tu cuenta lleva `origen=ejemplo`; el reporte advierte si se midió con ellas. `visibilidad.py importar-gsc --csv export.csv [--aplicar]` propone consultas reales de Search Console con `origen=gsc`.
2. Config: `visibilidad.py config` escribe `config.json` (modelos por motor, `search_context_size`, repeticiones, `user_location`, idioma). Nunca la edites a mano para cambiar la ubicación: corrige el contexto y regenera con `--forzar`.
3. Captura manual: `visibilidad.py captura --corrida <id> [--motores chatgpt,perplexity,gemini,claude,aio] [--repeticiones 3]` genera `captura_<fecha>_<id>.md` (instrucciones y un bloque por prompt × motor × repetición) y `respuestas_<fecha>_<id>.csv`, donde el usuario pega `respuesta` y `urls_citadas` (separadas por `|`). Si la captura llega en otro formato, `visibilidad.py importar-captura --csv <archivo>` (CSV con motor, prompt_id, pregunta, respuesta, urls_citadas, notas) o `visibilidad.py importar-txt --archivo <txt> --motor aio` (bloques `### <prompt_id>` con PREGUNTA, RESPUESTA, URLS y NOTAS) la normalizan y validan contra el panel sin sustituir preguntas. Capturas incompletas se bloquean salvo que se acepte `--forzar`; el override queda marcado en las notas y en el reporte, y no sirve de base para deltas comparables. AI Overviews requiere captura humana: una captura automatizada devuelve SIN_AIO donde una persona sí ve el resumen (nota de método en V-04), y sus fuentes son enlaces google.com/goto opacos que no cuentan como cita ni como ausencia de cita.
4. Modo API: `visibilidad.py correr --corrida <id> [--solo-costo]` usa las llaves de `.env` (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `GEMINI_API_KEY`), informa subtotal de tarifas conocidas y advierte si no puede estimar el costo total antes de consultar; guarda el crudo en `raw/`. AI Overviews queda excluido de la selección API por defecto y no se permite como motor API. Sin llaves no consulta nada. La serie API es un proxy: no se compara con la manual salvo en `calibrar`.
5. Análisis y métricas: `visibilidad.py analizar --respuestas <csv>` anexa al historial; `visibilidad.py metricas --corrida <id>` escribe `resumen.csv`, el reporte `salidas/AAAA-MM-DD_<dominio>_visibilidad_<id>.md` y el vector `salidas/tmp/<id>/visibilidad.json`. El titular son las métricas; la variabilidad acompaña cada observación y los deltas solo se muestran cuando coinciden panel, motores y modelos.
6. Subagente: lanza `geo-visibilidad` con la ruta de `visibilidad.json` como único argumento. Guarda su JSON en `salidas/tmp/<id>/subagente_visibilidad.json` y aplícalo con `visibilidad.py fusionar --corrida <id> --salida <ruta>`. Sus clasificaciones de precisión quedan como Hipótesis en el historial y en el reporte.
7. Calibración: cuando existan una corrida manual y una API con los mismos prompts, `visibilidad.py calibrar --manual <id> --api <id>` escribe `calibracion.csv` y el veredicto (confiable, parcial, no confiable) por motor.

Los módulos mql, compare, fix y monitor no están implementados (ver el paso 2 del Flujo).

## Acceso a red, archivos y llaves

- Red en audit: solo el sitio auditado. Descarga las páginas pedidas (o las que liste su sitemap), `robots.txt`, el sitemap que declara `robots.txt` (o `/sitemap.xml`) con sus sitemaps hijos, y `llms.txt`, y sigue sus redirecciones. Con `--resolver-sameas` consulta además cada URL de `sameAs`; con `--render`, Playwright carga la página con todos sus recursos (scripts, estilos, imágenes y terceros que la página incluya).
- Red en visibilidad: la captura manual, el análisis y las métricas no salen a la red. En modo API (`visibilidad.py correr`) solo consulta `api.openai.com`, `api.anthropic.com`, `api.perplexity.ai` y `generativelanguage.googleapis.com`; para Gemini sigue además, con una petición HEAD, los enlaces de cita de `vertexaisearch.cloud.google.com` hasta la URL final citada. `--solo-costo` no consulta nada.
- Llaves: se leen solo de `.env` (o del archivo que indique `--env`) y solo en modo API. No se leen variables de entorno del sistema.
- Archivos: escribe solo en `salidas/` y `datos/` (caché, historial y visibilidad). Nunca escribe en el sitio auditado, el CMS, el CRM ni la analítica.

## Dónde está cada cosa

- Reglas con fuente, fuerza, tipo de evidencia y fecha de verificación: `reglas/rulebook.yaml`. Cita el id de la regla en cada hallazgo.
- Bots de IA verificados por categoría: `referencias/bots-ia.md` y `bots-ia.json`.
- Etiquetas y priorización: `referencias/etiquetas-confianza.md`.
- Bitácora de fuentes verificadas y qué NO dicen: `referencias/fuentes-verificadas.md`.
- Tipos de página y señales: `referencias/tipos-de-pagina.md`.
- Plantillas de JSON-LD y reporte: `plantillas/`.
- Contexto de negocio: `contexto/negocio.md`, copiado de `contexto/negocio.plantilla.md`. Datos: `datos/`. Salidas: `salidas/`.

## Errores que debes evitar

| Tentación | Qué hacer en su lugar |
|---|---|
| Recomendar Article en la home o FAQPage en todas las páginas | Aplica solo las reglas del tipo de página detectado; el rulebook lista `tipos_pagina` |
| Contar cualquier número como estadística | Usa el colector `estadisticas`, que excluye teléfonos, fechas, años sueltos y menús |
| Decir "bloquear GPTBot te quita visibilidad" | Solo los bots de búsqueda y los fetchers por usuario afectan las respuestas; pide la decisión de política |
| Escribir "esto subirá el puntaje 18 puntos" | Impacto esperado alto/medio/bajo, esfuerzo y horizonte |
| Rellenar una reescritura con cifras plausibles | `[DATO REQUERIDO: ...]` en cada hueco; `fix` no existe, así que revisa a mano que no quede ninguna cifra sin fuente |
| Presentar un juicio del modelo como observación | Etiquétalo `Hipótesis` y pide revisión humana |
| Elegir una URL o un sitio por tu cuenta | Usa solo la URL que dé el usuario o las fixturas de `tests/fixturas/` |
