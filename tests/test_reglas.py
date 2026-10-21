"""Integridad del rulebook y del parser YAML mínimo."""
from __future__ import annotations

import pytest

from geomql import RUTA_RULEBOOK
from geomql import reglas as mod


def test_rulebook_carga_y_valida():
    reglas = mod.cargar_rulebook()
    assert len(reglas) >= 55
    ids = [r["id"] for r in reglas]
    assert len(ids) == len(set(ids))
    assert "E-09" not in ids, "E-09 se eliminó por decisión del 2026-09-10"


def test_cada_regla_tiene_fuente_fuerza_tipo_y_fecha():
    for r in mod.cargar_rulebook():
        assert r["fuerza"] in mod.FUERZAS, r["id"]
        assert r["tipo_evidencia"] in mod.TIPOS_EVIDENCIA, r["id"]
        assert r["verificado_el"] == "2026-09-10", r["id"]
        assert r["fuentes"] and all(f["url"] for f in r["fuentes"]), r["id"]
        assert all(f.get("fuerza") in mod.FUERZAS for f in r["fuentes"]), r["id"]


def test_princeton_no_se_presenta_como_efecto_esperado():
    idx = mod.indice(mod.cargar_rulebook())
    for rid in ("X-04", "X-05", "X-06", "X-07"):
        fuentes_princeton = [f for f in idx[rid]["fuentes"] if "2311.09735" in f["url"]]
        assert fuentes_princeton, rid
        for f in fuentes_princeton:
            assert f["fuerza"] == "B", rid
            assert f["tipo_evidencia"] == "efecto_experimental", rid
            assert "simulado" in f.get("nota", ""), rid


def test_reglas_de_metodo_y_principio_no_puntuan():
    idx = mod.indice(mod.cargar_rulebook())
    for rid in ("X-00", "S-00", "T-06", "V-01", "V-02", "N-01", "N-04"):
        assert not idx[rid].puntua, rid
    assert idx["T-01"].puntua
    assert idx["X-04"].puntua


def test_filtrado_por_tipo_de_pagina():
    reglas = mod.cargar_rulebook()
    home = {r["id"] for r in mod.reglas_para(reglas, tipo_pagina="home", categoria="schema")}
    articulo = {r["id"] for r in mod.reglas_para(reglas, tipo_pagina="articulo", categoria="schema")}
    assert "S-04" in home and "S-04" not in articulo
    assert "S-03" in articulo and "S-03" not in home
    assert "S-05" in articulo and "S-05" not in home, "BreadcrumbList solo en interiores"
    assert "S-08" not in home and "S-08" not in articulo, "FAQPage solo en páginas faq"


def test_etiqueta_fuerza_muestra_tipo():
    idx = mod.indice(mod.cargar_rulebook())
    assert idx["T-01"].etiqueta_fuerza() == "A · requisito oficial"
    assert idx["X-05"].etiqueta_fuerza() == "B · experimental"
    assert idx["X-13"].etiqueta_fuerza() == "C · consenso"


def test_parser_minimo_coincide_con_pyyaml():
    yaml = pytest.importorskip("yaml")
    texto = RUTA_RULEBOOK.read_text(encoding="utf-8")
    assert mod.cargar_yaml_minimo(texto) == yaml.safe_load(texto)


def test_parser_minimo_casos_basicos():
    texto = """
# comentario
- id: A-1
  lista: [uno, "dos, con coma", 3]
  activo: true
  nada: null
  texto: "con: dos puntos y un # dentro"
  fuentes:
    - titulo: "F1"
      url: "https://x.y"
    - titulo: "F2"
      url: "https://z.w"
- id: A-2
  lista: []
"""
    datos = mod.cargar_yaml_minimo(texto)
    assert datos[0]["lista"] == ["uno", "dos, con coma", 3]
    assert datos[0]["activo"] is True and datos[0]["nada"] is None
    assert datos[0]["texto"] == "con: dos puntos y un # dentro"
    assert [f["titulo"] for f in datos[0]["fuentes"]] == ["F1", "F2"]
    assert datos[1]["lista"] == []


def test_validacion_detecta_errores(tmp_path):
    ruta = tmp_path / "malo.yaml"
    ruta.write_text('- id: Z-1\n  categoria: tecnico\n  ambito: pagina\n  enunciado: "x"\n  fuerza: D\n  tipo_evidencia: consenso\n  verificado_el: "2026-09-10"\n  fuentes:\n    - titulo: "t"\n      url: "https://a.b"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="fuerza inválida"):
        mod.cargar_rulebook(ruta)
