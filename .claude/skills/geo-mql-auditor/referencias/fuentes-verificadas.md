# Bitácora de fuentes verificadas

Fecha de verificación: 2026-09-10. Método: lectura directa de la página (fetch) salvo donde se indica "snippet". Las fuentes verificadas solo por snippet valen como máximo C hasta leerlas.

## Papers

| Fuente | URL | Qué dice | Qué NO dice |
|---|---|---|---|
| Aggarwal et al., GEO (KDD 2024) | https://arxiv.org/abs/2311.09735 | 9 métodos; hasta 40% en PAWC en motor simulado con GPT-3.5; 115.1% solo Cite Sources en posición 5 (Tabla 2); Keyword Stuffing 10% peor | Nada de Flesch, topic relevance, length; nada de −60%, 3.2x, +14% |
| Puerto et al., C-SEO Bench (NeurIPS D&B 2025) | https://arxiv.org/abs/2506.11097 | La mayoría de métodos C-SEO son ineficaces o negativos; la posición en el contexto pesa más | No evalúa schema ni llms.txt |
| Wu et al., AutoGEO (ICLR 2026) | https://arxiv.org/abs/2510.11438 | Extracción de reglas de preferencia con modelos frontera; hasta +50.99% sobre el mejor baseline en su benchmark | No es 2502.13392 (robotaxis) |
| Pfrommer et al., Ranking Manipulation for Conversational Search Engines (EMNLP 2024) | https://arxiv.org/abs/2406.03589 | Los LLM son sensibles a la posición en el contexto; ataques adversariales suben rankings | Nada sobre técnicas legítimas |
| Nestaas et al., Adversarial SEO for LLMs (ICLR 2025) | https://arxiv.org/abs/2406.18382 | Inyecciones suben recomendaciones 2.5x en Bing y Perplexity; dilema del prisionero | Nada sobre técnicas legítimas |
| Grossman et al., How Generative AI Disrupts Search (SIGIR 2026) | https://arxiv.org/abs/2604.27790 | 11,500 consultas; AI Overviews en 51.5%; sitios que bloquean crawlers de IA aparecen menos | No mide técnicas de optimización |
| Zhang, He y Yao, From Citation Selection to Citation Absorption (preprint 2026) | https://arxiv.org/abs/2604.25707 | 602 prompts, 21,143 citas; páginas influyentes son más estructuradas y ricas en definiciones, cifras, comparaciones y pasos | Correlacional |
| Yu et al., GEO-SFE (preprint 2026) | https://arxiv.org/abs/2603.29979 | Estructura mejora citación 14-20% en 6 motores | Estructura en general, no listas |

## Documentación oficial

| Fuente | URL | Qué dice |
|---|---|---|
| Google, AI features and your website (2025-12-10) | https://developers.google.com/search/docs/appearance/ai-features | Sin requisitos adicionales; controles nosnippet, data-nosnippet, max-snippet, noindex |
| Google, AI optimization guide (2026-07-10) | https://developers.google.com/search/docs/fundamentals/ai-optimization-guide | Schema no requerido; sin archivos ni Markdown especiales; contenido no commodity; contenido principal distinguible |
| Google, Search Central updates | https://developers.google.com/search/updates | FAQ rich result retirado el 2026-05-07 (entrada 2026-05-08); documentación eliminada 2026-06-15; llms.txt no necesario para Google Search (2026-06-15) |
| Google, intro y políticas de datos estructurados | https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data y /sd-policies | JSON-LD recomendado; no marcar contenido no visible; representación fiel |
| Google, Article | https://developers.google.com/search/docs/appearance/structured-data/article | Recomendadas: author, author.name, author.url, dateModified, datePublished, headline, image |
| Google, Organization | https://developers.google.com/search/docs/appearance/structured-data/organization | name, url, logo, sameAs, description, address, contactPoint… |
| Google, Breadcrumb, Product, Local business, Profile page | rutas /breadcrumb, /product-snippet, /local-business, /profile-page | Propiedades requeridas y recomendadas; Person sin rich result propio |
| Google, Publication dates | https://developers.google.com/search/docs/appearance/publication-dates | Fecha visible etiquetada, coherente con datePublished/dateModified; minimizar otras fechas |
| Google, JavaScript SEO basics (2026-03-04) | https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics | Chromium evergreen; "not all bots can run JavaScript"; SSR o prerender |
| Google, Consolidate duplicate URLs | https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls | rel=canonical señal fuerte; absoluto; autorreferente |
| Google, Robots meta tag | https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag | nosnippet y max-snippet limitan el insumo de AI Overviews y AI Mode |
| Google, Build a sitemap | https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap | lastmod = última actualización significativa; ignora priority y changefreq; 50k URL / 50 MB |
| Google, robots.txt interpretation (2026-08-31) | https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt | Grupo más específico; regla más larga; empate menos restrictivo; por host, protocolo y puerto |
| Google, HTTP status codes (2026-02-04) | https://developers.google.com/search/docs/crawling-indexing/http-network-errors | Hasta 10 saltos; 301 fuerte, 302 débil; 4xx fuera del índice |
| Google, Localized versions (2025-12-22) | https://developers.google.com/search/docs/specialty/international/localized-versions | hreflang bidireccional; x-default |
| Google, Snippets (2026-04-20) | https://developers.google.com/search/docs/appearance/snippet | Snippets desde el contenido; meta description descriptiva |
| Google, Creating helpful content | https://developers.google.com/search/docs/fundamentals/creating-helpful-content | Who, How, Why; bylines; confianza |
| Google, common crawlers | https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers | Google-Extended: token de control; no afecta inclusión ni ranking |
| RFC 9309 | https://www.rfc-editor.org/rfc/rfc9309.html | Coincidencia más específica; empate a Allow; 5xx = disallow total; 500 KiB |
| W3C JSON-LD 1.1 | https://www.w3.org/TR/json-ld11/ | @id identifica nodos; referencias por @id; @graph |
| OpenAI, crawlers | https://developers.openai.com/api/docs/bots | OAI-SearchBot, ChatGPT-User, GPTBot, OAI-AdsBot; IPs publicadas |
| Anthropic, crawlers (2026-04-07) | https://support.claude.com/en/articles/8896518 | ClaudeBot, Claude-User, Claude-SearchBot; respetan robots.txt; nada sobre llms.txt |
| Perplexity, crawlers | https://docs.perplexity.ai/guides/bots | PerplexityBot no entrena; Perplexity-User ignora robots.txt |
| Apple, Applebot | https://support.apple.com/en-us/119829 | Applebot-Extended no rastrea; opt-out de entrenamiento |
| Meta, web crawlers (2026-05-21) | https://developers.facebook.com/docs/sharing/webmasters/web-crawlers | Meta-WebIndexer, Meta-ExternalFetcher, Meta-ExternalAgent |
| Bing Webmaster, AI Performance (2026-02-10) | https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview | Encabezados claros, tablas, secciones FAQ, ejemplos, datos con fuente, frescura, IndexNow |
| Bing Webmaster, Bing Chat controls (2023-09-22) | blogs.bing.com/webmaster/september-2023 | nocache y noarchive |
| Google Analytics, Default channel group | https://support.google.com/analytics/answer/9756891 | Canal AI Assistant (medium ai-assistant); excluye AI Overviews y AI Mode |
| Google Analytics, What's new (2026-05-13, 2026-06-11) | https://support.google.com/analytics/answer/9164320 | Canal AI Assistant; Source Group con ChatGPT y Perplexity |
| Google Analytics, Custom channel groups | https://support.google.com/analytics/answer/13051316 | 2 grupos por propiedad; retroactivos |
| Google Analytics, Recommended events | https://support.google.com/analytics/answer/9267735 | generate_lead, qualify_lead, working_lead, close_convert_lead |
| Google Analytics, Campaign URLs | https://support.google.com/analytics/answer/10917952 | utm_source, utm_medium, utm_campaign siempre |
| llms.txt | https://llmstxt.org/ | Especificación: H1, blockquote, secciones H2 con enlaces, sección Optional |

## Estudios de industria leídos

| Fuente | URL | Muestra y hallazgo | Fuerza |
|---|---|---|---|
| Ahrefs, schema y citas (2026-05-11) | https://ahrefs.com/blog/schema-ai-citations/ | 1,885 páginas vs 4,000 control; sin aumento de citas | B · experimental |
| Ahrefs, 38% de citas de AIO del top 10 (2026-03-02) | https://ahrefs.com/blog/ai-overview-citations-top-10/ | 863k SERPs, 4M URLs | B · correlacional |
| Ahrefs, 12% de URLs citadas en top 10 (2025-08-11) | https://ahrefs.com/blog/ai-search-overlap/ | 15k prompts; Perplexity 28.6%, ChatGPT 8% | B · correlacional |
| Ahrefs, frescura (2025-07-28) | https://ahrefs.com/blog/do-ai-assistants-prefer-to-cite-fresh-content/ | 16.9M URLs; contenido citado 25.7% más reciente | B · correlacional |
| Ahrefs, 75k marcas (2025-12-12) | https://ahrefs.com/blog/ai-brand-visibility-correlations/ | Spearman ~0.74 con menciones en YouTube | B · correlacional |
| Ahrefs, llms.txt (2026-06-15) | https://ahrefs.com/blog/llmstxt-study/ | 137,210 dominios; 28% lo publica; 97% sin peticiones | B · correlacional |
| Profound, citation patterns (2025-06-05) | https://www.tryprofound.com/blog/ai-platform-citation-patterns | 680M citas; Wikipedia 7.8% en ChatGPT; Reddit 6.6% en Perplexity | B · correlacional |
| Pew Research (2025-07-22) | https://www.pewresearch.org/short-reads/2025/07/22/google-users-are-less-likely-to-click-on-links-when-an-ai-summary-appears-in-the-results/ | 900 adultos, 68,879 búsquedas; clic 8% vs 15% | B · correlacional |
| Seer Interactive (2025-06-03) | https://www.seerinteractive.com/insights/case-study-6-learnings-about-how-traffic-from-chatgpt-converts | Un cliente; conversión ChatGPT 15.9% vs orgánico 1.76% | B · correlacional (n=1) |
| Indig y Semrush, Ghost Citations (2026) | https://www.semrush.com/blog/the-ghost-citations-study/ | 600k citas; correlación citas y menciones −0.229; 62% de citas sin mención | B · correlacional (metodología parcial) |

## Verificadas solo por snippet (no se usan como A ni B)

Semrush AI Visibility Index; Similarweb referidos por industria; Adobe Digital Insights; Perplexity "source labels"; OpenAI "Searching the web with ChatGPT"; Bing Webmaster Guidelines (contenido servido con JavaScript).

## Sin fuente primaria (descartadas)

"+115% general", "autoría anónima −60%", "frescura 3.2x", "listas +14%", "corpus de 41 millones de citas", "Anthropic y Perplexity confirmaron consumo de llms.txt", "FAQ schema ~40% más citas en ChatGPT".
