"""Lecturas transversales de un audit sobre varias URL: hallazgos sistémicos vs puntuales,
tipos de página detectados, peticiones por área responsable y comparación con una corrida anterior."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .hallazgos import Hallazgo

UMBRAL_SISTEMICO = 3
AREAS = {
    "contenido": "Contenido",
    "desarrollo": "Desarrollo (o quien controle el CMS)",
    "analitica": "Analítica",
    "direccion": "Dirección, marketing y terceros",
}
_DEP_AREA = {"contenido": "contenido", "desarrollo": "desarrollo", "cms": "desarrollo", "": "desarrollo", "ninguna": "desarrollo", "propio": "desarrollo", "analitica": "analitica", "crm": "analitica", "terceros": "direccion", "direccion": "direccion", "legal": "direccion", "legal o dirección": "direccion", "dirección": "direccion"}
_HORIZONTE = {"30d": "30 días", "90d": "90 días", "largo": "largo plazo"}


def _h(h: Hallazgo | dict[str, Any]) -> dict[str, Any]:
    return h.a_dict() if isinstance(h, Hallazgo) else h


def agrupar_hallazgos(hallazgos: list[Any], n_urls_medidas: int, *, umbral: int = UMBRAL_SISTEMICO) -> dict[str, Any]:
    """Sistémico: la misma regla falla en `umbral` o más URL (se corrige una vez en la plantilla). Puntual: 1 o 2 URL."""
    sistemicos, puntuales = [], []
    for h in map(_h, hallazgos):
        urls = list(dict.fromkeys(h.get("urls_afectadas") or ([h.get("url")] if h.get("url") else [])))
        entrada = {"id": h["id"], "regla_id": h["regla_id"], "titulo": h["titulo"], "evidencia_observacion": h["evidencia_observacion"], "fuerza_regla": h["fuerza_regla"], "n_urls": len(urls), "n_urls_medidas": n_urls_medidas, "urls": urls, "horizonte": h.get("horizonte", "")}
        (sistemicos if len(urls) >= umbral else puntuales).append(entrada)
    sistemicos.sort(key=lambda x: (-x["n_urls"], x["regla_id"]))
    puntuales.sort(key=lambda x: (-x["n_urls"], x["regla_id"]))
    return {"umbral_sistemico": umbral, "n_urls_medidas": n_urls_medidas, "sistemicos": sistemicos, "puntuales": puntuales}


def tipos_detectados(registros: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in registros:
        t = r.get("tipo") or "otra"
        out.setdefault(t, {"n": 0, "urls": []})
        out[t]["n"] += 1
        out[t]["urls"].append(r.get("url", ""))
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["n"], kv[0])))


def _primera_oracion(texto: str) -> str:
    t = (texto or "").strip().splitlines()[0] if (texto or "").strip() else ""
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    return (m.group(1) if m else t).strip()


def por_area(hallazgos: list[Any], n_urls_medidas: int) -> dict[str, list[dict[str, Any]]]:
    """Cada hallazgo va a exactamente un área según su dependencia; la petición es la primera oración de la recomendación."""
    out: dict[str, list[dict[str, Any]]] = {a: [] for a in AREAS}
    for h in map(_h, hallazgos):
        area = _DEP_AREA.get((h.get("dependencia") or "").strip().lower(), "direccion")
        urls = list(dict.fromkeys(h.get("urls_afectadas") or []))
        out[area].append({
            "id": h["id"],
            "regla_id": h["regla_id"],
            "titulo": h["titulo"],
            "peticion": _primera_oracion(h.get("recomendacion", "")) or h["titulo"],
            "evidencia": f"regla {h['regla_id']} · {h['evidencia_observacion']}, {h['fuerza_regla']} · {len(urls)} de {n_urls_medidas} URL" + (" (revisión humana)" if h["evidencia_observacion"] == "Hipótesis" else ""),
            "horizonte": _HORIZONTE.get(h.get("horizonte", ""), h.get("horizonte", "")),
            "urls": urls,
        })
    return out


def comparar_con(hallazgos: list[Any], ruta_base: Path | str, *, umbral: int = UMBRAL_SISTEMICO) -> dict[str, Any]:
    """Compara las reglas con hallazgo en esta corrida contra una corrida anterior (JSON del reporte)."""
    base = json.loads(Path(ruta_base).read_text(encoding="utf-8"))
    reglas_base = {h["regla_id"]: h for h in base.get("hallazgos", [])}
    actual: dict[str, int] = {}
    for h in map(_h, hallazgos):
        actual[h["regla_id"]] = max(actual.get(h["regla_id"], 0), len(h.get("urls_afectadas") or []))
    return {
        "base": {"archivo": str(ruta_base), "fecha": base.get("meta", {}).get("fecha", ""), "n_urls": base.get("meta", {}).get("n_urls", 0), "corrida": base.get("meta", {}).get("corrida", "")},
        "patron_del_sitio": sorted(r for r in reglas_base if actual.get(r, 0) >= umbral),
        "puntual_incluye_portada": sorted(r for r in reglas_base if 0 < actual.get(r, 0) < umbral),
        "exclusivo_de_la_portada": sorted(r for r in reglas_base if r not in actual),
        "nuevas_fuera_de_la_portada": sorted(r for r in actual if r not in reglas_base),
        "titulos": {r: (reglas_base.get(r) or {}).get("titulo", "") for r in reglas_base} | {r: next((_h(h)["titulo"] for h in hallazgos if _h(h)["regla_id"] == r), "") for r in actual},
        "n_urls_actual": actual,
    }


def markdown_extras(grupos: dict[str, Any] | None, tipos: dict[str, Any] | None, areas: dict[str, Any] | None, comparacion: dict[str, Any] | None) -> str:
    lineas: list[str] = []
    if tipos:
        lineas += ["## Tipos de página detectados", "", "| Tipo | URL | Ejemplos |", "|---|---|---|"]
        lineas += [f"| {t} | {v['n']} | {', '.join(v['urls'][:3])}{' …' if v['n'] > 3 else ''} |" for t, v in tipos.items()]
        lineas.append("")
    if grupos:
        n = grupos["n_urls_medidas"]
        lineas += [f"## Hallazgos sistémicos (la misma regla falla en {grupos['umbral_sistemico']} o más URL)", "", "Se corrigen una vez en la plantilla o en la configuración del sitio.", ""]
        if grupos["sistemicos"]:
            for h in grupos["sistemicos"]:
                lineas.append(f"- [{h['regla_id']}] {h['titulo']} · **{h['n_urls']} de {n} URL medidas** · {h['evidencia_observacion']}, {h['fuerza_regla']}")
                lineas.extend(f"  - {u}" for u in h["urls"])
        else:
            lineas.append("_Ninguno._")
        lineas += ["", "## Hallazgos puntuales (1 o 2 URL)", "", "Se corrigen página por página.", ""]
        lineas += [f"- [{h['regla_id']}] {h['titulo']} · {h['n_urls']} de {n} URL · {h['evidencia_observacion']}, {h['fuerza_regla']} · " + ", ".join(h["urls"]) for h in grupos["puntuales"]] or ["_Ninguno._"]
        lineas.append("")
    if comparacion:
        b = comparacion["base"]
        t = comparacion["titulos"]
        lineas += [f"## Comparación con la corrida anterior ({b['fecha']}, {b['n_urls']} URL)", ""]
        for clave, titulo, nota in (
            ("patron_del_sitio", "Patrón del sitio", "fallaba en la portada y falla en 3 o más URL de la muestra"),
            ("puntual_incluye_portada", "Puntual, incluye la portada", "fallaba en la portada y en la muestra aparece en 1 o 2 URL"),
            ("exclusivo_de_la_portada", "Exclusivo de la portada", "fallaba en la portada y no aparece en el resto de la muestra"),
            ("nuevas_fuera_de_la_portada", "Nuevos fuera de la portada", "no fallaba en la portada; aparece en otras páginas"),
        ):
            lineas += [f"### {titulo}", "", f"_{nota}._", ""]
            lineas += [f"- {r}: {t.get(r, '')}" + (f" ({comparacion['n_urls_actual'][r]} URL)" if r in comparacion["n_urls_actual"] else "") for r in comparacion[clave]] or ["_Ninguno._"]
            lineas.append("")
    if areas:
        lineas += ["## Qué pedirle a cada área", "", "Una petición por línea, con la evidencia que la sustenta y el horizonte. Las Hipótesis requieren revisión humana antes de pedirlas.", ""]
        for clave, nombre in AREAS.items():
            items = areas.get(clave) or []
            lineas += [f"### {nombre}", ""]
            lineas += [f"- {p['peticion']} Evidencia: {p['evidencia']}. Horizonte: {p['horizonte']}." for p in items] or ["_Sin peticiones._"]
            lineas.append("")
    return "\n".join(lineas)


DEPENDENCIAS_DE_NEGOCIO = ("terceros", "direccion", "dirección", "legal", "legal o dirección", "crm")
REGLAS_COMPARACION_FIJAS = [("JSON-LD", "Sin datos estructurados (JSON-LD) en la página"), ("T-09", None), ("X-02", None), ("T-12", None), ("S-05", None), ("T-14", None), ("T-10", None)]


def separar_no_evaluables(hallazgos: list[Any]) -> tuple[list[Any], list[Any]]:
    """Sin contexto de negocio, los hallazgos que dependen de terceros, dirección o CRM no se evalúan con supuestos."""
    evaluables, no_evaluables = [], []
    for h in hallazgos:
        dep = (_h(h).get("dependencia") or "").strip().lower()
        (no_evaluables if dep in DEPENDENCIAS_DE_NEGOCIO else evaluables).append(h)
    return evaluables, no_evaluables


def _conteos(resultados: list[dict[str, Any]], urls: list[dict[str, Any]], reglas: dict[str, Any]) -> tuple[dict[str, int], dict[str, str], int]:
    medidas = [u for u in urls if u.get("status") == 200]
    n = len(medidas)
    fallas: dict[str, int] = {}
    titulos: dict[str, str] = {}
    for r in resultados:
        if r.get("estado") == "falla":
            fallas[r["regla_id"]] = fallas.get(r["regla_id"], 0) + 1
    fallas["JSON-LD"] = sum(1 for u in medidas if not u.get("schema_tipos"))
    for rid in fallas:
        regla = reglas.get(rid)
        titulos[rid] = (regla.get("titulo_hallazgo") or regla.get("enunciado")) if regla else ""
    return fallas, titulos, n


def comparar_reglas(*, resultados: list[dict[str, Any]], urls: list[dict[str, Any]], dominio: str, ruta_base: Path | str, reglas: dict[str, Any], umbral: int = UMBRAL_SISTEMICO) -> dict[str, Any]:
    """Tabla regla por regla contra otra corrida: fallas de N URL medidas en cada dominio y veredicto compartido/exclusivo."""
    base = json.loads(Path(ruta_base).read_text(encoding="utf-8"))
    fb, tb, nb = _conteos(base.get("resultados", []), base.get("urls", []), reglas)
    fa, ta, na = _conteos(resultados, urls, reglas)
    candidatas = [r for r, _ in REGLAS_COMPARACION_FIJAS] + sorted(r for r in set(fb) | set(fa) if r not in dict(REGLAS_COMPARACION_FIJAS) and max(fb.get(r, 0), fa.get(r, 0)) >= umbral)

    def presente(f: int, n: int) -> bool:
        return f >= umbral or (n > 0 and f / n >= 0.5)

    filas = []
    for rid in candidatas:
        titulo = dict(REGLAS_COMPARACION_FIJAS).get(rid) or tb.get(rid) or ta.get(rid) or (reglas.get(rid, {}).get("titulo_hallazgo") if rid in reglas else "") or (reglas.get(rid, {}).get("enunciado") if rid in reglas else "") or rid
        b, a = fb.get(rid, 0), fa.get(rid, 0)
        pb, pa = presente(b, nb), presente(a, na)
        veredicto = "compartido" if (pb and pa) else "exclusivo_base" if pb else "exclusivo_actual" if pa else "en_ninguno"
        filas.append({"regla_id": rid, "titulo": titulo, "base_fallas": b, "base_n": nb, "actual_fallas": a, "actual_n": na, "veredicto": veredicto})
    return {
        "base": {"archivo": str(ruta_base), "dominio": base.get("meta", {}).get("dominio", ""), "fecha": base.get("meta", {}).get("fecha", ""), "n_urls": nb},
        "actual": {"dominio": dominio, "n_urls": na},
        "criterio": f"Un patrón está presente en un dominio si la regla falla en {umbral} o más URL, o en la mitad o más de las URL medidas.",
        "filas": filas,
        "compartidos": [f["regla_id"] for f in filas if f["veredicto"] == "compartido"],
        "exclusivos_base": [f["regla_id"] for f in filas if f["veredicto"] == "exclusivo_base"],
        "exclusivos_actual": [f["regla_id"] for f in filas if f["veredicto"] == "exclusivo_actual"],
        "en_ninguno": [f["regla_id"] for f in filas if f["veredicto"] == "en_ninguno"],
    }


def markdown_comparacion_reglas(c: dict[str, Any]) -> str:
    b, a = c["base"], c["actual"]
    lineas = [f"## Comparación regla por regla: {b['dominio']} ({b['fecha']}, {b['n_urls']} URL) frente a {a['dominio']} ({a['n_urls']} URL)", "", c["criterio"], "", f"| Regla | Patrón | {b['dominio']} | {a['dominio']} | Veredicto |", "|---|---|---|---|---|"]
    nombres = {"compartido": "compartido", "exclusivo_base": f"exclusivo de {b['dominio']}", "exclusivo_actual": f"exclusivo de {a['dominio']}", "en_ninguno": "en ninguno"}
    for f in c["filas"]:
        lineas.append(f"| {f['regla_id']} | {f['titulo']} | {f['base_fallas']} de {f['base_n']} | {f['actual_fallas']} de {f['actual_n']} | {nombres[f['veredicto']]} |")
    lineas += ["", "### Patrones compartidos por ambos dominios", ""] + ([f"- {r}" for r in c["compartidos"]] or ["_Ninguno._"])
    lineas += ["", f"### Exclusivos de {b['dominio']}", ""] + ([f"- {r}" for r in c["exclusivos_base"]] or ["_Ninguno._"])
    lineas += ["", f"### Exclusivos de {a['dominio']}", ""] + ([f"- {r}" for r in c["exclusivos_actual"]] or ["_Ninguno._"])
    lineas.append("")
    return "\n".join(lineas)


def markdown_no_evaluables(hallazgos: list[Any]) -> str:
    lineas = ["## No evaluables sin contexto de negocio", "", "Los hallazgos que dependen de dirección, terceros o CRM (presencia externa de la marca, decisiones de política, campos del CRM) no se evalúan con supuestos en una auditoría técnica sin contexto; se listan aquí en vez de en los hallazgos priorizados.", ""]
    lineas += [f"- [{_h(h)['regla_id']}] {_h(h)['titulo']} · {_h(h)['evidencia_observacion']}, {_h(h)['fuerza_regla']} · {len(_h(h).get('urls_afectadas') or [])} URL · no evaluable en esta corrida" for h in hallazgos] or ["_Ninguno en esta corrida._"]
    lineas.append("")
    return "\n".join(lineas)


def render_por_url(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Por URL: palabras de contenido principal sin y con JavaScript, veredicto, placeholders y tipos JSON-LD."""
    out = []
    for r in registros:
        out.append({
            "url": r.get("url", ""),
            "tipo": r.get("tipo", ""),
            "status": r.get("status"),
            "palabras_sin_js": r.get("palabras_sin_js"),
            "palabras_con_js": r.get("palabras_con_js"),
            "veredicto": r.get("dependencia_js", ""),
            "placeholders": r.get("placeholders", 0) or 0,
            "placeholders_principal": r.get("placeholders_principal", 0) or 0,
            "renderizado": bool(r.get("renderizado")),
            "jsonld_tipos": list(r.get("schema_tipos") or []),
        })
    return out


def por_tipo(resultados: list[dict[str, Any]], registros: list[dict[str, Any]], reglas: dict[str, Any]) -> dict[str, Any]:
    """Qué falla en todas las URL de un tipo y qué falla solo en algunas: base para estimar esfuerzo por plantilla."""
    tipo_de = {r.get("url"): r.get("tipo") or "otra" for r in registros if r.get("status") == 200}
    urls_por_tipo: dict[str, list[str]] = {}
    for u, t in tipo_de.items():
        urls_por_tipo.setdefault(t, []).append(u)
    fallas: dict[str, dict[str, set[str]]] = {}
    for r in resultados:
        if r.get("estado") != "falla" or r.get("url") not in tipo_de:
            continue
        t = tipo_de[r["url"]]
        fallas.setdefault(t, {}).setdefault(r["regla_id"], set()).add(r["url"])
    out: dict[str, Any] = {}
    for t, urls in sorted(urls_por_tipo.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        en_todas, en_algunas = [], []
        for rid, us in sorted(fallas.get(t, {}).items(), key=lambda kv: (-len(kv[1]), kv[0])):
            regla = reglas.get(rid)
            entrada = {"regla_id": rid, "titulo": (regla.get("titulo_hallazgo") or regla.get("enunciado")) if regla else "", "n": len(us), "n_urls": len(urls), "urls": sorted(us)}
            (en_todas if len(us) == len(urls) else en_algunas).append(entrada)
        out[t] = {"n_urls": len(urls), "urls": urls, "en_todas": en_todas, "en_algunas": en_algunas}
    return out


def markdown_por_tipo(pt: dict[str, Any], render: list[dict[str, Any]]) -> str:
    lineas = ["## Render y datos estructurados por URL", "", "Palabras de contenido principal en el HTML inicial (sin JS) y tras ejecutar JavaScript (con JS). Placeholders: marcadores de plantilla `{{…}}` visibles en el HTML servido, en toda la página y solo en el contenido principal.", "", "| URL | Tipo | Sin JS | Con JS | Veredicto | Placeholders (página / principal) | JSON-LD |", "|---|---|---|---|---|---|---|"]
    for r in render:
        con = r["palabras_con_js"] if r["palabras_con_js"] is not None else "sin render"
        lineas.append(f"| {r['url']} | {r['tipo']} | {r['palabras_sin_js']} | {con} | {r['veredicto']} | {r['placeholders']} / {r.get('placeholders_principal', 0)} | {', '.join(r['jsonld_tipos']) or 'ninguno'} |")
    lineas += ["", "## Hallazgos por tipo de página", "", "Lo que falla en todas las URL de un tipo se corrige en su plantilla; lo que falla en algunas, página por página.", ""]
    for t, v in pt.items():
        lineas += [f"### {t} ({v['n_urls']} URL)", "", "Falla en todas:", ""]
        lineas += [f"- [{x['regla_id']}] {x['titulo']} · {x['n']} de {x['n_urls']}" for x in v["en_todas"]] or ["_Ninguna._"]
        lineas += ["", "Falla en algunas:", ""]
        lineas += [f"- [{x['regla_id']}] {x['titulo']} · {x['n']} de {x['n_urls']} · " + ", ".join(u.split('/es/')[-1] if '/es/' in u else u for u in x["urls"][:8]) + (" …" if len(x["urls"]) > 8 else "") for x in v["en_algunas"]] or ["_Ninguna._"]
        lineas.append("")
    return "\n".join(lineas)
