"""Acceso de bots de IA por categoría (búsqueda, usuario, entrenamiento).

Derivado de scripts/ai_bot_access.py de best-aeo-skill (MIT, ver NOTICE).
Corrección central: separa bots de búsqueda y fetch por usuario de los bots de
entrenamiento, y evalúa el acceso con la precedencia real de robots.txt.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import RUTA_BOTS
from .robots import permitido

CATEGORIAS = ("busqueda", "usuario", "entrenamiento", "otro", "no_documentado")


def cargar_registro(ruta: Path | str | None = None) -> dict[str, Any]:
    ruta = Path(ruta) if ruta else RUTA_BOTS
    return json.loads(ruta.read_text(encoding="utf-8"))


def evaluar_acceso(robots_parsed: dict[str, Any], *, ruta: str = "/", registro: dict[str, Any] | None = None) -> dict[str, Any]:
    """Para cada bot documentado, si robots.txt le permite la ruta dada."""
    registro = registro or cargar_registro()
    por_categoria: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIAS}
    for bot in registro["bots"]:
        res = permitido(robots_parsed, bot["token"], ruta)
        por_categoria.setdefault(bot["categoria"], []).append({
            "token": bot["token"],
            "proveedor": bot["proveedor"],
            "categoria": bot["categoria"],
            "permitido": res["permitido"],
            "regla": res["regla"],
            "grupo": res["grupo"],
            "explicito": res["grupo"] not in (None, "*"),
            "respeta_robots": bot.get("respeta_robots"),
            "es_token_de_control": bot.get("es_token_de_control", False),
            "fuente": bot.get("fuente", ""),
            "nota": bot.get("nota", ""),
        })
    resumen = {
        f"{cat}_bloqueados": [b["token"] for b in lista if not b["permitido"]]
        for cat, lista in por_categoria.items()
    }
    resumen["busqueda_total"] = len(por_categoria["busqueda"])
    resumen["entrenamiento_total"] = len(por_categoria["entrenamiento"])
    resumen["politica_entrenamiento"] = (
        "bloquea_todo" if resumen["entrenamiento_bloqueados"] and len(resumen["entrenamiento_bloqueados"]) == len(por_categoria["entrenamiento"])
        else "permite_todo" if not resumen["entrenamiento_bloqueados"]
        else "mixta"
    )
    resumen["google_extended_bloqueado"] = any(
        b["token"] == "Google-Extended" and not b["permitido"] for b in por_categoria["entrenamiento"]
    )
    return {"ruta": ruta, "por_categoria": por_categoria, "resumen": resumen, "verificado_el": registro.get("verificado_el")}


def tokens_por_categoria(registro: dict[str, Any] | None = None) -> dict[str, list[str]]:
    registro = registro or cargar_registro()
    out: dict[str, list[str]] = {c: [] for c in CATEGORIAS}
    for b in registro["bots"]:
        out.setdefault(b["categoria"], []).append(b["token"])
    return out
