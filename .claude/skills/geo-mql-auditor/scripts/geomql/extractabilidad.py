"""Vector de extractabilidad: respuesta directa, jerarquía, tablas y listas, definiciones, párrafos, proporción de contenido principal, imágenes, FAQ visible, ejemplos y densidad de términos."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .html import Documento, contar_palabras, oraciones, texto_de

STOPWORDS = set("""
a al algo alguna algunas alguno algunos ante antes como con contra cual cuales cuando de del desde donde dos e el ella ellas ellos en entre era erais eran eras eres es esa esas ese eso esos esta estaba estaban estado estados estamos estan estar estas este esto estos fue fueron ha habia han hasta hay la las le les lo los mas me mi mis mucho muy nada ni no nos nosotros o os otra otras otro otros para pero poco por porque que quien quienes se sea ser si sin sobre son su sus tambien te tener tiene tienen todo todos tu tus un una uno unos y ya yo
the of and to in for on with as by at from that this is are be or an it its into your you we our they their can will not
""".split())
_DEF_RE = re.compile(r"^(?:el|la|los|las|un|una|unos|unas|the|a|an)?\s*(?P<termino>[^,.;:]{2,60}?)\s+(?:es|son|consiste en|se define como|significa|is|are|refers to|means)\b", re.I)
_EJEMPLO_RE = re.compile(r"\b(por ejemplo|p\. ?ej\.|ejemplo:|un ejemplo|caso de|caso de éxito|caso práctico|case study|for example|e\.g\.)\b", re.I)
_PREGUNTA_RE = re.compile(r"[?¿]")
_PALABRA_RE = re.compile(r"[a-záéíóúñü]{4,}", re.I)


MAX_PARRAFOS_MUESTRA = 40
MAX_CHARS_MUESTRA = 400


def _con_posicion(textos: list[str], prefijo: str, *, limite: int = MAX_CHARS_MUESTRA) -> list[dict[str, Any]]:
    return [{"posicion": f"{prefijo} #{i}", "texto": t[:limite]} for i, t in enumerate(textos, 1)]


def _oraciones_con(parrafos_pos: list[dict[str, Any]], patron: "re.Pattern[str]", *, maximo: int = 3) -> list[dict[str, Any]]:
    """Oraciones que cumplen el patrón, con la posición del párrafo donde aparecen."""
    out: list[dict[str, Any]] = []
    for p in parrafos_pos:
        for o in oraciones(p["texto"]):
            if patron.search(o):
                out.append({"posicion": p["posicion"], "texto": o.strip()[:MAX_CHARS_MUESTRA]})
                if len(out) >= maximo:
                    return out
    return out


def _terminos(texto: str) -> set[str]:
    return {w.lower() for w in _PALABRA_RE.findall(texto) if w.lower() not in STOPWORDS}


def _primeras_oraciones(doc: Documento, n: int = 3) -> tuple[list[str], str]:
    """Primeras oraciones del contenido principal tras el H1, saltando byline y breadcrumb, y la posición del párrafo usado."""
    parrafos = doc.parrafos(solo_principal=True)
    texto = ""
    posicion = "contenido principal"
    for i, p in enumerate(parrafos, 1):
        if re.match(r"^(por|by)\s+[A-ZÁÉÍÓÚ]", p, re.I) and len(p.split()) < 30:
            continue  # byline
        if len(p.split()) < 6:
            continue
        if re.match(r"^(actualizad[oa]|publicad[oa]|última actualización|ultima actualizacion|updated|published|last updated)\b", p, re.I) and len(p.split()) < 14:
            continue  # solo fecha etiquetada
        texto = p
        posicion = f"p #{i}"
        break
    if not texto:
        texto = doc.texto_principal()
    return oraciones(texto)[:n], posicion


def analizar(doc: Documento, *, tipo_pagina: str = "otra") -> dict[str, Any]:
    encabezados = doc.encabezados(solo_principal=True)
    contador_niveles: Counter[int] = Counter()
    encabezados_pos: list[dict[str, Any]] = []
    for e in encabezados:
        contador_niveles[e["nivel"]] += 1
        encabezados_pos.append({"posicion": f"h{e['nivel']} #{contador_niveles[e['nivel']]}", "nivel": e["nivel"], "texto": e["texto"][:MAX_CHARS_MUESTRA]})
    h1 = next((e["texto"] for e in encabezados if e["nivel"] == 1), "") or doc.titulo
    texto_principal = doc.texto_principal()
    palabras_principal = contar_palabras(texto_principal)
    palabras_total = contar_palabras(doc.texto(excluir_boilerplate=False))
    parrafos = doc.parrafos()
    parrafos_pos = _con_posicion(parrafos, "p")

    # respuesta directa
    primeras, posicion_apertura = _primeras_oraciones(doc)
    terminos_h1 = _terminos(h1)
    terminos_inicio = _terminos(" ".join(primeras))
    comparte = len(terminos_h1 & terminos_inicio)
    tiene_definicion = any(_DEF_RE.match(o.strip()) for o in primeras)
    palabras_inicio = contar_palabras(" ".join(primeras))
    respuesta_directa = {
        "oraciones": primeras,
        "posicion": posicion_apertura,
        "palabras": palabras_inicio,
        "terminos_compartidos_con_h1": comparte,
        "tiene_definicion": tiene_definicion,
        "empieza_con_pregunta": bool(primeras) and primeras[0].strip().startswith(("¿", "?")),
        "veredicto": bool(primeras) and 10 <= palabras_inicio <= 120 and (comparte >= 1 or tiene_definicion) and not (primeras[0].strip().startswith("¿")),
    }

    # jerarquía
    niveles = [e["nivel"] for e in encabezados]
    saltos = []
    anterior = 1
    for n in niveles:
        if n > anterior + 1:
            saltos.append(f"h{anterior}→h{n}")
        anterior = n
    h1_count = niveles.count(1)
    es_descriptivo = lambda e: len(e["texto"].split()) >= 3 or bool(_PREGUNTA_RE.search(e["texto"]))  # noqa: E731
    descriptivos = sum(1 for e in encabezados_pos if e["nivel"] >= 2 and es_descriptivo(e))
    subtitulos = sum(1 for e in encabezados_pos if e["nivel"] >= 2)
    no_descriptivos = [{"posicion": e["posicion"], "texto": e["texto"]} for e in encabezados_pos if e["nivel"] >= 2 and not es_descriptivo(e)]
    jerarquia = {
        "h1": h1_count,
        "h1_texto": h1,
        "h2": niveles.count(2),
        "h3": niveles.count(3),
        "saltos": saltos,
        "subtitulos_descriptivos": descriptivos,
        "subtitulos": subtitulos,
        "no_descriptivos": no_descriptivos,
        "veredicto": h1_count == 1 and not saltos and (subtitulos == 0 or descriptivos / subtitulos >= 0.6),
    }

    # tablas y listas
    tablas = doc.tablas()
    listas = doc.listas()
    comparacion_re = re.compile(r"\b(vs\.?|versus|comparad[oa]|comparativa|diferencias? entre)\b", re.I)
    pasos_re = re.compile(r"\b(paso \d|pasos|cómo (se )?(calcula|hace|configura)|how to)\b", re.I)
    tiene_comparacion = tipo_pagina == "comparativa" or bool(comparacion_re.search(texto_principal))
    tiene_pasos = bool(pasos_re.search(texto_principal))
    tablas_listas = {
        "oraciones": _oraciones_con(parrafos_pos, comparacion_re, maximo=2) + _oraciones_con(parrafos_pos, pasos_re, maximo=2),
        "tablas": len(tablas),
        "tablas_con_encabezado": sum(1 for t in tablas if t["con_encabezado"]),
        "listas": listas["ul"] + listas["ol"],
        "listas_ordenadas": listas["ol"],
        "items": listas["items"],
        "menciona_comparacion": tiene_comparacion,
        "menciona_pasos": tiene_pasos,
        "veredicto": (not tiene_comparacion or any(t["con_encabezado"] for t in tablas) or (listas["ul"] + listas["ol"]) >= 1)
        and (not tiene_pasos or listas["ol"] >= 1),
    }

    # definición
    definicion = None
    posicion_definicion = None
    for i, p in enumerate(parrafos[:4], 1):
        m = _DEF_RE.match(p.strip())
        if m and len(p.split()) >= 8:
            definicion = p[:240]
            posicion_definicion = f"p #{i}"
            break
    dl = listas["dl"]
    definicion_res = {"presente": bool(definicion) or dl > 0, "texto": definicion, "posicion": posicion_definicion, "listas_de_definicion": dl}

    # párrafos
    longitudes = [contar_palabras(p) for p in parrafos]
    largos = [l for l in longitudes if l > 100]
    largos_muestra = [{"posicion": f"p #{i}", "palabras": l, "texto": p[:600]} for i, (p, l) in enumerate(zip(parrafos, longitudes), 1) if l > 100][:3]
    mas_largo = max(enumerate(zip(parrafos, longitudes), 1), key=lambda x: x[1][1], default=None)
    parrafos_res = {
        "total": len(parrafos),
        "largos": len(largos),
        "largos_muestra": largos_muestra,
        "mas_largo": {"posicion": f"p #{mas_largo[0]}", "palabras": mas_largo[1][1], "texto": mas_largo[1][0][:MAX_CHARS_MUESTRA]} if mas_largo else None,
        "max_palabras": max(longitudes, default=0),
        "promedio": round(sum(longitudes) / len(longitudes), 1) if longitudes else 0,
    }

    # proporción de contenido principal
    proporcion = round(palabras_principal / palabras_total, 2) if palabras_total else 0.0
    proporcion_res = {"palabras_principal": palabras_principal, "palabras_total": palabras_total, "proporcion": proporcion, "veredicto": proporcion >= 0.5 or palabras_total < 120}

    # imágenes
    imgs = [i for i in doc.imagenes() if i["en_principal"]]
    sin_alt = [i["src"] for i in imgs if not (i["alt"] or "").strip()]
    sin_alt_pos = [{"posicion": f"img #{n}", "texto": i["src"]} for n, i in enumerate(imgs, 1) if not (i["alt"] or "").strip()][:5]
    con_alt_pos = [{"posicion": f"img #{n}", "texto": f"alt=\"{i['alt']}\" ({i['src']})"} for n, i in enumerate(imgs, 1) if (i["alt"] or "").strip()][:3]
    imagenes_res = {"en_principal": len(imgs), "sin_alt": sin_alt, "sin_alt_pos": sin_alt_pos, "con_alt_pos": con_alt_pos, "veredicto": not sin_alt}

    # FAQ visible
    preguntas_pos = [{"posicion": e["posicion"], "texto": e["texto"]} for e in encabezados_pos if e["nivel"] >= 2 and e["texto"].strip().endswith("?")]
    preguntas = [p["texto"] for p in preguntas_pos]
    faq_res = {"preguntas_en_encabezados": len(preguntas), "ejemplos": preguntas[:5], "ejemplos_pos": preguntas_pos[:5], "presente": len(preguntas) >= 2}

    # ejemplos
    ejemplos = _EJEMPLO_RE.findall(texto_principal)
    ejemplos_res = {"menciones": len(ejemplos), "presente": len(ejemplos) >= 1, "oraciones": _oraciones_con(parrafos_pos, _EJEMPLO_RE)}

    # densidad de términos (keyword stuffing)
    palabras = [w.lower() for w in _PALABRA_RE.findall(texto_principal) if w.lower() not in STOPWORDS]
    conteo = Counter(palabras)
    top = conteo.most_common(3)
    densidad_top = round(top[0][1] / max(len(palabras), 1), 3) if top else 0.0
    densidad_res = {
        "termino_top": top[0][0] if top else None,
        "frecuencia_top": top[0][1] if top else 0,
        "densidad_top": densidad_top,
        "top3": top,
        "oraciones_muestra": _oraciones_con(parrafos_pos, re.compile(r"\b" + re.escape(top[0][0]) + r"\b", re.I), maximo=2) if top else [],
        "veredicto": not (palabras_principal >= 200 and densidad_top > 0.04 and top[0][1] >= 12),
    }

    # apertura: párrafos con los que se sustentan los hallazgos de ausencia (sin cita, sin fecha, sin ejemplo, sin definición)
    apertura = parrafos_pos[:3] or ([{"posicion": "contenido principal", "texto": texto_principal[:MAX_CHARS_MUESTRA]}] if texto_principal.strip() else [])

    return {
        "muestra": {"encabezados": encabezados_pos, "parrafos": parrafos_pos[:MAX_PARRAFOS_MUESTRA], "parrafos_total": len(parrafos)},
        "apertura": apertura,
        "respuesta_directa": respuesta_directa,
        "jerarquia": jerarquia,
        "tablas_listas": tablas_listas,
        "definicion": definicion_res,
        "parrafos": parrafos_res,
        "proporcion_principal": proporcion_res,
        "imagenes": imagenes_res,
        "faq_visible": faq_res,
        "ejemplos": ejemplos_res,
        "densidad_terminos": densidad_res,
        "palabras_principal": palabras_principal,
    }
