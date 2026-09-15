"""Fechas: dateModified/datePublished en JSON-LD, metas, etiquetas time y fecha visible etiquetada; coherencia entre fuentes y antigüedad.

Derivado de scripts/freshness_check.py de best-aeo-skill (MIT, ver NOTICE).
Correcciones: solo fechas de Article/WebPage (no de nodos anidados), soporte
de zona horaria con dos puntos y de fechas en español, comparación con la fecha
visible y reporte de incoherencias.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from .html import Documento

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}
_ES_RE = re.compile(r"\b(\d{1,2})\s+de\s+([a-záé]+)\s+(?:de\s+)?(\d{4})\b", re.I)
_EN_RE = re.compile(r"\b([a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", re.I)
_NUM_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_ETIQUETA_RE = re.compile(r"(actualizad[oa]|última actualización|ultima actualizacion|publicad[oa]|fecha de publicación|updated|last updated|published|modified)", re.I)


def parsear_fecha(valor: str | None) -> datetime | None:
    if not valor or not isinstance(valor, str):
        return None
    v = valor.strip()
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    m = _ISO_RE.search(v)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    m = _ES_RE.search(v)
    if m and m.group(2).lower() in MESES:
        try:
            return datetime(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)), tzinfo=timezone.utc)
        except ValueError:
            return None
    m = _EN_RE.search(v)
    if m and m.group(1).lower() in MESES:
        try:
            return datetime(int(m.group(3)), MESES[m.group(1).lower()], int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            return None
    m = _NUM_RE.search(v)
    if m:
        d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if mth > 12 and d <= 12:
            d, mth = mth, d
        try:
            return datetime(y, mth, d, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _mismo_dia(a: datetime | None, b: datetime | None) -> bool:
    return bool(a and b) and a.date() == b.date()


def fechas_visibles(doc: Documento) -> list[dict[str, Any]]:
    """Fechas en el texto principal con la etiqueta cercana (publicado, actualizado)."""
    texto = doc.texto_principal()
    out = []
    for rx in (_ES_RE, _ISO_RE, _NUM_RE, _EN_RE):
        for m in rx.finditer(texto):
            f = parsear_fecha(m.group(0))
            if not f:
                continue
            contexto = texto[max(0, m.start() - 40):m.start()]
            et = _ETIQUETA_RE.search(contexto)
            out.append({"texto": m.group(0), "fecha": f.date().isoformat(), "etiqueta": et.group(1).lower() if et else None, "posicion": m.start()})
    for t in doc.times():
        if t.get("en_principal") and t["datetime"]:
            f = parsear_fecha(t["datetime"])
            if f:
                out.append({"texto": t["texto"] or t["datetime"], "fecha": f.date().isoformat(), "etiqueta": "time", "posicion": -1})
    vistos = set()
    unicas = []
    for f in sorted(out, key=lambda x: x["posicion"]):
        clave = (f["fecha"], f["etiqueta"])
        if clave in vistos:
            continue
        vistos.add(clave)
        unicas.append(f)
    return unicas


def analizar(doc: Documento, schema_res: dict[str, Any] | None = None, *, ahora: datetime | None = None) -> dict[str, Any]:
    ahora = ahora or datetime.now(timezone.utc)
    schema_res = schema_res or {}
    fechas_schema = schema_res.get("fechas", {}) if schema_res else {}
    candidatas: list[tuple[str, datetime | None, str | None]] = [
        ("json-ld dateModified", parsear_fecha(fechas_schema.get("dateModified")), fechas_schema.get("dateModified")),
        ("meta article:modified_time", parsear_fecha(doc.meta("article:modified_time")), doc.meta("article:modified_time") or None),
        ("meta og:updated_time", parsear_fecha(doc.meta("og:updated_time")), doc.meta("og:updated_time") or None),
        ("json-ld datePublished", parsear_fecha(fechas_schema.get("datePublished")), fechas_schema.get("datePublished")),
        ("meta article:published_time", parsear_fecha(doc.meta("article:published_time")), doc.meta("article:published_time") or None),
    ]
    visibles = fechas_visibles(doc)
    visibles_etiquetadas = [v for v in visibles if v["etiqueta"]]
    visible_mod = next((v for v in visibles_etiquetadas if v["etiqueta"] and v["etiqueta"].startswith(("actualiz", "última", "ultima", "updated", "last", "modified"))), None)
    visible_pub = next((v for v in visibles_etiquetadas if v["etiqueta"] and v["etiqueta"].startswith(("public", "fecha de pub", "published"))), None)
    visible_time = [v for v in visibles if v["etiqueta"] == "time"]

    mejor_fuente, mejor, crudo = next(((f, d, c) for f, d, c in candidatas if d), (None, None, None))
    if not mejor and visible_mod:
        mejor_fuente, mejor, crudo = "fecha visible (actualizado)", parsear_fecha(visible_mod["fecha"]), visible_mod["texto"]
    if not mejor and visible_time:
        mejor_fuente, mejor, crudo = "etiqueta time", parsear_fecha(visible_time[-1]["fecha"]), visible_time[-1]["texto"]
    if not mejor and visible_pub:
        mejor_fuente, mejor, crudo = "fecha visible (publicado)", parsear_fecha(visible_pub["fecha"]), visible_pub["texto"]

    incoherencias: list[str] = []
    dm = parsear_fecha(fechas_schema.get("dateModified"))
    dp = parsear_fecha(fechas_schema.get("datePublished"))
    if dm and visible_mod and not _mismo_dia(dm, parsear_fecha(visible_mod["fecha"])):
        incoherencias.append(f"dateModified {dm.date()} difiere de la fecha visible de actualización {visible_mod['fecha']}")
    if dp and visible_pub and not _mismo_dia(dp, parsear_fecha(visible_pub["fecha"])):
        incoherencias.append(f"datePublished {dp.date()} difiere de la fecha visible de publicación {visible_pub['fecha']}")
    if dm and dp and dm < dp:
        incoherencias.append("dateModified es anterior a datePublished")
    if mejor and mejor > ahora:
        incoherencias.append("la fecha principal está en el futuro")
    meta_mod = parsear_fecha(doc.meta("article:modified_time"))
    if dm and meta_mod and not _mismo_dia(dm, meta_mod):
        incoherencias.append("dateModified difiere de article:modified_time")

    fecha_visible_res = {
        "presente": bool(visibles),
        "etiquetada": bool(visibles_etiquetadas) or bool(visible_time),
        "actualizacion": visible_mod,
        "publicacion": visible_pub,
        "en_time": visible_time[:3],
        "total_fechas_en_principal": len(visibles),
    }
    return {
        "fecha_principal": mejor.date().isoformat() if mejor else None,
        "fuente": mejor_fuente,
        "valor_crudo": crudo,
        "antiguedad_dias": (ahora - mejor).days if mejor else None,
        "dateModified": fechas_schema.get("dateModified"),
        "datePublished": fechas_schema.get("datePublished"),
        "fecha_visible": fecha_visible_res,
        "incoherencias": incoherencias,
        "coherente": not incoherencias,
    }
