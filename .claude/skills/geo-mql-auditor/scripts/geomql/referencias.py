"""Extractos de las referencias del skill para embeber en los archivos de vector.

Los subagentes no leen `referencias/` ni el rulebook: cada regla del archivo de vector
lleva sus fuentes con URL y, cuando la fuente tiene bitácora o lectura corregida, el
extracto pertinente. Así el consumo de tokens no depende de que el modelo obedezca un
límite de lectura.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from . import RAIZ_SKILL

RUTA_REFERENCIAS = RAIZ_SKILL / "referencias"
_PRINCETON_SECCIONES = ("Qué evaluó", "El 115.1% y lo que no dice", "Lo que NO está en el paper", "Limitaciones que el propio paper reconoce", "Cómo lo usa este skill")
_BOTS_SECCIONES = ("Categorías", "Controles que no son robots.txt")
_PRINCETON_MARCAS = ("2311.09735", "Aggarwal", "Princeton", "KDD 2024")
_BOTS_MARCAS = ("/bots", "crawlers", "web-crawlers", "robots", "119829", "8896518", "amazonbot", "ccbot", "DuckAssist", "mistral.ai/robots", "ai-features", "bingbot", "september-2023")


@lru_cache(maxsize=None)
def _leer(nombre: str) -> str:
    ruta = RUTA_REFERENCIAS / nombre
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def seccion(md: str, titulo: str) -> str:
    """Texto bajo un encabezado `## titulo` hasta el siguiente `##`."""
    m = re.search(r"^##\s+" + re.escape(titulo) + r"\s*$(.*?)(?=^##\s|\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


def _norm_url(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip()).rstrip("/").lower()


def _filas_tablas(md: str) -> list[list[str]]:
    filas = []
    for linea in md.splitlines():
        if linea.startswith("|") and not re.match(r"^\|\s*-{3,}", linea):
            celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
            filas.append(celdas)
    return filas


@lru_cache(maxsize=None)
def _bitacora() -> list[dict[str, str]]:
    """Filas de fuentes-verificadas.md como {fuente, url, dice, no_dice}."""
    out = []
    for celdas in _filas_tablas(_leer("fuentes-verificadas.md")):
        if len(celdas) < 3 or celdas[0] in ("Fuente",):
            continue
        fuente, url = celdas[0], celdas[1]
        if len(celdas) >= 4 and celdas[3] and not re.match(r"^[ABC]\s*·", celdas[3]):
            dice, no_dice = celdas[2], celdas[3]
        else:
            dice, no_dice = celdas[2], ""
        out.append({"fuente": fuente, "url": url, "dice": dice, "no_dice": no_dice})
    return out


def bitacora_de(url: str) -> dict[str, str] | None:
    n = _norm_url(url)
    if not n:
        return None
    for fila in _bitacora():
        fu = _norm_url(fila["url"].split(" ")[0])
        if fu and (fu in n or n in fu):
            return fila
    return None


def extractos_para(regla: dict[str, Any]) -> list[dict[str, str]]:
    """Extractos de referencia pertinentes a una regla: bitácora por fuente, Princeton y bots."""
    out: list[dict[str, str]] = []
    fuentes = regla.get("fuentes") or []
    texto_fuentes = " ".join(f"{f.get('titulo', '')} {f.get('url', '')}" for f in fuentes)
    for f in fuentes:
        fila = bitacora_de(f.get("url", ""))
        if fila:
            texto = f"Qué dice: {fila['dice']}."
            if fila["no_dice"]:
                texto += f" Qué NO dice: {fila['no_dice']}."
            out.append({"titulo": f"Bitácora de verificación (2026-09-10): {fila['fuente']}", "texto": texto})
    if any(m in texto_fuentes for m in _PRINCETON_MARCAS):
        md = _leer("princeton-kdd-2024.md")
        partes = [f"{t}: {seccion(md, t)}" for t in _PRINCETON_SECCIONES if seccion(md, t)]
        if partes:
            out.append({"titulo": "Lectura corregida del paper de Princeton (Aggarwal et al., KDD 2024), motor simulado", "texto": "\n".join(partes)})
    if regla.get("categoria") == "tecnico" and any(m.lower() in texto_fuentes.lower() for m in _BOTS_MARCAS):
        md = _leer("bots-ia.md")
        partes = [f"{t}: {seccion(md, t)}" for t in _BOTS_SECCIONES if seccion(md, t)]
        if partes:
            out.append({"titulo": "Categorías de bots de IA y controles que no son robots.txt (verificado 2026-09-10)", "texto": "\n".join(partes)})
    return out


def guia() -> dict[str, str]:
    """Etiquetas y prioridad, para que el subagente no busque etiquetas-confianza.md."""
    md = _leer("etiquetas-confianza.md")
    return {
        "etiquetas": seccion(md, "Etiqueta 1: evidencia de la observación") + "\n\n" + seccion(md, "Etiqueta 2: fuerza de la regla con tipo de evidencia"),
        "prioridad": seccion(md, "Prioridad"),
        "principios": "Nunca impacto proyectado numérico. Un aviso o una regla con resultado 'pasa' no es un hallazgo. Las Hipótesis requieren revisión humana y no entran en el puntaje.",
    }
