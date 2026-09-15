"""geomql: colectores y utilidades del skill geo-mql-auditor.

Solo biblioteca estándar. Playwright y PyYAML son opcionales y se detectan en
tiempo de ejecución. Parte del código deriva de metawhisp/best-aeo-skill (MIT);
ver NOTICE en la raíz del proyecto.
"""
from __future__ import annotations

from pathlib import Path

VERSION = "0.1.0"

RAIZ_SKILL = Path(__file__).resolve().parent.parent.parent
RAIZ_PROYECTO = RAIZ_SKILL.parent.parent.parent
RUTA_RULEBOOK = RAIZ_SKILL / "reglas" / "rulebook.yaml"
RUTA_BOTS = RAIZ_SKILL / "referencias" / "bots-ia.json"
RUTA_PLANTILLAS = RAIZ_SKILL / "plantillas"
RUTA_CONTEXTO = RAIZ_PROYECTO / "contexto" / "negocio.md"
RUTA_SALIDAS = RAIZ_PROYECTO / "salidas"
RUTA_DATOS = RAIZ_PROYECTO / "datos"
