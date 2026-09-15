"""Detección del tipo de página: home, solucion, articulo, comparativa, faq, glosario, landing, local, perfil, programa, institucional, otra.

Devuelve el tipo, la confianza y las señales que lo sustentan. Se puede forzar
con --tipo en el CLI. Cada regla del rulebook se aplica solo a sus tipos.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .html import Documento, contar_palabras
from .schema import tipos_en_jsonld

_ART_TIPOS = {"Article", "BlogPosting", "NewsArticle", "TechArticle", "ScholarlyArticle", "Report"}
_RE = {
    "articulo": re.compile(r"/(blog|articulo|articulos|noticias|news|post|posts|recursos|insights|guia|guias|casos)(/|$)", re.I),
    "comparativa": re.compile(r"(/comparativa|/comparativas|/vs-|-vs-|/versus|/alternativas|/alternatives|/mejores-|/best-|/comparison)", re.I),
    "faq": re.compile(r"/(faq|faqs|preguntas-frecuentes|preguntas|ayuda|help)(/|$)", re.I),
    "glosario": re.compile(r"/(glosario|glossary|diccionario|que-es|definicion|definiciones)(/|$)", re.I),
    "solucion": re.compile(r"/(producto|productos|product|products|solucion|soluciones|solution|solutions|servicio|servicios|service|services|plataforma|platform|software|precios|pricing|planes|plans|features|funciones)(/|$)", re.I),
    "landing": re.compile(r"/(lp|landing|campana|campaign|descarga|download|webinar|demo|registro|signup|cotiza|cotizacion)(/|$)", re.I),
    "local": re.compile(r"/(sucursal|sucursales|oficina|oficinas|ubicacion|ubicaciones|locations|location|contacto-[a-z]+|ciudad)(/|$)", re.I),
    "perfil": re.compile(r"/(equipo|team|autor|autores|author|authors|perfil|profile|nosotros/[a-z])(/|$)", re.I),
    # programa educativo: carrera, prepa, posgrado, diplomado, curso o certificado, y sus catálogos
    "programa": re.compile(r"/(licenciatura|licenciaturas|ingenieria|ingenierias|carrera|carreras|carreras-[a-z]+|maestria|maestrias|posgrado|posgrados|especialidad|especialidades|doctorado|master|masters|preparatoria|preparatorias|prepa|bachillerato|diplomado|diplomados|programa|programas|oferta-educativa|oferta-academica|curso|cursos|certificado|certificados)(-[\w%-]+)?(/|\.html|$)", re.I),
    # institucional: quiénes somos, modelo educativo, admisiones, becas, contacto, campus, calculadoras
    "institucional": re.compile(r"/(quienes-somos|quienessomos|acerca|acerca-de|nosotros|about|about-us|sobre-nosotros|historia|mision|vision|modelo-educativo|modelo-[a-z]+|admision|admisiones|proceso-de-admision|proceso-de-admision-[a-z]+|inscripcion|inscripciones|becas|beca|becas-[\w-]+|financiamiento|colegiaturas|costos|calculadora-de-costos|contacto|contact|contactanos|campus|sedes|instalaciones)(/|\.html|$)", re.I),
}
_PROGRAMA_TXT = re.compile(r"\b(plan de estudios|perfil de egreso|campo laboral|semestres?|tetramestres?|bimestres?|cuatrimestres?|rvoe|validez oficial|modalidad|duraci[oó]n|materias|certificados? cocreados?|malla curricular|titulaci[oó]n)\b", re.I)
_INSTITUCIONAL_TXT = re.compile(r"\b(misi[oó]n|visi[oó]n|nuestra historia|fundad[ao] en|quiénes somos|quienes somos|modelo educativo|proceso de admisi[oó]n|requisitos de admisi[oó]n|solicitud de beca|tipos de becas|becas? (acad[eé]mica|deportiva|de excelencia)|financiamiento|colegiatura|campus)\b", re.I)
_H1_COMPARATIVA = re.compile(r"\b(vs\.?|versus|comparativa|comparación|comparacion|alternativas|mejores|top \d+|best)\b", re.I)
_H1_DEFINICION = re.compile(r"^(qué es|que es|what is|qué son|que son|definición de|definicion de)\b", re.I)
_TEL_RE = re.compile(r"(\+?\d{1,3}[\s\-.]?)?\(?\d{2,3}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{4}")
_DIR_RE = re.compile(r"\b(av\.|avenida|calle|blvd|boulevard|col\.|colonia|c\.p\.|cp\s?\d{5}|street|st\.|suite)\b", re.I)


def detectar(doc: Documento, url: str = "") -> dict[str, Any]:
    url = url or doc.url or ""
    ruta = urlparse(url).path if url else ""
    ruta_norm = ruta.rstrip("/") or "/"
    puntajes: dict[str, float] = {t: 0.0 for t in ("home", "solucion", "articulo", "comparativa", "faq", "glosario", "landing", "local", "perfil", "programa", "institucional")}
    senales: list[str] = []
    tipos_ld = set(tipos_en_jsonld(doc))
    encabezados = doc.encabezados(solo_principal=True)
    h1 = next((e["texto"] for e in encabezados if e["nivel"] == 1), "") or doc.titulo
    h2_preguntas = sum(1 for e in encabezados if e["nivel"] in (2, 3) and e["texto"].strip().endswith("?"))
    texto = doc.texto_principal()
    palabras = contar_palabras(texto)
    formularios = doc.formularios()
    robots = doc.robots_meta()

    # home
    if ruta_norm == "/" or re.fullmatch(r"/(index\.html?|es|en|es-mx|en-us|home|inicio)", ruta_norm, re.I):
        puntajes["home"] += 5
        senales.append("ruta raíz")
    if "WebSite" in tipos_ld:
        puntajes["home"] += 1
        senales.append("WebSite en JSON-LD")

    # por ruta
    for tipo, rx in _RE.items():
        if rx.search(ruta):
            puntajes[tipo] += 3
            senales.append(f"ruta sugiere {tipo}")

    # por schema
    if tipos_ld & _ART_TIPOS:
        puntajes["articulo"] += 3
        senales.append("Article en JSON-LD")
    if "FAQPage" in tipos_ld:
        puntajes["faq"] += 3
        senales.append("FAQPage en JSON-LD")
    if "LocalBusiness" in tipos_ld or any(t.endswith("Business") or t in ("Store", "Restaurant", "Dentist") for t in tipos_ld):
        puntajes["local"] += 4
        senales.append("LocalBusiness en JSON-LD")
    if tipos_ld & {"Product", "Service", "SoftwareApplication", "Offer"}:
        puntajes["solucion"] += 2
        senales.append("Product/Service en JSON-LD")
    if "DefinedTerm" in tipos_ld or "DefinedTermSet" in tipos_ld:
        puntajes["glosario"] += 3
        senales.append("DefinedTerm en JSON-LD")
    if "ProfilePage" in tipos_ld:
        puntajes["perfil"] += 4
        senales.append("ProfilePage en JSON-LD")

    # por contenido: programa e institucional
    muestra = (h1 + " " + texto[:3000])
    n_prog = len(set(m.group(0).lower() for m in _PROGRAMA_TXT.finditer(muestra)))
    if n_prog >= 2:
        puntajes["programa"] += min(3, n_prog)
        senales.append(f"{n_prog} señales de programa educativo (plan de estudios, duración, modalidad, RVOE…)")
    n_inst = len(set(m.group(0).lower() for m in _INSTITUCIONAL_TXT.finditer(muestra)))
    if n_inst >= 2:
        puntajes["institucional"] += min(3, n_inst)
        senales.append(f"{n_inst} señales institucionales (misión, historia, admisión, becas…)")
    if re.match(r"^(licenciatura|ingenier[ií]a|maestr[ií]a|preparatoria|prepa|bachillerato|diplomado|especialidad|doctorado|carrera)\b", h1.strip(), re.I):
        puntajes["programa"] += 2
        senales.append("H1 nombra un programa")
    if re.match(r"^(qui[eé]nes somos|acerca de|sobre nosotros|nuestra historia|modelo educativo|proceso de admisi[oó]n|admisi[oó]n|admisiones|becas|contacto)\b", h1.strip(), re.I):
        puntajes["institucional"] += 2
        senales.append("H1 institucional")

    # por contenido
    if _H1_COMPARATIVA.search(h1):
        puntajes["comparativa"] += 3
        senales.append("H1 con vs/comparativa")
    if _H1_DEFINICION.search(h1):
        puntajes["glosario"] += 2
        senales.append("H1 de definición")
    if h2_preguntas >= 3:
        puntajes["faq"] += 2
        senales.append(f"{h2_preguntas} encabezados con pregunta")
    if doc.listas()["dl"] >= 1:
        puntajes["glosario"] += 1
    byline = bool(doc.buscar("a", rel="author")) or bool(re.search(r"\b(por|by)\s+[A-ZÁÉÍÓÚ][a-záéíóú]+\s+[A-ZÁÉÍÓÚ]", texto[:600]))
    if byline:
        puntajes["articulo"] += 2
        senales.append("byline")
    if doc.times():
        puntajes["articulo"] += 1
    if palabras >= 500 and len([e for e in encabezados if e["nivel"] == 2]) >= 2 and not any(f["en_principal"] for f in formularios) and puntajes["programa"] == 0 and puntajes["institucional"] == 0:
        puntajes["articulo"] += 1
    if _TEL_RE.search(texto) and _DIR_RE.search(texto):
        puntajes["local"] += 2
        senales.append("teléfono y dirección en el contenido")
    if formularios and palabras < 250:
        puntajes["landing"] += 3
        senales.append("formulario con poco texto")
    if "noindex" in robots.get("robots", []):
        puntajes["landing"] += 1
    enlaces_nav = sum(1 for e in doc.enlaces() if e["boilerplate"])
    if formularios and enlaces_nav <= 2:
        puntajes["landing"] += 2
        senales.append("casi sin navegación")
    if re.search(r"\b(precio|precios|pricing|desde \$|al mes|mensual|cotiza|demo)\b", texto[:2000], re.I) and palabras >= 80:
        puntajes["solucion"] += 1

    tipo, mejor = max(puntajes.items(), key=lambda kv: kv[1])
    if mejor <= 0:
        tipo = "otra"
        confianza = 0.3
    else:
        segundo = sorted(puntajes.values(), reverse=True)[1]
        confianza = round(min(0.95, 0.5 + 0.1 * (mejor - segundo)), 2)
    return {"tipo": tipo, "confianza": confianza, "senales": senales, "puntajes": puntajes, "h1": h1, "palabras": palabras}
