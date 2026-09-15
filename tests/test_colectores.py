"""Colectores por vector sobre las fixturas: técnico, schema, extractabilidad, estadísticas, citas, frescura, entidad, llms.txt, contexto."""
from __future__ import annotations

from datetime import datetime, timezone

from geomql import citas, contexto, entidad, estadisticas, extractabilidad, fetch, frescura, llmstxt, schema, tecnico
from geomql.html import Documento

AHORA = datetime(2026, 9, 10, tzinfo=timezone.utc)


def _doc(html_de, nombre, url):
    return Documento(html_de(nombre), url)


# ------------------------------------------------------------------ técnico
def test_tecnico_canonical_directivas_y_hreflang(html_de):
    url = "https://www.nominafacil.mx/blog/reducir-rotacion-personal"
    d = _doc(html_de, "articulo.html", url)
    f = fetch._resultado_vacio(url, status=200, html=d.html)
    t = tecnico.analizar_pagina(f, d, url)
    assert t["codigo_http"]["status"] == 200 and t["codigo_http"]["saltos"] == 0
    assert t["canonical"]["autorreferente"] and t["canonical"]["absoluto"]
    assert not t["directivas"]["noindex"] and not t["directivas"]["nosnippet"]
    assert t["hreflang"]["incluye_self"] and t["hreflang"]["incluye_x_default"]
    assert t["dependencia_js"]["veredicto"] == "sin_dependencia"


def test_tecnico_landing_noindex_y_bingbot(html_de):
    url = "https://www.nominafacil.mx/lp/guia"
    d = _doc(html_de, "landing.html", url)
    t = tecnico.analizar_pagina(fetch._resultado_vacio(url, status=200), d, url)
    assert t["directivas"]["noindex"] and t["meta_bingbot"]["noarchive"]
    assert not t["canonical"]["presente"] and not t["meta_description"]["presente"]


def test_tecnico_spa_probable_dependencia_js(html_de):
    url = "https://app.nominafacil.mx/recursos/guia-nomina"
    d = _doc(html_de, "spa.html", url)
    t = tecnico.analizar_pagina(fetch._resultado_vacio(url, status=200), d, url)
    js = t["dependencia_js"]
    assert js["veredicto"] == "probable_dependencia" and js["observacion"] == "Probable"
    assert "Next.js" in js["marcadores_framework"] and js["contenedor_raiz_vacio"]
    con_render = tecnico.analizar_pagina(fetch._resultado_vacio(url, status=200), d, url, render={"disponible": True, "palabras_principal": 800})
    assert con_render["dependencia_js"]["veredicto"] == "dependencia_confirmada"


def test_tecnico_max_snippet_restrictivo(html_de):
    url = "https://www.nominafacil.mx/producto/timbrado"
    t = tecnico.analizar_pagina(fetch._resultado_vacio(url, status=200), _doc(html_de, "solucion.html", url), url)
    assert t["directivas"]["max_snippet"] == 50 and t["directivas"]["max_snippet_restrictivo"]


def test_tecnico_redirecciones_y_sitemap():
    url = "http://nominafacil.mx/"
    f = fetch._resultado_vacio(url, status=200, url_final="https://www.nominafacil.mx/", cadena_redirecciones=[{"de": url, "a": "https://nominafacil.mx/", "codigo": 301}, {"de": "https://nominafacil.mx/", "a": "https://www.nominafacil.mx/", "codigo": 302}])
    t = tecnico.analizar_pagina(f, Documento("<html><body><main><p>x</p></main></body></html>", url), url)
    assert t["codigo_http"]["saltos"] == 2 and t["codigo_http"]["solo_301"] is False
    s = tecnico.analizar_sitemap({"sitemap": "s", "urls_total": 4, "con_lastmod": 3, "sin_lastmod": 1, "urls": [{"loc": "a", "lastmod": "2026-08-15"}, {"loc": "b", "lastmod": "2027-01-01"}]}, ahora=AHORA)
    assert s["presente"] and s["lastmod_futuras"] == 1 and s["sin_lastmod"] == 1


# ------------------------------------------------------------------- schema
def test_schema_articulo_completo_con_graph(html_de):
    d = _doc(html_de, "articulo.html", "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    s = schema.analizar(d, tipo_pagina="articulo")
    assert s["bloques"] == 1 and not s["bloques_invalidos"]
    assert s["article"]["presente"] and s["article"]["faltantes"] == [] and s["article"]["fechas_iso_con_zona"]
    assert s["article"]["autor"] == "María López" and s["article"]["publisher_resuelto"]
    assert s["breadcrumb"]["valido"] and s["breadcrumb"]["items"] == 3
    assert s["referencias_rotas"] == [] and len(s["ids_definidos"]) == 3
    assert s["coherencia"] == []
    assert "María López" in s["person"]["con_url_o_sameas"]


def test_schema_faq_detecta_pregunta_no_visible(html_de):
    d = _doc(html_de, "faq.html", "https://www.nominafacil.mx/preguntas-frecuentes")
    s = schema.analizar(d, tipo_pagina="faq")
    assert s["faqpage"]["presente"] and s["faqpage"]["preguntas"] == 3
    assert s["faqpage"]["no_visibles"] == ["¿Ofrecen descuentos por volumen?"]
    assert any(c["campo"] == "FAQPage.mainEntity" for c in s["coherencia"])


def test_schema_home_organization_y_nombre_incoherente(html_de):
    d = _doc(html_de, "home.html", "https://www.nominafacil.mx/")
    s = schema.analizar(d, tipo_pagina="home")
    assert s["organization"]["presente"] and s["website"]["presente"]
    assert s["organization"]["faltantes"] == []
    assert any(c["campo"] == "Organization.name" for c in s["coherencia"]), "og:site_name con sufijo difiere del nombre"


def test_schema_local_y_referencia_rota(html_de):
    d = _doc(html_de, "local.html", "https://www.nominafacil.mx/sucursales/monterrey")
    s = schema.analizar(d, tipo_pagina="local")
    assert s["localbusiness"]["presente"] and s["localbusiness"]["faltantes_requeridos"] == []
    assert "url" in s["localbusiness"]["faltantes_recomendados"]
    roto = Documento('<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"x","author":{"@id":"#nadie"}}</script><h1>x</h1>')
    assert schema.analizar(roto)["referencias_rotas"] == ["#nadie"]


def test_schema_sin_jsonld(html_de):
    s = schema.analizar(_doc(html_de, "comparativa.html", "https://x"), tipo_pagina="comparativa")
    assert s["bloques"] == 0 and not s["article"]["presente"] and not s["organization"]["presente"]


# ---------------------------------------------------------- extractabilidad
def test_extractabilidad_articulo(html_de):
    d = _doc(html_de, "articulo.html", "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    x = extractabilidad.analizar(d, tipo_pagina="articulo")
    assert x["respuesta_directa"]["veredicto"] and x["respuesta_directa"]["tiene_definicion"]
    assert x["jerarquia"]["h1"] == 1 and x["jerarquia"]["saltos"] == [] and x["jerarquia"]["veredicto"]
    assert x["tablas_listas"]["tablas_con_encabezado"] == 1 and x["tablas_listas"]["listas_ordenadas"] == 1
    assert x["imagenes"]["veredicto"] and x["ejemplos"]["presente"]
    assert x["parrafos"]["largos"] == 0
    assert x["proporcion_principal"]["veredicto"]
    assert x["densidad_terminos"]["veredicto"]


def test_extractabilidad_comparativa_parrafo_largo_y_sin_tabla(html_de):
    d = _doc(html_de, "comparativa.html", "https://www.nominafacil.mx/comparativa/x")
    x = extractabilidad.analizar(d, tipo_pagina="comparativa")
    assert x["parrafos"]["largos"] == 1
    assert x["tablas_listas"]["menciona_comparacion"] and not x["tablas_listas"]["veredicto"]


def test_extractabilidad_glosario_definicion_y_pasos(html_de):
    d = _doc(html_de, "glosario.html", "https://www.nominafacil.mx/glosario/finiquito")
    x = extractabilidad.analizar(d, tipo_pagina="glosario")
    assert x["definicion"]["presente"] and x["definicion"]["listas_de_definicion"] == 1
    assert x["tablas_listas"]["menciona_pasos"] and x["tablas_listas"]["veredicto"]


def test_extractabilidad_keyword_stuffing():
    html = "<html><body><main><h1>Nómina</h1>" + "<p>" + " ".join(["nómina fácil nómina barata nómina rápida nómina"] * 60) + "</p></main></body></html>"
    x = extractabilidad.analizar(Documento(html), tipo_pagina="articulo")
    assert not x["densidad_terminos"]["veredicto"] and x["densidad_terminos"]["termino_top"] == "nómina"


# --------------------------------------------------------------- estadísticas
def test_estadisticas_ignora_navegacion_telefonos_fechas_y_detecta_fuentes(html_de):
    d = _doc(html_de, "articulo.html", "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    e = estadisticas.analizar(d, host="www.nominafacil.mx")
    valores = [m["valor"] for m in e["muestras"]]
    assert "18.4%" in valores and "62%" in valores and "230 clientes" in valores
    assert not any("1234" in v or "5678" in v for v in valores), "teléfono del pie excluido"
    assert not any(v in ("2025", "2026") for v in valores), "años sueltos excluidos"
    assert not any("64000" in v for v in valores), "código postal excluido"
    assert not any("1,200" in v for v in valores), "precio del menú excluido"
    inegi = next(m for m in e["muestras"] if m["valor"] == "18.4%")
    assert inegi["fuente_enlazada"] and inegi["con_fuente"]
    propio = next(m for m in e["muestras"] if m["valor"] == "62%")
    assert propio["fuente_propia"]
    sin_fuente = next(m for m in e["muestras"] if m["valor"].startswith("1.5"))
    assert not sin_fuente["con_fuente"]
    assert e["excluidos"].get("fechas", 0) >= 1 or e["excluidos"].get("anios_sueltos", 0) >= 1


def test_estadisticas_versiones_y_horas_excluidas():
    html = "<html><body><main><p>Con CFDI 4.0 y la versión 2.3.1 el timbrado tarda 5 segundos y cubre el 90% de casos; horario de 9:00 a 18:00.</p></main></body></html>"
    e = estadisticas.analizar(Documento(html))
    valores = [m["valor"] for m in e["muestras"]]
    assert "90%" in valores and "5 segundos" in valores
    assert not any("4.0" in v or "2.3.1" in v or "9:00" in v for v in valores)


# ---------------------------------------------------------------------- citas
def test_citas_atribuidas_y_enlaces_externos(html_de):
    d = _doc(html_de, "articulo.html", "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    c = citas.analizar(d, host="www.nominafacil.mx")
    assert c["total"] == 1 and c["atribuidas"] == 1
    assert c["citas"][0]["nombre"] == "Carlos Ruiz" and "director" in (c["citas"][0]["cargo"] or "").lower()
    assert c["enlaces"]["externos_principal"] == 1 and "www.inegi.org.mx" in c["enlaces"]["dominios_externos"]


def test_cita_sin_atribucion():
    html = '<html><body><main><p>“Este es un texto entre comillas con más de ocho palabras que no dice quién lo dijo”.</p></main></body></html>'
    c = citas.analizar(Documento(html))
    assert c["total"] == 1 and c["sin_atribucion"] == 1


# ------------------------------------------------------------------ frescura
def test_frescura_coherente_en_articulo(html_de):
    d = _doc(html_de, "articulo.html", "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    f = frescura.analizar(d, schema.analizar(d), ahora=AHORA)
    assert f["fecha_principal"] == "2026-08-15" and f["fuente"] == "json-ld dateModified"
    assert f["antiguedad_dias"] == 25 and f["coherente"]
    assert f["fecha_visible"]["actualizacion"]["fecha"] == "2026-08-15"


def test_frescura_incoherencia_y_fecha_visible_sin_schema(html_de):
    d = _doc(html_de, "faq.html", "https://www.nominafacil.mx/preguntas-frecuentes")
    f = frescura.analizar(d, schema.analizar(d), ahora=AHORA)
    assert f["fecha_principal"] == "2026-09-03" and f["fuente"].startswith("fecha visible")
    html = html_de("articulo.html").replace('"dateModified": "2026-08-15T10:30:00-06:00"', '"dateModified": "2026-09-01T10:30:00-06:00"')
    d2 = Documento(html)
    f2 = frescura.analizar(d2, schema.analizar(d2), ahora=AHORA)
    assert not f2["coherente"] and "difiere de la fecha visible" in f2["incoherencias"][0]


def test_parsear_fechas_varios_formatos():
    assert frescura.parsear_fecha("2026-08-15T10:30:00-06:00").date().isoformat() == "2026-08-15"
    assert frescura.parsear_fecha("15 de agosto de 2026").date().isoformat() == "2026-08-15"
    assert frescura.parsear_fecha("15/08/2026").date().isoformat() == "2026-08-15"
    assert frescura.parsear_fecha("August 15, 2026").date().isoformat() == "2026-08-15"
    assert frescura.parsear_fecha("ayer") is None


# ------------------------------------------------------------------- entidad
def test_entidad_autoria_nombre_y_contacto(html_de):
    d = _doc(html_de, "articulo.html", "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    e = entidad.analizar(d, schema.analizar(d))
    assert e["autoria"]["presente"] and e["autoria"]["nombre"] == "María López" and e["autoria"]["con_credenciales"]
    assert e["autoria"]["url_perfil"] == "/equipo/maria-lopez"
    assert e["nombre"]["consistente"], e["nombre"]
    assert e["acerca_contacto"]["acerca_presente"] and e["acerca_contacto"]["contacto_presente"]
    assert e["sameas"]["total"] == 2 and e["sameas"]["resueltos"][0]["resuelve"] is None


def test_entidad_nombre_inconsistente_en_home(html_de):
    d = _doc(html_de, "home.html", "https://www.nominafacil.mx/")
    e = entidad.analizar(d, schema.analizar(d), resolver=lambda u: {"status": 200 if "linkedin" in u else 404})
    assert not e["nombre"]["consistente"]
    assert [r["resuelve"] for r in e["sameas"]["resueltos"]] == [True, False]


def test_entidad_nap_local(html_de):
    d = _doc(html_de, "local.html", "https://www.nominafacil.mx/sucursales/monterrey")
    e = entidad.analizar(d, schema.analizar(d))
    assert e["nap"]["telefono_coincide"] and e["nap"]["direccion_coincide"]


# ------------------------------------------------------------------- llms.txt
def test_llmstxt_presente_y_ausente():
    def ok(url, **k):
        return fetch._resultado_vacio(url, status=200, html="# Nómina Fácil\n> Software de nómina\n\n## Docs\n- [Guía](https://x/guia): guía\n\n## Optional\n- [Blog](https://x/blog): blog\n")

    r = llmstxt.verificar("https://www.nominafacil.mx/", descargar=ok)
    assert r["presente"] and r["tiene_h1"] and r["tiene_optional"] and r["enlaces"] == 2

    def html(url, **k):
        return fetch._resultado_vacio(url, status=200, html="<html><body>404</body></html>")

    assert not llmstxt.verificar("https://www.nominafacil.mx/", descargar=html)["presente"]


# ------------------------------------------------------------------- contexto
def test_contexto_plantilla_vacia_marca_criticos(fixturas):
    """Usa la plantilla vacía de fixtura: contexto/negocio.md real puede estar lleno."""
    ctx = contexto.cargar(fixturas / "negocio_vacio.md")
    assert ctx["existe"] and not ctx["valido"]
    assert set(contexto.CRITICOS) <= set(ctx["faltantes_criticos"])
    assert len(contexto.preguntas_para_faltantes(ctx["faltantes_criticos"])) == len(contexto.CRITICOS)


def test_contexto_lleno(tmp_path):
    ruta = tmp_path / "negocio.md"
    ruta.write_text("""# Contexto
## Negocio
- nombre: Nómina Fácil
- dominio: nominafacil.mx
- dominios_alternos: app.nominafacil.mx
- variantes_de_nombre: NominaFacil, Nomina Facil
- descripcion_oficial: Software de nómina en la nube para empresas medianas en México.
## Oferta
- productos_servicios: Cálculo de nómina; Timbrado CFDI
## Mercado
- geografia: México, Monterrey
- idiomas: es, en
## ICP y personas
- icp: Empresas de 50 a 500 empleados; decisor: gerente de RH
## Competidores
- competidor: Contpaqi | https://www.contpaqi.com
- competidor: Runa | runahr.com
## Stack
- crm: HubSpot
""", encoding="utf-8")
    ctx = contexto.cargar(ruta)
    assert ctx["valido"], ctx["faltantes_criticos"]
    assert [c["dominio"] for c in ctx["competidores"]] == ["www.contpaqi.com", "runahr.com"]
    assert contexto.variantes_de_marca(ctx) == ["Nomina Facil", "Nómina Fácil", "NominaFacil"]
    assert contexto.dominios_propios(ctx) == ["app.nominafacil.mx", "nominafacil.mx"]


def test_crm_solo_es_critico_para_mql(fixturas, tmp_path):
    texto = (fixturas / "negocio_vacio.md").read_text(encoding="utf-8")
    for campo, valor in (("nombre", "Marca"), ("dominio", "marca.mx"), ("descripcion_oficial", "Qué es"), ("productos_servicios", "A; B"), ("geografia", "México, Monterrey"), ("idiomas", "es"), ("icp", "Jóvenes")):
        texto = texto.replace(f"- {campo}: (crítico", f"- {campo}: {valor} (crítico", 1)
    texto = texto.replace("- competidor: (crítico; formato Nombre | https://dominio.com; una línea por competidor, de 2 a 5)", "- competidor: Otro | https://otro.mx")
    ruta = tmp_path / "negocio.md"
    ruta.write_text(texto, encoding="utf-8")
    general = contexto.cargar(ruta)
    assert general["valido"] and "crm" not in general["faltantes_criticos"], general["faltantes_criticos"]
    assert contexto.cargar(ruta, modulo="visibilidad")["valido"]
    mql = contexto.cargar(ruta, modulo="mql")
    assert not mql["valido"] and mql["faltantes_criticos"] == ["crm"]
