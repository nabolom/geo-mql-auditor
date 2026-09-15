"""La garantía vive en los datos, no en el prompt: cada archivo de vector lleva las reglas completas
de su categoría con sus fuentes y extractos de referencia; los prompts de los subagentes no
mencionan rutas fuera de su archivo de vector; el titular y el orden del reporte priorizan
Confirmado y separan las Hipótesis."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from geomql import auditoria, fetch, reporte
from geomql.hallazgos import Hallazgo
from geomql.reglas import cargar_rulebook

RAIZ = Path(__file__).resolve().parent.parent
AGENTES = RAIZ / ".claude" / "agents"
NOM = "https://www.nominafacil.mx"
TEC = "https://universidadejemplo.mx/es"
VECTORES = ("tecnico", "extractabilidad", "schema", "entidad")


@pytest.fixture
def corrida_mixta(html_de, tmp_path):
    mapa = {
        f"{NOM}/": "home.html", f"{NOM}/blog/reducir-rotacion-personal": "articulo.html", f"{NOM}/comparativa/nomina-facil-vs-contpaqi": "comparativa.html",
        f"{NOM}/preguntas-frecuentes": "faq.html", f"{NOM}/robots.txt": "robots/basico.txt", f"{NOM}/sitemap.xml": "sitemap.xml",
    }

    def _d(u, **k):
        if u in mapa:
            return fetch._resultado_vacio(u, status=200, html=html_de(mapa[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    urls = [u for u in mapa if not u.endswith((".txt", ".xml"))]
    return auditoria.correr(urls=urls, url_base=f"{NOM}/", descargar=_d, dir_salidas=tmp_path / "s", dir_historial=tmp_path / "h", corrida="mixta", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11))


# ------------------------------------------------------------- 1. reglas dentro del vector
@pytest.mark.parametrize("vector", VECTORES)
def test_vector_lleva_las_reglas_completas_de_su_categoria_y_ninguna_otra(corrida_mixta, vector):
    datos = json.loads(Path(corrida_mixta["meta"]["archivos_vector"][vector]).read_text(encoding="utf-8"))
    evaluadas = {r["regla_id"] for r in corrida_mixta["resultados"]}
    esperadas = {r["id"] for r in cargar_rulebook() if r["categoria"] == vector and r["id"] in evaluadas}
    presentes = {r["regla_id"] for r in datos["reglas"]}
    assert presentes == esperadas, (presentes ^ esperadas)
    assert all(r["resultados_por_url"] for r in datos["reglas"]), "solo viajan reglas evaluadas en la corrida"
    for r in datos["reglas"]:
        assert r["enunciado"] and r["fuerza"] and r["tipo_evidencia"] and r["tipos_pagina"] and r["ambito"], r["regla_id"]
        assert r["fuentes"] and all(f.get("url") and f.get("titulo") for f in r["fuentes"]), r["regla_id"]
        assert "recomendacion" in r and "resultados_por_url" in r and "por_tipo" in r, r["regla_id"]
        for res in r["resultados_por_url"]:
            assert res["url"] and res["estado"] and res["observacion"] and "detalle" in res and "tipo_pagina" in res
    # cada resultado de la corrida aparece en su regla
    por_regla = {}
    for res in corrida_mixta["resultados"]:
        por_regla.setdefault(res["regla_id"], set()).add(res["url"])
    for r in datos["reglas"]:
        assert {x["url"] for x in r["resultados_por_url"]} == por_regla.get(r["regla_id"], set()), r["regla_id"]
    # guía de etiquetas y prioridad embebida (lo que el subagente iba a buscar en etiquetas-confianza.md)
    assert "Hipótesis" in datos["guia"]["etiquetas"] and "Horizonte" in datos["guia"]["prioridad"]


def test_extractos_de_referencia_van_junto_a_la_regla_que_los_cita(corrida_mixta):
    x = json.loads(Path(corrida_mixta["meta"]["archivos_vector"]["extractabilidad"]).read_text(encoding="utf-8"))
    x04 = next(r for r in x["reglas"] if r["regla_id"] == "X-04")
    textos = " ".join(ref["texto"] for ref in x04["referencias"])
    assert "simulado" in textos and "115.1%" in textos and "C-SEO Bench" in textos, "extracto del paper de Princeton junto a X-04"
    assert all(not re.search(r"\.md\b|referencias/", ref.get("texto", "") + ref.get("titulo", "")) for ref in x04["referencias"]), "extracto, no ruta"
    t = json.loads(Path(corrida_mixta["meta"]["archivos_vector"]["tecnico"]).read_text(encoding="utf-8"))
    por_id = {r["regla_id"]: r for r in t["reglas"]}

    def _texto(ref, reglas):
        """El extracto va completo en la primera regla que lo cita; las demás lo señalan por id dentro del mismo archivo."""
        if ref.get("ver_regla"):
            return next(x["texto"] for x in reglas[ref["ver_regla"]]["referencias"] if x["titulo"] == ref["titulo"])
        return ref["texto"]

    t04 = por_id["T-04"]
    assert any("entrenamiento" in _texto(ref, por_id).lower() and "política" in _texto(ref, por_id).lower() for ref in t04["referencias"]), "categorías de bots junto a T-04"
    assert all(not ref.get("ver_regla") or ref["ver_regla"] in por_id for r in t["reglas"] for ref in r["referencias"]), "los señalamientos apuntan a reglas del mismo archivo"
    x09 = next(r for r in x["reglas"] if r["regla_id"] == "X-09")
    assert any("25.7%" in ref["texto"] for ref in x09["referencias"]), "qué dice la fuente de Ahrefs (frescura) junto a X-09"
    s = json.loads(Path(corrida_mixta["meta"]["archivos_vector"]["schema"]).read_text(encoding="utf-8"))
    s04 = next(r for r in s["reglas"] if r["regla_id"] == "S-04")
    assert any("sameAs" in ref["texto"] for ref in s04["referencias"]), "bitácora de la documentación de Organization junto a S-04"
    # las reglas sin resultado en la corrida (S-00 principio, E-07 sin colector) no viajan
    assert not any(r["regla_id"] == "S-00" for r in s["reglas"])


# ------------------------------------------------------------- 2. prompts sin rutas externas
@pytest.mark.parametrize("vector", VECTORES)
def test_prompt_del_subagente_solo_menciona_su_archivo_de_vector(vector):
    texto = (AGENTES / f"geo-{vector}.md").read_text(encoding="utf-8")
    prohibidos = ["rulebook", "referencias/", ".yaml", ".py", "SKILL.md", "JSON del reporte", "reporte.json", "princeton-kdd", "bots-ia", "etiquetas-confianza", "fuentes-verificadas", "tipos-de-pagina", "plantillas/"]
    encontrados = [p for p in prohibidos if p in texto]
    assert not encontrados, encontrados
    otros_json = {m for m in re.findall(r"[\w\-./]+\.json", texto) if m != f"{vector}.json"}
    assert not otros_json, otros_json
    otros_md = set(re.findall(r"[\w\-./]+\.md\b", texto))
    assert not otros_md, otros_md
    assert f"{vector}.json" in texto


def test_skill_pasa_solo_el_archivo_de_vector():
    skill = (RAIZ / ".claude" / "skills" / "geo-mql-auditor" / "SKILL.md").read_text(encoding="utf-8")
    paso = next(l for l in skill.splitlines() if l.startswith("4. "))
    assert "solo la ruta de su archivo de vector" in paso and "JSON del reporte" not in paso


# ------------------------------------------------------------- 3. titular y orden
def _h(i, obs, impacto="alto", esfuerzo="bajo"):
    return Hallazgo(
        id=f"R-{i:02d}-001", regla_id=f"R-{i:02d}", categoria="extractabilidad", tipo_pagina="home", url=TEC,
        evidencia_observacion=obs, fuerza_regla="A", tipo_evidencia="requisito_oficial",
        impacto_esperado=impacto, esfuerzo=esfuerzo, dependencia="contenido", horizonte="30d",
        titulo=f"Hallazgo {i} {obs}", detalle="d", evidencia=[], recomendacion="r", fuente={"titulo": "f", "url": "https://x"}, urls_afectadas=[TEC],
    )


def _construir(hallazgos):
    return reporte.construir(modulo="audit", dominio="x.mx", urls=[], hallazgos=hallazgos, resultados=[], reglas={}, puntaje={"por_categoria": {}, "global": None}, sitio={}, contexto={"valido": True}, fecha=date(2026, 9, 11))


def test_titular_prioriza_confirmados_y_separa_hipotesis():
    # las hipótesis llegan primero por impacto; aun así no encabezan
    hs = [_h(1, "Hipótesis", "alto", "bajo"), _h(2, "Hipótesis", "alto", "bajo"), _h(3, "Confirmado", "medio", "bajo"), _h(4, "Probable", "medio", "medio"), _h(5, "Confirmado", "bajo", "alto")]
    p = _construir(hs)
    assert "Hipótesis" not in p["titular"] and "requiere revisión humana" not in p["titular"]
    assert "Hallazgo 3 Confirmado" in p["titular"] and "Hallazgo 4 Probable" in p["titular"] and "Hallazgo 5 Confirmado" in p["titular"]
    orden = [h["evidencia_observacion"] for h in p["hallazgos"]]
    assert orden == ["Confirmado", "Probable", "Confirmado", "Hipótesis", "Hipótesis"] or orden[:3] == ["Confirmado", "Confirmado", "Probable"] and orden[3:] == ["Hipótesis", "Hipótesis"]
    md = p["markdown"]
    bloque = "Requieren revisión humana antes de actuar"
    assert bloque in md
    assert md.index("Hallazgo 5 Confirmado") < md.index(bloque) < md.index("### 4. Hallazgo 1 Hipótesis") or md.index(bloque) < md.index("Hallazgo 1 Hipótesis")
    assert md.index("### 3.") < md.index(bloque) < md.index("### 4.")


def test_titular_con_solo_hipotesis_lleva_marca_de_revision():
    p = _construir([_h(1, "Hipótesis"), _h(2, "Hipótesis")])
    assert "Hallazgo 1 Hipótesis" in p["titular"] and "requiere revisión humana" in p["titular"]
    assert "Requieren revisión humana antes de actuar" in p["markdown"]


def test_titular_de_corrida_real_no_empieza_con_hipotesis(corrida_mixta):
    salida = {"vector": "extractabilidad", "hallazgos": [{"regla_id": "X-11", "titulo": "Juicio del modelo", "detalle": "d", "recomendacion": "r", "evidencia_observacion": "Hipótesis", "impacto_esperado": "alto", "esfuerzo": "bajo", "dependencia": "contenido", "horizonte": "30d", "urls_afectadas": [f"{NOM}/"], "nuevo": True}], "ajustes": [], "notas": []}
    nuevo = auditoria.fusionar(corrida_mixta["meta"]["archivos"]["json"], [salida])
    assert "Juicio del modelo" not in nuevo["titular"]
    assert nuevo["hallazgos"][0]["evidencia_observacion"] != "Hipótesis"
    assert nuevo["hallazgos"][-1]["evidencia_observacion"] == "Hipótesis"


def test_el_conjunto_de_reglas_del_vector_cambia_con_los_tipos_de_pagina(corrida_mixta, html_de, tmp_path):
    """Una corrida de solo home lleva menos reglas de extractabilidad y schema que una con artículo, comparativa y FAQ."""
    def _d(u, **k):
        mapa = {f"{NOM}/": "home.html", f"{NOM}/robots.txt": "robots/basico.txt", f"{NOM}/sitemap.xml": "sitemap.xml"}
        if u in mapa:
            return fetch._resultado_vacio(u, status=200, html=html_de(mapa[u]), url_final=u)
        return fetch._resultado_vacio(u, status=404, error="HTTP 404")

    solo_home = auditoria.correr(urls=[f"{NOM}/"], url_base=f"{NOM}/", descargar=_d, dir_salidas=tmp_path / "s2", dir_historial=tmp_path / "h2", corrida="home", ahora=datetime(2026, 9, 11, tzinfo=timezone.utc), fecha=date(2026, 9, 11))
    for vector in ("extractabilidad", "schema"):
        a = {r["regla_id"] for r in json.loads(Path(solo_home["meta"]["archivos_vector"][vector]).read_text(encoding="utf-8"))["reglas"]}
        b = {r["regla_id"] for r in json.loads(Path(corrida_mixta["meta"]["archivos_vector"][vector]).read_text(encoding="utf-8"))["reglas"]}
        assert a < b, (vector, sorted(b - a))
    x_home = {r["regla_id"] for r in json.loads(Path(solo_home["meta"]["archivos_vector"]["extractabilidad"]).read_text(encoding="utf-8"))["reglas"]}
    assert "X-01" not in x_home and "X-04" not in x_home, "reglas que no aplican a la home no viajan"
    assert "X-02" in x_home
