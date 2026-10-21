# Tipos de página y señales de detección

El colector `tipo_pagina.py` asigna uno de estos tipos y una confianza. Se puede forzar con `--tipo`. Cada regla del rulebook declara a qué tipos aplica; `interiores` significa todas menos la home.

| Tipo | Qué es | Señales |
|---|---|---|
| home | Portada del dominio | ruta raíz o índice; WebSite en JSON-LD |
| solucion | Página de producto, servicio, plataforma o precios | ruta producto/solucion/servicio/precios; Product, Service o SoftwareApplication; menciones de precio, demo o cotización |
| articulo | Blog, guía, noticia, recurso | ruta blog/articulo/recursos; Article o BlogPosting; byline; etiqueta time; texto largo con varios H2 |
| comparativa | Comparación o alternativas | "vs", "versus", "comparativa", "alternativas", "mejores" en ruta o H1 |
| faq | Preguntas frecuentes | ruta faq/preguntas-frecuentes; FAQPage; tres o más encabezados terminados en signo de interrogación |
| glosario | Definición de término | ruta glosario/que-es; H1 "Qué es"; DefinedTerm; listas de definición |
| landing | Página de campaña o captura | formulario con poco texto; casi sin navegación; noindex; ruta lp/landing/descarga |
| local | Sucursal u oficina | LocalBusiness; teléfono y dirección en el contenido; ruta sucursal/oficina/ubicacion |
| perfil | Perfil de autor o equipo | ruta equipo/autor/perfil; ProfilePage |
| otra | Sin señales suficientes | solo aplican las reglas marcadas `todas` |

## Reglas por tipo (resumen)

- Article (S-03) y autoría (E-04, S-10): artículo y comparativa; nunca en la home.
- Organization y WebSite (S-04), sameAs (E-02, E-03): home.
- BreadcrumbList (S-05): interiores.
- Product (S-06) y Service (S-07): solución.
- FAQPage (S-08): solo faq; y solo se mantiene si las preguntas son visibles.
- LocalBusiness (S-09) y NAP (E-06): local.
- Respuesta directa (X-01): artículo, faq, glosario, solución, comparativa.
- Definición (X-10): glosario, solución, faq.
- Tablas y listas (X-03): comparativa, artículo, solución.


## programa (añadido 2026-09-11)

Página de un programa educativo o su catálogo: carrera profesional, licenciatura, ingeniería, preparatoria, posgrado, diplomado, curso o certificado. Señales: ruta con esos términos; H1 que nombra el programa; texto con plan de estudios, perfil de egreso, campo laboral, duración en semestres o tetramestres, modalidad, RVOE o certificados. Le aplican las reglas de contenido (respuesta directa, definición, tablas y listas, imágenes, ejemplos) y las de sitio; no le aplican autoría, Article ni fecha visible, que son de artículos.

## institucional (añadido 2026-09-11)

Página corporativa o de proceso: quiénes somos, modelo educativo, admisiones, becas y financiamiento, contacto, campus, calculadora de costos. Señales: ruta con esos términos; H1 institucional; texto con misión, visión, historia, proceso o requisitos de admisión, tipos de becas, colegiatura. Le aplican las reglas de contenido (incluidos datos sin fuente para afirmaciones de resultados) y las de sitio; no le aplican autoría, Article ni fecha visible.
