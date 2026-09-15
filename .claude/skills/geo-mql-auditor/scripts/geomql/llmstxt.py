"""Presencia y forma de /llms.txt (prioridad baja; ver regla N-04).

Derivado de scripts/llms_txt_check.py de best-aeo-skill (MIT, ver NOTICE).
"""
from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlparse

from . import fetch as fetch_mod

_ENLACE_RE = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)", re.M)


def analizar_texto(texto: str) -> dict[str, Any]:
    lineas = texto.splitlines()
    h1 = next((l.strip() for l in lineas if l.startswith("# ")), None)
    blockquote = any(l.lstrip().startswith("> ") for l in lineas)
    secciones = [l.strip()[3:] for l in lineas if l.startswith("## ")]
    enlaces = _ENLACE_RE.findall(texto)
    return {
        "h1": h1,
        "tiene_h1": bool(h1),
        "tiene_resumen": blockquote,
        "secciones": secciones,
        "tiene_optional": any(s.strip().lower() == "optional" for s in secciones),
        "enlaces": len(enlaces),
        "lineas": len(lineas),
        "conforme_spec": bool(h1),
    }


def verificar(url_sitio: str, *, descargar: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    descargar = descargar or fetch_mod.descargar
    p = urlparse(url_sitio)
    url = f"{p.scheme}://{p.netloc}/llms.txt" if p.scheme != "file" else url_sitio.rsplit("/", 1)[0] + "/llms.txt"
    r = descargar(url, max_bytes=512 * 1024)
    if r.get("status") != 200 or not r.get("html"):
        return {"presente": False, "url": url, "status": r.get("status")}
    if "<html" in r["html"][:500].lower():
        return {"presente": False, "url": url, "status": r.get("status"), "nota": "devuelve HTML, no texto"}
    return {"presente": True, "url": url, "status": 200, **analizar_texto(r["html"])}
