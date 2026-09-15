"""Descarga de páginas y recursos.

Derivado de scripts/fetch_page.py de metawhisp/best-aeo-skill (MIT, ver NOTICE).
Correcciones: detección de charset, cadena de redirecciones, user-agent
configurable, límite de tamaño, soporte de file:// para fixturas y caché local.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import time
import zlib
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, url2pathname

UA_POR_DEFECTO = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 geo-mql-auditor/0.1"
)
MAX_BYTES_POR_DEFECTO = 5_000_000

_META_CHARSET_RE = re.compile(rb'<meta[^>]+charset=["\']?\s*([a-zA-Z0-9_\-]+)', re.IGNORECASE)


class _RegistroRedirecciones(HTTPRedirectHandler):
    """Registra cada salto de redirección para reportar la cadena completa."""

    def __init__(self) -> None:
        super().__init__()
        self.cadena: list[dict[str, Any]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        self.cadena.append({"de": req.full_url, "a": newurl, "codigo": code})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _detectar_charset(cabeceras: dict[str, str], cuerpo: bytes) -> str:
    tipo = cabeceras.get("Content-Type") or cabeceras.get("content-type") or ""
    m = re.search(r"charset=([\w\-]+)", tipo, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m = _META_CHARSET_RE.search(cuerpo[:8192])
    if m:
        return m.group(1).decode("ascii", "ignore").lower()
    return "utf-8"


def _decodificar(cuerpo: bytes, charset: str) -> str:
    for candidato in (charset, "utf-8", "latin-1"):
        try:
            return cuerpo.decode(candidato)
        except (LookupError, UnicodeDecodeError):
            continue
    return cuerpo.decode("utf-8", errors="replace")


def _descomprimir(cuerpo: bytes, codificacion: str) -> bytes:
    codificacion = (codificacion or "").lower()
    try:
        if codificacion == "gzip":
            return gzip.decompress(cuerpo)
        if codificacion == "deflate":
            try:
                return zlib.decompress(cuerpo)
            except zlib.error:
                return zlib.decompress(cuerpo, -zlib.MAX_WBITS)
    except (OSError, zlib.error):
        return cuerpo
    return cuerpo


def _resultado_vacio(url: str, **extra: Any) -> dict[str, Any]:
    base = {
        "url": url,
        "url_final": url,
        "status": 0,
        "html": "",
        "cabeceras": {},
        "cadena_redirecciones": [],
        "charset": None,
        "bytes": 0,
        "tiempo_ms": 0,
        "error": None,
    }
    base.update(extra)
    return base


def _descargar_local(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    ruta = Path(url2pathname(parsed.path))
    if not ruta.exists():
        return _resultado_vacio(url, status=404, error=f"archivo no encontrado: {ruta}")
    cuerpo = ruta.read_bytes()
    charset = _detectar_charset({}, cuerpo)
    return _resultado_vacio(
        url,
        status=200,
        html=_decodificar(cuerpo, charset),
        cabeceras={"Content-Type": "text/html"},
        charset=charset,
        bytes=len(cuerpo),
    )


def a_uri(url: str) -> str:
    """Convierte un IRI (ruta o consulta con acentos u otros caracteres no ASCII) a URI con percent-encoding; deja intactas las URL ya codificadas."""
    try:
        url.encode("ascii")
        return url
    except UnicodeEncodeError:
        p = urlparse(url)
        ruta = quote(p.path, safe="/%:@!$&'()*+,;=-._~")
        consulta = quote(p.query, safe="=&%:@!$'()*+,;/?-._~")
        return urlunparse((p.scheme, p.netloc.encode("idna").decode("ascii"), ruta, p.params, consulta, p.fragment))


def descargar(
    url: str,
    *,
    ua: str | None = None,
    timeout: int = 15,
    max_bytes: int = MAX_BYTES_POR_DEFECTO,
    metodo: str = "GET",
    cabeceras_extra: dict[str, str] | None = None,
    reintentos: int = 1,
) -> dict[str, Any]:
    """Descarga una URL y devuelve un dict con status, html, cabeceras y cadena de redirecciones.

    Nunca lanza excepciones: los errores van en la clave ``error`` con ``status`` 0.
    Soporta ``file://`` para fixturas locales. Codifica caracteres no ASCII de la ruta y
    reintenta una vez ante errores de red o tiempo de espera (no ante códigos HTTP).
    """
    if url.startswith("file://"):
        return _descargar_local(url)
    url = a_uri(url)
    resultado = _descargar_una_vez(url, ua=ua, timeout=timeout, max_bytes=max_bytes, metodo=metodo, cabeceras_extra=cabeceras_extra)
    intento = 0
    while resultado.get("status") == 0 and intento < reintentos:
        intento += 1
        time.sleep(1.5 * intento)
        resultado = _descargar_una_vez(url, ua=ua, timeout=timeout, max_bytes=max_bytes, metodo=metodo, cabeceras_extra=cabeceras_extra)
        if resultado.get("status") == 0:
            resultado["error"] = f"{resultado.get('error')} (tras {intento + 1} intentos)"
    return resultado


def _descargar_una_vez(
    url: str,
    *,
    ua: str | None,
    timeout: int,
    max_bytes: int,
    metodo: str,
    cabeceras_extra: dict[str, str] | None,
) -> dict[str, Any]:

    cabeceras = {
        "User-Agent": ua or UA_POR_DEFECTO,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.7",
        "Accept-Encoding": "gzip, deflate",
    }
    if cabeceras_extra:
        cabeceras.update(cabeceras_extra)
    req = Request(url, headers=cabeceras, method=metodo)
    registro = _RegistroRedirecciones()
    opener = build_opener(registro)
    inicio = time.time()
    try:
        with opener.open(req, timeout=timeout) as resp:
            cuerpo = resp.read(max_bytes + 1)
            truncado = len(cuerpo) > max_bytes
            cuerpo = cuerpo[:max_bytes]
            cabeceras_resp = {k: v for k, v in resp.headers.items()}
            cuerpo = _descomprimir(cuerpo, cabeceras_resp.get("Content-Encoding", ""))
            charset = _detectar_charset(cabeceras_resp, cuerpo)
            return {
                "url": url,
                "url_final": resp.geturl(),
                "status": resp.status,
                "html": _decodificar(cuerpo, charset) if metodo != "HEAD" else "",
                "cabeceras": cabeceras_resp,
                "cadena_redirecciones": registro.cadena,
                "charset": charset,
                "bytes": len(cuerpo),
                "tiempo_ms": int((time.time() - inicio) * 1000),
                "error": "respuesta truncada por tamaño" if truncado else None,
            }
    except HTTPError as e:
        cuerpo = b""
        try:
            cuerpo = e.read(max_bytes)
        except Exception:  # noqa: BLE001
            pass
        cabeceras_resp = {k: v for k, v in (e.headers or {}).items()}
        cuerpo = _descomprimir(cuerpo, cabeceras_resp.get("Content-Encoding", ""))
        charset = _detectar_charset(cabeceras_resp, cuerpo)
        return {
            "url": url,
            "url_final": e.geturl() if hasattr(e, "geturl") else url,
            "status": e.code,
            "html": _decodificar(cuerpo, charset),
            "cabeceras": cabeceras_resp,
            "cadena_redirecciones": registro.cadena,
            "charset": charset,
            "bytes": len(cuerpo),
            "tiempo_ms": int((time.time() - inicio) * 1000),
            "error": f"HTTP {e.code}",
        }
    except (URLError, TimeoutError, ValueError, OSError) as e:
        return _resultado_vacio(
            url,
            cadena_redirecciones=registro.cadena,
            tiempo_ms=int((time.time() - inicio) * 1000),
            error=str(e),
        )


def resolver(url: str, *, timeout: int = 10) -> dict[str, Any]:
    """Comprueba que una URL resuelve (HEAD y, si el servidor no lo acepta, GET)."""
    r = descargar(url, timeout=timeout, metodo="HEAD", max_bytes=1)
    if r["status"] in (0, 403, 405, 501):
        r = descargar(url, timeout=timeout, metodo="GET", max_bytes=65536)
    return {"url": url, "status": r["status"], "url_final": r["url_final"], "error": r["error"]}


def clave_cache(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def descargar_con_cache(
    url: str,
    dir_cache: Path | str | None,
    *,
    ttl_horas: float = 24,
    forzar: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Como ``descargar`` pero guarda el resultado en ``dir_cache`` durante ``ttl_horas``."""
    if not dir_cache:
        return descargar(url, **kwargs)
    dir_cache = Path(dir_cache)
    dir_cache.mkdir(parents=True, exist_ok=True)
    ruta = dir_cache / f"{clave_cache(url)}.json"
    if ruta.exists() and not forzar:
        edad_h = (time.time() - ruta.stat().st_mtime) / 3600
        if edad_h <= ttl_horas:
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                datos["desde_cache"] = True
                return datos
            except (OSError, ValueError):
                pass
    datos = descargar(url, **kwargs)
    datos["desde_cache"] = False
    if datos["status"] and not datos["error"]:
        try:
            ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return datos


if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) < 2:
        print("uso: fetch.py <url>", file=sys.stderr)
        sys.exit(2)
    r = descargar(sys.argv[1])
    r["html"] = r["html"][:300] + ("..." if len(r["html"]) > 300 else "")
    print(json.dumps(r, indent=2, ensure_ascii=False))
