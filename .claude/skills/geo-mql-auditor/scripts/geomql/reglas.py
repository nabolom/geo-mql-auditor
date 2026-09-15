"""Carga y validación del rulebook (reglas/rulebook.yaml).

Usa PyYAML si está instalado; si no, un parser mínimo del subconjunto de YAML
que emplea el rulebook (listas de mapas, mapas anidados, listas en línea,
escalares en una línea, cadenas entre comillas dobles).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import RUTA_RULEBOOK

FUERZAS = ("A", "B", "C")
TIPOS_EVIDENCIA = ("requisito_oficial", "efecto_experimental", "correlacional", "consenso")
CATEGORIAS = ("tecnico", "extractabilidad", "schema", "entidad", "mql", "visibilidad", "antipatron")
AMBITOS = ("pagina", "sitio", "metodo", "principio", "analitica", "crm", "offpage", "antipatron")
AMBITOS_SIN_PUNTAJE = {"metodo", "principio", "antipatron"}
TIPOS_PAGINA = ("home", "solucion", "articulo", "comparativa", "faq", "glosario", "landing", "local", "perfil", "programa", "institucional", "otra")
IMPACTOS = ("alto", "medio", "bajo")
ESFUERZOS = ("bajo", "medio", "alto")
HORIZONTES = ("30d", "90d", "largo")


# ---------------------------------------------------------------- parser mínimo
_CLAVE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s+(.*))?$")


def _escalar(valor: str) -> Any:
    v = valor.strip()
    if v == "" or v in ("null", "~"):
        return None
    if v in ("true", "True"):
        return True
    if v in ("false", "False"):
        return False
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        return v[1:-1].replace('\\"', '"')
    if v.startswith("'") and v.endswith("'") and len(v) >= 2:
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        interior = v[1:-1].strip()
        if not interior:
            return []
        return [_escalar(x) for x in _dividir_lista(interior)]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    return v


def _dividir_lista(s: str) -> list[str]:
    out, actual, comillas = [], [], None
    for ch in s:
        if comillas:
            actual.append(ch)
            if ch == comillas:
                comillas = None
        elif ch in ('"', "'"):
            comillas = ch
            actual.append(ch)
        elif ch == ",":
            out.append("".join(actual))
            actual = []
        else:
            actual.append(ch)
    if actual:
        out.append("".join(actual))
    return [x for x in out if x.strip()]


def _lineas_utiles(texto: str) -> list[tuple[int, str]]:
    out = []
    for cruda in texto.splitlines():
        if cruda.lstrip().startswith("#") or cruda.strip() == "" or cruda.strip() == "---":
            continue
        indent = len(cruda) - len(cruda.lstrip(" "))
        out.append((indent, cruda.rstrip()))
    return out


def _parsear_bloque(lineas: list[tuple[int, str]], i: int, indent: int) -> tuple[Any, int]:
    """Parsea un bloque (lista o mapa) que empieza en la línea i con la indentación dada."""
    if i >= len(lineas):
        return None, i
    if lineas[i][1].lstrip().startswith("- "):
        return _parsear_lista(lineas, i, indent)
    return _parsear_mapa(lineas, i, indent)


def _parsear_lista(lineas: list[tuple[int, str]], i: int, indent: int) -> tuple[list[Any], int]:
    out: list[Any] = []
    while i < len(lineas):
        ind, linea = lineas[i]
        if ind < indent:
            break
        if ind > indent:
            raise ValueError(f"indentación inesperada en línea: {linea!r}")
        contenido = linea.lstrip()
        if not contenido.startswith("- "):
            break
        resto = contenido[2:]
        m = _CLAVE_RE.match(resto)
        if m and not resto.startswith('"'):
            # elemento que es un mapa: la primera clave está en la misma línea
            sub_indent = indent + 2
            # reescribimos la primera línea como si estuviera indentada
            lineas_virtuales = [(sub_indent, " " * sub_indent + resto)]
            j = i + 1
            while j < len(lineas) and lineas[j][0] >= sub_indent:
                lineas_virtuales.append(lineas[j])
                j += 1
            mapa, _ = _parsear_mapa(lineas_virtuales, 0, sub_indent)
            out.append(mapa)
            i = j
        else:
            out.append(_escalar(resto))
            i += 1
    return out, i


def _parsear_mapa(lineas: list[tuple[int, str]], i: int, indent: int) -> tuple[dict[str, Any], int]:
    out: dict[str, Any] = {}
    while i < len(lineas):
        ind, linea = lineas[i]
        if ind < indent:
            break
        if ind > indent:
            raise ValueError(f"indentación inesperada en línea: {linea!r}")
        contenido = linea.lstrip()
        if contenido.startswith("- "):
            break
        m = _CLAVE_RE.match(contenido)
        if not m:
            raise ValueError(f"línea no reconocida: {linea!r}")
        clave, valor = m.group(1), m.group(2)
        if valor is None or valor.strip() == "":
            # bloque anidado
            if i + 1 < len(lineas) and lineas[i + 1][0] > indent:
                hijo, i = _parsear_bloque(lineas, i + 1, lineas[i + 1][0])
                out[clave] = hijo
            else:
                out[clave] = None
                i += 1
        else:
            out[clave] = _escalar(valor)
            i += 1
    return out, i


def cargar_yaml_minimo(texto: str) -> Any:
    lineas = _lineas_utiles(texto)
    if not lineas:
        return None
    datos, _ = _parsear_bloque(lineas, 0, lineas[0][0])
    return datos


def cargar_yaml(texto: str) -> Any:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(texto)
    except ImportError:
        return cargar_yaml_minimo(texto)


# ------------------------------------------------------------------- rulebook
class Regla(dict):
    """Una regla del rulebook (dict con acceso por atributo para comodidad)."""

    def __getattr__(self, nombre: str) -> Any:
        try:
            return self[nombre]
        except KeyError as e:
            raise AttributeError(nombre) from e

    @property
    def puntua(self) -> bool:
        return bool(self.get("puntua", True)) and self.get("ambito") not in AMBITOS_SIN_PUNTAJE

    @property
    def peso(self) -> int:
        return {"A": 3, "B": 2, "C": 1}[self["fuerza"]]

    def aplica_a(self, tipo_pagina: str) -> bool:
        tipos = self.get("tipos_pagina") or ["todas"]
        if "todas" in tipos:
            return True
        if "interiores" in tipos and tipo_pagina != "home":
            return True
        return tipo_pagina in tipos

    def etiqueta_fuerza(self) -> str:
        nombres = {
            "requisito_oficial": "requisito oficial",
            "efecto_experimental": "experimental",
            "correlacional": "correlacional",
            "consenso": "consenso",
        }
        return f"{self['fuerza']} · {nombres.get(self['tipo_evidencia'], self['tipo_evidencia'])}"


def validar_regla(r: dict[str, Any]) -> list[str]:
    errores = []
    for campo in ("id", "categoria", "ambito", "enunciado", "fuerza", "tipo_evidencia", "verificado_el", "fuentes"):
        if campo not in r or r[campo] in (None, ""):
            errores.append(f"{r.get('id', '?')}: falta {campo}")
    if r.get("fuerza") not in FUERZAS:
        errores.append(f"{r.get('id')}: fuerza inválida {r.get('fuerza')!r}")
    if r.get("tipo_evidencia") not in TIPOS_EVIDENCIA:
        errores.append(f"{r.get('id')}: tipo_evidencia inválido {r.get('tipo_evidencia')!r}")
    if r.get("categoria") not in CATEGORIAS:
        errores.append(f"{r.get('id')}: categoría inválida {r.get('categoria')!r}")
    if r.get("ambito") not in AMBITOS:
        errores.append(f"{r.get('id')}: ámbito inválido {r.get('ambito')!r}")
    for t in r.get("tipos_pagina") or []:
        if t not in TIPOS_PAGINA and t not in ("todas", "interiores"):
            errores.append(f"{r.get('id')}: tipo de página inválido {t!r}")
    fuentes = r.get("fuentes") or []
    if not isinstance(fuentes, list) or not fuentes:
        errores.append(f"{r.get('id')}: sin fuentes")
    else:
        for f in fuentes:
            if not isinstance(f, dict) or not f.get("url") or not f.get("titulo"):
                errores.append(f"{r.get('id')}: fuente sin título o URL")
            elif not str(f["url"]).startswith("http") and not str(f["url"]).endswith(".md"):
                # sin fuente primaria: la URL remite a un documento del repositorio (README.md)
                errores.append(f"{r.get('id')}: URL de fuente inválida {f['url']!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("verificado_el", ""))):
        errores.append(f"{r.get('id')}: verificado_el debe ser AAAA-MM-DD")
    if r.get("impacto_esperado") and r["impacto_esperado"] not in IMPACTOS:
        errores.append(f"{r.get('id')}: impacto inválido")
    if r.get("esfuerzo") and r["esfuerzo"] not in ESFUERZOS:
        errores.append(f"{r.get('id')}: esfuerzo inválido")
    if r.get("horizonte") and r["horizonte"] not in HORIZONTES:
        errores.append(f"{r.get('id')}: horizonte inválido")
    return errores


def cargar_rulebook(ruta: Path | str | None = None) -> list[Regla]:
    ruta = Path(ruta) if ruta else RUTA_RULEBOOK
    datos = cargar_yaml(ruta.read_text(encoding="utf-8"))
    if isinstance(datos, dict):
        datos = datos.get("reglas", [])
    reglas = [Regla(r) for r in datos or []]
    errores: list[str] = []
    ids: set[str] = set()
    for r in reglas:
        errores.extend(validar_regla(r))
        if r.get("id") in ids:
            errores.append(f"{r['id']}: id duplicado")
        ids.add(r.get("id"))
    if errores:
        raise ValueError("rulebook inválido:\n" + "\n".join(errores))
    return reglas


def indice(reglas: list[Regla]) -> dict[str, Regla]:
    return {r["id"]: r for r in reglas}


def reglas_para(reglas: list[Regla], *, tipo_pagina: str | None = None, categoria: str | None = None, ambito: str | None = None) -> list[Regla]:
    out = []
    for r in reglas:
        if categoria and r["categoria"] != categoria:
            continue
        if ambito and r["ambito"] != ambito:
            continue
        if tipo_pagina and r["ambito"] == "pagina" and not r.aplica_a(tipo_pagina):
            continue
        out.append(r)
    return out
