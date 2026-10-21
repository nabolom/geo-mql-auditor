"""Sitemaps XML: parseo de urlset e índices, recolección y muestreo de hasta N URLs."""
from __future__ import annotations

import re
import io
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any, Callable
from urllib.parse import urlparse

from . import fetch as fetch_mod

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_BYTES_SITEMAP = 5_000_000
MAX_ENTRADAS_SITEMAP = 50_001
MAX_URLS_MUESTREO = 1_000
MAX_SITEMAPS = 20
MAX_BYTES_ESTANDAR = 50 * 1024 * 1024


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parsear_sitemap(texto: str, *, max_entradas: int = MAX_ENTRADAS_SITEMAP) -> dict[str, Any]:
    urls: list[dict[str, str | None]] = []
    sitemaps: list[dict[str, str | None]] = []
    tipo = "desconocido"
    vistas = 0
    truncado = False
    try:
        iterador = ET.iterparse(io.StringIO(texto), events=("start", "end"))
        raiz = None
        for evento, elemento in iterador:
            if evento == "start" and raiz is None:
                raiz = elemento
                tipo = _local(elemento.tag)
                continue
            if evento != "end" or elemento is raiz:
                continue
            nombre = _local(elemento.tag)
            if nombre in ("url", "sitemap"):
                vistas += 1
                if vistas > max_entradas:
                    truncado = True
                    break
                loc = lastmod = None
                for campo in elemento:
                    c = _local(campo.tag)
                    if c == "loc":
                        loc = (campo.text or "").strip()
                    elif c == "lastmod":
                        lastmod = (campo.text or "").strip()
                if loc:
                    (urls if nombre == "url" else sitemaps).append({"loc": loc, "lastmod": lastmod})
                if raiz is not None:
                    raiz.clear()
    except ET.ParseError as e:
        return {"tipo": "invalido", "urls": [], "sitemaps": [], "total_entradas": vistas, "truncado": False, "error": str(e)}
    if tipo not in ("urlset", "sitemapindex"):
        tipo = "desconocido"
    return {"tipo": tipo, "urls": urls, "sitemaps": sitemaps, "total_entradas": vistas, "truncado": truncado, "error": None}


def recolectar_urls(
    url_sitemap: str,
    *,
    descargar: Callable[..., dict[str, Any]] | None = None,
    max_urls: int = 100,
    max_sitemaps: int = 20,
) -> dict[str, Any]:
    """Sigue índices con límites de documentos, bytes, entradas y memoria retenida."""
    if not 1 <= max_urls <= MAX_URLS_MUESTREO:
        raise ValueError(f"max_urls debe estar entre 1 y {MAX_URLS_MUESTREO}")
    if not 1 <= max_sitemaps <= MAX_SITEMAPS:
        raise ValueError(f"max_sitemaps debe estar entre 1 y {MAX_SITEMAPS}")
    descargar = descargar or fetch_mod.descargar
    pendientes = [url_sitemap]
    vistos: set[str] = set()
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errores: list[str] = []
    leidos = 0
    total_declarado = 0
    con_lastmod = 0
    entrada_truncada = False
    limite_bytes = False
    exceso_bytes = False
    exceso_urls = False
    bytes_max = 0
    while pendientes and leidos < max_sitemaps:
        actual = pendientes.pop(0)
        if actual in vistos:
            continue
        vistos.add(actual)
        r = descargar(actual, max_bytes=MAX_BYTES_SITEMAP)
        leidos += 1
        longitud_declarada = r.get("cabeceras", {}).get("Content-Length") or r.get("cabeceras", {}).get("content-length")
        try:
            declarado = int(longitud_declarada) if longitud_declarada else 0
        except (TypeError, ValueError):
            declarado = 0
        bytes_max = max(bytes_max, r.get("bytes", 0), declarado)
        exceso_bytes = exceso_bytes or declarado > MAX_BYTES_ESTANDAR or r.get("bytes", 0) > MAX_BYTES_ESTANDAR
        limite_bytes = limite_bytes or declarado > MAX_BYTES_SITEMAP
        if r["status"] != 200:
            errores.append(f"{actual}: HTTP {r['status']} {r.get('error') or ''}".strip())
            continue
        if r.get("error") and "truncada por tamaño" in r["error"]:
            limite_bytes = True
            errores.append(f"{actual}: contenido truncado por el límite local de {MAX_BYTES_SITEMAP} bytes; no se afirma cumplimiento")
            continue
        p = parsear_sitemap(r["html"])
        if p["error"]:
            errores.append(f"{actual}: {p['error']}")
            continue
        if p["tipo"] not in ("urlset", "sitemapindex"):
            errores.append(f"{actual}: XML sin raíz urlset o sitemapindex")
            continue
        total_declarado += p["total_entradas"] if p["tipo"] == "urlset" else 0
        entrada_truncada = entrada_truncada or p["truncado"]
        exceso_urls = exceso_urls or (p["tipo"] == "urlset" and p["total_entradas"] > 50_000)
        entradas = p["urls"] if p["tipo"] == "urlset" else p["sitemaps"]
        if p["tipo"] == "urlset":
            con_lastmod += sum(1 for u in entradas if u.get("lastmod"))
            for u in entradas:
                loc = u["loc"] or ""
                segmentos = [x for x in urlparse(loc).path.strip("/").split("/") if x]
                if segmentos and re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", segmentos[0], re.I):
                    segmentos = segmentos[1:]
                grupo = segmentos[0] if segmentos else ""
                if grupo in grupos or len(grupos) < max_urls:
                    if len(grupos[grupo]) < max_urls:
                        grupos[grupo].append(dict(u, sitemap=actual))
        else:
            pendientes.extend(s["loc"] for s in entradas)
    if pendientes:
        errores.append(f"se alcanzó el límite de {max_sitemaps} documentos con sitemaps aún pendientes")
    candidatos = [u for grupo in grupos.values() for u in grupo]
    muestra = muestrear(candidatos, max_urls)
    return {
        "sitemap": url_sitemap,
        "sitemaps_leidos": leidos,
        "urls_total": total_declarado,
        "urls": muestra,
        "truncado": total_declarado > len(muestra) or entrada_truncada,
        "entrada_truncada": entrada_truncada,
        "limite_bytes": limite_bytes,
        "exceso_bytes": exceso_bytes,
        "exceso_urls": exceso_urls,
        "bytes_max": bytes_max,
        "cobertura_completa": not errores and not entrada_truncada and not limite_bytes,
        "con_lastmod": con_lastmod,
        "sin_lastmod": max(0, total_declarado - con_lastmod),
        "errores": errores,
    }


def muestrear(urls: list[dict[str, Any]], max_urls: int) -> list[dict[str, Any]]:
    """Muestreo determinista que preserva diversidad por primer segmento de ruta."""
    if len(urls) <= max_urls:
        return list(urls)
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in urls:
        segmentos = [x for x in urlparse(u["loc"]).path.strip("/").split("/") if x]
        if segmentos and re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", segmentos[0], re.I):
            segmentos = segmentos[1:]  # prefijo de idioma o región: no es una sección
        grupos[segmentos[0] if segmentos else ""].append(u)
    salida: list[dict[str, Any]] = []
    claves = sorted(grupos)
    i = 0
    while len(salida) < max_urls and any(grupos.values()):
        clave = claves[i % len(claves)]
        if grupos[clave]:
            salida.append(grupos[clave].pop(0))
        i += 1
    return salida


def url_sitemap_por_defecto(url_sitio: str) -> str:
    p = urlparse(url_sitio)
    if p.scheme == "file":
        return url_sitio.rsplit("/", 1)[0] + "/sitemap.xml"
    return f"{p.scheme}://{p.netloc}/sitemap.xml"
