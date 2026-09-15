"""robots.txt (precedencia RFC 9309 / Google), categorías de bots y sitemaps."""
from __future__ import annotations

from geomql import bots, robots, sitemap
from geomql import fetch


def _robots(html_de, nombre):
    return robots.parsear_robots(html_de(f"robots/{nombre}"))


def test_parseo_basico(html_de):
    r = _robots(html_de, "basico.txt")
    assert r["sitemaps"] == ["https://www.nominafacil.mx/sitemap.xml"]
    assert r["grupos"][0]["agentes"] == ["*"]
    assert ("disallow", "/admin/") in r["grupos"][0]["reglas"]


def test_grupo_mas_especifico_y_comodin(html_de):
    r = _robots(html_de, "bloquea_entrenamiento.txt")
    assert robots.permitido(r, "GPTBot", "/blog/x")["permitido"] is False
    assert robots.permitido(r, "OAI-SearchBot", "/blog/x")["permitido"] is True
    assert robots.permitido(r, "PerplexityBot", "/blog/x")["permitido"] is True
    assert robots.permitido(r, "PerplexityBot", "/admin/x")["permitido"] is False
    # Googlebot-Image hereda del token Googlebot (prefijo) si existe; aquí cae en *
    assert robots.grupo_para(r, "Googlebot-Image")[0] == "*"


def test_precedencia_ruta_mas_larga_y_empate_allow(html_de):
    r = _robots(html_de, "precedencia.txt")
    assert robots.permitido(r, "Bot", "/blog/otro")["permitido"] is False
    assert robots.permitido(r, "Bot", "/blog/reducir-rotacion-personal")["permitido"] is True
    assert robots.permitido(r, "Bot", "/page")["permitido"] is True, "empate de longitud gana Allow"
    assert robots.permitido(r, "Bot", "/folder/x")["permitido"] is True, "Allow /folder/ es más largo que Disallow /folder"
    assert robots.permitido(r, "Bot", "/folderx")["permitido"] is False


def test_bloqueo_total_con_excepcion(html_de):
    r = _robots(html_de, "bloquea_busqueda.txt")
    assert robots.permitido(r, "OAI-SearchBot")["permitido"] is False
    assert robots.permitido(r, "Googlebot")["permitido"] is True


def test_comodines_y_ancla():
    r = robots.parsear_robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*\n")
    assert robots.permitido(r, "X", "/guia.pdf")["permitido"] is False
    assert robots.permitido(r, "X", "/guia.pdfx")["permitido"] is True
    assert robots.permitido(r, "X", "/tmp123")["permitido"] is False


def test_estado_5xx_y_404(monkeypatch):
    def cinco(url, **k):
        return fetch._resultado_vacio(url, status=503, error="HTTP 503")

    assert robots.cargar_robots("https://x.mx/pagina", descargar=cinco)["estado"] == "error_servidor"

    def cuatro(url, **k):
        return fetch._resultado_vacio(url, status=404, error="HTTP 404")

    assert robots.cargar_robots("https://x.mx/pagina", descargar=cuatro)["estado"] == "no_existe"


def test_categorias_de_bots_separan_entrenamiento_y_busqueda(html_de):
    r = _robots(html_de, "bloquea_entrenamiento.txt")
    acceso = bots.evaluar_acceso(r, ruta="/blog/x")
    res = acceso["resumen"]
    assert res["busqueda_bloqueados"] == []
    assert {"GPTBot", "ClaudeBot", "Google-Extended", "CCBot"} <= set(res["entrenamiento_bloqueados"])
    assert res["google_extended_bloqueado"] is True
    assert res["politica_entrenamiento"] == "mixta"
    tokens = {b["token"] for b in acceso["por_categoria"]["busqueda"]}
    assert {"OAI-SearchBot", "Claude-SearchBot", "PerplexityBot", "Googlebot", "bingbot", "Applebot", "Meta-WebIndexer"} <= tokens
    usuario = {b["token"] for b in acceso["por_categoria"]["usuario"]}
    assert {"ChatGPT-User", "Claude-User", "Perplexity-User"} <= usuario


def test_registro_de_bots_es_coherente():
    reg = bots.cargar_registro()
    assert reg["verificado_el"] == "2026-09-10"
    for b in reg["bots"]:
        assert b["categoria"] in bots.CATEGORIAS, b["token"]
        if b["categoria"] != "no_documentado":
            assert b["fuente"].startswith("http"), b["token"]
    google_ext = next(b for b in reg["bots"] if b["token"] == "Google-Extended")
    assert google_ext["es_token_de_control"] and google_ext["categoria"] == "entrenamiento"
    assert next(b for b in reg["bots"] if b["token"] == "anthropic-ai")["categoria"] == "no_documentado"


def test_sitemap_urlset_e_indice(html_de):
    p = sitemap.parsear_sitemap(html_de("sitemap.xml"))
    assert p["tipo"] == "urlset" and len(p["urls"]) == 4
    assert p["urls"][0]["lastmod"] == "2026-09-01" and p["urls"][3]["lastmod"] is None
    i = sitemap.parsear_sitemap(html_de("sitemap_index.xml"))
    assert i["tipo"] == "sitemapindex" and len(i["sitemaps"]) == 2
    assert sitemap.parsear_sitemap("<no xml")["tipo"] == "invalido"


def test_recolectar_sigue_indices_y_limita(html_de):
    docs = {
        "https://s.mx/sitemap.xml": html_de("sitemap_index.xml"),
        "https://www.nominafacil.mx/sitemap-paginas.xml": html_de("sitemap.xml"),
        "https://www.nominafacil.mx/sitemap-blog.xml": "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" + "".join(f"<url><loc>https://www.nominafacil.mx/blog/p{i}</loc></url>" for i in range(200)) + "</urlset>",
    }

    def falso(url, **k):
        if url in docs:
            return fetch._resultado_vacio(url, status=200, html=docs[url])
        return fetch._resultado_vacio(url, status=404, error="HTTP 404")

    r = sitemap.recolectar_urls("https://s.mx/sitemap.xml", descargar=falso, max_urls=50)
    assert r["urls_total"] == 204 and len(r["urls"]) == 50 and r["truncado"]
    rutas = {u["loc"] for u in r["urls"]}
    assert "https://www.nominafacil.mx/" in rutas, "el muestreo preserva diversidad por sección"
    assert r["sin_lastmod"] == 201


def test_muestreo_ignora_prefijo_de_idioma_y_reparte_por_seccion():
    """Con todas las URL bajo /es/, la diversidad se toma del segundo segmento; un sitio con 30 avisos legales no debe llenar la muestra."""
    urls = [{"loc": "https://s.mx/es"}] + [{"loc": f"https://s.mx/es/aviso-de-privacidad/{i}"} for i in range(30)] + [{"loc": f"https://s.mx/es/campus/{i}"} for i in range(10)] + [{"loc": f"https://s.mx/es/licenciatura-en-{n}"} for n in ("nutricion", "psicologia", "mercadotecnia")] + [{"loc": "https://s.mx/es/preparatoria-bilingue"}]
    m = [u["loc"] for u in sitemap.muestrear(urls, 8)]
    assert "https://s.mx/es" in m
    assert sum(1 for u in m if "aviso-de-privacidad" in u) <= 2, m
    assert any("licenciatura" in u for u in m) and any("campus" in u for u in m) and any("preparatoria" in u for u in m)
    assert len(m) == 8
