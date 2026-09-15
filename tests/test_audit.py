"""Audit de extremo a extremo sobre las fixturas, sin red: hallazgos, puntaje, archivos por vector, reporte y fusión de subagentes."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from geomql import auditoria, fetch
from geomql.reglas import cargar_rulebook, indice

BASE = "https://www.nominafacil.mx"
MAPA = {
    f"{BASE}/": "home.html",
    f"{BASE}/blog/reducir-rotacion-personal": "articulo.html",
    f"{BASE}/producto/timbrado": "solucion.html",
    f"{BASE}/comparativa/nomina-facil-vs-contpaqi": "comparativa.html",
    f"{BASE}/preguntas-frecuentes": "faq.html",
    f"{BASE}/sucursales/monterrey": "local.html",
    f"{BASE}/glosario/finiquito": "glosario.html",
    f"{BASE}/lp/guia-nomina-2026": "landing.html",
    f"{BASE}/robots.txt": "robots/bloquea_entrenamiento.txt",
    f"{BASE}/sitemap.xml": "sitemap.xml",
}


@pytest.fixture
def descargar_fixturas(html_de):
    def _d(url, **k):
        if url in MAPA:
            return fetch._resultado_vacio(url, status=200, html=html_de(MAPA[url]), url_final=url)
        if url.endswith("/llms.txt"):
            return fetch._resultado_vacio(url, status=404, error="HTTP 404")
        return fetch._resultado_vacio(url, status=404, error="HTTP 404")

    return _d


def test_audit_completo_sobre_fixturas(descargar_fixturas, tmp_path):
    urls = [u for u in MAPA if not u.endswith((".txt", ".xml"))]
    payload = auditoria.correr(
        urls=urls,
        url_base=f"{BASE}/",
        descargar=descargar_fixturas,
        dir_salidas=tmp_path / "salidas",
        dir_historial=tmp_path / "historial",
        corrida="prueba",
        ahora=datetime(2026, 9, 10, tzinfo=timezone.utc),
        fecha=date(2026, 9, 10),
    )
    meta = payload["meta"]
    assert meta["n_urls"] == 8 and meta["dominio"] == "nominafacil.mx"
    assert Path(meta["archivos"]["md"]).name == "2026-09-10_nominafacil.mx_audit.md"
    assert set(meta["archivos_vector"]) == {"tecnico", "extractabilidad", "schema", "entidad"}

    # tipos detectados
    tipos = {u["url"]: u["tipo"] for u in payload["urls"]}
    assert tipos[f"{BASE}/"] == "home" and tipos[f"{BASE}/blog/reducir-rotacion-personal"] == "articulo"

    # hallazgos con las dos etiquetas y sin impacto proyectado
    assert payload["hallazgos"], "debe haber hallazgos"
    for h in payload["hallazgos"]:
        assert h["evidencia_observacion"] in ("Confirmado", "Probable", "Hipótesis")
        assert h["fuerza_regla"] in ("A", "B", "C") and h["tipo_evidencia"]
        assert h["impacto_esperado"] in ("alto", "medio", "bajo") and h["horizonte"] in ("30d", "90d", "largo")
    md = payload["markdown"]
    assert "impacto proyectado" not in md.lower().replace("no se presentan impactos proyectados", "")
    assert "A · requisito oficial" in md

    ids = {h["regla_id"] for h in payload["hallazgos"]}
    assert "T-07" in ids, "landing con noindex y solución con max-snippet"
    assert "T-13" in ids, "landing con noarchive"
    assert "X-04" in ids, "dato sin fuente en el artículo"
    assert "S-08" in ids, "FAQPage con pregunta no visible"
    assert "X-13" in ids, "párrafo largo en la comparativa"
    assert "T-03" not in ids, "los bots de búsqueda no están bloqueados"
    assert "T-04" in ids, "política de entrenamiento mixta (CCBot bloqueado, otros no)"
    assert "S-03" not in {h["regla_id"] for h in payload["hallazgos"] if f"{BASE}/" in h["urls_afectadas"]}, "Article no se exige en la home"

    # sitio y política de bots
    sitio = payload["sitio"]
    assert sitio["bots"]["resumen"]["busqueda_bloqueados"] == []
    assert sitio["bots"]["resumen"]["google_extended_bloqueado"] is True
    assert sitio["sitemap"]["presente"] and sitio["sitemap"]["sin_lastmod"] == 1
    assert not sitio["llmstxt"]["presente"]

    # puntaje excluye principios y no aparece en el titular
    p = payload["puntaje_cumplimiento"]
    assert set(p["por_categoria"]) <= {"tecnico", "extractabilidad", "schema", "entidad"}
    assert p["global"] is not None and "cumplimiento" not in payload["titular"].lower()
    assert payload["titular"].startswith("**Tres hallazgos prioritarios**")

    # archivo de vector: resumen agregado, no detalle por URL
    tec = json.loads(Path(meta["archivos_vector"]["tecnico"]).read_text(encoding="utf-8"))
    assert tec["categoria"] == "tecnico" and tec["reglas"]
    regla_t07 = next(r for r in tec["reglas"] if r["regla_id"] == "T-07")
    assert regla_t07["por_tipo"]["landing"]["falla"] == 1 and len(regla_t07["ejemplos_falla"]) <= 3
    assert "sitio" in tec and tec["contexto"]["n_urls"] == 8

    # snapshot para monitor
    snap = json.loads(Path(meta["snapshot"]).read_text(encoding="utf-8"))
    assert snap["dominio"] == "nominafacil.mx" and len(snap["resultados"]) == len(payload["resultados"])


def test_puntaje_no_incluye_hipotesis_ni_principios(descargar_fixturas, tmp_path):
    payload = auditoria.correr(urls=[f"{BASE}/blog/reducir-rotacion-personal"], url_base=f"{BASE}/", descargar=descargar_fixturas, dir_salidas=tmp_path, dir_historial=tmp_path, corrida="p2", ahora=datetime(2026, 9, 10, tzinfo=timezone.utc))
    reglas = indice(cargar_rulebook())
    for r in payload["resultados"]:
        if r["observacion"] == "Hipótesis" or not reglas[r["regla_id"]].puntua:
            continue
    assert all(r["regla_id"] not in ("X-00", "S-00", "N-04", "V-01") for r in payload["resultados"])


def test_fusionar_subagentes(descargar_fixturas, tmp_path):
    payload = auditoria.correr(urls=[f"{BASE}/blog/reducir-rotacion-personal", f"{BASE}/"], url_base=f"{BASE}/", descargar=descargar_fixturas, dir_salidas=tmp_path, dir_historial=tmp_path, corrida="p3", ahora=datetime(2026, 9, 10, tzinfo=timezone.utc))
    ruta_json = payload["meta"]["archivos"]["json"]
    primero = payload["hallazgos"][0]["id"]
    salida = {
        "vector": "extractabilidad",
        "hallazgos": [
            {"regla_id": "X-11", "titulo": "Contenido con aporte propio limitado", "detalle": "El artículo repite definiciones genéricas.", "recomendacion": "Añade datos propios con método.", "evidencia_observacion": "Hipótesis", "urls_afectadas": [f"{BASE}/blog/reducir-rotacion-personal"], "nuevo": True},
        ],
        "ajustes": [{"hallazgo_id": primero, "evidencia_observacion": "Probable", "motivo": "la heurística no distingue el caso"}],
        "notas": ["Revisar manualmente la apertura del artículo."],
    }
    nuevo = auditoria.fusionar(ruta_json, [salida])
    ids = {h["regla_id"] for h in nuevo["hallazgos"]}
    assert "X-11" in ids
    ajustado = next(h for h in nuevo["hallazgos"] if h["id"] == primero)
    assert ajustado["evidencia_observacion"] == "Probable" and "Ajuste del subagente" in ajustado["detalle"]
    assert "Nota de subagente" in nuevo["markdown"] and "subagentes" in nuevo["markdown"]
    assert Path(nuevo["meta"]["archivos"]["md"]).read_text(encoding="utf-8") == nuevo["markdown"]


def test_validacion_rechaza_impacto_proyectado():
    errores = auditoria.validar_salida_subagente({"hallazgos": [{"regla_id": "X-04", "titulo": "t", "detalle": "subirá +18 puntos", "recomendacion": "r", "evidencia_observacion": "Confirmado"}]})
    assert any("impacto proyectado" in e for e in errores)
    assert auditoria.validar_salida_subagente({"hallazgos": []}) == []


def test_pagina_con_error_http(descargar_fixturas, tmp_path):
    payload = auditoria.correr(urls=[f"{BASE}/no-existe"], url_base=f"{BASE}/", descargar=descargar_fixturas, dir_salidas=tmp_path, dir_historial=tmp_path, corrida="p4")
    assert payload["hallazgos"][0]["regla_id"] == "T-01" and "404" in payload["hallazgos"][0]["detalle"]
