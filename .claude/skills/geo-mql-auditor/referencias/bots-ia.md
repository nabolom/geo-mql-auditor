# Bots de IA verificados (2026-09-10)

Fuente única para los scripts: `bots-ia.json`. Todo se verificó leyendo la documentación oficial de cada proveedor; lo que no aparece en documentación oficial se marca **no documentado**.

## Categorías

- **Búsqueda / índice**: indexan para mostrar y citar el sitio en respuestas. Bloquearlos sí quita visibilidad.
- **Fetch por usuario**: descargan una página cuando un usuario lo pide. OpenAI, Perplexity, Google, Meta y Amazon declaran que estos fetchers pueden ignorar robots.txt; Anthropic dice que Claude-User sí lo respeta. Bloquearlos en el WAF reduce la visibilidad en respuestas en tiempo real.
- **Entrenamiento**: recolectan contenido para entrenar modelos. Bloquearlos es decisión de política; los proveedores declaran que no afecta la aparición en búsqueda.

## Tabla

| Proveedor | Token | Categoría | Nota oficial | Fuente |
|---|---|---|---|---|
| OpenAI | OAI-SearchBot | búsqueda | Sin él, el sitio no aparece en respuestas de ChatGPT search (puede aparecer como enlace de navegación) | developers.openai.com/api/docs/bots |
| OpenAI | ChatGPT-User | usuario | "robots.txt rules may not apply"; no determina la aparición en búsqueda | ídem |
| OpenAI | GPTBot | entrenamiento | Disallow = no usar en entrenamiento | ídem |
| Anthropic | Claude-SearchBot | búsqueda | Mejora la calidad de resultados de búsqueda | support.claude.com, artículo 8896518 (2026-04-07) |
| Anthropic | Claude-User | usuario | Respeta robots.txt; bloquearlo reduce visibilidad en búsqueda dirigida por el usuario | ídem |
| Anthropic | ClaudeBot | entrenamiento | Contenido que podría contribuir al entrenamiento | ídem |
| Anthropic | anthropic-ai, Claude-Web | no documentado | Ausentes del artículo oficial (legado) | ídem |
| Google | Googlebot | búsqueda | AI Overviews y AI Mode usan el índice de Search; se controlan con nosnippet, max-snippet, data-nosnippet y noindex | developers.google.com (common crawlers, ai-features) |
| Google | Google-Extended | entrenamiento (token de control, no user-agent) | Entrenamiento y grounding en Gemini Apps y Vertex AI; "does not impact a site's inclusion in Google Search nor is it used as a ranking signal" | ídem |
| Google | GoogleOther, Google-CloudVertexBot | otro | Sin relación con visibilidad en respuestas | ídem |
| Perplexity | PerplexityBot | búsqueda | "not used to crawl content for AI foundation models" | docs.perplexity.ai/guides/bots |
| Perplexity | Perplexity-User | usuario | "generally ignores robots.txt rules" | ídem |
| Apple | Applebot | búsqueda | Spotlight, Siri, Safari; sin regla propia sigue las de Googlebot | support.apple.com/en-us/119829 |
| Apple | Applebot-Extended | entrenamiento (token) | No rastrea; bloquearlo no afecta Spotlight, Siri ni Safari | ídem |
| Microsoft | bingbot | búsqueda | Copilot no tiene user-agent propio; se controla con meta bingbot nocache (solo URL, título y snippet) o noarchive (fuera de respuestas y de entrenamiento) | Bing Webmaster help y blog 2023-09-22 |
| Meta | Meta-WebIndexer | búsqueda | Permitirlo ayuda a citar y enlazar en respuestas de Meta AI | developers.facebook.com web-crawlers (2026-05-21) |
| Meta | Meta-ExternalFetcher | usuario | Puede saltarse robots.txt por fetch a petición del usuario | ídem |
| Meta | Meta-ExternalAgent | entrenamiento | Entrenamiento e indexación directa | ídem |
| Meta | facebookexternalhit | otro | Vistas previas de enlaces | ídem |
| Meta | FacebookBot | no documentado | Ya no aparece en la documentación | ídem |
| DuckDuckGo | DuckAssistBot | búsqueda | No entrena modelos | duckduckgo.com help |
| Amazon | Amzn-SearchBot, Amzn-User | búsqueda, usuario | No entrenan | developer.amazon.com/amazonbot |
| Amazon | Amazonbot | entrenamiento | "may be used to train Amazon AI models" | ídem |
| Mistral | MistralAI-User | usuario | No entrena | docs.mistral.ai/robots |
| Common Crawl | CCBot | entrenamiento (indirecto) | Repositorio abierto; terceros entrenan con sus datos | commoncrawl.org/ccbot |
| ByteDance | Bytespider | no documentado | Sin documentación oficial accesible | — |
| Cohere | cohere-ai | no documentado | Cohere declara que no rastrea con ese token | docs.cohere.com |

## Controles que no son robots.txt

- Google AI Overviews / AI Mode: `nosnippet`, `max-snippet`, `data-nosnippet`, `noindex`. Google-Extended no los controla.
- Microsoft Copilot / Bing: meta `bingbot` con `nocache` o `noarchive`.

## Verificación de identidad

OpenAI publica rangos IP en openai.com/gptbot.json, searchbot.json y chatgpt-user.json; Anthropic en claude.com/crawling/bots.json; Perplexity en perplexity.com/perplexitybot.json y perplexity-user.json; Google en gstatic.com/ipranges; Apple en search.developer.apple.com/applebot.json; DuckDuckGo en duckduckgo.com/duckassistbot.json. Un bloqueo por IP sin verificación puede dejar fuera a bots legítimos.
