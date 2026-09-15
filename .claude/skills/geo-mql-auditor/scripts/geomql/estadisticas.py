"""Datos numéricos del contenido principal y si llevan fuente.

Derivado de scripts/statistic_density.py de best-aeo-skill (MIT, ver NOTICE).
Correcciones: solo contenido principal por bloque (p, li, td, blockquote);
excluye teléfonos, años sueltos, fechas, horas, direcciones, códigos postales,
paginación y versiones; detecta fuente enlazada o citada en el mismo bloque.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .html import Documento, Nodo, contar_palabras, oraciones, texto_de

_TEL_RE = re.compile(r"(?:\+?\d{1,3}[\s\-.]?)?\(?\d{2,3}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{4}\b")
_FECHA_RE = re.compile(
    r"\b\d{1,2}\s+de\s+[a-záé]+\s+(?:de\s+)?\d{4}\b|\b\d{4}-\d{2}-\d{2}(?:T[\d:.+\-Z]+)?\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december)\s+(?:de\s+)?\d{4}\b",
    re.I,
)
_HORA_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:h|hrs|am|pm)?\b", re.I)
_CP_RE = re.compile(r"\bC\.?\s?P\.?\s?\d{5}\b|\bcódigo postal\s*\d{5}\b|\bzip\s*\d{5}\b", re.I)
_DIRECCION_RE = re.compile(r"\b(?:av\.?|avenida|calle|blvd\.?|boulevard|carretera|km\.?|no\.?|núm\.?|#|int\.?|piso|suite|local)\s*\d+[\w\-]*", re.I)
_PAGINACION_RE = re.compile(r"\b(?:página|pagina|page|paso|step|capítulo|capitulo|figura|tabla|table)\s+\d+(?:\s+de\s+\d+)?\b", re.I)
_VERSION_RE = re.compile(r"\b(?:v(?:ersión|ersion)?\.?\s?)?\d+\.\d+(?:\.\d+)+\b|\b[A-Z]{2,}[\s\-]?\d+\.\d\b")
_ANIO_RE = re.compile(r"(?<![\d.,$%])\b(?:19|20)\d{2}\b(?![\d.,%])")
_LEGAL_RE = re.compile(r"\b(?:artículo|articulo|art\.|fracción|ley|norma|nom)\s*-?\s*\d+\b", re.I)

_ESTADISTICA_RE = re.compile(
    r"(?P<pct>\d+(?:[.,]\d+)?\s?%)"
    r"|(?P<moneda>(?:\$|USD|MXN|EUR|€|£)\s?\d[\d,.]*(?:\s?(?:mil|millones|millón|billones|k|m|mdp|mdd|mxn|usd))?)"
    r"|(?P<moneda2>\b\d[\d,.]*\s?(?:pesos|dólares|dolares|euros|mxn|usd)\b)"
    r"|(?P<mult>\b\d+(?:[.,]\d+)?\s?(?:x|×|veces)\b)"
    r"|(?P<magnitud>\b\d+(?:[.,]\d+)?\s?(?:mil|millones|millón|billones|miles|k|M)\b)"
    r"|(?P<unidad>\b\d[\d,.]*\s?(?:empleados|empresas|clientes|usuarios|personas|colaboradores|trabajadores|casos|encuestados|respuestas|participantes|meses|días|dias|semanas|años|anos|horas|minutos|segundos|km|kg|puntos|MB|GB|TB|estados|países|paises|ciudades|sucursales|recibos|transacciones|leads|visitas|sesiones|pp|puntos porcentuales))\b"
    r"|(?P<decimal>\b\d+[.,]\d+\b)"
    r"|(?P<miles>\b\d{1,3}(?:[,.]\d{3})+\b)",
    re.I,
)
_FUENTE_RE = re.compile(r"\b(según|de acuerdo con|de acuerdo a|conforme a|fuente:|fuentes:|reporta|reportó|informe|estudio|encuesta|datos de|cifras de|according to|source:|report|study|survey)\b", re.I)
_PROPIA_RE = re.compile(r"\b(estudio interno|encuesta interna|nuestros datos|datos propios|análisis interno|nuestro estudio|our data|internal study|internal survey|clientes de|caso publicado)\b", re.I)
_BLOQUES = {"p", "li", "td", "th", "blockquote", "dd", "figcaption", "summary"}


def _excluir(oracion: str) -> tuple[str, dict[str, int]]:
    """Elimina de la oración los patrones que no son estadísticas y cuenta cuántos había."""
    conteo: dict[str, int] = {}
    for nombre, rx in (("telefonos", _TEL_RE), ("fechas", _FECHA_RE), ("horas", _HORA_RE), ("codigos_postales", _CP_RE), ("direcciones", _DIRECCION_RE), ("paginacion", _PAGINACION_RE), ("versiones", _VERSION_RE), ("referencias_legales", _LEGAL_RE)):
        oracion, n = rx.subn(" ", oracion)
        if n:
            conteo[nombre] = conteo.get(nombre, 0) + n
    oracion, n = _ANIO_RE.subn(" ", oracion)
    if n:
        conteo["anios_sueltos"] = n
    return oracion, conteo


def _dominio(href: str) -> str:
    return urlparse(href).netloc.lower()


def analizar(doc: Documento, *, host: str = "") -> dict[str, Any]:
    principal = doc.principal
    host = host.lower()
    hallazgos: list[dict[str, Any]] = []
    excluidos: dict[str, int] = {}
    palabras = contar_palabras(doc.texto_principal())
    for nodo in principal.buscar(_BLOQUES):
        if nodo.es_boilerplate():
            continue
        if any(a.etiqueta in _BLOQUES and a is not nodo for a in nodo.ancestros() if a.etiqueta in ("li", "blockquote") and nodo.etiqueta == "p"):
            pass
        texto = texto_de(nodo, con_saltos=False)
        if not texto or len(texto.split()) < 4:
            continue
        enlaces = [a.atributo("href") for a in nodo.buscar("a") if a.atributo("href")]
        externos = [h for h in enlaces if _dominio(h) and _dominio(h) != host and not _dominio(h).endswith("." + host) if host] if host else [h for h in enlaces if _dominio(h)]
        for oracion in oraciones(texto):
            limpia, conteo = _excluir(oracion)
            for k, v in conteo.items():
                excluidos[k] = excluidos.get(k, 0) + v
            for m in _ESTADISTICA_RE.finditer(limpia):
                valor = m.group(0).strip()
                tipo = m.lastgroup or "otro"
                con_enlace = bool(externos)
                con_mencion = bool(_FUENTE_RE.search(oracion))
                propia = bool(_PROPIA_RE.search(oracion))
                hallazgos.append({
                    "valor": valor,
                    "tipo": tipo,
                    "oracion": oracion[:240],
                    "fuente_enlazada": con_enlace,
                    "fuente_mencionada": con_mencion,
                    "fuente_propia": propia,
                    "con_fuente": con_enlace or con_mencion or propia,
                    "enlaces": externos[:3],
                })
    con_fuente = [h for h in hallazgos if h["con_fuente"]]
    return {
        "total": len(hallazgos),
        "con_fuente": len(con_fuente),
        "sin_fuente": len(hallazgos) - len(con_fuente),
        "propias": sum(1 for h in hallazgos if h["fuente_propia"]),
        "densidad_por_100": round(len(hallazgos) / max(palabras, 1) * 100, 2),
        "palabras_principal": palabras,
        "muestras": hallazgos[:20],
        "sin_fuente_muestras": [h for h in hallazgos if not h["con_fuente"]][:10],
        "excluidos": excluidos,
    }
