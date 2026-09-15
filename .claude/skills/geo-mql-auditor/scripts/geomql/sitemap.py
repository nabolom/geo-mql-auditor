"""Sitemaps XML: parseo de urlset e índices, recolección y muestreo de hasta N URLs."""
from __future__ import annotations

import re

import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any, Callable
from urllib.parse import urlparse

from . import fetch as fetch_mod

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parsear_sitemap(texto: str) -> dict[str, Any]:
    try:
        raiz = ET.fromstring(texto.strip())
    except ET.ParseError as e:
        return {"tipo": "invalido", "urls": [], "sitemaps": [], "error": str(e)}
    tipo = _local(raiz.tag)
    urls: list[dict[str, str | None]] = []
    sitemaps: list[dict[str, str | None]] = []
    for hijo in raiz:
        nombre = _local(hijo.tag)
        loc = lastmod = None
        for campo in hijo:
            c = _local(campo.tag)
            if c == "loc":
                loc = (campo.text or "").strip()
            elif c == "lastmod":
                lastmod = (campo.text or "").strip()
        if not loc:
            continue
        (urls if nombre == "url" else sitemaps if nombre == "sitemap" else []).append({"loc": loc, "lastmod": lastmod})
    if tipo not in ("urlset", "sitemapindex"):
        tipo = "desconocido"
    return {"tipo": tipo, "urls": urls, "sitemaps": sitemaps, "error": None}


def recolectar_urls(
    url_sitemap: str,
    *,
    descargar: Callable[..., dict[str, Any]] | None = None,
    max_urls: int = 100,
    max_sitemaps: int = 20,
) -> dict[str, Any]:
    """Sigue índices de sitemaps y devuelve hasta ``max_urls`` URLs con lastmod."""
    descargar = descargar or fetch_mod.descargar
    pendientes = [url_sitemap]
    vistos: set[str] = set()
    urls: list[dict[str, Any]] = []
    errores: list[str] = []
    leidos = 0
    total_declarado = 0
    while pendientes and leidos < max_sitemaps:
        actual = pendientes.pop(0)
        if actual in vistos:
            continue
        vistos.add(actual)
        r = descargar(actual)
        leidos += 1
        if r.get("status") != 200 or not r.get("html"):
            errores.append(f"{actual}: HTTP {r.get('status')} {r.get('error') or ''}".strip())
            continue
        p = parsear_sitemap(r["html"])
        if p["error"]:
            errores.append(f"{actual}: {p['error']}")
            continue
        total_declarado += len(p["urls"])
        urls.extend(dict(u, sitemap=actual) for u in p["urls"])
        pendientes.extend(s["loc"] for s in p["sitemaps"])
    con_lastmod = sum(1 for u in urls if u.get("lastmod"))
    muestra = muestrear(urls, max_urls)
    return {
        "sitemap": url_sitemap,
        "sitemaps_leidos": leidos,
        "urls_total": len(urls),
        "urls": muestra,
        "truncado": len(urls) > len(muestra),
        "con_lastmod": con_lastmod,
        "sin_lastmod": len(urls) - con_lastmod,
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
