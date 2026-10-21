"""Citas textuales atribuidas y enlaces a fuentes externas.

Derivado de scripts/quote_extractor.py y scripts/citation_check.py de
best-aeo-skill (MIT, ver NOTICE). Correcciones: exige atribución (nombre y
verbo de habla o guion), trabaja solo sobre el contenido principal y separa
enlaces del contenido de los de navegación.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .html import Documento, texto_de

_COMILLAS_RE = re.compile(r"[“\"«]([^”\"»]{40,600})[”\"»]")
_ATRIBUCION_RE = re.compile(
    r"(?:—|–|-)\s*(?P<nombre>[A-ZÁÉÍÓÚ][\wáéíóúñü'’\-]+(?:\s+[A-ZÁÉÍÓÚ][\wáéíóúñü'’\-]+){1,3})"
    r"|(?:\b(?:afirma|afirmó|dice|dijo|señala|señaló|explica|explicó|comenta|comentó|asegura|aseguró|apunta|apuntó|sostiene|sostuvo|según|indica|indicó|advierte|advirtió|said|says|according to|notes|explains|argues)\s+(?P<nombre2>[A-ZÁÉÍÓÚ][\wáéíóúñü'’\-]+(?:\s+[A-ZÁÉÍÓÚ][\wáéíóúñü'’\-]+){1,3}))"
    r"|(?:(?P<nombre3>[A-ZÁÉÍÓÚ][\wáéíóúñü'’\-]+(?:\s+[A-ZÁÉÍÓÚ][\wáéíóúñü'’\-]+){1,3})\s*,\s*(?P<cargo>(?:directora?|gerente|CEO|CTO|CFO|CMO|fundadora?|presidenta?|responsable|jefa?|líder|especialista|consultora?|analista|profesora?|investigadora?|head|director|manager|founder)[^,.;]{0,80}))",
)
_CARGO_RE = re.compile(r"\b(directora?|gerente|CEO|CTO|CFO|CMO|COO|fundadora?|cofundadora?|presidenta?|responsable|jefa?|líder|especialista|consultora?|analista|profesora?|investigadora?|head of|director|manager|founder|vp|vicepresidente)\b", re.I)


def _clave(texto: str) -> str:
    return re.sub(r"[“”\"«»\s]+", " ", texto).strip().lower()[:80]


def _atribucion(contexto: str) -> dict[str, Any]:
    m = _ATRIBUCION_RE.search(contexto)
    if not m:
        return {"atribuida": False, "nombre": None, "cargo": None}
    nombre = m.group("nombre") or m.group("nombre2") or m.group("nombre3")
    cargo_m = _CARGO_RE.search(contexto)
    return {"atribuida": True, "nombre": nombre, "cargo": (m.groupdict().get("cargo") or (cargo_m.group(0) if cargo_m else None))}


def analizar(doc: Documento, *, host: str = "") -> dict[str, Any]:
    principal = doc.principal
    citas: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for bq in principal.buscar({"blockquote", "q"}):
        if bq.es_boilerplate():
            continue
        texto = texto_de(bq, con_saltos=False)
        if len(texto.split()) < 8:
            continue
        contexto = texto
        padre = bq.padre
        if padre is not None:
            contexto = texto_de(padre, con_saltos=False)
        cita = {"texto": texto[:300], "origen": bq.etiqueta, **_atribucion(contexto)}
        citas.append(cita)
        vistos.add(_clave(texto))
    texto_principal = doc.texto_principal()
    for m in _COMILLAS_RE.finditer(texto_principal):
        frase = m.group(1).strip()
        if len(frase.split()) < 8 or _clave(frase) in vistos:
            continue
        inicio = max(0, m.start() - 200)
        contexto = texto_principal[inicio:m.end() + 220]
        citas.append({"texto": frase[:300], "origen": "comillas", **_atribucion(contexto)})
        vistos.add(_clave(frase))

    host = host.lower()
    enlaces = doc.enlaces()
    externos_principal, internos_principal, externos_todos = [], 0, 0
    dominios: dict[str, int] = {}
    nofollow = 0
    for e in enlaces:
        href = e["href"]
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        dom = urlparse(href).netloc.lower()
        es_externo = bool(dom) and (not host or (dom != host and not dom.endswith("." + host)))
        if es_externo:
            externos_todos += 1
        if not e["en_principal"] or e["boilerplate"]:
            continue
        if es_externo:
            externos_principal.append({"href": href, "texto": e["texto"][:100], "rel": e["rel"]})
            dominios[dom] = dominios.get(dom, 0) + 1
            if "nofollow" in e["rel"]:
                nofollow += 1
        else:
            internos_principal += 1
    return {
        "citas": citas[:20],
        "total": len(citas),
        "atribuidas": sum(1 for c in citas if c["atribuida"]),
        "sin_atribucion": sum(1 for c in citas if not c["atribuida"]),
        "enlaces": {
            "externos_principal": len(externos_principal),
            "internos_principal": internos_principal,
            "externos_total": externos_todos,
            "dominios_externos": dominios,
            "nofollow": nofollow,
            "muestras": externos_principal[:10],
        },
    }
