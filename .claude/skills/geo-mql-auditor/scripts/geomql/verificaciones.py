"""Motor de verificaciones: aplica cada regla del rulebook a la evidencia recolectada.

Cada verificación devuelve un ResultadoRegla con estado (pasa, falla, no_aplica,
sin_evidencia, sin_colector) y la etiqueta de observación (Confirmado, Probable,
Hipótesis). Nunca produce cifras de "impacto proyectado".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .hallazgos import ResultadoRegla
from .html import Documento
from .reglas import Regla


@dataclass
class EvidenciaSitio:
    url: str
    host: str
    robots: dict[str, Any] = field(default_factory=dict)
    bots: dict[str, Any] = field(default_factory=dict)
    sitemap: dict[str, Any] = field(default_factory=dict)
    llmstxt: dict[str, Any] = field(default_factory=dict)
    idiomas_esperados: list[str] = field(default_factory=list)
    acerca_contacto: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenciaPagina:
    url: str
    tipo_pagina: str
    fetch: dict[str, Any]
    doc: Documento
    tecnico: dict[str, Any]
    schema: dict[str, Any]
    extractabilidad: dict[str, Any]
    estadisticas: dict[str, Any]
    citas: dict[str, Any]
    frescura: dict[str, Any]
    entidad: dict[str, Any]
    deteccion: dict[str, Any] = field(default_factory=dict)


def _r(ev: EvidenciaPagina | EvidenciaSitio, regla_id: str, estado: str, detalle: str = "", *, obs: str = "Confirmado", evidencia: list[dict[str, Any]] | None = None, colector: str = "") -> ResultadoRegla:
    tipo = ev.tipo_pagina if isinstance(ev, EvidenciaPagina) else "sitio"
    return ResultadoRegla(regla_id=regla_id, url=ev.url, estado=estado, observacion=obs, detalle=detalle, evidencia=evidencia or [], tipo_pagina=tipo, colector=colector)


MAX_EXTRACTO = 600


def _ev(colector: str, dato: Any, extracto: "str | list[dict[str, Any]]" = "") -> dict[str, Any]:
    """Evidencia de un colector. `extracto` puede ser texto o una lista de {posicion, texto};
    la lista se conserva en `extractos` y se aplana en `extracto` para el Markdown."""
    if isinstance(extracto, list):
        extractos = [{"posicion": str(x.get("posicion") or ""), "texto": str(x.get("texto") or "")} for x in extracto if x.get("texto")]
        plano = " | ".join(f"[{x['posicion']}] {x['texto']}" if x["posicion"] else x["texto"] for x in extractos)
        return {"colector": colector, "dato": dato, "extracto": plano[:MAX_EXTRACTO], "extractos": extractos}
    return {"colector": colector, "dato": dato, "extracto": (extracto or "")[:MAX_EXTRACTO]}


def _apertura(ev: "EvidenciaPagina") -> list[dict[str, Any]]:
    """Párrafos de apertura: sustentan los hallazgos de ausencia (sin cita, sin fecha, sin ejemplo, sin definición)."""
    return ev.extractabilidad.get("apertura") or []


def _o(lista: list[dict[str, Any]], ev: "EvidenciaPagina") -> list[dict[str, Any]]:
    """Lista de extractos o, si está vacía, la apertura."""
    return lista or _apertura(ev)


# =============================================================== TÉCNICO (página)
def v_t01(ev: EvidenciaPagina) -> ResultadoRegla:
    c = ev.tecnico["codigo_http"]
    problemas = []
    if c["status"] != 200:
        problemas.append(f"código {c['status']}")
    if c["saltos"] > 2:
        problemas.append(f"{c['saltos']} saltos de redirección")
    if c["codigos_redireccion"] and c["solo_301"] is False:
        problemas.append("redirecciones temporales (302/307) en la cadena")
    if problemas:
        return _r(ev, "T-01", "falla", "; ".join(problemas), evidencia=[_ev("tecnico.codigo_http", c)])
    return _r(ev, "T-01", "pasa", f"200 con {c['saltos']} saltos", evidencia=[_ev("tecnico.codigo_http", c)])


def v_t07(ev: EvidenciaPagina) -> ResultadoRegla:
    d = ev.tecnico["directivas"]
    problemas = []
    if d["noindex"]:
        problemas.append("noindex")
    if d["nosnippet"]:
        problemas.append("nosnippet")
    if d["max_snippet_restrictivo"]:
        problemas.append(f"max-snippet:{d['max_snippet']}")
    if d["data_nosnippet_en_principal"]:
        problemas.append(f"data-nosnippet en {d['data_nosnippet_en_principal']} bloque(s) del contenido principal")
    if problemas:
        return _r(ev, "T-07", "falla", "Directivas que limitan AI Overviews/AI Mode: " + ", ".join(problemas), evidencia=[_ev("tecnico.directivas", d)])
    return _r(ev, "T-07", "pasa", "sin noindex, nosnippet ni max-snippet restrictivo", evidencia=[_ev("tecnico.directivas", d)])


def v_t09(ev: EvidenciaPagina) -> ResultadoRegla:
    js = ev.tecnico["dependencia_js"]
    ver = js["veredicto"]
    evd = [_ev("tecnico.dependencia_js", {k: js[k] for k in ("palabras_principal_sin_js", "palabras_principal_con_js", "marcadores_framework", "contenedor_raiz_vacio", "veredicto")})]
    if ver == "sin_dependencia":
        return _r(ev, "T-09", "pasa", f"{js['palabras_principal_sin_js']} palabras de contenido principal en el HTML inicial", evidencia=evd)
    if ver in ("dependencia_confirmada", "parcial"):
        return _r(ev, "T-09", "falla", f"con JavaScript aparecen {js['delta_palabras']} palabras más en el contenido principal", evidencia=evd)
    if ver == "probable_dependencia":
        return _r(ev, "T-09", "falla", f"HTML inicial casi vacío ({js['palabras_total_sin_js']} palabras); marcadores: {', '.join(js['marcadores_framework']) or 'ninguno'}; instala Playwright y usa --render para confirmar", obs="Probable", evidencia=evd)
    return _r(ev, "T-09", "sin_evidencia", "contenido corto sin marcadores de framework; usa --render para confirmar", obs="Hipótesis", evidencia=evd)


def v_t10(ev: EvidenciaPagina) -> ResultadoRegla:
    c = ev.tecnico["canonical"]
    evd = [_ev("tecnico.canonical", c)]
    if str(c.get("url_final", "")).startswith("file://"):
        return _r(ev, "T-10", "no_aplica", "fixtura local: la URL final no es HTTP", evidencia=evd)
    if not c["presente"]:
        return _r(ev, "T-10", "falla", "sin rel=canonical", evidencia=evd)
    if not c["absoluto"]:
        return _r(ev, "T-10", "falla", f"canonical relativo: {c['valor']}", evidencia=evd)
    if not c["autorreferente"]:
        return _r(ev, "T-10", "falla", f"canonical apunta a {c['valor']} y no a la URL final {c['url_final']}; confirma si la consolidación es intencional", evidencia=evd)
    return _r(ev, "T-10", "pasa", "canonical absoluto y autorreferente", evidencia=evd)


def v_t12(ev: EvidenciaPagina, idiomas_esperados: list[str] | None = None) -> ResultadoRegla:
    h = ev.tecnico["hreflang"]
    evd = [_ev("tecnico.hreflang", h)]
    if not h["presente"]:
        if idiomas_esperados and len(idiomas_esperados) > 1:
            return _r(ev, "T-12", "falla", f"el contexto declara {len(idiomas_esperados)} idiomas y la página no tiene hreflang", obs="Probable", evidencia=evd)
        return _r(ev, "T-12", "no_aplica", "sin versiones por idioma declaradas", evidencia=evd)
    problemas = []
    if not h["incluye_self"]:
        problemas.append("no se incluye a sí misma")
    if not h["incluye_x_default"]:
        problemas.append("sin x-default")
    if problemas:
        return _r(ev, "T-12", "falla", "; ".join(problemas), evidencia=evd)
    return _r(ev, "T-12", "pasa", f"hreflang para {', '.join(h['idiomas'])}", evidencia=evd)


def v_t13(ev: EvidenciaPagina) -> ResultadoRegla:
    b = ev.tecnico["meta_bingbot"]
    evd = [_ev("tecnico.meta_bingbot", b)]
    if b["noarchive"]:
        return _r(ev, "T-13", "falla", "meta noarchive: excluida de las respuestas de Copilot y de su entrenamiento", evidencia=evd)
    if b["nocache"]:
        return _r(ev, "T-13", "falla", "meta bingbot nocache: Copilot solo puede usar URL, título y snippet", evidencia=evd)
    return _r(ev, "T-13", "pasa", "sin nocache ni noarchive", evidencia=evd)


def v_t14(ev: EvidenciaPagina) -> ResultadoRegla:
    m = ev.tecnico["meta_description"]
    if m.get("parece_codigo"):
        return _r(ev, "T-14", "falla", f"la meta description contiene código (CSS, HTML o JSON) en lugar de una descripción legible: «{m.get('texto', '')[:120]}»", evidencia=[_ev("tecnico.meta_description", m, [{"posicion": "meta description", "texto": m.get("texto", "")}])])
    evd = [_ev("tecnico.meta_description", m)]
    if not m["presente"]:
        return _r(ev, "T-14", "falla", "sin meta description", evidencia=evd)
    if m["longitud"] < 50:
        return _r(ev, "T-14", "falla", f"meta description muy corta ({m['longitud']} caracteres)", evidencia=evd)
    return _r(ev, "T-14", "pasa", f"{m['longitud']} caracteres", evidencia=evd)


# ======================================================== EXTRACTABILIDAD (página)
def v_x01(ev: EvidenciaPagina) -> ResultadoRegla:
    r = ev.extractabilidad["respuesta_directa"]
    evd = [_ev("extractabilidad.respuesta_directa", {k: r[k] for k in ("palabras", "terminos_compartidos_con_h1", "tiene_definicion")}, _o([{"posicion": r.get("posicion", "apertura"), "texto": " ".join(r["oraciones"])}] if r["oraciones"] else [], ev))]
    if not r["oraciones"]:
        return _r(ev, "X-01", "falla", "no se encontró texto de apertura en el contenido principal", obs="Probable", evidencia=evd)
    if r["veredicto"]:
        return _r(ev, "X-01", "pasa", "la apertura comparte términos con el H1 o contiene una definición", obs="Probable", evidencia=evd)
    return _r(ev, "X-01", "falla", "las primeras oraciones no responden al H1 ni definen el tema", obs="Probable", evidencia=evd)


def v_x02(ev: EvidenciaPagina) -> ResultadoRegla:
    j = ev.extractabilidad["jerarquia"]
    muestra = ev.extractabilidad.get("muestra", {}).get("encabezados", [])
    extractos = j.get("no_descriptivos") or [{"posicion": e["posicion"], "texto": e["texto"]} for e in muestra[:8]]
    evd = [_ev("extractabilidad.jerarquia", {k: j[k] for k in ("h1", "h2", "h3", "saltos", "subtitulos_descriptivos", "subtitulos")}, _o(extractos, ev))]
    problemas = []
    if j["h1"] != 1:
        problemas.append(f"{j['h1']} H1")
    if j["saltos"]:
        problemas.append("saltos " + ", ".join(j["saltos"]))
    if j["subtitulos"] and j["subtitulos_descriptivos"] / j["subtitulos"] < 0.6:
        problemas.append(f"solo {j['subtitulos_descriptivos']} de {j['subtitulos']} subtítulos son descriptivos")
    if problemas:
        return _r(ev, "X-02", "falla", "; ".join(problemas), evidencia=evd)
    return _r(ev, "X-02", "pasa", f"1 H1, {j['h2']} H2, {j['h3']} H3 sin saltos", evidencia=evd)


def v_x03(ev: EvidenciaPagina) -> ResultadoRegla:
    t = ev.extractabilidad["tablas_listas"]
    evd = [_ev("extractabilidad.tablas_listas", {k: v for k, v in t.items() if k != "oraciones"}, _o(t.get("oraciones", []), ev))]
    if not t["menciona_comparacion"] and not t["menciona_pasos"]:
        return _r(ev, "X-03", "no_aplica", "la página no compara ni describe pasos", evidencia=evd)
    if t["veredicto"]:
        return _r(ev, "X-03", "pasa", f"{t['tablas_con_encabezado']} tabla(s) con encabezado y {t['listas_ordenadas']} lista(s) ordenada(s)", evidencia=evd)
    faltan = []
    if t["menciona_comparacion"] and not t["tablas_con_encabezado"] and not t["listas"]:
        faltan.append("comparación sin tabla ni lista")
    if t["menciona_pasos"] and not t["listas_ordenadas"]:
        faltan.append("pasos sin lista ordenada")
    return _r(ev, "X-03", "falla", "; ".join(faltan) or "estructura insuficiente", evidencia=evd)


def v_x04(ev: EvidenciaPagina) -> ResultadoRegla:
    e = ev.estadisticas
    muestras = [{"posicion": f"dato #{i}", "texto": f"{m['valor']}: {m['oracion']}"} for i, m in enumerate(e["sin_fuente_muestras"][:3], 1)]
    evd = [_ev("estadisticas", {"total": e["total"], "con_fuente": e["con_fuente"], "sin_fuente": e["sin_fuente"], "excluidos": e["excluidos"]}, _o(muestras, ev))]
    if e["total"] == 0:
        return _r(ev, "X-04", "no_aplica", "sin datos numéricos en el contenido principal", evidencia=evd)
    if e["sin_fuente"] == 0:
        return _r(ev, "X-04", "pasa", f"{e['total']} dato(s) con fuente enlazada, citada o propia", evidencia=evd)
    return _r(ev, "X-04", "falla", f"{e['sin_fuente']} de {e['total']} datos sin fuente en la misma oración o párrafo", evidencia=evd)


def v_x05(ev: EvidenciaPagina) -> ResultadoRegla:
    c = ev.citas
    evd = [_ev("citas", {"total": c["total"], "atribuidas": c["atribuidas"]}, _o([{"posicion": f"cita #{i}", "texto": q["texto"]} for i, q in enumerate(c["citas"][:2], 1)], ev))]
    if c["total"] == 0:
        return _r(ev, "X-05", "falla", "sin citas textuales de expertos", obs="Confirmado", evidencia=evd)
    if c["sin_atribucion"]:
        return _r(ev, "X-05", "falla", f"{c['sin_atribucion']} cita(s) sin nombre o cargo", evidencia=evd)
    return _r(ev, "X-05", "pasa", f"{c['atribuidas']} cita(s) atribuida(s)", evidencia=evd)


def v_x07(ev: EvidenciaPagina) -> ResultadoRegla:
    d = ev.extractabilidad["densidad_terminos"]
    evd = [_ev("extractabilidad.densidad_terminos", {k: v for k, v in d.items() if k != "oraciones_muestra"}, _o(d.get("oraciones_muestra", []), ev))]
    if d["veredicto"]:
        return _r(ev, "X-07", "pasa", f"término más frecuente: {d['termino_top']} ({d['densidad_top']:.1%})", obs="Probable", evidencia=evd)
    return _r(ev, "X-07", "falla", f"'{d['termino_top']}' aparece {d['frecuencia_top']} veces ({d['densidad_top']:.1%} de las palabras significativas)", obs="Probable", evidencia=evd)


def v_x08(ev: EvidenciaPagina) -> ResultadoRegla:
    f = ev.frescura
    fv = f["fecha_visible"]
    visible = fv["actualizacion"] or fv["publicacion"]
    evd = [_ev("frescura", {"fecha_principal": f["fecha_principal"], "fuente": f["fuente"], "visible": visible, "incoherencias": f["incoherencias"]}, _o([{"posicion": "fecha visible", "texto": visible["texto"]}] if isinstance(visible, dict) and visible.get("texto") else [], ev))]
    if not fv["presente"]:
        return _r(ev, "X-08", "falla", "sin fecha visible en el contenido principal", evidencia=evd)
    if not fv["etiquetada"]:
        return _r(ev, "X-08", "falla", "hay fechas pero ninguna etiquetada como publicado o actualizado", evidencia=evd)
    if f["incoherencias"]:
        return _r(ev, "X-08", "falla", "; ".join(f["incoherencias"]), evidencia=evd)
    return _r(ev, "X-08", "pasa", f"fecha visible etiquetada y coherente ({f['fecha_principal']})", evidencia=evd)


def v_x09(ev: EvidenciaPagina) -> ResultadoRegla:
    f = ev.frescura
    evd = [_ev("frescura", {"fecha_principal": f["fecha_principal"], "antiguedad_dias": f["antiguedad_dias"], "fuente": f["fuente"]}, _o([{"posicion": f["fuente"] or "fecha", "texto": str(f.get("fecha_cruda") or f["fecha_principal"])}] if f["fecha_principal"] else [], ev))]
    if f["antiguedad_dias"] is None:
        return _r(ev, "X-09", "sin_evidencia", "sin fecha de modificación detectable", obs="Hipótesis", evidencia=evd)
    if f["antiguedad_dias"] > 90:
        return _r(ev, "X-09", "falla", f"última actualización hace {f['antiguedad_dias']} días ({f['fuente']})", evidencia=evd)
    return _r(ev, "X-09", "pasa", f"actualizado hace {f['antiguedad_dias']} días", evidencia=evd)


def v_x10(ev: EvidenciaPagina) -> ResultadoRegla:
    d = ev.extractabilidad["definicion"]
    evd = [_ev("extractabilidad.definicion", d, _o([{"posicion": d.get("posicion") or "definición", "texto": d["texto"]}] if d.get("texto") else [], ev))]
    if d["presente"]:
        return _r(ev, "X-10", "pasa", "definición explícita encontrada", obs="Probable", evidencia=evd)
    return _r(ev, "X-10", "falla", "sin oración de definición (sujeto + es/son + para quién)", obs="Probable", evidencia=evd)


def v_x12(ev: EvidenciaPagina) -> ResultadoRegla:
    p = ev.extractabilidad["proporcion_principal"]
    evd = [_ev("extractabilidad.proporcion_principal", p, _apertura(ev))]
    if p["veredicto"]:
        return _r(ev, "X-12", "pasa", f"{p['proporcion']:.0%} del texto es contenido principal", evidencia=evd)
    return _r(ev, "X-12", "falla", f"solo {p['proporcion']:.0%} del texto es contenido principal ({p['palabras_principal']} de {p['palabras_total']} palabras)", evidencia=evd)


def v_x13(ev: EvidenciaPagina) -> ResultadoRegla:
    p = ev.extractabilidad["parrafos"]
    evd = [_ev("extractabilidad.parrafos", {k: v for k, v in p.items() if k not in ("largos_muestra", "mas_largo")}, _o(p.get("largos_muestra") or ([p["mas_largo"]] if p.get("mas_largo") else []), ev))]
    if p["total"] == 0:
        return _r(ev, "X-13", "no_aplica", "sin párrafos", evidencia=evd)
    if p["largos"]:
        return _r(ev, "X-13", "falla", f"{p['largos']} párrafo(s) de más de 100 palabras (máximo {p['max_palabras']})", evidencia=evd)
    return _r(ev, "X-13", "pasa", f"párrafos de {p['promedio']} palabras en promedio", evidencia=evd)


def v_x14(ev: EvidenciaPagina) -> ResultadoRegla:
    i = ev.extractabilidad["imagenes"]
    evd = [_ev("extractabilidad.imagenes", {k: v for k, v in i.items() if k not in ("sin_alt_pos", "con_alt_pos")}, _o(i.get("sin_alt_pos") or i.get("con_alt_pos") or [], ev))]
    if i["en_principal"] == 0:
        return _r(ev, "X-14", "no_aplica", "sin imágenes en el contenido principal", evidencia=evd)
    if i["sin_alt"]:
        return _r(ev, "X-14", "falla", f"{len(i['sin_alt'])} de {i['en_principal']} imágenes sin alt", evidencia=evd)
    return _r(ev, "X-14", "pasa", f"{i['en_principal']} imagen(es) con alt", evidencia=evd)


def v_x15(ev: EvidenciaPagina) -> ResultadoRegla:
    f = ev.extractabilidad["faq_visible"]
    evd = [_ev("extractabilidad.faq_visible", {k: v for k, v in f.items() if k != "ejemplos_pos"}, _o(f.get("ejemplos_pos") or [{"posicion": e["posicion"], "texto": e["texto"]} for e in ev.extractabilidad.get("muestra", {}).get("encabezados", [])[:6] if e["nivel"] >= 2], ev))]
    if f["presente"]:
        return _r(ev, "X-15", "pasa", f"{f['preguntas_en_encabezados']} preguntas visibles en encabezados", evidencia=evd)
    if ev.tipo_pagina == "faq":
        return _r(ev, "X-15", "falla", "página de preguntas sin encabezados en forma de pregunta", evidencia=evd)
    return _r(ev, "X-15", "no_aplica", "sin sección de preguntas; añade una solo si hay preguntas reales", evidencia=evd)


def v_x16(ev: EvidenciaPagina) -> ResultadoRegla:
    e = ev.extractabilidad["ejemplos"]
    evd = [_ev("extractabilidad.ejemplos", {k: v for k, v in e.items() if k != "oraciones"}, _o(e.get("oraciones", []), ev))]
    if e["presente"]:
        return _r(ev, "X-16", "pasa", f"{e['menciones']} mención(es) de ejemplos o casos", obs="Probable", evidencia=evd)
    return _r(ev, "X-16", "falla", "sin ejemplos ni casos concretos detectables", obs="Probable", evidencia=evd)


# ================================================================ SCHEMA (página)
def v_s01(ev: EvidenciaPagina) -> ResultadoRegla:
    s = ev.schema
    evd = [_ev("schema", {"bloques": s["bloques"], "invalidos": s["bloques_invalidos"]})]
    if s["bloques"] == 0:
        return _r(ev, "S-01", "no_aplica", "sin JSON-LD", evidencia=evd)
    if s["bloques_invalidos"]:
        return _r(ev, "S-01", "falla", "; ".join(s["bloques_invalidos"]), evidencia=evd)
    return _r(ev, "S-01", "pasa", f"{s['bloques']} bloque(s) válido(s)", evidencia=evd)


def v_s02(ev: EvidenciaPagina) -> ResultadoRegla:
    s = ev.schema
    evd = [_ev("schema.coherencia", s["coherencia"])]
    if s["bloques"] == 0:
        return _r(ev, "S-02", "no_aplica", "sin JSON-LD", evidencia=evd)
    if s["coherencia"]:
        return _r(ev, "S-02", "falla", "; ".join(f"{c['campo']}: {c['problema']}" for c in s["coherencia"]), evidencia=evd)
    return _r(ev, "S-02", "pasa", "el markup coincide con el contenido visible", evidencia=evd)


def v_s03(ev: EvidenciaPagina) -> ResultadoRegla:
    a = ev.schema["article"]
    evd = [_ev("schema.article", a)]
    if not a["presente"]:
        return _r(ev, "S-03", "falla", "sin Article ni BlogPosting", evidencia=evd)
    problemas = list(a["faltantes"])
    if not a["fechas_iso_con_zona"]:
        problemas.append("fechas sin zona horaria ISO 8601")
    if problemas:
        return _r(ev, "S-03", "falla", "faltan: " + ", ".join(problemas), evidencia=evd)
    return _r(ev, "S-03", "pasa", f"{a['tipo']} con todas las propiedades recomendadas", evidencia=evd)


def v_s04(ev: EvidenciaPagina) -> ResultadoRegla:
    o = ev.schema["organization"]
    w = ev.schema["website"]
    evd = [_ev("schema.organization", o), _ev("schema.website", w)]
    if not o["presente"]:
        return _r(ev, "S-04", "falla", "sin Organization en la home", evidencia=evd)
    problemas = list(o.get("faltantes", []))
    if not w["presente"]:
        problemas.append("WebSite")
    if problemas:
        return _r(ev, "S-04", "falla", "faltan: " + ", ".join(problemas), evidencia=evd)
    return _r(ev, "S-04", "pasa", "Organization y WebSite completos", evidencia=evd)


def v_s05(ev: EvidenciaPagina) -> ResultadoRegla:
    b = ev.schema["breadcrumb"]
    evd = [_ev("schema.breadcrumb", b)]
    if not b["presente"]:
        return _r(ev, "S-05", "falla", "sin BreadcrumbList", evidencia=evd)
    if not b["valido"]:
        return _r(ev, "S-05", "falla", "BreadcrumbList incompleto: " + (", ".join(str(x) for x in b.get("sin_item", [])) or "faltan position o name"), evidencia=evd)
    return _r(ev, "S-05", "pasa", f"BreadcrumbList con {b['items']} elementos", evidencia=evd)


def v_s06(ev: EvidenciaPagina) -> ResultadoRegla:
    p = ev.schema["product"]
    precios = any(m["tipo"] in ("moneda", "moneda2") for m in ev.estadisticas["muestras"])
    evd = [_ev("schema.product", p), _ev("estadisticas.precios", precios)]
    if p["presente"]:
        if p["tiene_oferta_o_review"]:
            return _r(ev, "S-06", "pasa", "Product con offers, review o aggregateRating", evidencia=evd)
        return _r(ev, "S-06", "falla", "Product sin offers, review ni aggregateRating", evidencia=evd)
    if precios:
        return _r(ev, "S-06", "falla", "la página muestra precios y no tiene Product", obs="Probable", evidencia=evd)
    return _r(ev, "S-06", "no_aplica", "no parece página de un producto con precio", evidencia=evd)


def v_s07(ev: EvidenciaPagina) -> ResultadoRegla:
    s = ev.schema["service"]
    evd = [_ev("schema.service", s)]
    if not s["presente"]:
        return _r(ev, "S-07", "falla", "sin Service (opcional, sin efecto demostrado)", evidencia=evd)
    if s["faltantes"]:
        return _r(ev, "S-07", "falla", "Service sin: " + ", ".join(s["faltantes"]), evidencia=evd)
    return _r(ev, "S-07", "pasa", "Service completo", evidencia=evd)


def v_s08(ev: EvidenciaPagina) -> ResultadoRegla:
    f = ev.schema["faqpage"]
    evd = [_ev("schema.faqpage", f)]
    if not f["presente"]:
        return _r(ev, "S-08", "no_aplica", "sin FAQPage (no es prioritario)", evidencia=evd)
    if f["no_visibles"]:
        return _r(ev, "S-08", "falla", f"{len(f['no_visibles'])} pregunta(s) del markup no aparecen en la página", evidencia=evd)
    return _r(ev, "S-08", "pasa", f"FAQPage con {f['preguntas']} preguntas visibles", evidencia=evd)


def v_s09(ev: EvidenciaPagina) -> ResultadoRegla:
    l = ev.schema["localbusiness"]
    evd = [_ev("schema.localbusiness", {k: v for k, v in l.items() if k != "address"})]
    if not l["presente"]:
        return _r(ev, "S-09", "falla", "sin LocalBusiness", evidencia=evd)
    if l["faltantes_requeridos"]:
        return _r(ev, "S-09", "falla", "faltan requeridos: " + ", ".join(l["faltantes_requeridos"]), evidencia=evd)
    if l["faltantes_recomendados"]:
        return _r(ev, "S-09", "pasa", "requeridos completos; recomendados ausentes: " + ", ".join(l["faltantes_recomendados"]), evidencia=evd)
    return _r(ev, "S-09", "pasa", "LocalBusiness completo", evidencia=evd)


def v_s10(ev: EvidenciaPagina) -> ResultadoRegla:
    p = ev.schema["person"]
    a = ev.schema["article"]
    evd = [_ev("schema.person", p)]
    if ev.tipo_pagina == "perfil":
        if ev.schema["profilepage"]["presente"]:
            return _r(ev, "S-10", "pasa", "ProfilePage presente", evidencia=evd)
        return _r(ev, "S-10", "falla", "perfil sin ProfilePage", evidencia=evd)
    if not a["presente"] or not a.get("autor"):
        return _r(ev, "S-10", "falla", "el artículo no declara autor en el markup", evidencia=evd)
    if a["autor"] in p["con_url_o_sameas"]:
        return _r(ev, "S-10", "pasa", f"autor {a['autor']} con url o sameAs", evidencia=evd)
    return _r(ev, "S-10", "falla", f"autor {a['autor']} sin Person con url o sameAs", evidencia=evd)


def v_s11(ev: EvidenciaPagina) -> ResultadoRegla:
    s = ev.schema
    evd = [_ev("schema.ids", {"definidos": s["ids_definidos"], "rotas": s["referencias_rotas"], "duplicados": s["ids_duplicados"]})]
    if s["bloques"] == 0:
        return _r(ev, "S-11", "no_aplica", "sin JSON-LD", evidencia=evd)
    if s["referencias_rotas"]:
        return _r(ev, "S-11", "falla", "referencias @id sin destino: " + ", ".join(s["referencias_rotas"]), evidencia=evd)
    if s["ids_duplicados"]:
        return _r(ev, "S-11", "falla", "@id duplicados: " + ", ".join(s["ids_duplicados"]), evidencia=evd)
    entidades = sum(s["conteo_tipos"].get(t, 0) for t in ("Organization", "Person"))
    if entidades >= 2 and not s["ids_definidos"]:
        return _r(ev, "S-11", "falla", "Organization y Person sin @id; no se pueden referenciar entre sí", evidencia=evd)
    return _r(ev, "S-11", "pasa", f"{len(s['ids_definidos'])} @id definidos y todas las referencias resueltas", evidencia=evd)


def v_s12(ev: EvidenciaPagina) -> ResultadoRegla:
    s = ev.schema
    evd = [_ev("schema.duplicados", s["duplicados_raiz"])]
    if s["bloques"] == 0:
        return _r(ev, "S-12", "no_aplica", "sin JSON-LD", evidencia=evd)
    if s["duplicados_raiz"]:
        return _r(ev, "S-12", "falla", "tipos repetidos: " + ", ".join(s["duplicados_raiz"]), evidencia=evd)
    return _r(ev, "S-12", "pasa", "sin bloques duplicados", evidencia=evd)


def v_s13(ev: EvidenciaPagina) -> ResultadoRegla:
    d = ev.schema["definedterm"]
    evd = [_ev("schema.definedterm", d)]
    if d["presente"]:
        return _r(ev, "S-13", "pasa", "DefinedTerm presente", evidencia=evd)
    return _r(ev, "S-13", "falla", "glosario sin DefinedTerm (opcional)", evidencia=evd)


# =============================================================== ENTIDAD (página)
def v_e01(ev: EvidenciaPagina) -> ResultadoRegla:
    n = ev.entidad["nombre"]
    evd = [_ev("entidad.nombre", n)]
    if len(n["candidatos"]) < 2:
        return _r(ev, "E-01", "sin_evidencia", "solo una superficie con nombre de marca", obs="Hipótesis", evidencia=evd)
    if n["consistente"]:
        return _r(ev, "E-01", "pasa", "mismo nombre en " + ", ".join(n["candidatos"]), evidencia=evd)
    return _r(ev, "E-01", "falla", "variantes: " + " | ".join(f"{k}: {v}" for k, v in n["candidatos"].items()), evidencia=evd)


def v_e02(ev: EvidenciaPagina) -> ResultadoRegla:
    s = ev.entidad["sameas"]
    evd = [_ev("entidad.sameas", s["urls"])]
    if not ev.schema["organization"]["presente"]:
        return _r(ev, "E-02", "falla", "sin Organization, por tanto sin sameAs", evidencia=evd)
    if s["total"] == 0:
        return _r(ev, "E-02", "falla", "Organization sin sameAs", evidencia=evd)
    return _r(ev, "E-02", "pasa", f"{s['total']} sameAs declarados", evidencia=evd)


def v_e03(ev: EvidenciaPagina) -> ResultadoRegla:
    s = ev.entidad["sameas"]
    evd = [_ev("entidad.sameas.resueltos", s["resueltos"])]
    if s["total"] == 0:
        return _r(ev, "E-03", "no_aplica", "sin sameAs", evidencia=evd)
    if any(r["resuelve"] is None for r in s["resueltos"]):
        return _r(ev, "E-03", "sin_evidencia", "sameAs no verificados (corre con --resolver-sameas)", obs="Hipótesis", evidencia=evd)
    rotos = [r["url"] for r in s["resueltos"] if not r["resuelve"]]
    if rotos:
        return _r(ev, "E-03", "falla", "no resuelven: " + ", ".join(rotos), evidencia=evd)
    return _r(ev, "E-03", "pasa", "todos los sameAs resuelven", evidencia=evd)


def v_e04(ev: EvidenciaPagina) -> ResultadoRegla:
    a = ev.entidad["autoria"]
    evd = [_ev("entidad.autoria", a)]
    if not a["presente"]:
        return _r(ev, "E-04", "falla", "sin autor visible ni en el markup", evidencia=evd)
    if not a["visible"]:
        return _r(ev, "E-04", "falla", f"el autor {a['nombre']} está en el markup pero no visible", evidencia=evd)
    if not a["con_credenciales"]:
        return _r(ev, "E-04", "falla", f"autor {a['nombre']} sin cargo ni perfil enlazado", evidencia=evd)
    return _r(ev, "E-04", "pasa", f"{a['nombre']} ({a['cargo'] or 'perfil enlazado'})", evidencia=evd)


def v_e06(ev: EvidenciaPagina) -> ResultadoRegla:
    n = ev.entidad["nap"]
    evd = [_ev("entidad.nap", n)]
    if not ev.schema["localbusiness"]["presente"]:
        return _r(ev, "E-06", "sin_evidencia", "sin LocalBusiness contra el cual comparar", obs="Hipótesis", evidencia=evd)
    problemas = []
    if n["telefono_coincide"] is False:
        problemas.append("teléfono del markup no aparece en la página")
    if n["direccion_coincide"] is False:
        problemas.append("dirección del markup no coincide con la visible")
    if problemas:
        return _r(ev, "E-06", "falla", "; ".join(problemas), evidencia=evd)
    if n["telefono_coincide"] is None and n["direccion_coincide"] is None:
        return _r(ev, "E-06", "sin_evidencia", "LocalBusiness sin teléfono ni dirección comparables", obs="Hipótesis", evidencia=evd)
    return _r(ev, "E-06", "pasa", "teléfono y dirección coinciden", evidencia=evd)


# ================================================================== SITIO
def v_t02(s: EvidenciaSitio) -> ResultadoRegla:
    r = s.robots
    evd = [_ev("robots", {"status": r.get("status"), "estado": r.get("estado"), "url": r.get("url")})]
    if r.get("estado") in ("ok", "no_existe"):
        return _r(s, "T-02", "pasa", f"robots.txt responde {r.get('status')}", evidencia=evd)
    if r.get("estado") == "error_servidor":
        return _r(s, "T-02", "falla", f"robots.txt responde {r.get('status')}: los crawlers conformes asumen bloqueo total", evidencia=evd)
    return _r(s, "T-02", "sin_evidencia", f"no se pudo obtener robots.txt: {r.get('error')}", obs="Hipótesis", evidencia=evd)


def v_t03(s: EvidenciaSitio, regla_id: str = "T-03") -> ResultadoRegla:
    b = s.bots.get("resumen", {})
    bloq = b.get("busqueda_bloqueados", [])
    evd = [_ev("bots.busqueda", {"bloqueados": bloq, "total": b.get("busqueda_total")})]
    if s.robots.get("estado") == "error_servidor":
        return _r(s, regla_id, "falla", "robots.txt con error de servidor bloquea a todos los bots conformes", evidencia=evd)
    if s.robots.get("estado") == "inaccesible":
        return _r(s, regla_id, "sin_evidencia", "robots.txt inaccesible", obs="Hipótesis", evidencia=evd)
    if bloq:
        return _r(s, regla_id, "falla", "bots de búsqueda bloqueados: " + ", ".join(bloq), evidencia=evd)
    return _r(s, regla_id, "pasa", f"{b.get('busqueda_total', 0)} bots de búsqueda con acceso", evidencia=evd)


def v_t04(s: EvidenciaSitio) -> ResultadoRegla:
    b = s.bots.get("resumen", {})
    evd = [_ev("bots.entrenamiento", {"politica": b.get("politica_entrenamiento"), "bloqueados": b.get("entrenamiento_bloqueados")})]
    pol = b.get("politica_entrenamiento")
    if pol == "mixta":
        return _r(s, "T-04", "falla", "política inconsistente: bloquea " + ", ".join(b.get("entrenamiento_bloqueados", [])) + " pero permite otros bots de entrenamiento; decide una política única", evidencia=evd)
    return _r(s, "T-04", "pasa", f"política de entrenamiento: {pol} (decisión de política, no afecta la búsqueda)", evidencia=evd)


def v_t05(s: EvidenciaSitio) -> ResultadoRegla:
    b = s.bots.get("resumen", {})
    bloq = b.get("usuario_bloqueados", [])
    evd = [_ev("bots.usuario", {"bloqueados": bloq})]
    if bloq:
        return _r(s, "T-05", "falla", "fetchers por usuario bloqueados en robots.txt (varios lo ignoran, pero Claude-User lo respeta): " + ", ".join(bloq), evidencia=evd)
    return _r(s, "T-05", "pasa", "fetchers por usuario permitidos", evidencia=evd)


def v_t08(s: EvidenciaSitio) -> ResultadoRegla:
    b = s.bots.get("resumen", {})
    evd = [_ev("bots.google_extended", b.get("google_extended_bloqueado"))]
    if b.get("google_extended_bloqueado"):
        return _r(s, "T-08", "pasa", "Google-Extended bloqueado: solo afecta entrenamiento y grounding en Gemini y Vertex AI, no AI Overviews ni AI Mode", evidencia=evd)
    return _r(s, "T-08", "pasa", "Google-Extended permitido", evidencia=evd)


def v_t11(s: EvidenciaSitio) -> ResultadoRegla:
    m = s.sitemap
    declarado = m.get("declarado_en_robots")
    if declarado is None:
        declarado = bool(s.robots.get("sitemaps"))
    evd = [_ev("sitemap", {k: m.get(k) for k in ("url", "urls_total", "con_lastmod", "sin_lastmod", "lastmod_futuras", "errores")} | {"declarado_en_robots": declarado})]
    if not m.get("presente"):
        return _r(s, "T-11", "falla", "sin sitemap XML accesible (" + "; ".join(m.get("errores", [])[:2]) + ")", evidencia=evd)
    problemas = []
    if m.get("sin_lastmod"):
        problemas.append(f"{m['sin_lastmod']} de {m['urls_total']} URL sin lastmod")
    if m.get("lastmod_futuras"):
        problemas.append(f"{m['lastmod_futuras']} lastmod en el futuro")
    aviso = "" if declarado else "; aviso: sitemap no declarado en robots.txt (se cumple por /sitemap.xml, pero los crawlers que solo leen robots.txt no lo descubren)"
    if problemas:
        return _r(s, "T-11", "falla", "; ".join(problemas) + aviso, evidencia=evd)
    return _r(s, "T-11", "pasa", f"sitemap con {m['urls_total']} URL y lastmod completo" + aviso, evidencia=evd)


def v_t15(s: EvidenciaSitio) -> ResultadoRegla:
    m = s.sitemap
    evd = [_ev("sitemap.lastmod", {"dias_desde_lastmod": m.get("dias_desde_lastmod")})]
    if not m.get("presente"):
        return _r(s, "T-15", "falla", "sin sitemap; IndexNow no verificable desde fuera", obs="Probable", evidencia=evd)
    d = m.get("dias_desde_lastmod")
    if d is None:
        return _r(s, "T-15", "falla", "sitemap sin lastmod; IndexNow no verificable desde fuera", obs="Probable", evidencia=evd)
    if d > 90:
        return _r(s, "T-15", "falla", f"último lastmod hace {d} días; IndexNow no verificable desde fuera", obs="Probable", evidencia=evd)
    return _r(s, "T-15", "pasa", f"lastmod reciente ({d} días); IndexNow no verificable desde fuera", obs="Probable", evidencia=evd)


def v_e05(s: EvidenciaSitio) -> ResultadoRegla:
    a = s.acerca_contacto
    evd = [_ev("entidad.acerca_contacto", a)]
    if not a:
        return _r(s, "E-05", "sin_evidencia", "sin páginas analizadas", obs="Hipótesis", evidencia=evd)
    faltan = []
    if not a.get("acerca_presente"):
        faltan.append("acerca de")
    if not a.get("contacto_presente"):
        faltan.append("contacto")
    if faltan:
        return _r(s, "E-05", "falla", "sin enlace a " + " ni ".join(faltan), evidencia=evd)
    return _r(s, "E-05", "pasa", "enlaces a acerca de y contacto presentes", evidencia=evd)


VERIFICACIONES_PAGINA: dict[str, Callable[..., ResultadoRegla]] = {
    "T-01": v_t01, "T-07": v_t07, "T-09": v_t09, "T-10": v_t10, "T-12": v_t12, "T-13": v_t13, "T-14": v_t14,
    "X-01": v_x01, "X-02": v_x02, "X-03": v_x03, "X-04": v_x04, "X-05": v_x05, "X-07": v_x07, "X-08": v_x08,
    "X-09": v_x09, "X-10": v_x10, "X-12": v_x12, "X-13": v_x13, "X-14": v_x14, "X-15": v_x15, "X-16": v_x16,
    "S-01": v_s01, "S-02": v_s02, "S-03": v_s03, "S-04": v_s04, "S-05": v_s05, "S-06": v_s06, "S-07": v_s07,
    "S-08": v_s08, "S-09": v_s09, "S-10": v_s10, "S-11": v_s11, "S-12": v_s12, "S-13": v_s13,
    "E-01": v_e01, "E-02": v_e02, "E-03": v_e03, "E-04": v_e04, "E-06": v_e06,
}
VERIFICACIONES_SITIO: dict[str, Callable[..., ResultadoRegla]] = {
    "T-02": v_t02, "T-03": v_t03, "T-04": v_t04, "T-05": v_t05, "T-08": v_t08, "T-11": v_t11, "T-15": v_t15,
    "E-05": v_e05, "E-08": lambda s: v_t03(s, "E-08"),
}
CATEGORIAS_AUDIT = ("tecnico", "extractabilidad", "schema", "entidad")


def evaluar_pagina(ev: EvidenciaPagina, reglas: list[Regla], *, idiomas_esperados: list[str] | None = None) -> list[ResultadoRegla]:
    out: list[ResultadoRegla] = []
    for regla in reglas:
        if regla["categoria"] not in CATEGORIAS_AUDIT or regla["ambito"] != "pagina":
            continue
        if not regla.aplica_a(ev.tipo_pagina):
            continue
        fn = VERIFICACIONES_PAGINA.get(regla["id"])
        if fn is None:
            out.append(ResultadoRegla(regla_id=regla["id"], url=ev.url, estado="sin_colector", observacion="Hipótesis", detalle="requiere revisión humana o del subagente", tipo_pagina=ev.tipo_pagina))
            continue
        try:
            r = fn(ev, idiomas_esperados) if regla["id"] == "T-12" else fn(ev)
        except Exception as e:  # noqa: BLE001 - un colector roto no debe tumbar el audit
            r = ResultadoRegla(regla_id=regla["id"], url=ev.url, estado="sin_evidencia", observacion="Hipótesis", detalle=f"error en la verificación: {e}", tipo_pagina=ev.tipo_pagina)
        r.colector = regla.get("colector") or ""
        out.append(r)
    return out


def evaluar_sitio(s: EvidenciaSitio, reglas: list[Regla]) -> list[ResultadoRegla]:
    out: list[ResultadoRegla] = []
    for regla in reglas:
        if regla["categoria"] not in CATEGORIAS_AUDIT or regla["ambito"] != "sitio":
            continue
        fn = VERIFICACIONES_SITIO.get(regla["id"])
        if fn is None:
            out.append(ResultadoRegla(regla_id=regla["id"], url=s.url, estado="sin_colector", observacion="Hipótesis", detalle="requiere revisión humana o del subagente", tipo_pagina="sitio"))
            continue
        try:
            r = fn(s)
        except Exception as e:  # noqa: BLE001
            r = ResultadoRegla(regla_id=regla["id"], url=s.url, estado="sin_evidencia", observacion="Hipótesis", detalle=f"error en la verificación: {e}", tipo_pagina="sitio")
        r.colector = regla.get("colector") or ""
        out.append(r)
    return out
