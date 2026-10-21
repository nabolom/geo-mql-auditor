"""Vector de entidad: nombre consistente, sameAs, autoría, acerca de y contacto, NAP.

Derivado de scripts/entity_extractor.py y scripts/author_check.py de
best-aeo-skill (MIT, ver NOTICE). Correcciones: byline en español e inglés,
credenciales reales (cargo, url, sameAs), resolución opcional de sameAs,
consistencia de nombre entre superficies y NAP contra LocalBusiness.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable

from .html import Documento, texto_de

_BYLINE_RE = re.compile(r"\b(?:por|by|escrito por|autor[a]?:|written by)\s*:?\s*(?P<nombre>[A-ZÁÉÍÓÚÑ][\wáéíóúñü'’\-]+(?:\s+(?:de|del|la|von|van|y)?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñü'’\-]+){1,3})", re.I)
_CARGO_RE = re.compile(r"\b(directora?|gerente|CEO|CTO|CFO|CMO|COO|fundadora?|cofundadora?|presidenta?|responsable|jefa?|líder|especialista|consultora?|analista|profesora?|investigadora?|ingeniera?|abogada?|contadora?|doctora?|dra?\.|mtra?\.|lic\.|head of|director|manager|founder|vp)\b", re.I)
_COPYRIGHT_RE = re.compile(r"(?:©|\(c\)|copyright|D\.\s?R\.)\s*(?:©\s*)?(?:\d{4})?\s*(?:[-–]\s*\d{4})?\s*(?P<nombre>[A-ZÁÉÍÓÚÑ][^.|·•\n]{1,60}?)(?:\s*(?:S\.?A\.?|S\.? de R\.?L\.?|A\.?C\.?|Inc|LLC|Ltd|todos los derechos|all rights|\.|$|·|\|))", re.I)
# Convención mexicana: "Nombre D.R. Razón social, A.C." (Derechos Reservados tras el nombre de marca).
_DR_ANTES_RE = re.compile(r"(?P<nombre>[A-ZÁÉÍÓÚÑ][\wáéíóúñü'’\- ]{1,60}?)\s+D\.\s?R\.(?:\s|©|$)")
_SEPARADORES_TITLE = (" | ", " – ", " - ", " — ", " · ", " :: ")
_TEL_RE = re.compile(r"(?:\+?\d{1,3}[\s\-.]?)?\(?\d{2,3}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{4}\b")
_DIR_RE = re.compile(r"\b(?:av\.?|avenida|calle|blvd\.?|boulevard|carretera|paseo|prol\.?)\s+[^,\n]{3,60}\d[^,\n]{0,20}", re.I)
_ACERCA_RE = re.compile(r"(acerca|about|nosotros|quienes-somos|quiénes|quienes somos|empresa|compan[iy]|our-story|historia|equipo|team)", re.I)
_CONTACTO_RE = re.compile(r"(contacto|contact|contáctanos|contactanos|hablemos|talk-to)", re.I)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _digitos(t: str | None) -> str:
    return re.sub(r"\D", "", t or "")


def _nombre_en_pie(doc: Documento) -> str | None:
    footer = doc.raiz.primero("footer")
    if footer is None:
        return None
    texto = texto_de(footer, con_saltos=False)
    # "Marca D.R. Razón social" (nombre antes) tiene prioridad salvo que sea "D.R. © 2023 Marca" (nombre después).
    patrones = [_COPYRIGHT_RE, _DR_ANTES_RE] if re.search(r"D\.\s?R\.\s*©", texto) else [_DR_ANTES_RE, _COPYRIGHT_RE]
    for patron in patrones:
        m = patron.search(texto)
        if m and m.group("nombre").strip(" ,.·|"):
            return m.group("nombre").strip(" ,.·|")
    return None


def _nombre_en_title(titulo: str, otros: list[str], *, tipo_pagina: str) -> str | None:
    """Lado del title que corresponde a la marca.

    Con separador: el lado que coincide con otra superficie; si ninguno coincide,
    en la home el lado más corto y en el resto el sufijo (patrón "Título | Marca").
    Sin separador: en la home el title completo es la marca; en otras páginas el
    title es el título del contenido y no cuenta como superficie de marca.
    """
    titulo = (titulo or "").strip()
    if not titulo:
        return None
    for sep in _SEPARADORES_TITLE:
        if sep in titulo:
            prefijo = titulo.split(sep, 1)[0].strip()
            sufijo = titulo.rsplit(sep, 1)[-1].strip()
            normalizados = {_norm(o) for o in otros if o}
            for lado in (sufijo, prefijo):
                if lado and _norm(lado) in normalizados:
                    return lado
            if tipo_pagina == "home":
                return min((prefijo, sufijo), key=lambda t: (len(t.split()), len(t)))
            return sufijo
    return titulo if tipo_pagina == "home" else None


def nombres_de_marca(doc: Documento, schema_res: dict[str, Any] | None, *, tipo_pagina: str = "otra") -> dict[str, Any]:
    og = doc.meta("og:site_name") or None
    org = (schema_res or {}).get("organization", {}).get("name") if schema_res else None
    pie = _nombre_en_pie(doc)
    titulo = _nombre_en_title(doc.titulo, [og, org, pie], tipo_pagina=tipo_pagina)
    candidatos = {"title": titulo, "og:site_name": og, "Organization.name": org, "pie": pie}
    presentes = {k: v for k, v in candidatos.items() if v}
    normalizados = {_norm(v) for v in presentes.values()}
    return {
        "candidatos": presentes,
        "ausentes": [k for k, v in candidatos.items() if not v],
        "title_completo": doc.titulo,
        "variantes": sorted({v for v in presentes.values()}),
        "consistente": len(normalizados) <= 1,
        "distintos": len(normalizados),
    }


def autoria(doc: Documento, schema_res: dict[str, Any] | None) -> dict[str, Any]:
    schema_res = schema_res or {}
    art = schema_res.get("article", {})
    person = schema_res.get("person", {})
    nombre = art.get("autor") if art.get("presente") else None
    fuente = "json-ld" if nombre else None
    url_perfil = None
    cargo = None
    for a in doc.buscar("a", rel="author"):
        url_perfil = a.atributo("href")
        nombre = nombre or texto_de(a, con_saltos=False)
        fuente = fuente or "rel=author"
    texto = doc.texto_principal()[:800]
    m = _BYLINE_RE.search(texto)
    if m:
        nombre = nombre or m.group("nombre")
        fuente = fuente or "byline"
        tras = texto[m.end():m.end() + 120]
        c = _CARGO_RE.search(tras)
        if c:
            cargo = tras[c.start():].split("·")[0].split("\n")[0].strip()[:80]
    con_credenciales = bool(cargo) or (bool(nombre) and nombre in (person.get("con_url_o_sameas") or []))
    return {
        "presente": bool(nombre),
        "nombre": nombre,
        "fuente": fuente,
        "cargo": cargo,
        "url_perfil": url_perfil,
        "person_con_url_o_sameas": bool(nombre) and nombre in (person.get("con_url_o_sameas") or []),
        "con_credenciales": con_credenciales,
        "visible": bool(nombre) and _norm(nombre) in _norm(doc.texto(excluir_boilerplate=False)),
    }


def acerca_y_contacto(doc: Documento) -> dict[str, Any]:
    acerca = []
    contacto = []
    for e in doc.enlaces():
        objetivo = f"{e['href']} {e['texto']}"
        if _ACERCA_RE.search(objetivo) and not e["href"].startswith(("#", "mailto:")):
            acerca.append(e["href"])
        if _CONTACTO_RE.search(objetivo) or e["href"].startswith(("mailto:", "tel:")):
            contacto.append(e["href"])
    return {"acerca": sorted(set(acerca))[:5], "contacto": sorted(set(contacto))[:5], "acerca_presente": bool(acerca), "contacto_presente": bool(contacto)}


def nap(doc: Documento, schema_res: dict[str, Any] | None) -> dict[str, Any]:
    texto = doc.texto(excluir_boilerplate=False)
    tels = sorted({_digitos(t)[-10:] for t in _TEL_RE.findall(texto) if len(_digitos(t)) >= 10})
    dirs = sorted({d.strip() for d in _DIR_RE.findall(texto)})[:5]
    lb = (schema_res or {}).get("localbusiness", {}) if schema_res else {}
    tel_schema = _digitos(lb.get("telephone"))[-10:] if lb.get("telephone") else None
    addr = lb.get("address")
    calle_schema = addr.get("streetAddress") if isinstance(addr, dict) else (addr if isinstance(addr, str) else None)
    return {
        "telefonos_visibles": tels,
        "direcciones_visibles": dirs,
        "telefono_schema": tel_schema,
        "direccion_schema": calle_schema,
        "telefono_coincide": (tel_schema in tels) if tel_schema else None,
        "direccion_coincide": (any(_norm(calle_schema) in _norm(d) or _norm(d) in _norm(calle_schema) for d in dirs) if calle_schema and dirs else None),
    }


def resolver_sameas(urls: list[str], resolver: Callable[[str], dict[str, Any]] | None) -> list[dict[str, Any]]:
    if resolver is None:
        return [{"url": u, "status": None, "resuelve": None} for u in urls]
    out = []
    for u in urls[:10]:
        r = resolver(u)
        out.append({"url": u, "status": r.get("status"), "resuelve": r.get("status") in (200, 301, 302, 303, 307, 308) or (200 <= (r.get("status") or 0) < 400)})
    return out


def analizar(doc: Documento, schema_res: dict[str, Any] | None = None, *, resolver: Callable[[str], dict[str, Any]] | None = None, tipo_pagina: str = "otra") -> dict[str, Any]:
    same = (schema_res or {}).get("organization", {}).get("sameAs", []) if schema_res else []
    same = [s for s in same if isinstance(s, str)]
    return {
        "nombre": nombres_de_marca(doc, schema_res, tipo_pagina=tipo_pagina),
        "autoria": autoria(doc, schema_res),
        "acerca_contacto": acerca_y_contacto(doc),
        "nap": nap(doc, schema_res),
        "sameas": {"urls": same, "total": len(same), "resueltos": resolver_sameas(same, resolver)},
    }
