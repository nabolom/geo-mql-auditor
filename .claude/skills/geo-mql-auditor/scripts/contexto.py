#!/usr/bin/env python3
"""CLI del módulo 0 (contexto): valida contexto/negocio.md y lista lo que falta.

  python3 contexto.py validar [--ruta contexto/negocio.md] [--modulo mql] [--json]
  python3 contexto.py faltantes [--modulo mql]

El CRM solo es crítico para el módulo mql (--modulo mql).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geomql import contexto as contexto_mod  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="geo-mql-auditor · contexto de negocio")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validar")
    v.add_argument("--ruta")
    v.add_argument("--json", action="store_true")
    v.add_argument("--modulo", help="módulo que va a correr; el CRM solo es crítico para mql")
    f = sub.add_parser("faltantes")
    f.add_argument("--ruta")
    f.add_argument("--modulo")
    args = p.parse_args(argv)
    ctx = contexto_mod.cargar(args.ruta, modulo=args.modulo)
    if args.cmd == "validar":
        if args.json:
            print(json.dumps({k: v for k, v in ctx.items() if k != "campos"} | {"campos": ctx["campos"]}, ensure_ascii=False, indent=2))
        else:
            print(f"Archivo: {ctx['ruta']} ({'existe' if ctx['existe'] else 'no existe'})")
            print(f"Válido para recomendar: {'sí' if ctx['valido'] else 'no'}")
            if ctx["faltantes_criticos"]:
                print("Campos críticos faltantes: " + ", ".join(ctx["faltantes_criticos"]))
            if ctx["faltantes"]:
                print("Otros campos vacíos: " + ", ".join(ctx["faltantes"]))
            if ctx.get("competidores"):
                print("Competidores: " + ", ".join(f"{c['nombre']} ({c['dominio']})" for c in ctx["competidores"]))
        return 0 if ctx["valido"] else 1
    preguntas = contexto_mod.preguntas_para_faltantes(ctx["faltantes_criticos"])
    if not preguntas:
        print("No falta ningún campo crítico.")
        return 0
    print("Antes de recomendar necesito estas respuestas:")
    for q in preguntas:
        print(f"- {q}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
