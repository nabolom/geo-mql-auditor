"""Reporte de audit sobre una muestra: tipos de página detectados, hallazgos sistémicos y puntuales,
comparación con una corrida anterior y sección por área responsable."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from geomql import auditoria, fetch

NOM = "https://www.nominafacil.mx"
MAPA = {
    f"{NOM}/": "home.html", f"{NOM}/blog/reducir-rotacion-personal": "articulo.html", f"{NOM}/producto/timbrado": "solucion.html",
    f"{NOM}/comparativa/nomina-facil-vs-contpaqi": "comparativa.html", f"{NOM}/preguntas-frecuentes": "faq.html", f"{NOM}/sucursales/monterrey": "local.html",
    f"{NOM}/glosario/finiquito": "glosario.html", f"{NOM}/lp/guia-nomina-2026": "landing.html", f"{NOM}/robots.txt": "robots/basico.txt", f"{NOM}/sitemap.xml": "sitemap.xml",
}


@pytest.fixture
def descargar(html_de):
    def _d(u, **k):
        if u in MAPA:
            return fetch._resultado_vacio(u, status=200, html=html_de(MAPA[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")
    return _d


def _correr(descargar, tmp_path, urls, corrida, **extra):
    return auditoria.correr(urls=urls, url_base=f"{NOM}/", descargar=descargar, dir_salidas=tmp_path / "s", dir_historial=tmp_path / "h", corrida=corrida, ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11), **extra)


def test_reporte_de_muestra_separa_sistemicos_y_puntuales_y_cuenta_tipos(descargar, tmp_path):
    urls = [u for u in MAPA if not u.endswith((".txt", ".xml"))]
    payload = _correr(descargar, tmp_path, urls, "muestra", sufijo="sitemap")
    assert Path(payload["meta"]["archivos"]["md"]).name == "2026-09-11_nominafacil.mx_audit_sitemap.md"
    g = payload["grupos"]
    assert g["umbral_sistemico"] == 3
    for h in g["sistemicos"]:
        assert h["n_urls"] >= 3 and len(h["urls"]) == h["n_urls"] and h["n_urls_medidas"] == 8
    for h in g["puntuales"]:
        assert 1 <= h["n_urls"] <= 2
    assert g["sistemicos"] and g["puntuales"]
    ids_sis = {h["id"] for h in g["sistemicos"]}
    assert all(h["id"] in ids_sis for h in payload["hallazgos"] if len(h["urls_afectadas"]) >= 3)
    tipos = payload["tipos_detectados"]
    assert tipos["home"]["n"] == 1 and tipos["articulo"]["n"] == 1 and sum(t["n"] for t in tipos.values()) == 8
    md = payload["markdown"]
    assert "## Tipos de página detectados" in md and "## Hallazgos sistémicos" in md and "## Hallazgos puntuales" in md
    assert "de 8 URL medidas" in md
    assert "## Qué pedirle a cada área" in md and "### Contenido" in md and "### Desarrollo" in md and "### Analítica" in md
    # las Hipótesis siguen en su bloque y los avisos no son hallazgos
    assert "Requieren revisión humana" in md or not any(h["evidencia_observacion"] == "Hipótesis" for h in payload["hallazgos"])


def test_comparacion_con_corrida_anterior_de_la_home(descargar, tmp_path):
    home = _correr(descargar, tmp_path / "a", [f"{NOM}/"], "home")
    urls = [u for u in MAPA if not u.endswith((".txt", ".xml"))]
    muestra = _correr(descargar, tmp_path / "b", urls, "muestra", sufijo="sitemap", comparar=home["meta"]["archivos"]["json"])
    c = muestra["comparacion"]
    assert c["base"]["n_urls"] == 1 and c["base"]["fecha"] == "2026-09-11"
    reglas_home = {h["regla_id"] for h in home["hallazgos"]}
    assert set(c["patron_del_sitio"]) | set(c["puntual_incluye_portada"]) | set(c["exclusivo_de_la_portada"]) == reglas_home
    assert set(c["nuevas_fuera_de_la_portada"]).isdisjoint(reglas_home)
    for rid in c["patron_del_sitio"]:
        assert len(next(h for h in muestra["hallazgos"] if h["regla_id"] == rid)["urls_afectadas"]) >= 3
    md = muestra["markdown"]
    assert "## Comparación con la corrida anterior" in md and "Patrón del sitio" in md and "Exclusivo de la portada" in md


def test_areas_agrupan_por_dependencia(descargar, tmp_path):
    urls = [u for u in MAPA if not u.endswith((".txt", ".xml"))]
    payload = _correr(descargar, tmp_path, urls, "muestra")
    areas = payload["por_area"]
    assert set(areas) >= {"contenido", "desarrollo", "analitica"}
    todos = [p["id"] for a in areas.values() for p in a]
    assert len(todos) == len(payload["hallazgos"]), "cada hallazgo va a exactamente un área"
    for a in areas.values():
        for p in a:
            assert p["peticion"] and p["evidencia"] and p["horizonte"] in ("30 días", "90 días", "largo plazo")


# ------------------------------------------------------------- páginas que dependen de JavaScript
def test_plantilla_con_placeholders_es_dependencia_probable_y_las_reglas_de_contenido_quedan_sin_evidencia(html_de, tmp_path):
    url = f"{NOM}/carrera/psicologia"

    def _d(u, **k):
        if u == url:
            return fetch._resultado_vacio(u, status=200, html=html_de("plantilla_js.html"), url_final=u)
        if u in MAPA:
            return fetch._resultado_vacio(u, status=200, html=html_de(MAPA[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    payload = _correr(_d, tmp_path, [url], "js")
    res = {r["regla_id"]: r for r in payload["resultados"] if r["url"] == url}
    assert res["T-09"]["estado"] == "falla" and res["T-09"]["observacion"] == "Probable"
    assert "plantilla" in res["T-09"]["detalle"].lower() or "placeholder" in res["T-09"]["detalle"].lower()
    # las reglas de contenido y de datos estructurados no se juzgan sobre un HTML vacío
    for rid in ("X-02", "X-12", "X-13", "S-05", "E-01"):
        if rid in res:
            assert res[rid]["estado"] == "sin_evidencia" and res[rid]["observacion"] == "Hipótesis", (rid, res[rid])
            assert "JavaScript" in res[rid]["detalle"]
    ids = {h["regla_id"] for h in payload["hallazgos"]}
    assert "T-09" in ids and "X-02" not in ids and "S-05" not in ids
    assert any("JavaScript" in s for s in payload["supuestos"])


def test_con_render_el_contenido_renderizado_alimenta_los_colectores(html_de, tmp_path):
    url = f"{NOM}/carrera/psicologia"
    renderizado = html_de("articulo.html")

    def _d(u, **k):
        if u == url:
            return fetch._resultado_vacio(u, status=200, html=html_de("plantilla_js.html"), url_final=u)
        if u in MAPA:
            return fetch._resultado_vacio(u, status=200, html=html_de(MAPA[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    def render_fn(u):
        from geomql.html import Documento, contar_palabras
        return {"disponible": True, "html": renderizado, "palabras_principal": contar_palabras(Documento(renderizado, u).texto_principal()), "error": None}

    payload = _correr(_d, tmp_path, [url], "jsr", render_fn=render_fn)
    res = {r["regla_id"]: r for r in payload["resultados"] if r["url"] == url}
    assert res["T-09"]["estado"] == "falla" and res["T-09"]["observacion"] == "Confirmado"
    u = payload["urls"][0]
    assert u["palabras_principal"] > 200 and u["renderizado"] is True
    assert res["X-02"]["estado"] in ("pasa", "falla"), "con render las reglas de contenido sí se evalúan"
    assert not any("Sin render con JavaScript" in s for s in payload["supuestos"])


def test_meta_description_con_css_falla_t14():
    from geomql import tecnico, verificaciones
    from geomql.html import Documento

    html = '<html><head><title>Becas | X</title><meta name="description" content=".eachFilter.eitem { display: inline-block; margin-right: 10px; flex-shrink: 0; } .categoriesCarousel-a-1 { overflow: auto; } .card { color: red; }"></head><body><main><p>' + ("Texto de becas. " * 60) + '</p></main></body></html>'
    d = Documento(html, "https://x.mx/becas")
    f = {"status": 200, "url_final": "https://x.mx/becas", "cabeceras": {}, "cadena_redirecciones": []}
    tec = tecnico.analizar_pagina(f, d, "https://x.mx/becas")
    assert tec["meta_description"]["parece_codigo"] is True
    ev = verificaciones.EvidenciaPagina(url="https://x.mx/becas", tipo_pagina="articulo", fetch=f, doc=d, tecnico=tec, schema={}, extractabilidad={}, estadisticas={}, citas={}, frescura={}, entidad={})
    r = verificaciones.v_t14(ev)
    assert r.estado == "falla" and "código" in r.detalle.lower()


# ------------------------------------------------------------- anexo técnico comparativo sin contexto de negocio
def test_anexo_tecnico_sin_contexto_marca_no_evaluables_y_compara_reglas(descargar, html_de, tmp_path):
    urls = [u for u in MAPA if not u.endswith((".txt", ".xml"))]
    base = _correr(descargar, tmp_path / "base", urls, "base")
    otro = "https://otro.mx"
    mapa2 = {f"{otro}/": "universidad_home.html", f"{otro}/curso": "plantilla_js.html", f"{otro}/robots.txt": "robots/drupal_sin_sitemap.txt", f"{otro}/sitemap.xml": "universidad_sitemap.xml"}

    def _d2(u, **k):
        if u in mapa2:
            return fetch._resultado_vacio(u, status=200, html=html_de(mapa2[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    payload = auditoria.correr(urls=[f"{otro}/", f"{otro}/curso"], url_base=f"{otro}/", descargar=_d2, dir_salidas=tmp_path / "s", dir_historial=tmp_path / "h", corrida="anexo", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11), sufijo="anexo", anexo_tecnico=True, comparar_reglas=base["meta"]["archivos"]["json"], contexto={"existe": False, "valido": False, "campos": {"competidores": []}, "faltantes_criticos": [], "faltantes": [], "competidores": []})
    md = payload["markdown"]
    assert payload["meta"]["anexo_tecnico"] is True
    assert "Auditoría técnica comparativa" in md.split("\n")[0:6].__str__() or "Auditoría técnica comparativa" in md[:600]
    assert "sin contexto de negocio" in md[:800] and "sin medición de visibilidad" in md[:800]
    assert any("ICP" in s and "competidores" in s for s in payload["supuestos"])
    # hallazgos que dependen del negocio quedan fuera de la lista y en su propia sección
    assert not any(h["dependencia"] in ("terceros", "direccion", "legal") for h in payload["hallazgos"])
    assert "## No evaluables sin contexto de negocio" in md
    # comparación regla por regla
    c = payload["comparacion_reglas"]
    assert c["base"]["dominio"] == "nominafacil.mx" and c["base"]["n_urls"] == 8 and c["actual"]["n_urls"] == 2
    filas = {f["regla_id"]: f for f in c["filas"]}
    for rid in ("JSON-LD", "T-09", "X-02", "T-12", "S-05", "T-14", "T-10"):
        assert rid in filas, rid
        assert set(filas[rid]) >= {"regla_id", "titulo", "base_fallas", "base_n", "actual_fallas", "actual_n", "veredicto"}
    assert filas["JSON-LD"]["actual_fallas"] == 2, "las dos páginas del dominio nuevo no tienen JSON-LD"
    assert filas["JSON-LD"]["base_fallas"] < 8, "las fixturas de nominafacil sí traen JSON-LD en varias páginas"
    assert set(c["compartidos"]) | set(c["exclusivos_base"]) | set(c["exclusivos_actual"]) | set(c["en_ninguno"]) | set(c["evidencia_insuficiente"]) == set(filas)
    assert "## Comparación regla por regla" in md and "Patrones compartidos" in md and "Exclusivos de" in md
    assert "X de N" not in md


# ------------------------------------------------------------- hallazgos por tipo de página, render por URL y JSON-LD por URL
def test_reporte_agrupa_por_tipo_y_tabla_de_render(descargar, html_de, tmp_path):
    otro = "https://u.mx"
    mapa = {f"{otro}/es": "universidad_home.html", f"{otro}/es/licenciatura-en-psicologia": "programa.html", f"{otro}/es/ingenieria-en-software": "plantilla_js.html", f"{otro}/es/quienes-somos": "institucional.html", f"{otro}/es/becas": "institucional_becas.html", f"{otro}/robots.txt": "robots/drupal_sin_sitemap.txt", f"{otro}/sitemap.xml": "universidad_sitemap.xml"}

    def _d(u, **k):
        if u in mapa:
            return fetch._resultado_vacio(u, status=200, html=html_de(mapa[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    def render_fn(u):
        from geomql.html import Documento, contar_palabras
        html = html_de("programa.html") if u.endswith("ingenieria-en-software") else mapa.get(u) and html_de(mapa[u])
        return {"disponible": True, "html": html or "", "palabras_principal": contar_palabras(Documento(html or "", u).texto_principal()), "palabras_visibles": 0, "error": None}

    urls = [u for u in mapa if not u.endswith((".txt", ".xml"))]
    payload = auditoria.correr(urls=urls, url_base=f"{otro}/es", descargar=_d, render_fn=render_fn, dir_salidas=tmp_path / "s", dir_historial=tmp_path / "h", corrida="tipos", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11))
    tipos = {u["url"]: u["tipo"] for u in payload["urls"]}
    assert tipos[f"{otro}/es/licenciatura-en-psicologia"] == "programa" and tipos[f"{otro}/es/ingenieria-en-software"] == "programa"
    assert tipos[f"{otro}/es/quienes-somos"] == "institucional" and tipos[f"{otro}/es/becas"] == "institucional"
    assert "otra" not in tipos.values()
    # tabla de render por URL: palabras sin JS y con JS, veredicto y placeholders
    render = {r["url"]: r for r in payload["render_por_url"]}
    js = render[f"{otro}/es/ingenieria-en-software"]
    assert js["palabras_sin_js"] < 60 and js["palabras_con_js"] > 100 and js["placeholders"] >= 3 and js["veredicto"] in ("dependencia_confirmada", "parcial")
    assert render[f"{otro}/es/licenciatura-en-psicologia"]["veredicto"] == "sin_dependencia"
    # JSON-LD por URL
    assert all("jsonld_tipos" in r for r in payload["render_por_url"])
    # agrupación por tipo
    pt = payload["por_tipo"]
    assert set(pt) >= {"programa", "institucional", "home"} and pt["programa"]["n_urls"] == 2
    assert all("en_todas" in v and "en_algunas" in v for v in pt.values())
    assert any(x["regla_id"] == "S-05" for x in pt["programa"]["en_todas"]), "BreadcrumbList falta en las dos páginas de programa"
    md = payload["markdown"]
    assert "## Hallazgos por tipo de página" in md and "### programa" in md and "Falla en todas" in md
    assert "## Render y datos estructurados por URL" in md and "Sin JS" in md and "Con JS" in md and "Placeholders" in md
