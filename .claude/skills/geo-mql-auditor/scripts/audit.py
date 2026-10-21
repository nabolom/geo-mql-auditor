#!/usr/bin/env python3
"""CLI del módulo audit.

Ejemplos:
  python3 audit.py correr --url https://ejemplo.com/pagina
  python3 audit.py correr --sitemap https://ejemplo.com/sitemap.xml --max-urls 100
  python3 audit.py correr --url https://ejemplo.com --render --resolver-sameas
  python3 audit.py fusionar --reporte salidas/2026-09-10_ejemplo.com_audit.json --hallazgos tecnico.json schema.json
  python3 audit.py resumen --corrida <id> --vector tecnico
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geomql import RUTA_DATOS, RUTA_SALIDAS, auditoria, contexto as contexto_mod, fetch, render, sitemap  # noqa: E402


def _descargador(sin_cache: bool):
    dir_cache = None if sin_cache else RUTA_DATOS / "cache"

    def _d(url, **k):
        return fetch.descargar_con_cache(url, dir_cache, **k)

    return _d


def cmd_correr(args: argparse.Namespace) -> int:
    if args.sin_negocio or args.anexo_tecnico:
        ctx = {"existe": False, "ruta": "", "campos": {"competidores": []}, "faltantes_criticos": [], "faltantes": [], "valido": False, "competidores": []}
    else:
        ctx = contexto_mod.cargar(args.contexto)
    if not ctx["valido"] and not args.sin_contexto and not (args.sin_negocio or args.anexo_tecnico):
        print("AVISO: contexto/negocio.md incompleto. Faltan campos críticos: " + ", ".join(ctx["faltantes_criticos"]), file=sys.stderr)
        print("El reporte marcará supuestos. Usa --sin-contexto para silenciar este aviso.", file=sys.stderr)
    descargar = _descargador(args.sin_cache)
    recoleccion = None
    if args.sitemap:
        recoleccion = sitemap.recolectar_urls(args.sitemap, descargar=descargar, max_urls=args.max_urls)
        urls = [u["loc"] for u in recoleccion["urls"]]
        if not urls:
            print("No se obtuvieron URLs del sitemap: " + "; ".join(recoleccion["errores"]), file=sys.stderr)
            return 1
        url_base = args.url or urls[0]
    elif args.urls:
        urls = list(args.urls)
        url_base = args.url or urls[0]
    else:
        urls = [args.url]
        url_base = args.url
    render_fn = None
    if args.render:
        if render.disponible():
            render_fn = lambda u: render.renderizar(u)  # noqa: E731
        else:
            print("AVISO: --render pedido pero Playwright no está instalado; se usa heurística.", file=sys.stderr)
    resolver = fetch.resolver if args.resolver_sameas else None
    payload = auditoria.correr(
        sufijo=args.sufijo,
        comparar=args.comparar,
        anexo_tecnico=args.anexo_tecnico,
        comparar_reglas=args.comparar_reglas,
        urls=urls,
        url_base=url_base,
        contexto=ctx,
        tipo_forzado=args.tipo,
        descargar=descargar,
        render_fn=render_fn,
        resolver=resolver,
        recoleccion_sitemap=recoleccion,
        corrida=args.corrida,
        dir_salidas=args.salidas,
        workers=args.workers,
    )
    meta = payload["meta"]
    print(f"Corrida: {meta['corrida']}")
    print(f"Reporte Markdown: {meta['archivos']['md']}")
    print(f"Reporte JSON:     {meta['archivos']['json']}")
    print("Archivos por vector para subagentes:")
    for cat, ruta in meta["archivos_vector"].items():
        print(f"  - {cat}: {ruta}")
    print()
    print(payload["titular"])
    print(payload["resumen"])
    if args.formato in ("json", "ambos"):
        print(json.dumps({k: v for k, v in payload.items() if k in ("meta", "titular", "resumen", "puntaje_cumplimiento")}, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_fusionar(args: argparse.Namespace) -> int:
    salidas = []
    for ruta in args.hallazgos:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        errores = auditoria.validar_salida_subagente(datos)
        if errores:
            print(f"{ruta}: " + "; ".join(errores), file=sys.stderr)
            return 2
        salidas.append(datos)
    nuevo = auditoria.fusionar(args.reporte, salidas)
    print(f"Reporte actualizado: {nuevo['meta']['archivos']['md']}")
    fusion = nuevo["meta"].get("fusion", {})
    print(f"Hallazgos rechazados por regla que pasa: {fusion.get('n_rechazados', 0)}")
    for r in fusion.get("rechazados", []):
        print(f"  - {r['vector']} {r['regla_id']}: '{r['titulo']}' ({r['motivo']})")
    print(f"Hallazgos en el reporte: {len(nuevo['hallazgos'])}")
    print(nuevo["titular"])
    return 0


def cmd_resumen(args: argparse.Namespace) -> int:
    ruta = RUTA_SALIDAS / "tmp" / args.corrida / f"{args.vector}.json"
    if not ruta.exists():
        print(f"No existe {ruta}", file=sys.stderr)
        return 1
    print(ruta.read_text(encoding="utf-8"))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="geo-mql-auditor · módulo audit")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("correr", help="audita una URL o un sitemap")
    c.add_argument("--url", help="URL de la página (o URL base cuando se usa --sitemap)")
    c.add_argument("--sitemap", help="URL del sitemap XML (hasta --max-urls URLs)")
    c.add_argument("--urls", nargs="+", help="lista explícita de URLs a auditar")
    c.add_argument("--max-urls", type=int, default=100)
    c.add_argument("--tipo", choices=auditoria.TIPOS_VALIDOS, help="fuerza el tipo de página")
    c.add_argument("--render", action="store_true", help="render con JavaScript vía Playwright si está instalado")
    c.add_argument("--resolver-sameas", action="store_true", help="verifica en red que los sameAs resuelven")
    c.add_argument("--sin-cache", action="store_true")
    c.add_argument("--sin-contexto", action="store_true", help="no avisar si el contexto está incompleto")
    c.add_argument("--contexto", help="ruta a contexto/negocio.md")
    c.add_argument("--salidas", help="directorio de salidas (por defecto salidas/)")
    c.add_argument("--corrida", help="identificador de la corrida")
    c.add_argument("--workers", type=int, default=4)
    c.add_argument("--formato", choices=["md", "json", "ambos"], default="md")
    c.add_argument("--sufijo", help="sufijo del nombre del reporte (por ejemplo, sitemap) para no pisar otro del mismo día")
    c.add_argument("--comparar", help="JSON de una corrida anterior para comparar hallazgos (patrón del sitio vs exclusivos)")
    c.add_argument("--anexo-tecnico", action="store_true", help="auditoría técnica comparativa: sin contexto de negocio ni visibilidad; los hallazgos de negocio quedan como no evaluables")
    c.add_argument("--sin-negocio", action="store_true", help="ignora contexto/negocio.md (corre con contexto vacío)")
    c.add_argument("--comparar-reglas", help="JSON de otra corrida para la tabla regla por regla (X de N en cada dominio)")
    c.set_defaults(fn=cmd_correr)
    f = sub.add_parser("fusionar", help="incorpora hallazgos de subagentes y regenera el reporte")
    f.add_argument("--reporte", required=True, help="ruta al JSON del reporte")
    f.add_argument("--hallazgos", nargs="+", required=True, help="archivos JSON producidos por los subagentes")
    f.set_defaults(fn=cmd_fusionar)
    r = sub.add_parser("resumen", help="imprime el archivo de un vector")
    r.add_argument("--corrida", required=True)
    r.add_argument("--vector", required=True, choices=["tecnico", "extractabilidad", "schema", "entidad"])
    r.set_defaults(fn=cmd_resumen)
    args = p.parse_args(argv)
    if args.cmd == "correr" and not (args.url or args.sitemap or args.urls):
        p.error("indica --url, --urls o --sitemap")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
