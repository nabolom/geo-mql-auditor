"""Lectura y validación de contexto/negocio.md."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import RUTA_CONTEXTO

CRITICOS = ("nombre", "dominio", "descripcion_oficial", "productos_servicios", "geografia", "idiomas", "icp", "competidor")
# Campos críticos adicionales por módulo: el CRM solo bloquea el módulo mql.
CRITICOS_POR_MODULO = {"mql": ("crm",)}
_CAMPO_RE = re.compile(r"^\s*-\s*([a-záéíóúñ_]+)\s*:\s*(.*)$", re.I)


def _limpiar(valor: str) -> str:
    v = valor.strip()
    if v.startswith("(") and v.endswith(")"):
        return ""
    v = re.sub(r"\s*\((?:crítico|critico)[^)]*\)\s*$", "", v).strip()
    return v


def parsear(texto: str) -> dict[str, Any]:
    secciones: dict[str, dict[str, Any]] = {}
    actual = "general"
    campos: dict[str, Any] = {}
    for linea in texto.splitlines():
        if linea.startswith("## "):
            actual = linea[3:].strip().lower()
            secciones.setdefault(actual, {})
            continue
        m = _CAMPO_RE.match(linea)
        if not m:
            continue
        clave = m.group(1).lower()
        valor = _limpiar(m.group(2))
        if clave == "competidor":
            campos.setdefault("competidores", [])
            if valor:
                nombre, _, url = valor.partition("|")
                url = url.strip() or nombre.strip()
                if not url.startswith("http"):
                    url = "https://" + url
                campos["competidores"].append({"nombre": nombre.strip(), "url": url, "dominio": urlparse(url).netloc.lower()})
            continue
        if clave in campos and campos[clave] and not valor:
            continue
        campos[clave] = valor
        secciones.setdefault(actual, {})[clave] = valor
    campos.setdefault("competidores", [])
    return {"campos": campos, "secciones": secciones}


def criticos_para(modulo: str | None = None) -> tuple[str, ...]:
    return CRITICOS + CRITICOS_POR_MODULO.get(modulo or "", ())


def cargar(ruta: Path | str | None = None, *, modulo: str | None = None) -> dict[str, Any]:
    ruta = Path(ruta) if ruta else RUTA_CONTEXTO
    criticos = criticos_para(modulo)
    if not ruta.exists():
        return {"existe": False, "ruta": str(ruta), "campos": {"competidores": []}, "faltantes_criticos": list(criticos), "faltantes": [], "valido": False, "modulo": modulo}
    datos = parsear(ruta.read_text(encoding="utf-8"))
    campos = datos["campos"]
    faltantes_criticos = []
    for c in criticos:
        if c == "competidor":
            if not campos.get("competidores"):
                faltantes_criticos.append("competidor")
        elif not campos.get(c):
            faltantes_criticos.append(c)
    faltantes = [k for k, v in campos.items() if k != "competidores" and not v]
    return {
        "existe": True,
        "ruta": str(ruta),
        "campos": campos,
        "faltantes_criticos": faltantes_criticos,
        "faltantes": faltantes,
        "valido": not faltantes_criticos,
        "competidores": campos.get("competidores", []),
        "modulo": modulo,
    }


def lista(campos: dict[str, Any], clave: str) -> list[str]:
    v = campos.get(clave) or ""
    return [x.strip() for x in re.split(r"[;,]", v) if x.strip()]


def lista_pc(campos: dict[str, Any], clave: str) -> list[str]:
    """Lista separada solo por punto y coma (las preguntas pueden llevar comas)."""
    v = campos.get(clave) or ""
    return [x.strip() for x in v.split(";") if x.strip()]


def variantes_de_marca(ctx: dict[str, Any]) -> list[str]:
    campos = ctx.get("campos", {})
    out = []
    if campos.get("nombre"):
        out.append(campos["nombre"])
    out.extend(lista(campos, "variantes_de_nombre"))
    return sorted(set(out), key=lambda v: (-len(v), v))


def dominios_propios(ctx: dict[str, Any]) -> list[str]:
    campos = ctx.get("campos", {})
    out = []
    for d in [campos.get("dominio", "")] + lista(campos, "dominios_alternos"):
        d = d.strip().lower()
        if not d:
            continue
        if d.startswith("http"):
            d = urlparse(d).netloc
        out.append(d.removeprefix("www."))
    return sorted(set(out))


def preguntas_para_faltantes(faltantes: list[str]) -> list[str]:
    textos = {
        "nombre": "¿Cómo se llama la marca o negocio?",
        "dominio": "¿Cuál es el dominio principal del sitio (solo el host)?",
        "descripcion_oficial": "En una frase, ¿qué es la marca y qué hace? (se usa para juzgar si las respuestas de IA la describen bien)",
        "productos_servicios": "¿Qué productos o servicios vende, separados por punto y coma?",
        "geografia": "¿En qué país y ciudad principal opera? (se usa como ubicación en las consultas a los motores)",
        "idiomas": "¿En qué idiomas publica el sitio? (códigos: es, en)",
        "icp": "¿Cuál es el perfil de cliente ideal: tamaño de empresa, sector, rol decisor?",
        "competidor": "¿Cuáles son de 2 a 5 competidores, con nombre y URL?",
        "crm": "¿Qué CRM usan (HubSpot, Salesforce, Dynamics, Zoho, Pipedrive u otro)?",
    }
    return [textos.get(f, f"Falta el campo {f}") for f in faltantes]
