"""Modelo de resultados por regla, hallazgos, priorización y puntaje de cumplimiento.

Estructura derivada de las dataclasses de scripts/audit.py de best-aeo-skill
(MIT, ver NOTICE), sin penalizaciones fijas ni "impacto proyectado".
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from .reglas import Regla

OBSERVACIONES = ("Confirmado", "Probable", "Hipótesis")
ESTADOS = ("pasa", "falla", "no_aplica", "sin_evidencia", "sin_colector")
ORDEN_IMPACTO = {"alto": 0, "medio": 1, "bajo": 2}
ORDEN_ESFUERZO = {"bajo": 0, "medio": 1, "alto": 2}
ORDEN_OBS = {"Confirmado": 0, "Probable": 1, "Hipótesis": 2}
ORDEN_FUERZA = {"A": 0, "B": 1, "C": 2}


@dataclass
class ResultadoRegla:
    """Resultado de evaluar una regla sobre una URL (o sobre el sitio)."""

    regla_id: str
    url: str
    estado: str                      # pasa | falla | no_aplica | sin_evidencia | sin_colector
    observacion: str = "Confirmado"  # Confirmado | Probable | Hipótesis
    detalle: str = ""
    evidencia: list[dict[str, Any]] = field(default_factory=list)
    tipo_pagina: str = ""
    colector: str = ""

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Hallazgo:
    id: str
    regla_id: str
    categoria: str
    tipo_pagina: str
    url: str
    evidencia_observacion: str
    fuerza_regla: str
    tipo_evidencia: str
    impacto_esperado: str
    esfuerzo: str
    dependencia: str
    horizonte: str
    titulo: str
    detalle: str
    evidencia: list[dict[str, Any]]
    recomendacion: str
    fuente: dict[str, Any]
    urls_afectadas: list[str] = field(default_factory=list)
    origen: str = "colector"   # colector | subagente | humano

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    def etiqueta(self) -> str:
        nombres = {
            "requisito_oficial": "requisito oficial",
            "efecto_experimental": "experimental",
            "correlacional": "correlacional",
            "consenso": "consenso",
        }
        return f"{self.evidencia_observacion} · {self.fuerza_regla} · {nombres.get(self.tipo_evidencia, self.tipo_evidencia)}"


DEPENDENCIAS_INTERNAS = ("", "ninguna", "propio", "contenido", "desarrollo", "analitica")


def horizonte_para(impacto: str, esfuerzo: str, dependencia: str) -> str:
    if esfuerzo == "bajo" and impacto in ("alto", "medio") and dependencia in DEPENDENCIAS_INTERNAS:
        return "30d"
    if esfuerzo == "alto":
        return "largo"
    return "90d"


def hallazgo_desde_resultado(regla: Regla, resultados: list[ResultadoRegla], *, indice: int) -> Hallazgo:
    """Crea un hallazgo agrupando los resultados fallidos de una misma regla."""
    urls = [r.url for r in resultados]
    obs = min((r.observacion for r in resultados), key=lambda o: ORDEN_OBS[o])
    evidencia: list[dict[str, Any]] = []
    for r in resultados[:5]:
        for e in r.evidencia[:3]:
            e = dict(e)
            e.setdefault("url", r.url)
            evidencia.append(e)
    detalles = list(dict.fromkeys(r.detalle for r in resultados if r.detalle))
    detalle = "; ".join(detalles[:2]) + (f" (y {len(detalles) - 2} detalle(s) más en el JSON)" if len(detalles) > 2 else "")
    if len(resultados) > 1:
        detalle = f"{len(resultados)} URL afectadas. " + detalle
    impacto = regla.get("impacto_esperado", "medio")
    esfuerzo = regla.get("esfuerzo", "medio")
    dependencia = regla.get("dependencia", "")
    fuente_principal = (regla.get("fuentes") or [{}])[0]
    return Hallazgo(
        id=f"{regla['id']}-{indice:03d}",
        regla_id=regla["id"],
        categoria=regla["categoria"],
        tipo_pagina=resultados[0].tipo_pagina,
        url=urls[0],
        evidencia_observacion=obs,
        fuerza_regla=regla["fuerza"],
        tipo_evidencia=regla["tipo_evidencia"],
        impacto_esperado=impacto,
        esfuerzo=esfuerzo,
        dependencia=dependencia,
        horizonte=regla.get("horizonte") or horizonte_para(impacto, esfuerzo, dependencia),
        titulo=regla.get("titulo_hallazgo") or regla["enunciado"],
        detalle=detalle[:1200],
        evidencia=evidencia,
        recomendacion=regla.get("recomendacion", ""),
        fuente={"titulo": fuente_principal.get("titulo", ""), "url": fuente_principal.get("url", "")},
        urls_afectadas=urls,
    )


def priorizar(hallazgos: list[Hallazgo]) -> list[Hallazgo]:
    return sorted(
        hallazgos,
        key=lambda h: (
            ORDEN_IMPACTO.get(h.impacto_esperado, 9),
            ORDEN_ESFUERZO.get(h.esfuerzo, 9),
            ORDEN_OBS.get(h.evidencia_observacion, 9),
            ORDEN_FUERZA.get(h.fuerza_regla, 9),
            -len(h.urls_afectadas),
            h.regla_id,
        ),
    )


def agrupar_por_horizonte(hallazgos: list[Hallazgo]) -> dict[str, list[Hallazgo]]:
    out: dict[str, list[Hallazgo]] = {"30d": [], "90d": [], "largo": []}
    for h in hallazgos:
        out.setdefault(h.horizonte, []).append(h)
    return out


def puntaje_cumplimiento(resultados: list[ResultadoRegla], reglas: dict[str, Regla]) -> dict[str, Any]:
    """Porcentaje ponderado de verificaciones aplicables superadas, por categoría y global.

    Excluye reglas sin puntaje (principio, método, anti-patrón), resultados
    no aplicables o sin evidencia, y observaciones marcadas Hipótesis.
    """
    acumulado: dict[str, dict[str, float]] = defaultdict(lambda: {"superado": 0.0, "aplicable": 0.0, "reglas": 0})
    vistas: dict[str, set[str]] = defaultdict(set)
    for r in resultados:
        regla = reglas.get(r.regla_id)
        if regla is None or not regla.puntua:
            continue
        if r.estado not in ("pasa", "falla") or r.observacion == "Hipótesis":
            continue
        cat = regla["categoria"]
        acumulado[cat]["aplicable"] += regla.peso
        if r.estado == "pasa":
            acumulado[cat]["superado"] += regla.peso
        vistas[cat].add(r.regla_id)
    salida: dict[str, Any] = {"por_categoria": {}, "global": None, "leyenda": "Cumplimiento de verificaciones aplicables; no es una predicción de visibilidad."}
    tot_sup = tot_apl = 0.0
    for cat, v in acumulado.items():
        tot_sup += v["superado"]
        tot_apl += v["aplicable"]
        salida["por_categoria"][cat] = {
            "puntaje": round(100 * v["superado"] / v["aplicable"]) if v["aplicable"] else None,
            "reglas_evaluadas": len(vistas[cat]),
        }
    salida["global"] = round(100 * tot_sup / tot_apl) if tot_apl else None
    return salida


MAX_RESULTADOS_CON_EVIDENCIA = 10


def resumen_por_vector(resultados: list[ResultadoRegla], reglas: dict[str, Regla], categoria: str, *, max_ejemplos: int = 3) -> dict[str, Any]:
    """Entrada completa de un subagente: las reglas de la categoría evaluadas en la corrida, con su texto, fuentes con URL,
    extractos de referencia, conteos por tipo de página, ejemplos y el resultado de la verificación en cada URL.
    El subagente no necesita abrir el rulebook ni las referencias."""
    from . import referencias  # import local para evitar ciclos

    evaluadas = {r.regla_id for r in resultados}
    por_regla: dict[str, dict[str, Any]] = {}
    for rid, regla in reglas.items():
        if regla["categoria"] != categoria or rid not in evaluadas:
            continue  # solo viajan las reglas evaluadas en esta corrida (aplicables a los tipos de página presentes)
        por_regla[rid] = {
            "regla_id": rid,
            "categoria": regla["categoria"],
            "ambito": regla.get("ambito", ""),
            "tipos_pagina": list(regla.get("tipos_pagina") or ["todas"]),
            "enunciado": regla["enunciado"],
            "titulo_hallazgo": regla.get("titulo_hallazgo", ""),
            "fuerza": regla.etiqueta_fuerza(),
            "fuerza_letra": regla["fuerza"],
            "tipo_evidencia": regla["tipo_evidencia"],
            "puntua": regla.puntua,
            "colector": regla.get("colector", ""),
            "fuentes": [{"titulo": f.get("titulo", ""), "url": f.get("url", ""), "fuerza": f.get("fuerza", regla["fuerza"]), "tipo_evidencia": f.get("tipo_evidencia", regla["tipo_evidencia"]), "nota": f.get("nota", "")} for f in (regla.get("fuentes") or [])],
            "referencias": referencias.extractos_para(regla),
            "impacto_esperado": regla.get("impacto_esperado", "medio"),
            "esfuerzo": regla.get("esfuerzo", "medio"),
            "dependencia": regla.get("dependencia", ""),
            "recomendacion": regla.get("recomendacion", ""),
            "verificado_el": regla.get("verificado_el", ""),
            "por_tipo": defaultdict(lambda: {"pasa": 0, "falla": 0, "no_aplica": 0, "sin_evidencia": 0, "sin_colector": 0}),
            "ejemplos_falla": [],
            "ejemplos_pasa": [],
            "ejemplos_sin_evidencia": [],
            "observacion_minima": "Confirmado",
            "resultados_por_url": [],
        }
    for r in resultados:
        entrada = por_regla.get(r.regla_id)
        if entrada is None:
            continue
        tipo = r.tipo_pagina or "sitio"
        entrada["por_tipo"][tipo][r.estado] += 1
        if ORDEN_OBS[r.observacion] > ORDEN_OBS[entrada["observacion_minima"]]:
            entrada["observacion_minima"] = r.observacion
        destino = {"falla": entrada["ejemplos_falla"], "pasa": entrada["ejemplos_pasa"], "sin_evidencia": entrada["ejemplos_sin_evidencia"]}.get(r.estado)
        if destino is not None and len(destino) < max_ejemplos:
            destino.append({"url": r.url, "detalle": r.detalle[:300], "evidencia": r.evidencia[:2], "observacion": r.observacion})
        con_evidencia = sum(1 for x in entrada["resultados_por_url"] if x.get("evidencia")) < MAX_RESULTADOS_CON_EVIDENCIA
        entrada["resultados_por_url"].append({
            "url": r.url,
            "tipo_pagina": tipo,
            "estado": r.estado,
            "observacion": r.observacion,
            "detalle": r.detalle,
            "colector": r.colector,
            "evidencia": r.evidencia if con_evidencia else [],
        })
    # Un extracto largo (Princeton, categorías de bots) va completo junto a la primera regla que lo cita;
    # las siguientes reglas del mismo archivo lo señalan por id de regla, no por ruta.
    primera_con: dict[str, str] = {}
    for e in por_regla.values():
        e["por_tipo"] = {k: dict(v) for k, v in e["por_tipo"].items()}
        for ref in e["referencias"]:
            if len(ref["texto"]) < 600:
                continue
            if ref["titulo"] in primera_con:
                ref["texto"] = f"Mismo extracto que en la regla {primera_con[ref['titulo']]} de este archivo."
                ref["ver_regla"] = primera_con[ref["titulo"]]
            else:
                primera_con[ref["titulo"]] = e["regla_id"]
    return {"categoria": categoria, "reglas": list(por_regla.values())}
