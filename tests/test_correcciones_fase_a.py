"""Regresiones de los defectos detectados al cerrar la fase (a): nombre del snapshot,
superficies de marca para E-01, extractos de extractabilidad, roadmap sin truncar y
aviso T-11 cuando robots.txt no declara el sitemap."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from geomql import auditoria, entidad, extractabilidad, fetch, reporte, schema, tecnico, verificaciones
from geomql.hallazgos import Hallazgo
from geomql.html import Documento

TEC = "https://universidadejemplo.mx/es"
NOM = "https://www.nominafacil.mx"


@pytest.fixture
def descargar_universidad(html_de):
    """Home, robots.txt (sin directiva Sitemap) y sitemap de una universidad ficticia (fixturas inventadas)."""
    mapa = {
        TEC: ("universidad_home.html", "text/html"),
        "https://universidadejemplo.mx/robots.txt": ("robots/drupal_sin_sitemap.txt", "text/plain"),
        "https://universidadejemplo.mx/sitemap.xml": ("universidad_sitemap.xml", "application/xml"),
    }

    def _d(url, **k):
        if url in mapa:
            return fetch._resultado_vacio(url, status=200, html=html_de(mapa[url][0]), url_final=url)
        return fetch._resultado_vacio(url, status=404, error="HTTP 404")

    return _d


@pytest.fixture
def descargar_nominafacil(html_de):
    mapa = {f"{NOM}/": "home.html", f"{NOM}/robots.txt": "robots/basico.txt", f"{NOM}/sitemap.xml": "sitemap.xml"}

    def _d(url, **k):
        if url in mapa:
            return fetch._resultado_vacio(url, status=200, html=html_de(mapa[url]), url_final=url)
        return fetch._resultado_vacio(url, status=404, error="HTTP 404")

    return _d


def _correr(descargar, tmp_path, url, corrida, url_base=None):
    return auditoria.correr(
        urls=[url], url_base=url_base or url, descargar=descargar,
        dir_salidas=tmp_path / "salidas", dir_historial=tmp_path / "historial",
        corrida=corrida, ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11),
    )


# ------------------------------------------------------------- 1. snapshot
@pytest.mark.parametrize(
    "dominio, corrida, esperado",
    [
        ("universidadejemplo.mx", "universidad", "2026-09-11_universidadejemplo.mx_audit_universidad.json"),
        ("plataforma-de-nomina-para-empresas-medianas.com.mx", "2026-09-11_103000_plataforma-de-nomina-para-empresas-medianas.com.mx", "2026-09-11_plataforma-de-nomina-para-empresas-medianas.com.mx_audit_2026-09-11_103000_plataforma-de-nomina-para-empresas-medianas.com.mx.json"),
        ("blog.ejemplo.com", "ejemplo_fixturas", "2026-09-11_blog.ejemplo.com_audit_ejemplo_fixturas.json"),
        ("localhost:8000", "local dev", "2026-09-11_localhost_8000_audit_local_dev.json"),
        ("local", "Fixturas/2", "2026-09-11_local_audit_fixturas_2.json"),
    ],
)
def test_nombre_snapshot_conserva_dominio_y_corrida_completos(dominio, corrida, esperado):
    assert reporte.nombre_snapshot(dominio, "audit", corrida, date(2026, 9, 11)) == esperado


def test_snapshot_de_corrida_completa_lleva_corrida_completa(descargar_universidad, tmp_path):
    payload = _correr(descargar_universidad, tmp_path, TEC, "universidad")
    assert Path(payload["meta"]["snapshot"]).name == "2026-09-11_universidadejemplo.mx_audit_universidad.json"
    snap = json.loads(Path(payload["meta"]["snapshot"]).read_text(encoding="utf-8"))
    assert snap["corrida"] == "universidad" and snap["dominio"] == "universidadejemplo.mx"


def test_snapshot_con_ruta_de_fixtura(url_de, sin_red, tmp_path):
    url = url_de("home.html")
    payload = auditoria.correr(urls=[url], url_base=url, dir_salidas=tmp_path / "s", dir_historial=tmp_path / "h", corrida="ejemplo_fixturas", fecha=date(2026, 9, 11))
    assert Path(payload["meta"]["snapshot"]).name == "2026-09-11_local_audit_ejemplo_fixturas.json"


def test_snapshots_historicos_renombrados():
    historial = Path(__file__).resolve().parent.parent / "datos" / "historial"
    if not historial.is_dir():
        pytest.skip("sin datos/historial en este árbol: la prueba revisa snapshots de corridas locales")
    nombres = {p.name for p in historial.glob("*.json")}
    assert not any(n.endswith(("_ilenio.json", "_xturas.json")) for n in nombres), nombres
    for p in historial.glob("*.json"):
        snap = json.loads(p.read_text(encoding="utf-8"))
        assert p.name == reporte.nombre_snapshot(snap["dominio"], snap["modulo"], snap["corrida"], date.fromisoformat(snap["fecha"]))


# ------------------------------------------------------------- 2. entidad: E-01
def test_nombre_de_marca_home_sin_separador_usa_title_completo_y_pie_con_dr(html_de):
    d = Documento(html_de("universidad_home.html"), TEC)
    e = entidad.analizar(d, schema.analizar(d, tipo_pagina="home", url=TEC), tipo_pagina="home")
    c = e["nombre"]["candidatos"]
    assert c["title"] == "Universidad Ejemplo"
    assert c["pie"] == "Universidad Ejemplo", c
    assert "og:site_name" not in c, "la home no declara og:site_name; no debe inventarse"
    assert e["nombre"]["consistente"] and e["nombre"]["distintos"] == 1
    assert "og:site_name" in e["nombre"]["ausentes"] and "Organization.name" in e["nombre"]["ausentes"]


def test_nombre_de_marca_home_con_separador_toma_el_lado_que_es_marca(html_de):
    d = Documento(html_de("home.html"), f"{NOM}/")
    e = entidad.analizar(d, schema.analizar(d, tipo_pagina="home", url=f"{NOM}/"), tipo_pagina="home")
    c = e["nombre"]["candidatos"]
    assert c["title"] == "Nómina Fácil", c
    assert c["og:site_name"] == "Nomina Facil MX" and c["pie"] == "Nómina Fácil"
    assert not e["nombre"]["consistente"], "og:site_name difiere del resto"


def test_nombre_de_marca_articulo_sigue_usando_el_sufijo(html_de):
    d = Documento(html_de("articulo.html"), f"{NOM}/blog/reducir-rotacion-personal")
    e = entidad.analizar(d, schema.analizar(d, tipo_pagina="articulo", url=f"{NOM}/blog/x"), tipo_pagina="articulo")
    assert e["nombre"]["candidatos"]["title"] == "Nómina Fácil"


def test_e01_se_evalua_con_evidencia_en_la_home(descargar_universidad, tmp_path):
    payload = _correr(descargar_universidad, tmp_path, TEC, "ue-e01")
    r = next(r for r in payload["resultados"] if r["regla_id"] == "E-01")
    assert r["estado"] == "pasa" and r["observacion"] == "Confirmado", r
    assert r["evidencia"][0]["dato"]["candidatos"]["title"] == "Universidad Ejemplo"
    # el archivo de vector expone las superficies aunque el estado no sea falla
    ent = json.loads(Path(payload["meta"]["archivos_vector"]["entidad"]).read_text(encoding="utf-8"))
    e01 = next(x for x in ent["reglas"] if x["regla_id"] == "E-01")
    ejemplos = e01["ejemplos_pasa"] + e01["ejemplos_falla"] + e01.get("ejemplos_sin_evidencia", [])
    assert ejemplos and ejemplos[0]["evidencia"][0]["dato"]["candidatos"]["title"] == "Universidad Ejemplo"


def test_e01_sin_evidencia_expone_candidatos_en_el_vector(descargar_nominafacil, html_de, tmp_path, monkeypatch):
    """Una landing sin og:site_name, sin Organization y sin pie deja E-01 sin evidencia, pero el vector debe mostrar qué se encontró."""
    url = f"{NOM}/lp/guia-nomina-2026"

    def _d(u, **k):
        if u == url:
            return fetch._resultado_vacio(u, status=200, html=html_de("landing.html"), url_final=u)
        return descargar_nominafacil(u, **k)

    payload = _correr(_d, tmp_path, url, "lp", url_base=f"{NOM}/")
    r = next(r for r in payload["resultados"] if r["regla_id"] == "E-01")
    assert r["estado"] == "sin_evidencia"
    ent = json.loads(Path(payload["meta"]["archivos_vector"]["entidad"]).read_text(encoding="utf-8"))
    e01 = next(x for x in ent["reglas"] if x["regla_id"] == "E-01")
    assert e01["ejemplos_sin_evidencia"] and "candidatos" in e01["ejemplos_sin_evidencia"][0]["evidencia"][0]["dato"]


# ------------------------------------------------------------- 3. extractos
def test_x02_extracto_lista_encabezados_no_descriptivos_con_posicion(html_de):
    d = Documento(html_de("universidad_home.html"), TEC)
    x = extractabilidad.analizar(d, tipo_pagina="home")
    no_desc = x["jerarquia"]["no_descriptivos"]
    assert any(n["texto"] == "Admisiones" for n in no_desc)
    assert all(n["posicion"].startswith("h") and "#" in n["posicion"] for n in no_desc), no_desc
    muestra = x["muestra"]
    assert muestra["encabezados"][0]["nivel"] == 1 and muestra["encabezados"][0]["posicion"] == "h1 #1"
    assert muestra["parrafos"] and muestra["parrafos"][0]["posicion"] == "p #1" and muestra["parrafos"][0]["texto"]


def test_x13_extracto_trae_el_parrafo_largo_con_posicion(html_de):
    d = Documento(html_de("comparativa.html"), f"{NOM}/comparativa/nomina-facil-vs-contpaqi")
    x = extractabilidad.analizar(d, tipo_pagina="comparativa")
    largos = x["parrafos"]["largos_muestra"]
    assert largos and largos[0]["posicion"].startswith("p #") and len(largos[0]["texto"].split()) > 40


def test_todo_resultado_y_hallazgo_de_extractabilidad_trae_extracto(html_de, tmp_path):
    mapa = {
        f"{NOM}/": "home.html", f"{NOM}/blog/reducir-rotacion-personal": "articulo.html", f"{NOM}/producto/timbrado": "solucion.html",
        f"{NOM}/comparativa/nomina-facil-vs-contpaqi": "comparativa.html", f"{NOM}/preguntas-frecuentes": "faq.html",
        f"{NOM}/sucursales/monterrey": "local.html", f"{NOM}/glosario/finiquito": "glosario.html", f"{NOM}/lp/guia-nomina-2026": "landing.html",
        f"{NOM}/robots.txt": "robots/basico.txt", f"{NOM}/sitemap.xml": "sitemap.xml",
    }

    def _d(u, **k):
        if u in mapa:
            return fetch._resultado_vacio(u, status=200, html=html_de(mapa[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    urls = [u for u in mapa if not u.endswith((".txt", ".xml"))] + [TEC]

    def _d2(u, **k):
        if u == TEC:
            return fetch._resultado_vacio(u, status=200, html=html_de("universidad_home.html"), url_final=u)
        return _d(u, **k)

    payload = auditoria.correr(urls=urls, url_base=f"{NOM}/", descargar=_d2, dir_salidas=tmp_path / "s", dir_historial=tmp_path / "h", corrida="x", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11))
    vacios = []
    for r in payload["resultados"]:
        if r["regla_id"].startswith("X-") and r["estado"] in ("pasa", "falla"):
            ev = r["evidencia"]
            if not ev or not ev[0].get("extracto") or not ev[0].get("extractos"):
                vacios.append((r["regla_id"], r["url"], r["estado"]))
            else:
                assert all(x.get("posicion") and x.get("texto") for x in ev[0]["extractos"]), (r["regla_id"], ev[0]["extractos"])
    assert not vacios, f"resultados X-* sin extracto: {vacios}"
    sin = [(h["id"], h["url"]) for h in payload["hallazgos"] if h["categoria"] == "extractabilidad" for e in h["evidencia"] if not e.get("extracto")]
    assert not sin, f"hallazgos de extractabilidad sin extracto: {sin}"
    # el vector lleva muestras de texto por URL para que el subagente no descargue el HTML
    vec = json.loads(Path(payload["meta"]["archivos_vector"]["extractabilidad"]).read_text(encoding="utf-8"))
    assert vec["muestras_texto"], "faltan muestras_texto"
    m = next(x for x in vec["muestras_texto"] if x["url"] == TEC)
    assert m["h1"].startswith("Aprende a tu ritmo") and m["encabezados"][1]["posicion"] and m["parrafos"][0]["texto"]
    assert any("Admisiones" in e["texto"] for e in m["encabezados"])
    # el extracto llega al Markdown del hallazgo
    x02 = next(h for h in payload["hallazgos"] if h["regla_id"] == "X-02" and TEC in h["urls_afectadas"])
    ev_tec = next(e for e in x02["evidencia"] if e["url"] == TEC)
    assert "Admisiones" in ev_tec["extracto"] and any(x["texto"] == "Admisiones" and x["posicion"].startswith("h2 #") for x in ev_tec["extractos"])
    assert "Admisiones" in payload["markdown"]


# ------------------------------------------------------------- 4. roadmap
def _hallazgo(recomendacion: str) -> Hallazgo:
    return Hallazgo(
        id="S-04-001", regla_id="S-04", categoria="schema", tipo_pagina="home", url=TEC,
        evidencia_observacion="Confirmado", fuerza_regla="A", tipo_evidencia="requisito_oficial",
        impacto_esperado="medio", esfuerzo="bajo", dependencia="desarrollo", horizonte="30d",
        titulo="Organization ausente", detalle="sin Organization", evidencia=[], recomendacion=recomendacion,
        fuente={"titulo": "Google", "url": "https://developers.google.com/x"}, urls_afectadas=[TEC], origen="subagente",
    )


def test_roadmap_no_trunca_recomendaciones_largas_ni_con_saltos():
    rec = ("Añade un bloque JSON-LD Organization en la home con name, url, logo, sameAs, description y datos de contacto. " * 6).strip()
    rec += "\nSegunda línea: junto con un bloque WebSite.\nTercera línea: valida con Rich Results Test."
    assert len(rec) > 500
    payload = reporte.construir(modulo="audit", dominio="universidadejemplo.mx", urls=[], hallazgos=[_hallazgo(rec)], resultados=[], reglas={}, puntaje={"por_categoria": {}, "global": None}, sitio={}, contexto={"valido": True}, fecha=date(2026, 9, 11))
    md = payload["markdown"]
    assert payload["hallazgos"][0]["recomendacion"] == rec
    roadmap = md.split("## Roadmap", 1)[1]
    for linea in rec.splitlines():
        assert linea in roadmap, linea[:60]
    assert "Tercera línea: valida con Rich Results Test." in roadmap
    # la sección del hallazgo también la lleva completa y sin romper la lista
    seccion = md.split("### 1. Organization ausente", 1)[1].split("##", 1)[0]
    assert "Tercera línea: valida con Rich Results Test." in seccion
    assert "\n  Segunda línea" in seccion and "\n  Segunda línea" in roadmap, "las líneas siguientes van indentadas dentro del ítem"


def test_fusionar_conserva_recomendacion_larga(descargar_universidad, tmp_path):
    payload = _correr(descargar_universidad, tmp_path, TEC, "fus")
    rec = ("Junto a la cifra de empleabilidad añade el año de la medición, la población y el instrumento, y enlaza el estudio. " * 6).strip() + "\nSi no hay método documentado, retira la cifra."
    salida = {"vector": "extractabilidad", "hallazgos": [{"regla_id": "X-11", "titulo": "Cifra sin método", "detalle": "d", "recomendacion": rec, "evidencia_observacion": "Hipótesis", "impacto_esperado": "medio", "esfuerzo": "bajo", "dependencia": "contenido", "horizonte": "30d", "urls_afectadas": [TEC], "nuevo": True}], "ajustes": [], "notas": []}
    nuevo = auditoria.fusionar(payload["meta"]["archivos"]["json"], [salida])
    h = next(h for h in nuevo["hallazgos"] if h["regla_id"] == "X-11")
    assert h["recomendacion"] == rec
    assert "retira la cifra." in nuevo["markdown"].split("## Roadmap", 1)[1]


# ------------------------------------------------------------- 5. T-11
def _sitio(robots_sitemaps, sitemap_presente):
    rec = {"sitemap": "https://x.mx/sitemap.xml", "urls_total": 3, "con_lastmod": 3, "sin_lastmod": 0, "urls": [{"loc": "https://x.mx/", "lastmod": "2026-09-01"}], "errores": [], "sitemaps_leidos": 1} if sitemap_presente else {"sitemap": "https://x.mx/sitemap.xml", "urls_total": 0, "con_lastmod": 0, "sin_lastmod": 0, "urls": [], "errores": ["HTTP 404"], "sitemaps_leidos": 0}
    sm = tecnico.analizar_sitemap(rec, ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), declarado_en_robots=bool(robots_sitemaps))
    return verificaciones.EvidenciaSitio(url="https://x.mx/", host="x.mx", robots={"estado": "ok", "status": 200, "sitemaps": robots_sitemaps}, sitemap=sm)


def test_t11_declarado_en_robots_pasa_sin_aviso():
    s = _sitio(["https://x.mx/sitemap.xml"], True)
    r = verificaciones.v_t11(s)
    assert r.estado == "pasa" and "aviso" not in r.detalle.lower()
    assert s.sitemap["declarado_en_robots"] is True
    assert tecnico.avisos_sitio(s.robots, s.sitemap) == []


def test_t11_sitemap_existente_no_declarado_pasa_con_aviso():
    s = _sitio([], True)
    r = verificaciones.v_t11(s)
    assert r.estado == "pasa", r
    assert "no declarado en robots.txt" in r.detalle
    assert r.evidencia[0]["dato"]["declarado_en_robots"] is False
    avisos = tecnico.avisos_sitio(s.robots, s.sitemap)
    assert len(avisos) == 1 and "Sitemap:" in avisos[0] and "robots.txt" in avisos[0]


def test_t11_sitemap_ausente_falla_sin_aviso_de_declaracion():
    s = _sitio([], False)
    r = verificaciones.v_t11(s)
    assert r.estado == "falla" and "no declarado" not in r.detalle
    assert tecnico.avisos_sitio(s.robots, s.sitemap) == []


def test_aviso_t11_llega_al_reporte(descargar_universidad, descargar_nominafacil, tmp_path):
    payload = _correr(descargar_universidad, tmp_path, TEC, "t11")
    assert payload["sitio"]["avisos"] and "Sitemap:" in payload["sitio"]["avisos"][0]
    assert "- Avisos:" in payload["markdown"] and "no lo declara" in payload["markdown"]
    t11 = next(r for r in payload["resultados"] if r["regla_id"] == "T-11")
    assert t11["estado"] == "pasa"
    limpio = _correr(descargar_nominafacil, tmp_path / "b", f"{NOM}/", "t11b")
    assert limpio["sitio"]["avisos"] == []


# ------------------------------------------------------------- 6. avisos no son hallazgos
def _salida(vector, hallazgos):
    return {"vector": vector, "hallazgos": hallazgos, "ajustes": [], "notas": []}


def _h(regla_id, urls, **extra):
    base = {"regla_id": regla_id, "titulo": f"Hallazgo {regla_id}", "detalle": "detalle de prueba", "recomendacion": "recomendación de prueba", "evidencia_observacion": "Confirmado", "urls_afectadas": urls, "nuevo": True}
    return base | extra


def test_fusionar_rechaza_hallazgo_sobre_aviso_de_regla_que_pasa(descargar_universidad, tmp_path):
    """La corrida de la universidad ficticia trae el aviso T-11 (regla pasa). Un subagente que lo convierta en hallazgo debe ser rechazado y registrado."""
    payload = _correr(descargar_universidad, tmp_path, TEC, "aviso")
    assert payload["sitio"]["avisos"] and next(r for r in payload["resultados"] if r["regla_id"] == "T-11")["estado"] == "pasa"
    salida_tec = _salida("tecnico", [_h("T-11", ["https://universidadejemplo.mx/robots.txt", "https://universidadejemplo.mx/sitemap.xml"], titulo="Sitemap no declarado en robots.txt")])
    salida_x = _salida("extractabilidad", [_h("X-11", [TEC], evidencia_observacion="Hipótesis")])
    nuevo = auditoria.fusionar(payload["meta"]["archivos"]["json"], [salida_tec, salida_x])
    ids = [h["regla_id"] for h in nuevo["hallazgos"]]
    assert "T-11" not in ids, "el aviso T-11 no debe convertirse en hallazgo"
    assert "X-11" in ids, "un hallazgo legítimo sobre una regla sin colector sí entra"
    rechazados = nuevo["meta"]["fusion"]["rechazados"]
    assert len(rechazados) == 1 and rechazados[0]["regla_id"] == "T-11" and rechazados[0]["vector"] == "tecnico" and "pasa" in rechazados[0]["motivo"]
    assert nuevo["meta"]["fusion"]["n_rechazados"] == 1
    # el aviso sigue en su línea, con la recomendación de una línea, y no aparece como hallazgo en el Markdown
    md = nuevo["markdown"]
    assert "- Avisos:" in md and "añade `Sitemap: https://universidadejemplo.mx/sitemap.xml` a robots.txt" in md
    assert "### " not in md.split("## Hallazgos priorizados", 1)[1].split("## Sitio", 1)[0].replace("### ", "###", 0) or "Sitemap no declarado en robots.txt" not in md.split("## Hallazgos priorizados", 1)[1].split("## Sitio", 1)[0]
    assert "Rechazado" in md or "rechaz" in md.lower(), "el reporte registra el rechazo"


def test_fusionar_no_rechaza_regla_que_falla_en_otra_url(html_de, tmp_path):
    """Una regla que pasa en una URL y falla en otra admite hallazgos sobre la URL que falla, y rechaza los de la que pasa."""
    mapa = {f"{NOM}/": "home.html", f"{NOM}/comparativa/nomina-facil-vs-contpaqi": "comparativa.html", f"{NOM}/robots.txt": "robots/basico.txt", f"{NOM}/sitemap.xml": "sitemap.xml"}

    def _d(u, **k):
        if u in mapa:
            return fetch._resultado_vacio(u, status=200, html=html_de(mapa[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    payload = auditoria.correr(urls=[f"{NOM}/", f"{NOM}/comparativa/nomina-facil-vs-contpaqi"], url_base=f"{NOM}/", descargar=_d, dir_salidas=tmp_path / "s", dir_historial=tmp_path / "h", corrida="mix", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11))
    estados = {(r["regla_id"], r["url"]): r["estado"] for r in payload["resultados"]}
    assert estados[("X-13", f"{NOM}/comparativa/nomina-facil-vs-contpaqi")] == "falla" and estados[("X-13", f"{NOM}/")] == "pasa"
    salida = _salida("extractabilidad", [
        _h("X-13", [f"{NOM}/comparativa/nomina-facil-vs-contpaqi"], titulo="Párrafo largo en la comparativa", nuevo=False),
        _h("X-13", [f"{NOM}/"], titulo="Intento sobre la home, donde X-13 pasa"),
    ])
    nuevo = auditoria.fusionar(payload["meta"]["archivos"]["json"], [salida])
    titulos = [h["titulo"] for h in nuevo["hallazgos"]]
    assert "Intento sobre la home, donde X-13 pasa" not in titulos
    assert nuevo["meta"]["fusion"]["n_rechazados"] == 1 and nuevo["meta"]["fusion"]["rechazados"][0]["urls"] == [f"{NOM}/"]
    assert any(h["regla_id"] == "X-13" for h in nuevo["hallazgos"])
