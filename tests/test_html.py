"""Parser HTML: contenido principal, encabezados, enlaces, JSON-LD, formularios."""
from __future__ import annotations

from geomql.html import Documento, contar_palabras, oraciones


def test_metadatos_basicos(html_de):
    d = Documento(html_de("articulo.html"), "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    assert d.titulo.startswith("Cómo reducir la rotación")
    assert d.lang == "es-mx"
    assert d.canonical == "https://www.nominafacil.mx/blog/reducir-rotacion-personal"
    assert "empresas medianas" in d.meta("description")
    assert d.meta("og:site_name") == "Nómina Fácil"
    assert {h["lang"] for h in d.hreflang()} == {"es-mx", "en", "x-default"}


def test_contenido_principal_excluye_navegacion_y_pie(html_de):
    d = Documento(html_de("articulo.html"))
    assert d.principal.etiqueta in ("main", "article")
    tp = d.texto_principal()
    assert "rotación de personal es la proporción" in tp
    assert "Precios (desde $1,200)" not in tp
    assert "+52 81 1234 5678" not in tp
    assert "Artículos relacionados" not in tp
    assert "Inicio › Blog" not in tp, "el breadcrumb es boilerplate aunque esté dentro de article"


def test_encabezados_listas_tablas(html_de):
    d = Documento(html_de("articulo.html"))
    enc = d.encabezados(solo_principal=True)
    assert [e["nivel"] for e in enc][:3] == [1, 2, 2]
    assert sum(1 for e in enc if e["nivel"] == 1) == 1
    assert d.listas()["ol"] == 1 and d.listas()["items"] == 3
    tablas = d.tablas()
    assert len(tablas) == 1 and tablas[0]["con_encabezado"] and tablas[0]["columnas"] == 3


def test_enlaces_marcan_principal_y_boilerplate(html_de):
    d = Documento(html_de("articulo.html"), "https://www.nominafacil.mx/blog/reducir-rotacion-personal")
    enlaces = d.enlaces()
    inegi = next(e for e in enlaces if "inegi" in e["href"])
    assert inegi["en_principal"] and not inegi["boilerplate"]
    precios = next(e for e in enlaces if e["href"] == "/precios")
    assert precios["boilerplate"]


def test_json_ld_con_graph_y_error(html_de):
    d = Documento(html_de("articulo.html"))
    bloques = d.json_ld()
    assert len(bloques) == 1 and bloques[0]["error"] is None
    assert "@graph" in bloques[0]["datos"]
    roto = Documento('<script type="application/ld+json">{"@type": "Thing",}</script>')
    assert roto.json_ld()[0]["error"]


def test_formularios_y_campos_ocultos(html_de):
    d = Documento(html_de("home.html"))
    forms = d.formularios()
    assert len(forms) == 1
    ocultos = {c["name"] for c in forms[0]["campos"] if c["oculto"]}
    assert {"utm_source", "utm_medium", "utm_campaign", "referrer"} <= ocultos


def test_spa_sin_contenido(html_de):
    d = Documento(html_de("spa.html"))
    assert contar_palabras(d.texto_principal()) < 5
    assert "JavaScript" in d.texto_noscript()


def test_times_y_robots_meta(html_de):
    d = Documento(html_de("articulo.html"))
    assert [t["datetime"] for t in d.times()] == ["2026-06-01", "2026-08-15"]
    l = Documento(html_de("landing.html"))
    rm = l.robots_meta()
    assert "noindex" in rm["robots"] and "noarchive" in rm["bingbot"]


def test_oraciones_y_palabras():
    texto = "La rotación es alta. ¿Por qué? Porque no pagan a tiempo. Según el INEGI, 18.4% en 2025."
    assert len(oraciones(texto)) == 4
    assert contar_palabras("uno dos tres") == 3


def test_principal_ignora_article_vacio_y_toma_el_bloque_denso():
    """Drupal deja un <article> cascarón sin texto y pinta el contenido en otra región; el principal debe ser el bloque con texto."""
    from geomql.html import Documento, contar_palabras

    cuerpo = " ".join(["El plan de estudios combina certificados cocreados con empresas y prácticas profesionales desde el primer semestre."] * 12)
    html = f"""<html><body>
    <header><nav><a href="/">Inicio</a><a href="/oferta">Oferta</a></nav></header>
    <div class="page"><div class="region region-content">
      <article class="node node--type-oferta-academica"></article>
      <div class="block block-content"><div class="content"><div class="field field--name-body"><h2>Plan de estudios</h2><p>{cuerpo}</p></div></div></div>
    </div></div>
    <footer><p>© 2026 Marca</p></footer></body></html>"""
    d = Documento(html, "https://x.mx/p")
    assert contar_palabras(d.texto_principal()) > 100, d.principal.etiqueta
    assert "certificados cocreados" in d.texto_principal()
