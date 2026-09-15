"""robots.txt: descarga, parseo y evaluación con precedencia de RFC 9309 y Google.

Derivado de scripts/robots_check.py de best-aeo-skill (MIT, ver NOTICE).
Correcciones: grupos por user-agent más específico, regla de ruta más larga,
empate resuelto a favor de Allow, comodines * y $, estados 4xx/5xx según RFC.
"""
from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlparse

from . import fetch as fetch_mod

MAX_BYTES_ROBOTS = 512 * 1024


def parsear_robots(texto: str) -> dict[str, Any]:
    """Devuelve grupos [{agentes, reglas:[(directiva, patron)]}], sitemaps y avisos."""
    grupos: list[dict[str, Any]] = []
    sitemaps: list[str] = []
    avisos: list[str] = []
    actual: dict[str, Any] | None = None
    ultimo_fue_agente = False
    for cruda in texto.splitlines():
        linea = cruda.split("#", 1)[0].strip()
        if not linea:
            continue
        if ":" not in linea:
            avisos.append(f"línea sin ':' ignorada: {linea[:60]}")
            continue
        clave, _, valor = linea.partition(":")
        clave = clave.strip().lower()
        valor = valor.strip()
        if clave == "user-agent":
            if actual is None or not ultimo_fue_agente:
                actual = {"agentes": [], "reglas": []}
                grupos.append(actual)
            actual["agentes"].append(valor.lower())
            ultimo_fue_agente = True
            continue
        ultimo_fue_agente = False
        if clave in ("allow", "disallow"):
            if actual is None:
                avisos.append(f"regla {clave} antes de cualquier user-agent: ignorada")
                continue
            actual["reglas"].append((clave, valor))
        elif clave == "sitemap":
            sitemaps.append(valor)
        elif clave in ("crawl-delay", "host", "clean-param"):
            if actual is not None:
                actual.setdefault("extras", []).append((clave, valor))
        else:
            avisos.append(f"directiva desconocida: {clave}")
    return {"grupos": grupos, "sitemaps": sitemaps, "avisos": avisos}


def _patron_a_regex(patron: str) -> re.Pattern[str]:
    anclado = patron.endswith("$")
    if anclado:
        patron = patron[:-1]
    partes = [re.escape(p) for p in patron.split("*")]
    cuerpo = ".*".join(partes)
    return re.compile("^" + cuerpo + ("$" if anclado else ""))


def grupo_para(robots: dict[str, Any], agente: str) -> tuple[str | None, list[tuple[str, str]]]:
    """Reglas aplicables a un agente: el token más específico que sea prefijo del agente; si no, '*'."""
    agente_l = agente.lower()
    mejor_token: str | None = None
    reglas: list[tuple[str, str]] = []
    for g in robots.get("grupos", []):
        for token in g["agentes"]:
            if token == "*":
                continue
            if agente_l == token or agente_l.startswith(token):
                if mejor_token is None or len(token) > len(mejor_token):
                    mejor_token = token
    if mejor_token is not None:
        for g in robots.get("grupos", []):
            if mejor_token in g["agentes"]:
                reglas.extend(g["reglas"])
        return mejor_token, reglas
    for g in robots.get("grupos", []):
        if "*" in g["agentes"]:
            reglas.extend(g["reglas"])
    return ("*" if reglas or any("*" in g["agentes"] for g in robots.get("grupos", [])) else None), reglas


def permitido(robots: dict[str, Any], agente: str, ruta: str = "/") -> dict[str, Any]:
    """Aplica la regla más específica (más larga); en empate gana Allow (RFC 9309 §2.2.2)."""
    token, reglas = grupo_para(robots, agente)
    if token is None:
        return {"permitido": True, "regla": None, "grupo": None, "motivo": "sin grupo aplicable"}
    ruta = ruta or "/"
    mejor: tuple[int, int, tuple[str, str]] | None = None  # (longitud, prioridad_allow, regla)
    for directiva, patron in reglas:
        if patron == "":
            if directiva == "disallow":
                continue  # Disallow vacío = permitir todo
            candidato = (0, 1, (directiva, patron))
        else:
            if not _patron_a_regex(patron).match(ruta):
                continue
            candidato = (len(patron), 1 if directiva == "allow" else 0, (directiva, patron))
        if mejor is None or candidato[:2] > mejor[:2]:
            mejor = candidato
    if mejor is None:
        return {"permitido": True, "regla": None, "grupo": token, "motivo": "ninguna regla coincide"}
    directiva, patron = mejor[2]
    return {"permitido": directiva == "allow", "regla": f"{directiva.capitalize()}: {patron}", "grupo": token, "motivo": "regla más específica"}


def cargar_robots(url_sitio: str, *, descargar: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Descarga y parsea /robots.txt del host de ``url_sitio``.

    estado: ok | no_existe (4xx) | error_servidor (5xx, equivale a disallow total) | inaccesible.
    """
    descargar = descargar or fetch_mod.descargar
    p = urlparse(url_sitio)
    if p.scheme == "file":
        url_robots = url_sitio.rsplit("/", 1)[0] + "/robots.txt"
    else:
        url_robots = f"{p.scheme}://{p.netloc}/robots.txt"
    r = descargar(url_robots, max_bytes=MAX_BYTES_ROBOTS)
    status = r.get("status", 0)
    if status == 200:
        estado = "ok"
    elif 400 <= status < 500:
        estado = "no_existe"
    elif status >= 500:
        estado = "error_servidor"
    else:
        estado = "inaccesible"
    parsed = parsear_robots(r.get("html", "")) if estado == "ok" else {"grupos": [], "sitemaps": [], "avisos": []}
    return {
        "url": url_robots,
        "status": status,
        "estado": estado,
        "texto": r.get("html", "")[:20000],
        "parsed": parsed,
        "sitemaps": parsed["sitemaps"],
        "error": r.get("error"),
        "bytes": r.get("bytes", 0),
    }


def agentes_declarados(robots: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for g in robots.get("grupos", []):
        out.extend(g["agentes"])
    return out
