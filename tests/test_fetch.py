"""Descarga: file://, charset, caché y resolver sin red."""
from __future__ import annotations

from geomql import fetch


def test_descarga_local(url_de):
    r = fetch.descargar(url_de("articulo.html"))
    assert r["status"] == 200 and "Nómina Fácil" in r["html"] and r["error"] is None


def test_archivo_inexistente(url_de):
    r = fetch.descargar(url_de("no-existe.html"))
    assert r["status"] == 404 and r["error"]


def test_charset_desde_cabecera_y_meta():
    assert fetch._detectar_charset({"Content-Type": "text/html; charset=ISO-8859-1"}, b"") == "iso-8859-1"
    assert fetch._detectar_charset({}, b'<html><head><meta charset="windows-1252">') == "windows-1252"
    assert fetch._detectar_charset({}, b"<html>") == "utf-8"
    assert fetch._decodificar("año".encode("latin-1"), "latin-1") == "año"


def test_cache_escribe_y_lee(tmp_path, url_de):
    url = url_de("home.html")
    r1 = fetch.descargar_con_cache(url, tmp_path)
    assert r1["desde_cache"] is False
    r2 = fetch.descargar_con_cache(url, tmp_path)
    assert r2["desde_cache"] is True and r2["html"] == r1["html"]
    r3 = fetch.descargar_con_cache(url, tmp_path, forzar=True)
    assert r3["desde_cache"] is False


def test_resolver_usa_get_si_head_falla(monkeypatch):
    llamadas = []

    def falso(url, **k):
        llamadas.append(k.get("metodo"))
        if k.get("metodo") == "HEAD":
            return fetch._resultado_vacio(url, status=405, error="HTTP 405")
        return fetch._resultado_vacio(url, status=200)

    monkeypatch.setattr(fetch, "descargar", falso)
    r = fetch.resolver("https://ejemplo.com/perfil")
    assert r["status"] == 200 and llamadas == ["HEAD", "GET"]


def test_red_bloqueada_en_pruebas(sin_red):
    r = fetch.descargar("https://www.nominafacil.mx/")
    assert r["status"] == 0 and "bloqueada" in r["error"]


def test_descargar_codifica_caracteres_no_ascii_en_la_ruta(monkeypatch):
    """Una URL con acento sin codificar (IRI) debe convertirse a percent-encoding antes de pedirla, no fallar con 'ascii codec'."""
    import urllib.request
    from geomql import fetch

    pedidas = []

    class _Resp:
        status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self, url):
            self._url = url

        def geturl(self):
            return self._url

        def read(self, *a):
            return b"<html><body>ok</body></html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Opener:
        def open(self, req, timeout=None):
            pedidas.append(req.full_url)
            return _Resp(req.full_url)

    monkeypatch.setattr(fetch, "build_opener", lambda *a, **k: _Opener())
    r = fetch.descargar("https://universidadejemplo.mx/es/licenciatura-en-enfermería")
    assert r["status"] == 200 and r.get("error") in (None, "")
    assert pedidas and pedidas[0] == "https://universidadejemplo.mx/es/licenciatura-en-enfermer%C3%ADa"
    # una URL ya codificada no se codifica dos veces
    fetch.descargar("https://universidadejemplo.mx/es/licenciatura-en-enfermer%C3%ADa")
    assert pedidas[-1] == "https://universidadejemplo.mx/es/licenciatura-en-enfermer%C3%ADa"


def test_descargar_reintenta_una_vez_ante_error_de_red(monkeypatch):
    import urllib.request
    from urllib.error import URLError
    from geomql import fetch

    intentos = []

    class _Resp:
        status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self, url):
            self._url = url

        def geturl(self):
            return self._url

        def read(self, *a):
            return b"<html><body>ok</body></html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Opener:
        def open(self, req, timeout=None):
            intentos.append(req.full_url)
            if len(intentos) == 1:
                raise URLError("Remote end closed connection without response")
            return _Resp(req.full_url)

    monkeypatch.setattr(fetch, "build_opener", lambda *a, **k: _Opener())
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    r = fetch.descargar("https://x.mx/p")
    assert r["status"] == 200 and len(intentos) == 2
