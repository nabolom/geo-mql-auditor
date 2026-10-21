"""JSON-LD: tipos, campos recomendados por tipo de página, coherencia con el contenido visible y referencias @id.

Derivado de scripts/schema_validate.py de best-aeo-skill (MIT, ver NOTICE).
Correcciones: lee @graph y nodos anidados, valida campos recomendados según la
documentación de Google por tipo, comprueba coherencia con el contenido visible
y resuelve referencias @id.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .html import Documento, texto_de

ARTICULO = {"Article", "BlogPosting", "NewsArticle", "TechArticle", "ScholarlyArticle", "Report", "AnalysisNewsArticle", "BackgroundNewsArticle", "OpinionNewsArticle", "ReportageNewsArticle", "ReviewNewsArticle"}
LOCAL = {"LocalBusiness", "Store", "Restaurant", "Dentist", "MedicalBusiness", "ProfessionalService", "FinancialService", "LegalService", "AutoDealer", "HomeAndConstructionBusiness", "Hotel", "RealEstateAgent", "TravelAgency"}


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _tipos(nodo: dict[str, Any]) -> list[str]:
    t = nodo.get("@type")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [x for x in t if isinstance(x, str)]
    return []


def nodos_jsonld(doc: Documento) -> list[dict[str, Any]]:
    """Todos los nodos con @type, aplanando @graph y anidamientos."""
    out: list[dict[str, Any]] = []

    def rec(n: Any, bloque: int, ruta: str) -> None:
        if isinstance(n, dict):
            if _tipos(n):
                out.append({"tipos": _tipos(n), "nodo": n, "bloque": bloque, "ruta": ruta})
            for k, v in n.items():
                if k.startswith("@") and k not in ("@graph",):
                    continue
                rec(v, bloque, f"{ruta}.{k}" if ruta else k)
        elif isinstance(n, list):
            for i, x in enumerate(n):
                rec(x, bloque, f"{ruta}[{i}]")

    for i, b in enumerate(doc.json_ld()):
        if b["datos"] is not None:
            rec(b["datos"], i, "")
    return out


def tipos_en_jsonld(doc: Documento) -> list[str]:
    tipos: list[str] = []
    for n in nodos_jsonld(doc):
        tipos.extend(n["tipos"])
    return sorted(set(tipos))


def _por_tipo(nodos: list[dict[str, Any]], tipos: set[str]) -> list[dict[str, Any]]:
    return [n["nodo"] for n in nodos if set(n["tipos"]) & tipos]


def _valor(nodo: dict[str, Any], clave: str) -> Any:
    v = nodo.get(clave)
    if isinstance(v, list) and len(v) == 1:
        return v[0]
    return v


def _nombre_de(v: Any, indice_ids: dict[str, dict[str, Any]]) -> str | None:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        if "@id" in v and len(v) == 1 and v["@id"] in indice_ids:
            v = indice_ids[v["@id"]]
        n = v.get("name")
        return n if isinstance(n, str) else None
    if isinstance(v, list) and v:
        return _nombre_de(v[0], indice_ids)
    return None


def _resolver(v: Any, indice_ids: dict[str, dict[str, Any]]) -> Any:
    if isinstance(v, dict) and "@id" in v and len(v) == 1:
        return indice_ids.get(v["@id"], v)
    if isinstance(v, list) and len(v) == 1:
        return _resolver(v[0], indice_ids)
    return v


def _campos(nodo: dict[str, Any], requeridos: list[str], indice_ids: dict[str, dict[str, Any]]) -> dict[str, bool]:
    out = {}
    for c in requeridos:
        if "." in c:
            padre, hijo = c.split(".", 1)
            base = _resolver(nodo.get(padre), indice_ids)
            if hijo.startswith("(") and hijo.endswith(")"):
                alternativas = hijo[1:-1].split("|")
                out[c] = isinstance(base, dict) and any(base.get(a) for a in alternativas)
            else:
                out[c] = isinstance(base, dict) and bool(base.get(hijo))
        elif c.startswith("(") and c.endswith(")"):
            out[c] = any(nodo.get(a) for a in c[1:-1].split("|"))
        else:
            out[c] = bool(nodo.get(c))
    return out


def _fecha_iso_con_zona(v: Any) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2}))?", v))


def _visible(texto_norm: str, valor: Any) -> bool:
    if not isinstance(valor, str) or not valor.strip():
        return False
    return _normalizar(valor)[:80] in texto_norm


def analizar(doc: Documento, *, tipo_pagina: str = "otra", url: str = "") -> dict[str, Any]:
    bloques = doc.json_ld()
    nodos = nodos_jsonld(doc)
    indice_ids: dict[str, dict[str, Any]] = {}
    ids_duplicados: list[str] = []
    for n in nodos:
        i = n["nodo"].get("@id")
        if isinstance(i, str):
            if i in indice_ids:
                ids_duplicados.append(i)
            indice_ids[i] = n["nodo"]
    texto_norm = _normalizar(doc.texto(excluir_boilerplate=False))
    texto_principal_norm = _normalizar(doc.texto_principal())
    h1 = next((e["texto"] for e in doc.encabezados(solo_principal=True) if e["nivel"] == 1), "")

    # referencias @id no resueltas
    referencias_rotas: list[str] = []

    def buscar_refs(n: Any) -> None:
        if isinstance(n, dict):
            if set(n.keys()) == {"@id"} and isinstance(n["@id"], str) and n["@id"] not in indice_ids:
                referencias_rotas.append(n["@id"])
            for v in n.values():
                buscar_refs(v)
        elif isinstance(n, list):
            for x in n:
                buscar_refs(x)

    for b in bloques:
        if b["datos"] is not None:
            buscar_refs(b["datos"])

    tipos = tipos_en_jsonld(doc)
    conteo: dict[str, int] = {}
    for n in nodos:
        for t in n["tipos"]:
            conteo[t] = conteo.get(t, 0) + 1

    res: dict[str, Any] = {
        "bloques": len(bloques),
        "bloques_invalidos": [b["error"] for b in bloques if b["error"]],
        "tipos": tipos,
        "conteo_tipos": conteo,
        "ids_definidos": sorted(indice_ids),
        "ids_duplicados": ids_duplicados,
        "referencias_rotas": referencias_rotas,
        "duplicados_raiz": [t for t, c in conteo.items() if c > 1 and t in ("Organization", "WebSite", "FAQPage", "BreadcrumbList", *ARTICULO)],
        "coherencia": [],
    }

    # ----- Article
    arts = _por_tipo(nodos, ARTICULO)
    if arts:
        a = arts[0]
        campos = _campos(a, ["headline", "image", "datePublished", "dateModified", "author.name", "author.(url|sameAs)"], indice_ids)
        res["article"] = {
            "presente": True,
            "tipo": _tipos(a)[0],
            "campos": campos,
            "faltantes": [c for c, ok in campos.items() if not ok],
            "fechas_iso_con_zona": all(_fecha_iso_con_zona(a.get(k)) for k in ("datePublished", "dateModified") if a.get(k)),
            "headline": a.get("headline"),
            "autor": _nombre_de(a.get("author"), indice_ids),
            "dateModified": a.get("dateModified"),
            "datePublished": a.get("datePublished"),
            "publisher_resuelto": isinstance(_resolver(a.get("publisher"), indice_ids), dict) and "name" in _resolver(a.get("publisher"), indice_ids),
        }
        if a.get("headline") and h1 and _normalizar(a["headline"])[:60] != _normalizar(h1)[:60] and _normalizar(a["headline"])[:40] not in _normalizar(doc.titulo):
            res["coherencia"].append({"campo": "Article.headline", "valor": a["headline"], "problema": "no coincide con el H1 ni con el title"})
        autor = res["article"]["autor"]
        if autor and not _visible(texto_norm, autor):
            res["coherencia"].append({"campo": "Article.author.name", "valor": autor, "problema": "el nombre del autor no aparece en el contenido visible"})
    else:
        res["article"] = {"presente": False}

    # ----- Organization / WebSite
    orgs = _por_tipo(nodos, {"Organization", "Corporation", "LocalBusiness", "EducationalOrganization", "NGO"} | LOCAL)
    if orgs:
        o = orgs[0]
        campos = _campos(o, ["name", "url", "logo", "sameAs", "description", "(address|contactPoint|telephone|email)"], indice_ids)
        same = o.get("sameAs") or []
        res["organization"] = {
            "presente": True,
            "name": o.get("name"),
            "campos": campos,
            "faltantes": [c for c, ok in campos.items() if not ok],
            "sameAs": same if isinstance(same, list) else [same],
            "tiene_id": bool(o.get("@id")),
        }
        site_name = doc.meta("og:site_name")
        if o.get("name") and site_name and _normalizar(o["name"]) != _normalizar(site_name):
            res["coherencia"].append({"campo": "Organization.name", "valor": o["name"], "problema": f"difiere de og:site_name ({site_name})"})
    else:
        res["organization"] = {"presente": False, "sameAs": []}
    res["website"] = {"presente": bool(_por_tipo(nodos, {"WebSite"}))}

    # ----- BreadcrumbList
    bcs = _por_tipo(nodos, {"BreadcrumbList"})
    if bcs:
        items = bcs[0].get("itemListElement") or []
        ok = isinstance(items, list) and bool(items) and all(isinstance(i, dict) and i.get("position") and i.get("name") for i in items)
        sin_item = [i.get("name") for i in items[:-1] if isinstance(i, dict) and not i.get("item")] if isinstance(items, list) else []
        res["breadcrumb"] = {"presente": True, "valido": ok and not sin_item, "items": len(items) if isinstance(items, list) else 0, "sin_item": sin_item}
    else:
        res["breadcrumb"] = {"presente": False}

    # ----- Product / Service
    prods = _por_tipo(nodos, {"Product", "SoftwareApplication"})
    if prods:
        p = prods[0]
        res["product"] = {"presente": True, "name": p.get("name"), "tiene_oferta_o_review": bool(p.get("offers") or p.get("review") or p.get("aggregateRating"))}
    else:
        res["product"] = {"presente": False}
    servs = _por_tipo(nodos, {"Service"})
    if servs:
        s = servs[0]
        campos = _campos(s, ["name", "provider", "serviceType", "areaServed", "offers"], indice_ids)
        res["service"] = {"presente": True, "campos": campos, "faltantes": [c for c, ok in campos.items() if not ok]}
    else:
        res["service"] = {"presente": False}

    # ----- LocalBusiness
    locales = _por_tipo(nodos, LOCAL)
    if locales:
        l = locales[0]
        campos = _campos(l, ["name", "address", "telephone", "openingHoursSpecification", "geo", "url"], indice_ids)
        direccion = l.get("address")
        res["localbusiness"] = {
            "presente": True,
            "name": l.get("name"),
            "telephone": l.get("telephone"),
            "address": direccion,
            "campos": campos,
            "faltantes_requeridos": [c for c in ("name", "address") if not campos.get(c)],
            "faltantes_recomendados": [c for c in ("telephone", "openingHoursSpecification", "geo", "url") if not campos.get(c)],
        }
    else:
        res["localbusiness"] = {"presente": False}

    # ----- FAQPage
    faqs = _por_tipo(nodos, {"FAQPage"})
    if faqs:
        preguntas = []
        me = faqs[0].get("mainEntity") or []
        if isinstance(me, dict):
            me = [me]
        for q in me:
            if isinstance(q, dict):
                nombre = q.get("name", "")
                preguntas.append({"pregunta": nombre, "visible": _visible(texto_norm, nombre)})
        res["faqpage"] = {"presente": True, "preguntas": len(preguntas), "no_visibles": [p["pregunta"] for p in preguntas if not p["visible"]]}
        for p in res["faqpage"]["no_visibles"]:
            res["coherencia"].append({"campo": "FAQPage.mainEntity", "valor": p, "problema": "pregunta marcada que no aparece en el contenido visible"})
    else:
        res["faqpage"] = {"presente": False}

    # ----- Person / ProfilePage / DefinedTerm
    personas = _por_tipo(nodos, {"Person"})
    res["person"] = {
        "presente": bool(personas),
        "con_url_o_sameas": [p.get("name") for p in personas if p.get("url") or p.get("sameAs")],
        "sin_url_ni_sameas": [p.get("name") for p in personas if not (p.get("url") or p.get("sameAs"))],
        "nombres": [p.get("name") for p in personas if p.get("name")],
    }
    res["profilepage"] = {"presente": bool(_por_tipo(nodos, {"ProfilePage"}))}
    res["definedterm"] = {"presente": bool(_por_tipo(nodos, {"DefinedTerm", "DefinedTermSet"}))}

    # ----- fechas para coherencia con lo visible (frescura las cruza)
    res["fechas"] = {
        "dateModified": res["article"].get("dateModified") if res["article"].get("presente") else None,
        "datePublished": res["article"].get("datePublished") if res["article"].get("presente") else None,
    }
    for n in _por_tipo(nodos, {"WebPage"}):
        for k in ("dateModified", "datePublished"):
            if n.get(k) and not res["fechas"].get(k):
                res["fechas"][k] = n[k]
    return res
