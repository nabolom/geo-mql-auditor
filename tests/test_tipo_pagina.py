"""Detección del tipo de página sobre las fixturas."""
from __future__ import annotations

import pytest

from geomql.html import Documento
from geomql.tipo_pagina import detectar

CASOS = [
    ("home.html", "https://www.nominaejemplo.example/", "home"),
    ("articulo.html", "https://www.nominaejemplo.example/blog/reducir-rotacion-personal", "articulo"),
    ("solucion.html", "https://www.nominaejemplo.example/producto/timbrado", "solucion"),
    ("comparativa.html", "https://www.nominaejemplo.example/comparativa/nomina-ejemplo-vs-competidora", "comparativa"),
    ("faq.html", "https://www.nominaejemplo.example/preguntas-frecuentes", "faq"),
    ("local.html", "https://www.nominaejemplo.example/sucursales/ciudad-ejemplo", "local"),
    ("glosario.html", "https://www.nominaejemplo.example/glosario/finiquito", "glosario"),
    ("landing.html", "https://www.nominaejemplo.example/lp/guia-nomina-2026", "landing"),
]


@pytest.mark.parametrize("archivo,url,esperado", CASOS)
def test_tipos(html_de, archivo, url, esperado):
    r = detectar(Documento(html_de(archivo), url), url)
    assert r["tipo"] == esperado, r


def test_sin_senales_es_otra():
    d = Documento("<html><body><main><p>Hola.</p></main></body></html>", "https://x.mx/cosa")
    assert detectar(d)["tipo"] == "otra"


def test_articulo_sin_ruta_por_schema_y_byline(html_de):
    html = html_de("articulo.html")
    r = detectar(Documento(html, "https://www.nominaejemplo.example/x"), "https://www.nominaejemplo.example/x")
    assert r["tipo"] == "articulo" and "Article en JSON-LD" in r["senales"]


# ------------------------------------------------------------- tipos programa e institucional
def _doc(html_de, nombre, url):
    from geomql.html import Documento
    return Documento(html_de(nombre), url)


def test_pagina_de_carrera_es_programa(html_de):
    from geomql import tipo_pagina
    d = _doc(html_de, "programa.html", "https://universidad.example/es/licenciatura-en-psicologia")
    r = tipo_pagina.detectar(d, d.url)
    assert r["tipo"] == "programa" and r["confianza"] >= 0.6, r
    assert any("programa" in s for s in r["senales"])


def test_quienes_somos_y_becas_son_institucional(html_de):
    from geomql import tipo_pagina
    d = _doc(html_de, "institucional.html", "https://universidad.example/es/quienes-somos")
    r = tipo_pagina.detectar(d, d.url)
    assert r["tipo"] == "institucional", r
    d2 = _doc(html_de, "institucional_becas.html", "https://universidad.example/es/becas-y-financiamiento")
    assert tipo_pagina.detectar(d2, d2.url)["tipo"] == "institucional"


def test_carrera_renderizada_es_programa_por_ruta_y_contenido(html_de):
    """La ruta /es/ingenieria-… y el texto de plan de estudios deben bastar aunque el H1 falte."""
    from geomql import tipo_pagina
    from geomql.html import Documento
    html = html_de("programa.html").replace("<h1>Licenciatura en Psicología</h1>", "")
    d = Documento(html, "https://universidad.example/es/ingenieria-en-desarrollo-de-software")
    assert tipo_pagina.detectar(d, d.url)["tipo"] == "programa"


def test_las_reglas_de_autoria_article_y_fecha_no_aplican_a_programa_ni_institucional():
    from geomql.reglas import cargar_rulebook, indice
    idx = indice(cargar_rulebook())
    for rid in ("E-04", "S-03", "S-10", "X-08", "X-09", "X-05"):
        for tipo in ("programa", "institucional"):
            assert not idx[rid].aplica_a(tipo), (rid, tipo)
    for rid in ("X-01", "X-02", "X-10", "X-14", "X-16", "S-05", "T-09", "T-10"):
        for tipo in ("programa", "institucional"):
            assert idx[rid].aplica_a(tipo), (rid, tipo)


def test_los_tipos_nuevos_existen_en_la_lista_valida_y_el_cli():
    from geomql import auditoria
    assert "programa" in auditoria.TIPOS_VALIDOS and "institucional" in auditoria.TIPOS_VALIDOS
