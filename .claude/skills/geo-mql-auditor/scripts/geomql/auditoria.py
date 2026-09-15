"""Orquestación del módulo audit: URLs, colectores, verificaciones, hallazgos, resúmenes por vector y reporte.

Estructura derivada de scripts/audit.py de best-aeo-skill (MIT, ver NOTICE),
sin pesos por perfil, sin penalizaciones fijas y sin impacto proyectado.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from . import RUTA_DATOS, RUTA_SALIDAS, VERSION, citas, contexto as contexto_mod, entidad, estadisticas, extractabilidad, fetch, frescura, llmstxt, referencias, reporte, robots, schema, sitemap, tecnico, tipo_pagina
from .bots import evaluar_acceso
from .hallazgos import Hallazgo, ResultadoRegla, hallazgo_desde_resultado, priorizar, puntaje_cumplimiento, resumen_por_vector
from .html import Documento, contar_palabras
from .reglas import Regla, cargar_rulebook, indice
from .verificaciones import CATEGORIAS_AUDIT, EvidenciaPagina, EvidenciaSitio, evaluar_pagina, evaluar_sitio

TIPOS_VALIDOS = ("home", "solucion", "articulo", "comparativa", "faq", "glosario", "landing", "local", "perfil", "programa", "institucional", "otra")


def nueva_corrida(dominio: str, ahora: datetime | None = None) -> str:
    ahora = ahora or datetime.now()
    return f"{ahora.strftime('%Y-%m-%d_%H%M%S')}_{re.sub(r'[^a-z0-9.-]', '_', dominio.lower())}"


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def analizar_pagina(
    url: str,
    *,
    reglas: list[Regla],
    tipo_forzado: str | None = None,
    descargar: Callable[..., dict[str, Any]] | None = None,
    render_fn: Callable[[str], dict[str, Any]] | None = None,
    resolver: Callable[[str], dict[str, Any]] | None = None,
    idiomas_esperados: list[str] | None = None,
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Descarga y analiza una URL; devuelve evidencia, resultados y un registro compacto."""
    descargar = descargar or fetch.descargar
    f = descargar(url)
    host = _host(f.get("url_final") or url)
    doc_crudo = Documento(f.get("html", ""), f.get("url_final") or url)
    render = render_fn(url) if render_fn else None
    tec = tecnico.analizar_pagina(f, doc_crudo, url, render=render)
    # Con render disponible, los colectores de contenido leen el HTML renderizado; el técnico compara ambos.
    renderizado = bool(render and render.get("disponible") and render.get("html") and (render.get("palabras_principal") or 0) > tec["dependencia_js"]["palabras_principal_sin_js"])
    doc = Documento(render["html"], f.get("url_final") or url) if renderizado else doc_crudo
    deteccion = tipo_pagina.detectar(doc, f.get("url_final") or url)
    tipo = tipo_forzado if tipo_forzado in TIPOS_VALIDOS else deteccion["tipo"]
    sch = schema.analizar(doc, tipo_pagina=tipo, url=url)
    ev = EvidenciaPagina(
        url=url,
        tipo_pagina=tipo,
        fetch=f,
        doc=doc,
        tecnico=tec,
        schema=sch,
        extractabilidad=extractabilidad.analizar(doc, tipo_pagina=tipo),
        estadisticas=estadisticas.analizar(doc, host=host),
        citas=citas.analizar(doc, host=host),
        frescura=frescura.analizar(doc, sch, ahora=ahora),
        entidad=entidad.analizar(doc, sch, resolver=resolver, tipo_pagina=tipo),
        deteccion=deteccion,
    )
    if f.get("status") != 200 or not f.get("html"):
        resultados = [ResultadoRegla(regla_id="T-01", url=url, estado="falla", observacion="Confirmado", detalle=f"código {f.get('status')}: {f.get('error') or 'sin contenido'}", evidencia=[{"colector": "fetch", "dato": {"status": f.get("status"), "error": f.get("error")}}], tipo_pagina=tipo, colector="tecnico.codigo_http")]
    else:
        resultados = evaluar_pagina(ev, reglas, idiomas_esperados=idiomas_esperados)
        if not renderizado and tec["dependencia_js"]["veredicto"] == "probable_dependencia":
            # Compuerta: sin el contenido real no se juzgan extractabilidad, schema ni entidad de página.
            for r in resultados:
                if r.regla_id.startswith(("X-", "S-", "E-")) and r.estado in ("pasa", "falla"):
                    r.estado = "sin_evidencia"
                    r.observacion = "Hipótesis"
                    r.detalle = f"contenido no disponible sin JavaScript (HTML inicial con {tec['dependencia_js']['palabras_principal_sin_js']} palabras de contenido principal); usa --render para evaluarla. Resultado sobre el HTML crudo: {r.detalle}"
    registro = {
        "url": url,
        "url_final": f.get("url_final"),
        "status": f.get("status"),
        "tipo": tipo,
        "tipo_forzado": bool(tipo_forzado),
        "confianza_tipo": deteccion["confianza"],
        "senales_tipo": deteccion["senales"],
        "titulo": doc.titulo,
        "h1": deteccion.get("h1"),
        "palabras_principal": ev.extractabilidad.get("palabras_principal"),
        "fecha_principal": ev.frescura.get("fecha_principal"),
        "antiguedad_dias": ev.frescura.get("antiguedad_dias"),
        "schema_tipos": sch["tipos"],
        "datos_sin_fuente": ev.estadisticas["sin_fuente"],
        "dependencia_js": ev.tecnico["dependencia_js"]["veredicto"],
        "renderizado": renderizado,
        "palabras_sin_js": ev.tecnico["dependencia_js"]["palabras_principal_sin_js"],
        "palabras_con_js": ev.tecnico["dependencia_js"]["palabras_principal_con_js"],
        "placeholders": ev.tecnico["dependencia_js"].get("placeholders_plantilla", 0),
        "placeholders_principal": ev.tecnico["dependencia_js"].get("placeholders_principal", 0),
        "marcadores_framework": ev.tecnico["dependencia_js"]["marcadores_framework"],
        "fallas": [r.regla_id for r in resultados if r.estado == "falla"],
        "pasan": [r.regla_id for r in resultados if r.estado == "pasa"],
        "acerca_contacto": ev.entidad["acerca_contacto"],
        "ruta": urlparse(url).path or "/",
    }
    return {"evidencia": ev, "resultados": resultados, "registro": registro}


def evidencia_sitio(url_base: str, *, recoleccion_sitemap: dict[str, Any] | None, descargar: Callable[..., dict[str, Any]] | None = None, idiomas_esperados: list[str] | None = None, ahora: datetime | None = None, rutas: list[str] | None = None) -> EvidenciaSitio:
    descargar = descargar or fetch.descargar
    rob = robots.cargar_robots(url_base, descargar=descargar)
    acceso = evaluar_acceso(rob["parsed"], ruta="/")
    if rutas:
        bloqueos_por_ruta: dict[str, list[str]] = {}
        for ruta in rutas:
            a = evaluar_acceso(rob["parsed"], ruta=ruta)
            if a["resumen"]["busqueda_bloqueados"]:
                bloqueos_por_ruta[ruta] = a["resumen"]["busqueda_bloqueados"]
        acceso["resumen"]["busqueda_bloqueados_por_ruta"] = bloqueos_por_ruta
        for ruta, lista in bloqueos_por_ruta.items():
            for b in lista:
                if b not in acceso["resumen"]["busqueda_bloqueados"]:
                    acceso["resumen"]["busqueda_bloqueados"].append(f"{b} (en {ruta})")
    if recoleccion_sitemap is None:
        candidatos = list(rob["sitemaps"]) or [sitemap.url_sitemap_por_defecto(url_base)]
        recoleccion_sitemap = sitemap.recolectar_urls(candidatos[0], descargar=descargar, max_urls=100, max_sitemaps=5)
    return EvidenciaSitio(
        url=url_base,
        host=_host(url_base),
        robots={k: v for k, v in rob.items() if k != "parsed"} | {"parsed": rob["parsed"]},
        bots=acceso,
        sitemap=tecnico.analizar_sitemap(recoleccion_sitemap, ahora=ahora, declarado_en_robots=bool(rob.get("sitemaps"))),
        llmstxt=llmstxt.verificar(url_base, descargar=descargar),
        idiomas_esperados=idiomas_esperados or [],
    )


def construir_hallazgos(resultados: list[ResultadoRegla], reglas_idx: dict[str, Regla]) -> list[Hallazgo]:
    por_regla: dict[str, list[ResultadoRegla]] = {}
    for r in resultados:
        if r.estado == "falla":
            por_regla.setdefault(r.regla_id, []).append(r)
    hallazgos = []
    for i, (rid, lista) in enumerate(sorted(por_regla.items()), 1):
        regla = reglas_idx.get(rid)
        if regla is None:
            continue
        hallazgos.append(hallazgo_desde_resultado(regla, lista, indice=i))
    return priorizar(hallazgos)


def correr(
    *,
    urls: list[str],
    url_base: str | None = None,
    contexto: dict[str, Any] | None = None,
    tipo_forzado: str | None = None,
    descargar: Callable[..., dict[str, Any]] | None = None,
    render_fn: Callable[[str], dict[str, Any]] | None = None,
    resolver: Callable[[str], dict[str, Any]] | None = None,
    recoleccion_sitemap: dict[str, Any] | None = None,
    corrida: str | None = None,
    dir_salidas: Path | str | None = None,
    dir_historial: Path | str | None = None,
    workers: int = 4,
    ahora: datetime | None = None,
    fecha: date | None = None,
    sufijo: str | None = None,
    comparar: Path | str | None = None,
    anexo_tecnico: bool = False,
    comparar_reglas: Path | str | None = None,
) -> dict[str, Any]:
    reglas = cargar_rulebook()
    reglas_idx = indice(reglas)
    contexto = contexto or contexto_mod.cargar()
    idiomas = contexto_mod.lista(contexto.get("campos", {}), "idiomas") if contexto.get("existe") else []
    url_base = url_base or urls[0]
    dominio = reporte.dominio_de(url_base)
    corrida = corrida or nueva_corrida(dominio)
    dir_salidas = Path(dir_salidas) if dir_salidas else RUTA_SALIDAS
    dir_tmp = dir_salidas / "tmp" / corrida
    dir_tmp.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        paginas = list(pool.map(lambda u: analizar_pagina(u, reglas=reglas, tipo_forzado=tipo_forzado, descargar=descargar, render_fn=render_fn, resolver=resolver, idiomas_esperados=idiomas, ahora=ahora), urls))

    rutas = [p["registro"]["ruta"] for p in paginas]
    sitio = evidencia_sitio(url_base, recoleccion_sitemap=recoleccion_sitemap, descargar=descargar, idiomas_esperados=idiomas, ahora=ahora, rutas=rutas)
    sitio.acerca_contacto = {
        "acerca_presente": any(p["registro"]["acerca_contacto"].get("acerca_presente") for p in paginas),
        "contacto_presente": any(p["registro"]["acerca_contacto"].get("contacto_presente") for p in paginas),
        "acerca": sorted({a for p in paginas for a in p["registro"]["acerca_contacto"].get("acerca", [])})[:5],
        "contacto": sorted({a for p in paginas for a in p["registro"]["acerca_contacto"].get("contacto", [])})[:5],
    }
    resultados = evaluar_sitio(sitio, reglas)
    for p in paginas:
        resultados.extend(p["resultados"])
    hallazgos = construir_hallazgos(resultados, reglas_idx)
    puntaje = puntaje_cumplimiento(resultados, reglas_idx)

    sitio_dict = {
        "url": sitio.url,
        "host": sitio.host,
        "robots": {k: v for k, v in sitio.robots.items() if k not in ("parsed", "texto")},
        "bots": sitio.bots,
        "sitemap": sitio.sitemap,
        "llmstxt": sitio.llmstxt,
        "acerca_contacto": sitio.acerca_contacto,
        "avisos": tecnico.avisos_sitio(sitio.robots, sitio.sitemap),
    }
    registros = [p["registro"] for p in paginas]
    supuestos = []
    if tipo_forzado:
        supuestos.append(f"Tipo de página forzado a '{tipo_forzado}' para todas las URL.")
    if not any(p["evidencia"].tecnico["dependencia_js"]["render_disponible"] for p in paginas):
        supuestos.append("Sin render con JavaScript (Playwright no disponible o no solicitado): la dependencia de JavaScript se evalúa por heurística.")
        con_js = [p["registro"]["url"] for p in paginas if p["evidencia"].tecnico["dependencia_js"]["veredicto"] == "probable_dependencia"]
        if con_js:
            supuestos.append(f"{len(con_js)} URL dependen probablemente de JavaScript y su contenido no se pudo evaluar (reglas de extractabilidad, schema y entidad marcadas sin evidencia): " + ", ".join(con_js) + ". Repite con --render para auditarlas.")
    if resolver is None:
        supuestos.append("sameAs no verificados en red (usa --resolver-sameas).")

    payload = reporte.construir(
        modulo="audit",
        dominio=dominio,
        urls=registros,
        hallazgos=hallazgos,
        resultados=resultados,
        reglas=reglas_idx,
        puntaje=puntaje,
        sitio=sitio_dict,
        contexto=contexto,
        supuestos=supuestos,
        fecha=fecha,
        comparar=comparar,
        anexo_tecnico=anexo_tecnico,
        comparar_reglas=comparar_reglas,
    )
    payload["meta"]["corrida"] = corrida
    payload["meta"]["sufijo"] = sufijo
    payload["meta"]["dir_tmp"] = str(dir_tmp)

    # archivos por vector para los subagentes
    archivos_vector = {}
    for cat in CATEGORIAS_AUDIT:
        resumen = resumen_por_vector(resultados, reglas_idx, cat)
        resumen["guia"] = referencias.guia()
        resumen["nota_lectura"] = "Este archivo es la única entrada del subagente: trae las reglas completas de su categoría con fuentes y extractos de referencia, el resultado por URL y la guía de etiquetas. No hace falta abrir el rulebook, las referencias ni el reporte."
        resumen["contexto"] = {
            "dominio": dominio,
            "corrida": corrida,
            "n_urls": len(urls),
            "tipos_de_pagina": sorted({r["tipo"] for r in registros}),
            "negocio": {k: contexto.get("campos", {}).get(k) for k in ("nombre", "descripcion_oficial", "icp", "geografia", "idiomas", "crm")},
            "contexto_valido": contexto.get("valido", False),
        }
        if cat == "tecnico":
            resumen["sitio"] = sitio_dict
        if cat == "entidad":
            n04 = reglas_idx.get("N-04")
            resumen["sitio"] = {
                "acerca_contacto": sitio.acerca_contacto,
                "llmstxt": sitio.llmstxt | ({"regla_relacionada": {"regla_id": "N-04", "categoria": n04["categoria"], "enunciado": n04["enunciado"], "recomendacion": n04.get("recomendacion", ""), "fuentes": [{"titulo": f.get("titulo", ""), "url": f.get("url", ""), "nota": f.get("nota", "")} for f in n04.get("fuentes") or []], "referencias": referencias.extractos_para(n04), "nota": "Regla de anti-patrón, no puntúa y no es de tu categoría: solo para que no la busques fuera. llms.txt ausente es a lo sumo una nota de prioridad baja."}} if n04 else {}),
            }
        if cat == "extractabilidad":
            resumen["muestras_texto"] = muestras_texto(paginas)
            resumen["nota_muestras"] = "Encabezados y párrafos del contenido principal por URL (hasta %d URL, priorizando las que fallan reglas X-*); úsalos en lugar de descargar el HTML." % MAX_URLS_MUESTRA
        resumen["hallazgos_actuales"] = [h.a_dict() for h in hallazgos if h.categoria == cat]
        ruta = dir_tmp / f"{cat}.json"
        ruta.write_text(json.dumps(resumen, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        archivos_vector[cat] = str(ruta)
    payload["meta"]["archivos_vector"] = archivos_vector

    nombre = reporte.nombre_archivo(dominio, "audit", date.fromisoformat(payload["meta"]["fecha"])) + (f"_{reporte._slug(sufijo)}" if sufijo else "")
    rutas_salida = reporte.escribir(payload, directorio=dir_salidas, nombre=nombre)
    payload["meta"]["archivos"] = rutas_salida
    (dir_tmp / "meta.json").write_text(json.dumps({"corrida": corrida, "dominio": dominio, "archivos": rutas_salida, "archivos_vector": archivos_vector, "fecha": payload["meta"]["fecha"]}, ensure_ascii=False, indent=2), encoding="utf-8")

    # snapshot para monitor
    dir_historial = Path(dir_historial) if dir_historial else RUTA_DATOS / "historial"
    dir_historial.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "fecha": payload["meta"]["fecha"],
        "corrida": corrida,
        "dominio": dominio,
        "modulo": "audit",
        "version_skill": VERSION,
        "puntaje": puntaje,
        "resultados": [{"regla_id": r.regla_id, "url": r.url, "estado": r.estado, "observacion": r.observacion} for r in resultados],
        "urls": [{"url": r["url"], "tipo": r["tipo"], "fecha_principal": r["fecha_principal"], "antiguedad_dias": r["antiguedad_dias"]} for r in registros],
    }
    ruta_snapshot = dir_historial / reporte.nombre_snapshot(dominio, "audit", corrida, date.fromisoformat(payload["meta"]["fecha"]))
    ruta_snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    payload["meta"]["snapshot"] = str(ruta_snapshot)
    return payload


MAX_URLS_MUESTRA = 10


def muestras_texto(paginas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Muestras de texto por URL para el subagente de extractabilidad: H1, encabezados y párrafos con posición."""
    def fallas_x(p: dict[str, Any]) -> int:
        return sum(1 for r in p["resultados"] if r.regla_id.startswith("X-") and r.estado == "falla")

    elegidas = sorted(paginas, key=lambda p: (-fallas_x(p), p["registro"]["url"]))[:MAX_URLS_MUESTRA]
    out = []
    for p in elegidas:
        x = p["evidencia"].extractabilidad
        m = x.get("muestra", {})
        out.append({
            "url": p["registro"]["url"],
            "tipo": p["registro"]["tipo"],
            "h1": x.get("jerarquia", {}).get("h1_texto") or p["registro"].get("h1") or "",
            "apertura": x.get("respuesta_directa", {}).get("oraciones", []),
            "encabezados": m.get("encabezados", []),
            "parrafos": m.get("parrafos", []),
            "parrafos_total": m.get("parrafos_total", 0),
        })
    return out


# ------------------------------------------------------------------ fusionar
CAMPOS_HALLAZGO_SUBAGENTE = ("regla_id", "titulo", "detalle", "recomendacion", "evidencia_observacion")


def validar_salida_subagente(datos: dict[str, Any]) -> list[str]:
    errores = []
    if not isinstance(datos, dict) or "hallazgos" not in datos:
        return ["la salida debe ser un objeto con la clave 'hallazgos'"]
    for i, h in enumerate(datos.get("hallazgos") or []):
        for c in CAMPOS_HALLAZGO_SUBAGENTE:
            if not h.get(c):
                errores.append(f"hallazgo {i}: falta {c}")
        if h.get("evidencia_observacion") not in ("Confirmado", "Probable", "Hipótesis"):
            errores.append(f"hallazgo {i}: evidencia_observacion inválida")
        if re.search(r"\+\s?\d+\s?(%|puntos)|impacto proyectado", (h.get("detalle", "") + h.get("recomendacion", "")), re.I):
            errores.append(f"hallazgo {i}: contiene impacto proyectado numérico (prohibido)")
    for a in datos.get("ajustes") or []:
        if not a.get("hallazgo_id") or a.get("evidencia_observacion") not in ("Confirmado", "Probable", "Hipótesis"):
            errores.append("ajuste inválido: requiere hallazgo_id y evidencia_observacion válida")
    return errores


def estados_por_regla(resultados: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """{regla_id: {url: estado}} a partir de los resultados de la corrida."""
    out: dict[str, dict[str, str]] = {}
    for r in resultados:
        out.setdefault(r["regla_id"], {})[r["url"]] = r["estado"]
    return out


def motivo_rechazo(hallazgo: dict[str, Any], estados: dict[str, dict[str, str]]) -> str | None:
    """Un hallazgo de subagente solo procede de una regla que falla o que requiere juicio.

    Si la regla tiene resultado en la corrida y ese resultado es `pasa` en todas las URL
    relevantes (las afectadas por el hallazgo o, si ninguna coincide, todas las evaluadas),
    se rechaza: un aviso sobre una regla que se cumple no es un hallazgo.
    """
    por_url = estados.get(hallazgo["regla_id"]) or {}
    if not por_url:
        return None  # regla sin resultado en la corrida (sin colector, por ejemplo): la juzga el subagente
    urls = [u for u in (hallazgo.get("urls_afectadas") or []) if u in por_url]
    relevantes = {u: por_url[u] for u in urls} if urls else por_url
    if all(e == "pasa" for e in relevantes.values()):
        donde = ", ".join(relevantes) if len(relevantes) <= 3 else f"{len(relevantes)} URL"
        return f"La regla {hallazgo['regla_id']} tiene resultado 'pasa' en {donde}; un aviso sobre una regla que se cumple no es un hallazgo."
    return None


def fusionar(ruta_json_reporte: Path | str, salidas_subagentes: list[dict[str, Any]], *, dir_salidas: Path | str | None = None) -> dict[str, Any]:
    """Incorpora hallazgos y ajustes de los subagentes y regenera el reporte."""
    ruta_json_reporte = Path(ruta_json_reporte)
    payload = json.loads(ruta_json_reporte.read_text(encoding="utf-8"))
    reglas_idx = indice(cargar_rulebook())
    hallazgos = [Hallazgo(**h) for h in payload["hallazgos"]] + [Hallazgo(**h) for h in payload.get("no_evaluables") or []]
    por_id = {h.id: h for h in hallazgos}
    notas: list[str] = []
    rechazados: list[dict[str, Any]] = []
    estados = estados_por_regla(payload["resultados"])
    for salida in salidas_subagentes:
        errores = validar_salida_subagente(salida)
        if errores:
            raise ValueError("salida de subagente inválida: " + "; ".join(errores))
        aceptados = []
        for nh in salida.get("hallazgos") or []:
            motivo = motivo_rechazo(nh, estados)
            if motivo:
                rechazados.append({"vector": salida.get("vector", ""), "regla_id": nh["regla_id"], "titulo": nh.get("titulo", ""), "urls": list(nh.get("urls_afectadas") or []), "motivo": motivo})
            else:
                aceptados.append(nh)
        salida = dict(salida) | {"hallazgos": aceptados}
        for a in salida.get("ajustes") or []:
            h = por_id.get(a["hallazgo_id"])
            if h:
                h.evidencia_observacion = a["evidencia_observacion"]
                if a.get("motivo"):
                    h.detalle += f" Ajuste del subagente: {a['motivo']}"
                for campo in ("impacto_esperado", "esfuerzo", "horizonte"):
                    if a.get(campo):
                        setattr(h, campo, a[campo])
        for i, nh in enumerate(salida.get("hallazgos") or [], 1):
            regla = reglas_idx.get(nh["regla_id"])
            if regla is None:
                continue
            existente = next((h for h in hallazgos if h.regla_id == nh["regla_id"] and h.origen == "colector"), None)
            if existente and not nh.get("nuevo"):
                existente.detalle += f" Nota del subagente: {nh['detalle']}"
                if nh.get("recomendacion"):
                    existente.recomendacion = nh["recomendacion"]
                continue
            fuente = (regla.get("fuentes") or [{}])[0]
            hallazgos.append(Hallazgo(
                id=f"{nh['regla_id']}-S{i:02d}",
                regla_id=nh["regla_id"],
                categoria=regla["categoria"],
                tipo_pagina=nh.get("tipo_pagina", ""),
                url=(nh.get("urls_afectadas") or [payload["sitio"].get("url", "")])[0],
                evidencia_observacion=nh["evidencia_observacion"],
                fuerza_regla=regla["fuerza"],
                tipo_evidencia=regla["tipo_evidencia"],
                impacto_esperado=nh.get("impacto_esperado") or regla.get("impacto_esperado", "medio"),
                esfuerzo=nh.get("esfuerzo") or regla.get("esfuerzo", "medio"),
                dependencia=nh.get("dependencia") or regla.get("dependencia", ""),
                horizonte=nh.get("horizonte") or regla.get("horizonte") or "90d",
                titulo=nh["titulo"],
                detalle=nh["detalle"],
                evidencia=nh.get("evidencia") or [],
                recomendacion=nh["recomendacion"],
                fuente={"titulo": fuente.get("titulo", ""), "url": fuente.get("url", "")},
                urls_afectadas=nh.get("urls_afectadas") or [],
                origen="subagente",
            ))
        notas.extend(salida.get("notas") or [])
    hallazgos = priorizar(hallazgos)
    resultados = [ResultadoRegla(**r) for r in payload["resultados"]]
    contexto = {"valido": payload["meta"].get("contexto_valido", False), "faltantes_criticos": []}
    supuestos = [s for s in payload.get("supuestos", []) if not s.startswith("Contexto de negocio incompleto")]
    nuevo = reporte.construir(
        modulo=payload["meta"]["modulo"],
        dominio=payload["meta"]["dominio"],
        urls=payload["urls"],
        hallazgos=hallazgos,
        resultados=resultados,
        reglas=reglas_idx,
        puntaje=payload["puntaje_cumplimiento"],
        sitio=payload["sitio"],
        contexto=contexto if contexto["valido"] else {"valido": False, "faltantes_criticos": ["ver contexto/negocio.md"]},
        supuestos=supuestos + [f"Nota de subagente: {n}" for n in notas] + [f"Rechazado por fusionar ({r['vector']}, {r['regla_id']}): '{r['titulo']}'. {r['motivo']}" for r in rechazados],
        metricas_visibilidad=payload.get("metricas_visibilidad"),
        kpis=payload.get("kpis"),
        metodo_extra="Hallazgos enriquecidos por subagentes (origen 'subagente').",
        fecha=date.fromisoformat(payload["meta"]["fecha"]),
        comparar=payload["meta"].get("comparar"),
        anexo_tecnico=bool(payload["meta"].get("anexo_tecnico")),
        comparar_reglas=payload["meta"].get("comparar_reglas"),
    )
    nuevo["meta"].update({k: v for k, v in payload["meta"].items() if k not in nuevo["meta"]})
    nuevo["meta"]["fusion"] = {"n_rechazados": len(rechazados), "rechazados": rechazados, "vectores": [s.get("vector", "") for s in salidas_subagentes]}
    rutas = reporte.escribir(nuevo, directorio=Path(dir_salidas) if dir_salidas else ruta_json_reporte.parent, nombre=ruta_json_reporte.stem)
    nuevo["meta"]["archivos"] = rutas
    return nuevo
