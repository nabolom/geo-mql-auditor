"""El denominador de una regla es el número de URL donde fue evaluable (estado pasa o falla),
no el total de URL de la corrida. Los estados no_aplica y sin_evidencia quedan fuera del
denominador y nunca cuentan como aprobados."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from geomql import agrupacion, auditoria, fetch

NOM = "https://www.nominafacil.mx"
URLS = [f"{NOM}/", f"{NOM}/blog/a", f"{NOM}/blog/b", f"{NOM}/faq"]


def _res(rid, url, estado):
    return {"regla_id": rid, "url": url, "estado": estado, "observacion": "Confirmado", "detalle": "", "evidencia": []}


def _urls(status=200):
    return [{"url": u, "status": status, "tipo": "home" if u.endswith("/") else "articulo", "schema_tipos": []} for u in URLS]


def _corrida():
    """Cuatro URL. S-05 no se evalúa en la home (no_aplica) y falla en las otras tres.
    X-16 solo es evaluable en dos artículos (falla en uno, pasa en otro); en el resto sin_evidencia.
    X-02 se evalúa en las cuatro y falla en dos."""
    r = []
    r += [_res("S-05", URLS[0], "no_aplica")] + [_res("S-05", u, "falla") for u in URLS[1:]]
    r += [_res("X-16", URLS[0], "sin_evidencia"), _res("X-16", URLS[1], "falla"), _res("X-16", URLS[2], "pasa"), _res("X-16", URLS[3], "no_aplica")]
    r += [_res("X-02", u, e) for u, e in zip(URLS, ("falla", "falla", "pasa", "pasa"))]
    return r


REGLAS = {"S-05": {"titulo_hallazgo": "BreadcrumbList ausente"}, "X-16": {"titulo_hallazgo": "Sin ejemplos"}, "X-02": {"titulo_hallazgo": "Jerarquía"}}


def test_evaluables_por_regla_cuenta_solo_pasa_y_falla():
    ev = agrupacion.evaluables_por_regla(_corrida())
    assert ev == {"S-05": 3, "X-16": 2, "X-02": 4}


def test_comparar_reglas_usa_el_denominador_de_cada_regla(tmp_path):
    base = {"meta": {"dominio": "base.mx", "fecha": "2026-09-11"}, "resultados": _corrida(), "urls": _urls()}
    ruta = tmp_path / "base.json"
    ruta.write_text(json.dumps(base), encoding="utf-8")
    c = agrupacion.comparar_reglas(resultados=_corrida(), urls=_urls(), dominio="actual.mx", ruta_base=ruta, reglas=REGLAS, umbral=1)
    filas = {f["regla_id"]: f for f in c["filas"]}
    assert (filas["S-05"]["base_fallas"], filas["S-05"]["base_n"]) == (3, 3), "S-05 no se evalúa en la home: 3 de 3, no 3 de 4"
    assert (filas["S-05"]["actual_fallas"], filas["S-05"]["actual_n"]) == (3, 3)
    assert (filas["X-16"]["base_fallas"], filas["X-16"]["base_n"]) == (1, 2), "X-16 solo fue evaluable en 2 URL"
    assert (filas["X-02"]["base_fallas"], filas["X-02"]["base_n"]) == (2, 4)
    # la fila sintética JSON-LD sí usa el total de páginas con 200: todas son evaluables para tener o no JSON-LD
    assert (filas["JSON-LD"]["base_fallas"], filas["JSON-LD"]["base_n"]) == (4, 4)
    # el veredicto se calcula con el denominador de la regla: X-16 falla en 1 de 2 (50%) y está presente en ambos
    assert filas["X-16"]["veredicto"] == "compartido"
    assert c["base"]["n_urls"] == 4 and c["actual"]["n_urls"] == 4, "el encabezado conserva las URL medidas"
    md = agrupacion.markdown_comparacion_reglas(c)
    assert "| S-05 | BreadcrumbList ausente | 3 de 3 | 3 de 3 |" in md
    assert "| X-16 | Sin ejemplos | 1 de 2 | 1 de 2 |" in md
    assert "3 de 4" not in md and "1 de 4" not in md


def test_regla_no_evaluable_en_un_dominio_se_muestra_como_no_evaluable(tmp_path):
    base = {"meta": {"dominio": "base.mx", "fecha": "2026-09-11"}, "resultados": _corrida(), "urls": _urls()}
    ruta = tmp_path / "base.json"
    ruta.write_text(json.dumps(base), encoding="utf-8")
    actual = [r for r in _corrida() if r["regla_id"] != "S-05"] + [_res("S-05", u, "no_aplica") for u in URLS]
    c = agrupacion.comparar_reglas(resultados=actual, urls=_urls(), dominio="actual.mx", ruta_base=ruta, reglas=REGLAS, umbral=1)
    f = next(f for f in c["filas"] if f["regla_id"] == "S-05")
    assert (f["actual_fallas"], f["actual_n"], f["veredicto"]) == (0, 0, "exclusivo_base")
    assert "| S-05 | BreadcrumbList ausente | 3 de 3 | no evaluable |" in agrupacion.markdown_comparacion_reglas(c)


def test_por_tipo_marca_en_todas_cuando_falla_en_todas_las_evaluables():
    pt = agrupacion.por_tipo(_corrida(), _urls(), REGLAS)
    art = pt["articulo"]
    assert art["n_urls"] == 3
    s05 = next(x for x in art["en_todas"] if x["regla_id"] == "S-05")
    assert (s05["n"], s05["n_evaluables"]) == (3, 3)
    x16 = next(x for x in art["en_algunas"] if x["regla_id"] == "X-16")
    assert (x16["n"], x16["n_evaluables"]) == (1, 2), "X-16 falla en 1 de sus 2 evaluables, no de las 3 del tipo"
    assert not any(x["regla_id"] == "X-16" for x in art["en_todas"])
    md = agrupacion.markdown_por_tipo(pt, [])
    assert "[X-16] Sin ejemplos · 1 de 2 evaluables (de 3 del tipo)" in md and "Sin ejemplos · 1 de 3" not in md


def test_sistemicos_y_areas_muestran_evaluables_por_regla():
    from geomql.hallazgos import Hallazgo

    def _h(rid, urls):
        return Hallazgo(id=f"{rid}-001", regla_id=rid, categoria="schema", tipo_pagina="articulo", url=urls[0], evidencia_observacion="Confirmado", fuerza_regla="A", tipo_evidencia="requisito_oficial", impacto_esperado="medio", esfuerzo="bajo", dependencia="desarrollo", horizonte="30d", titulo=f"H {rid}", detalle="d", evidencia=[], recomendacion="r", fuente={"titulo": "f", "url": "https://x"}, urls_afectadas=urls)

    ev = agrupacion.evaluables_por_regla(_corrida())
    g = agrupacion.agrupar_hallazgos([_h("S-05", URLS[1:]), _h("X-16", URLS[1:2])], 4, evaluables=ev)
    s05 = next(h for h in g["sistemicos"] if h["regla_id"] == "S-05")
    assert (s05["n_urls"], s05["n_evaluables"], s05["n_urls_medidas"]) == (3, 3, 4)
    md = agrupacion.markdown_extras(g, None, None, None)
    assert "3 de 3 URL evaluables" in md and "3 de 4 URL medidas" not in md
    areas = agrupacion.por_area([_h("S-05", URLS[1:])], 4, evaluables=ev)
    assert "3 de 3 URL evaluables" in areas["desarrollo"][0]["evidencia"]
    # sin mapa de evaluables (o regla no evaluada) se conserva el total medido
    g2 = agrupacion.agrupar_hallazgos([_h("S-05", URLS[1:])], 4)
    assert g2["sistemicos"][0]["n_evaluables"] == 4 and "3 de 4 URL medidas" in agrupacion.markdown_extras(g2, None, None, None)


def test_corrida_real_con_fixturas_usa_evaluables(html_de, tmp_path):
    """Con las fixturas de la empresa ficticia, S-05 no se evalúa en la home y el reporte lo refleja."""
    mapa = {f"{NOM}/": "home.html", f"{NOM}/blog/reducir-rotacion-personal": "articulo.html", f"{NOM}/preguntas-frecuentes": "faq.html", f"{NOM}/robots.txt": "robots/basico.txt", f"{NOM}/sitemap.xml": "sitemap.xml"}

    def _d(u, **k):
        if u in mapa:
            return fetch._resultado_vacio(u, status=200, html=html_de(mapa[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    urls = [u for u in mapa if not u.endswith((".txt", ".xml"))]
    base = auditoria.correr(urls=urls, url_base=f"{NOM}/", descargar=_d, dir_salidas=tmp_path / "a", dir_historial=tmp_path / "h", corrida="base", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11))
    p = auditoria.correr(urls=urls, url_base=f"{NOM}/", descargar=_d, dir_salidas=tmp_path / "b", dir_historial=tmp_path / "h2", corrida="cmp", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11), comparar_reglas=base["meta"]["archivos"]["json"])
    ev = {}
    for r in p["resultados"]:
        if r["estado"] in ("pasa", "falla"):
            ev[r["regla_id"]] = ev.get(r["regla_id"], 0) + 1
    assert ev["S-05"] < len(urls), "la fixtura debe tener una regla evaluable en un subconjunto (S-05 excluye la home)"
    filas = {f["regla_id"]: f for f in p["comparacion_reglas"]["filas"]}
    assert filas["S-05"]["actual_n"] == ev["S-05"] and filas["S-05"]["base_n"] == ev["S-05"]
    for f in filas.values():
        if f["regla_id"] != "JSON-LD":
            assert f["actual_n"] == ev.get(f["regla_id"], 0), f
    for h in p["grupos"]["sistemicos"] + p["grupos"]["puntuales"]:
        assert h["n_evaluables"] == ev.get(h["regla_id"], len(urls)), h


def test_proporcion_requiere_minimo_de_evaluables(tmp_path):
    """Una regla con menos de MINIMO_EVALUABLES_PROPORCION URL evaluables no recibe veredicto por proporción:
    1 de 1 es 100 % pero no es un patrón. Se usan reglas de la lista fija para que entren en la tabla con el umbral por defecto."""
    urls = [f"{NOM}/p{i}" for i in range(1, 7)]
    reg = [{"url": u, "status": 200, "tipo": "articulo", "schema_tipos": ["Article"]} for u in urls]
    res = []
    res += [_res("T-14", urls[0], "falla")] + [_res("T-14", u, "no_aplica") for u in urls[1:]]  # 1 evaluable
    res += [_res("T-10", urls[0], "falla"), _res("T-10", urls[1], "falla")] + [_res("T-10", u, "no_aplica") for u in urls[2:]]  # 2 evaluables
    res += [_res("X-02", urls[0], "falla"), _res("X-02", urls[1], "falla"), _res("X-02", urls[2], "pasa")] + [_res("X-02", u, "no_aplica") for u in urls[3:]]  # 3 evaluables
    base = {"meta": {"dominio": "base.mx", "fecha": "2026-09-11"}, "resultados": res, "urls": reg}
    ruta = tmp_path / "base.json"
    ruta.write_text(json.dumps(base), encoding="utf-8")
    reglas = {"T-14": {"titulo_hallazgo": "Uno"}, "T-10": {"titulo_hallazgo": "Dos"}, "X-02": {"titulo_hallazgo": "Tres"}}
    c = agrupacion.comparar_reglas(resultados=res, urls=reg, dominio="actual.mx", ruta_base=ruta, reglas=reglas)
    filas = {f["regla_id"]: f for f in c["filas"]}
    assert agrupacion.MINIMO_EVALUABLES_PROPORCION == 3
    assert filas["T-14"]["veredicto"] == "evidencia_insuficiente" and filas["T-14"]["base_n"] == 1
    assert filas["T-10"]["veredicto"] == "evidencia_insuficiente" and filas["T-10"]["base_n"] == 2
    assert filas["X-02"]["veredicto"] == "compartido" and filas["X-02"]["base_n"] == 3, "con 3 evaluables y 2 fallas (67 %) sí hay veredicto"
    assert set(c["evidencia_insuficiente"]) == {"T-14", "T-10"}
    assert "T-14" not in c["compartidos"] and "T-10" not in c["compartidos"]
    md = agrupacion.markdown_comparacion_reglas(c)
    assert "| T-14 | Uno | 1 de 1 | 1 de 1 | evidencia insuficiente (1 evaluables) |" in md
    assert "| T-10 | Dos | 2 de 2 | 2 de 2 | evidencia insuficiente (2 evaluables) |" in md
    assert "| X-02 | Tres | 2 de 3 | 2 de 3 | compartido |" in md
    assert "### Sin veredicto por evidencia insuficiente" in md


def test_umbral_por_conteo_no_requiere_minimo_de_evaluables(tmp_path):
    """Si la regla falla en `umbral` o más URL, el veredicto no depende de la proporción ni del mínimo."""
    urls = [f"{NOM}/p{i}" for i in range(1, 5)]
    reg = [{"url": u, "status": 200, "tipo": "articulo", "schema_tipos": ["Article"]} for u in urls]
    res = [_res("R-4", u, "falla") for u in urls[:3]] + [_res("R-4", urls[3], "no_aplica")]
    base = {"meta": {"dominio": "base.mx", "fecha": "2026-09-11"}, "resultados": res, "urls": reg}
    ruta = tmp_path / "base.json"
    ruta.write_text(json.dumps(base), encoding="utf-8")
    c = agrupacion.comparar_reglas(resultados=res, urls=reg, dominio="actual.mx", ruta_base=ruta, reglas={"R-4": {"titulo_hallazgo": "Cuatro"}})
    f = next(f for f in c["filas"] if f["regla_id"] == "R-4")
    assert (f["base_fallas"], f["base_n"], f["veredicto"]) == (3, 3, "compartido")
