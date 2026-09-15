"""Vector técnico: códigos HTTP, canonical, directivas de snippet, meta bingbot, hreflang, dependencia de JavaScript, sitemap."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from .html import Documento, contar_palabras

MARCADORES_FRAMEWORK = {
    "__NEXT_DATA__": "Next.js",
    "__NUXT__": "Nuxt",
    "ng-version": "Angular",
    "data-reactroot": "React",
    "id=\"root\"": "SPA (root)",
    "id=\"app\"": "SPA (app)",
    "id=\"__next\"": "Next.js",
    "window.__INITIAL_STATE__": "SPA (estado inicial)",
    "data-server-rendered": "Vue SSR",
}


def _normalizar_url(u: str) -> str:
    p = urlparse(u)
    ruta = p.path or "/"
    if ruta != "/" and ruta.endswith("/"):
        ruta = ruta[:-1]
    return f"{p.scheme}://{p.netloc.lower()}{ruta}" + (f"?{p.query}" if p.query else "")


def analizar_pagina(fetch: dict[str, Any], doc: Documento, url: str, *, render: dict[str, Any] | None = None) -> dict[str, Any]:
    url_final = fetch.get("url_final") or url
    cadena = fetch.get("cadena_redirecciones") or []
    codigos = [c.get("codigo") for c in cadena]
    res: dict[str, Any] = {
        "codigo_http": {
            "status": fetch.get("status"),
            "url_final": url_final,
            "saltos": len(cadena),
            "codigos_redireccion": codigos,
            "solo_301": all(c == 301 for c in codigos) if codigos else None,
            "error": fetch.get("error"),
            "tiempo_ms": fetch.get("tiempo_ms"),
        }
    }

    # canonical
    can = doc.canonical
    can_abs = urljoin(url_final, can) if can else None
    res["canonical"] = {
        "presente": bool(can),
        "valor": can,
        "absoluto": bool(can) and bool(urlparse(can).scheme),
        "autorreferente": bool(can_abs) and _normalizar_url(can_abs) == _normalizar_url(url_final),
        "url_final": url_final,
    }

    # directivas meta robots y cabecera X-Robots-Tag
    rm = doc.robots_meta()
    directivas = set(rm.get("robots", [])) | set(rm.get("googlebot", []))
    x_robots = ""
    for k, v in (fetch.get("cabeceras") or {}).items():
        if k.lower() == "x-robots-tag":
            x_robots = v.lower()
    max_snippet = None
    for d in directivas:
        m = re.fullmatch(r"max-snippet:\s*(-?\d+)", d)
        if m:
            max_snippet = int(m.group(1))
    data_nosnippet = len(doc.buscar(None, **{"data-nosnippet": None}))
    data_nosnippet_principal = sum(1 for n in doc.buscar(None, **{"data-nosnippet": None}) if Documento._dentro(n, doc.principal))
    res["directivas"] = {
        "noindex": "noindex" in directivas or "noindex" in x_robots,
        "nosnippet": "nosnippet" in directivas or "nosnippet" in x_robots,
        "max_snippet": max_snippet,
        "max_snippet_restrictivo": max_snippet is not None and 0 <= max_snippet < 160,
        "data_nosnippet": data_nosnippet,
        "data_nosnippet_en_principal": data_nosnippet_principal,
        "x_robots_tag": x_robots,
        "meta_robots": sorted(directivas),
    }
    bing = set(rm.get("bingbot", []))
    res["meta_bingbot"] = {"nocache": "nocache" in bing, "noarchive": "noarchive" in bing or ("noarchive" in directivas)}

    desc = doc.meta("description")
    # Código volcado en la meta description (CSS, HTML, JSON): llaves con propiedades, etiquetas o selectores.
    parece_codigo = bool(re.search(r"[{}]\s*[\w-]+\s*:\s*[^;]+;|</?[a-z][a-z0-9-]*[\s>/]|^\s*[.#][\w-]+\s*\{", desc, re.I)) or desc.count("{") >= 2
    res["meta_description"] = {"presente": bool(desc), "longitud": len(desc), "texto": desc[:200], "parece_codigo": parece_codigo}

    # hreflang
    hl = doc.hreflang()
    idiomas = [h["lang"] for h in hl]
    res["hreflang"] = {
        "presente": bool(hl),
        "idiomas": idiomas,
        "incluye_x_default": "x-default" in idiomas,
        "incluye_self": any(_normalizar_url(urljoin(url_final, h["href"])) == _normalizar_url(url_final) for h in hl),
        "lang_html": doc.lang,
    }

    # dependencia de JavaScript
    html = doc.html
    palabras_html = contar_palabras(doc.texto_principal())
    palabras_total = contar_palabras(doc.texto(excluir_boilerplate=False))
    marcadores = sorted({nombre for marca, nombre in MARCADORES_FRAMEWORK.items() if marca in html})
    _PH = r"\{\{\s*[A-Za-z_][\w.]*\s*\}\}"
    placeholders = len(re.findall(_PH, doc.texto(excluir_boilerplate=False)))
    placeholders_principal = len(re.findall(_PH, doc.texto_principal()))
    plantilla_vacia = placeholders >= 3 and palabras_html < 60
    if plantilla_vacia:
        marcadores.append(f"plantilla sin renderizar ({placeholders} placeholders {{{{…}}}} visibles)")
    raiz_vacia = bool(re.search(r'<div[^>]+id=["\'](root|app|__next|__nuxt)["\'][^>]*>\s*</div>', html, re.I))
    ratio = round(len(doc.texto(excluir_boilerplate=False)) / max(len(html), 1), 3)
    noscript = doc.texto_noscript()
    if render and render.get("disponible"):
        palabras_render = render.get("palabras_principal", 0)
        delta = palabras_render - palabras_html
        # confirmada: el HTML inicial está casi vacío y el render trae contenido; parcial: el render añade al menos 50 palabras y más que duplica lo servido
        veredicto = "dependencia_confirmada" if palabras_html < 50 and palabras_render >= 150 else "parcial" if (delta >= 50 and delta > palabras_html) else "sin_dependencia"
        observacion = "Confirmado"
    else:
        palabras_render = None
        delta = None
        if (palabras_total < 40 or plantilla_vacia or (palabras_html < 40 and (marcadores or raiz_vacia))) and (marcadores or raiz_vacia or "javascript" in noscript.lower()):
            veredicto = "probable_dependencia"
            observacion = "Probable"
        elif palabras_html >= 150:
            veredicto = "sin_dependencia"
            observacion = "Confirmado"
        else:
            veredicto = "indeterminado"
            observacion = "Hipótesis"
    res["dependencia_js"] = {
        "palabras_principal_sin_js": palabras_html,
        "palabras_total_sin_js": palabras_total,
        "palabras_principal_con_js": palabras_render,
        "delta_palabras": delta,
        "marcadores_framework": marcadores,
        "contenedor_raiz_vacio": raiz_vacia,
        "placeholders_plantilla": placeholders,
        "placeholders_principal": placeholders_principal,
        "ratio_texto_html": ratio,
        "noscript": noscript[:200],
        "veredicto": veredicto,
        "observacion": observacion,
        "render_disponible": bool(render and render.get("disponible")),
    }
    return res


def _parsear_lastmod(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


AVISO_SITEMAP_NO_DECLARADO = (
    "El sitemap existe en {url} pero robots.txt no lo declara con la directiva `Sitemap:`. "
    "La regla T-11 se cumple por la vía alterna, pero los crawlers que solo leen robots.txt no lo descubren; añade `Sitemap: {url}` a robots.txt."
)


def analizar_sitemap(recoleccion: dict[str, Any] | None, *, ahora: datetime | None = None, declarado_en_robots: bool | None = None) -> dict[str, Any]:
    ahora = ahora or datetime.now(timezone.utc)
    if not recoleccion:
        return {"presente": False, "declarado_en_robots": declarado_en_robots}
    fechas = [d for d in (_parsear_lastmod(u.get("lastmod")) for u in recoleccion.get("urls", [])) if d]
    mas_reciente = max(fechas) if fechas else None
    futuras = sum(1 for d in fechas if d > ahora)
    return {
        "presente": recoleccion.get("urls_total", 0) > 0,
        "url": recoleccion.get("sitemap"),
        "urls_total": recoleccion.get("urls_total", 0),
        "con_lastmod": recoleccion.get("con_lastmod", 0),
        "sin_lastmod": recoleccion.get("sin_lastmod", 0),
        "lastmod_mas_reciente": mas_reciente.isoformat() if mas_reciente else None,
        "dias_desde_lastmod": (ahora - mas_reciente).days if mas_reciente else None,
        "lastmod_futuras": futuras,
        "errores": recoleccion.get("errores", []),
        "sitemaps_leidos": recoleccion.get("sitemaps_leidos", 0),
        "declarado_en_robots": declarado_en_robots,
    }


def avisos_sitio(robots_res: dict[str, Any] | None, sitemap_res: dict[str, Any] | None) -> list[str]:
    """Avisos de sitio que no son fallas de regla: hoy, sitemap existente pero no declarado en robots.txt."""
    avisos: list[str] = []
    m = sitemap_res or {}
    declarado = m.get("declarado_en_robots")
    if declarado is None:
        declarado = bool((robots_res or {}).get("sitemaps"))
    if m.get("presente") and not declarado:
        avisos.append(AVISO_SITEMAP_NO_DECLARADO.format(url=m.get("url") or "/sitemap.xml"))
    return avisos
