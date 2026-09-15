"""Generación de reportes en Markdown y JSON a partir de resultados y hallazgos."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import RUTA_PLANTILLAS, RUTA_SALIDAS, VERSION
from .hallazgos import Hallazgo, ResultadoRegla, agrupar_por_horizonte
from .reglas import Regla

KPIS = [
    ("share_of_answers", "Share of answers", "% de respuestas del panel que mencionan la marca"),
    ("tasa_citacion", "Tasa de citación", "% de respuestas que citan una URL del dominio"),
    ("trafico_referido_ia", "Tráfico referido por IA", "sesiones del canal AI Assistant y del grupo personalizado (export GA4)"),
    ("conversiones_ia", "Conversiones desde IA", "generate_lead atribuidos a fuentes de IA (export GA4)"),
    ("tasa_mql_sql", "Tasa MQL a SQL", "por fuente de IA (export CRM)"),
    ("pipeline_influenciado", "Pipeline influenciado", "monto de oportunidades con toque de IA (export CRM)"),
]


def dominio_de(url: str) -> str:
    host = urlparse(url).netloc.lower() or "local"
    return host.removeprefix("www.") or "local"


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9.\-]", "_", (texto or "").lower())


def nombre_archivo(dominio: str, modulo: str, fecha: date | None = None) -> str:
    fecha = fecha or date.today()
    return f"{fecha.isoformat()}_{_slug(dominio)}_{modulo}"


def nombre_snapshot(dominio: str, modulo: str, corrida: str, fecha: date | None = None) -> str:
    """Nombre del snapshot de historial: fecha, dominio, módulo y la corrida completa (sin recortar), para que monitor pueda comparar corridas."""
    return f"{nombre_archivo(dominio, modulo, fecha)}_{_slug(corrida)}.json"


def _md_tabla(encabezados: list[str], filas: list[list[Any]]) -> str:
    if not filas:
        return "_Sin datos._"
    out = ["| " + " | ".join(encabezados) + " |", "|" + "|".join("---" for _ in encabezados) + "|"]
    for f in filas:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in f) + " |")
    return "\n".join(out)


def _hallazgo_md(h: Hallazgo, i: int) -> str:
    lineas = [f"### {i}. {h.titulo}", "", f"- Etiquetas: **{h.evidencia_observacion}** · **{h.fuerza_regla} · {_tipo_ev(h.tipo_evidencia)}** · regla {h.regla_id}",
              f"- Prioridad: impacto {h.impacto_esperado}, esfuerzo {h.esfuerzo}, depende de {h.dependencia or 'propio'}, horizonte {_horizonte(h.horizonte)}",
              f"- URL: {h.url}" + (f" (+{len(h.urls_afectadas) - 1} más)" if len(h.urls_afectadas) > 1 else ""),
              f"- Qué se observó: {_multilinea(h.detalle)}"]
    vistas: set[str] = set()
    for e in h.evidencia:
        url_ev = e.get("url") or h.url
        if url_ev in vistas:
            continue
        vistas.add(url_ev)
        if len(vistas) > 3:
            lineas.append(f"- Evidencia de {len(h.urls_afectadas) - 3} URL más en el JSON.")
            break
        extractos = e.get("extractos") or []
        extracto = e.get("extracto") or ""
        donde = f" ({url_ev})" if len(h.urls_afectadas) > 1 else ""
        lineas.append(f"- Evidencia{donde}: colector `{e.get('colector')}`" + ("" if extractos else (f" — {extracto}" if extracto else "")))
        for x in extractos[:8]:
            lineas.append(f"  - `{x['posicion']}`: {x['texto']}" if x.get("posicion") else f"  - {x['texto']}")
    lineas.append(f"- Recomendación: {_multilinea(h.recomendacion)}")
    if h.fuente.get("url"):
        lineas.append(f"- Fuente: [{h.fuente.get('titulo')}]({h.fuente['url']})")
    if h.evidencia_observacion == "Hipótesis":
        lineas.append("- Requiere revisión humana antes de actuar.")
    return "\n".join(lineas)


def _hallazgos_md(hallazgos: list[Hallazgo]) -> str:
    """Confirmados y Probables primero; las Hipótesis en su propio bloque al final."""
    if not hallazgos:
        return "_Sin hallazgos._"
    partes = []
    bloque_abierto = False
    for i, h in enumerate(hallazgos, 1):
        if h.evidencia_observacion == "Hipótesis" and not bloque_abierto:
            partes.append("**Requieren revisión humana antes de actuar**\n\n_Los siguientes hallazgos son juicio del modelo o de un subagente, no observación de un colector. No encabezan el reporte ni entran en el puntaje; un humano decide si proceden._")
            bloque_abierto = True
        partes.append(_hallazgo_md(h, i))
    return "\n\n".join(partes)


def _tipo_ev(t: str) -> str:
    return {"requisito_oficial": "requisito oficial", "efecto_experimental": "experimental", "correlacional": "correlacional", "consenso": "consenso"}.get(t, t)


def _horizonte(h: str) -> str:
    return {"30d": "30 días", "90d": "90 días", "largo": "largo plazo"}.get(h, h)


def _multilinea(texto: str, sangria: str = "  ") -> str:
    """Texto de varias líneas dentro de un ítem de lista Markdown: las líneas siguientes van indentadas."""
    lineas = [l.rstrip() for l in (texto or "").splitlines()] or [""]
    return lineas[0] + "".join(f"\n{sangria}{l}" for l in lineas[1:])


def _roadmap_md(hs: list[Hallazgo]) -> str:
    if not hs:
        return "_Nada pendiente en este horizonte._"
    return "\n".join(f"- [{h.regla_id}] {h.titulo} ({h.evidencia_observacion}, {h.fuerza_regla}) — {_multilinea(h.recomendacion)}" for h in hs)


def _sitio_md(sitio: dict[str, Any]) -> str:
    if not sitio:
        return "_Sin evidencia de sitio._"
    r = sitio.get("robots", {})
    b = sitio.get("bots", {}).get("resumen", {})
    m = sitio.get("sitemap", {})
    l = sitio.get("llmstxt", {})
    lineas = [
        f"- robots.txt: {r.get('estado', 'sin dato')} (HTTP {r.get('status')}) en {r.get('url')}",
        f"- Bots de búsqueda bloqueados: {', '.join(b.get('busqueda_bloqueados', [])) or 'ninguno'} de {b.get('busqueda_total', 0)}",
        f"- Fetchers por usuario bloqueados: {', '.join(b.get('usuario_bloqueados', [])) or 'ninguno'}",
        f"- Política de entrenamiento: {b.get('politica_entrenamiento', 'sin dato')} (bloqueados: {', '.join(b.get('entrenamiento_bloqueados', [])) or 'ninguno'}). Es decisión de política, no un problema de visibilidad.",
        f"- Google-Extended bloqueado: {'sí' if b.get('google_extended_bloqueado') else 'no'} (no afecta AI Overviews ni AI Mode)",
        f"- Sitemap: {'presente' if m.get('presente') else 'ausente'}; {m.get('urls_total', 0)} URL, {m.get('sin_lastmod', 0)} sin lastmod, último lastmod hace {m.get('dias_desde_lastmod', 'sin dato')} días",
        f"- llms.txt: {'presente' if l.get('presente') else 'ausente'} (prioridad baja; Google no lo usa y ningún proveedor confirma consumirlo)",
    ]
    avisos = sitio.get("avisos") or []
    lineas.append("- Avisos: " + ("ninguno" if not avisos else "") )
    lineas.extend(f"  - {a}" for a in avisos)
    return "\n".join(lineas)


def construir(
    *,
    modulo: str,
    dominio: str,
    urls: list[dict[str, Any]],
    hallazgos: list[Hallazgo],
    resultados: list[ResultadoRegla],
    reglas: dict[str, Regla],
    puntaje: dict[str, Any],
    sitio: dict[str, Any],
    contexto: dict[str, Any],
    metricas_visibilidad: dict[str, Any] | None = None,
    kpis: dict[str, Any] | None = None,
    supuestos: list[str] | None = None,
    metodo_extra: str = "",
    fecha: date | None = None,
    comparar: Path | str | None = None,
    anexo_tecnico: bool = False,
    comparar_reglas: Path | str | None = None,
) -> dict[str, Any]:
    from . import agrupacion

    fecha = fecha or date.today()
    no_evaluables: list[Hallazgo] = []
    if anexo_tecnico:
        hallazgos, no_evaluables = agrupacion.separar_no_evaluables(hallazgos)
    kpis = kpis or {}
    supuestos = list(supuestos or [])
    if anexo_tecnico:
        supuestos.insert(0, "Auditoría técnica comparativa sin contexto de negocio y sin medición de visibilidad: las recomendaciones de negocio, ICP y competidores no aplican a este dominio; los hallazgos que dependen de dirección, terceros o CRM se listan como no evaluables.")
    elif not contexto.get("valido"):
        faltan = contexto.get("faltantes_criticos", [])
        supuestos.insert(0, "Contexto de negocio incompleto; faltan campos críticos: " + ", ".join(faltan) + ". Las recomendaciones asumen un negocio B2B genérico hasta completarlos.")
    # Las Hipótesis (juicio del modelo) van después de Confirmado y Probable y nunca encabezan si hay un Confirmado.
    firmes = [h for h in hallazgos if h.evidencia_observacion != "Hipótesis"]
    hipotesis = [h for h in hallazgos if h.evidencia_observacion == "Hipótesis"]
    hallazgos = firmes + hipotesis
    hay_confirmado = any(h.evidencia_observacion == "Confirmado" for h in hallazgos)
    candidatos = firmes if hay_confirmado else firmes + hipotesis
    top3 = candidatos[:3]

    def _titulo_titular(h: Hallazgo) -> str:
        if h.evidencia_observacion == "Hipótesis":
            return f"{h.titulo} (Hipótesis, {h.fuerza_regla}, requiere revisión humana)"
        return f"{h.titulo} ({h.evidencia_observacion}, {h.fuerza_regla})"

    if metricas_visibilidad:
        titular = "**Visibilidad**: " + "; ".join(f"{k}: {v}" for k, v in metricas_visibilidad.items() if k in ("share_of_answers", "tasa_citacion", "share_of_voice"))
    elif top3:
        etiqueta = "Tres hallazgos prioritarios" if len(top3) == 3 else f"{len(top3)} hallazgo(s) prioritario(s)"
        titular = f"**{etiqueta}**: " + " · ".join(_titulo_titular(h) for h in top3)
    else:
        titular = "**Sin hallazgos con falla en las reglas verificables.**"
    conteo = {"falla": 0, "pasa": 0, "no_aplica": 0, "sin_evidencia": 0, "sin_colector": 0}
    for r in resultados:
        conteo[r.estado] = conteo.get(r.estado, 0) + 1
    resumen = (
        f"Se evaluaron {len(urls)} URL con {len(reglas)} reglas del rulebook. "
        f"{conteo['falla']} verificaciones fallaron, {conteo['pasa']} pasaron, {conteo['no_aplica']} no aplican, "
        f"{conteo['sin_evidencia']} quedaron sin evidencia y {conteo['sin_colector']} requieren juicio humano. "
        f"Los hallazgos se agrupan por regla: {len(hallazgos)} en total, "
        f"{sum(1 for h in hallazgos if h.evidencia_observacion == 'Confirmado')} confirmados, "
        f"{sum(1 for h in hallazgos if h.evidencia_observacion == 'Probable')} probables y "
        f"{sum(1 for h in hallazgos if h.evidencia_observacion == 'Hipótesis')} hipótesis."
    )
    roadmap = agrupar_por_horizonte(hallazgos)
    filas_reglas = []
    for r in resultados:
        regla = reglas.get(r.regla_id)
        filas_reglas.append([r.regla_id, regla.etiqueta_fuerza() if regla else "", r.tipo_pagina, r.url[:70], r.estado, r.observacion, r.detalle[:110]])
    kpis_filas = []
    for clave, nombre, definicion in KPIS:
        valor = kpis.get(clave)
        kpis_filas.append([nombre, definicion, valor if valor not in (None, "") else "sin dato", kpis.get(f"{clave}_fuente", "") or ("falta export" if valor in (None, "") else "")])
    grupos = agrupacion.agrupar_hallazgos(hallazgos, len(urls)) if urls else None
    tipos = agrupacion.tipos_detectados(urls) if urls else None
    areas = agrupacion.por_area(hallazgos, len(urls)) if hallazgos else None
    comparacion = agrupacion.comparar_con(hallazgos, comparar) if comparar else None
    render = agrupacion.render_por_url(urls) if urls else []
    pt = agrupacion.por_tipo([r.a_dict() for r in resultados], urls, reglas) if urls else {}
    comp_reglas = agrupacion.comparar_reglas(resultados=[r.a_dict() for r in resultados], urls=urls, dominio=dominio, ruta_base=comparar_reglas, reglas=reglas) if comparar_reglas else None
    payload = {
        "meta": {"fecha": fecha.isoformat(), "dominio": dominio, "modulo": modulo, "version_skill": VERSION, "n_urls": len(urls), "contexto_valido": contexto.get("valido", False), "comparar": str(comparar) if comparar else None, "anexo_tecnico": anexo_tecnico, "comparar_reglas": str(comparar_reglas) if comparar_reglas else None},
        "no_evaluables": [h.a_dict() for h in no_evaluables],
        "render_por_url": render,
        "por_tipo": pt,
        "comparacion_reglas": comp_reglas,
        "grupos": grupos,
        "tipos_detectados": tipos,
        "por_area": areas,
        "comparacion": comparacion,
        "titular": titular,
        "resumen": resumen,
        "supuestos": supuestos,
        "puntaje_cumplimiento": puntaje,
        "hallazgos": [h.a_dict() for h in hallazgos],
        "resultados": [r.a_dict() for r in resultados],
        "urls": urls,
        "sitio": sitio,
        "roadmap": {k: [h.id for h in v] for k, v in roadmap.items()},
        "kpis": {clave: kpis.get(clave) for clave, _, _ in KPIS},
        "metricas_visibilidad": metricas_visibilidad,
    }
    puntaje_md = "_Excluye reglas de principio, método y anti-patrón y observaciones marcadas Hipótesis. " + puntaje.get("leyenda", "") + "_\n\n" + _md_tabla(
        ["Vector", "Cumplimiento", "Reglas evaluadas"],
        [[cat, f"{v['puntaje']}%" if v["puntaje"] is not None else "sin dato", v["reglas_evaluadas"]] for cat, v in puntaje.get("por_categoria", {}).items()] + [["global", f"{puntaje.get('global')}%" if puntaje.get("global") is not None else "sin dato", ""]],
    )
    plantilla = (RUTA_PLANTILLAS / "reporte.md").read_text(encoding="utf-8")
    valores = {
        "titulo": f"Reporte {modulo} · {dominio}" + (" · Auditoría técnica comparativa (sin contexto de negocio, sin medición de visibilidad)" if anexo_tecnico else ""),
        "titular": titular,
        "fecha": fecha.isoformat(),
        "dominio": dominio,
        "modulo": modulo,
        "n_urls": str(len(urls)),
        "modo_extra": " y subagentes" if any(h.origen == "subagente" for h in hallazgos) else "",
        "resumen": resumen,
        "supuestos": "\n".join(f"- {s}" for s in supuestos) if supuestos else "_Contexto completo; sin supuestos._",
        "hallazgos": _hallazgos_md(hallazgos),
        "sitio": _sitio_md(sitio),
        "reglas_evaluadas": _md_tabla(["Regla", "Fuerza", "Tipo", "URL", "Estado", "Observación", "Detalle"], filas_reglas),
        "puntaje": puntaje_md,
        "extras": (agrupacion.markdown_comparacion_reglas(comp_reglas) + "\n" if comp_reglas else "") + agrupacion.markdown_extras(grupos, tipos, areas, comparacion) + ("\n" + agrupacion.markdown_por_tipo(pt, render) if urls else "") + ("\n" + agrupacion.markdown_no_evaluables(no_evaluables) if anexo_tecnico else ""),
        "roadmap_30d": _roadmap_md(roadmap.get("30d", [])),
        "roadmap_90d": _roadmap_md(roadmap.get("90d", [])),
        "roadmap_largo": _roadmap_md(roadmap.get("largo", [])),
        "kpis": _md_tabla(["KPI", "Definición", "Valor actual", "Fuente"], kpis_filas),
        "metodo": (
            "Colectores deterministas sobre el HTML descargado (sin ejecutar JavaScript salvo con --render). "
            "Reglas y fuentes en reglas/rulebook.yaml (verificadas el 2026-09-10). "
            "Las etiquetas Confirmado/Probable/Hipótesis describen la observación; A/B/C y el tipo de evidencia describen la regla. "
            + metodo_extra
        ),
    }
    md = plantilla
    for k, v in valores.items():
        md = md.replace("{{" + k + "}}", v)
    payload["markdown"] = md
    return payload


def escribir(payload: dict[str, Any], *, directorio: Path | str | None = None, nombre: str | None = None) -> dict[str, str]:
    directorio = Path(directorio) if directorio else RUTA_SALIDAS
    directorio.mkdir(parents=True, exist_ok=True)
    nombre = nombre or nombre_archivo(payload["meta"]["dominio"], payload["meta"]["modulo"], date.fromisoformat(payload["meta"]["fecha"]))
    ruta_md = directorio / f"{nombre}.md"
    ruta_json = directorio / f"{nombre}.json"
    ruta_md.write_text(payload["markdown"], encoding="utf-8")
    sin_md = {k: v for k, v in payload.items() if k != "markdown"}
    ruta_json.write_text(json.dumps(sin_md, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"md": str(ruta_md), "json": str(ruta_json)}
