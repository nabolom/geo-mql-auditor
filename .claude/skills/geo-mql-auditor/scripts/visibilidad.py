#!/usr/bin/env python3
"""CLI del módulo 2 (visibilidad).

  python3 visibilidad.py prompts      [--contexto contexto/negocio.md] [--prompts datos/visibilidad/prompts.csv]
  python3 visibilidad.py config       [--contexto ...] [--config datos/visibilidad/config.json] [--forzar]
  python3 visibilidad.py captura      --corrida m1 [--motores chatgpt,perplexity,gemini,claude,aio] [--repeticiones 3]
  python3 visibilidad.py correr       --corrida a1 [--motores chatgpt,perplexity,gemini,claude] [--repeticiones 3] [--env .env] [--solo-costo]
  python3 visibilidad.py importar-captura --csv <externo.csv> --corrida m1   # normaliza una captura externa y la valida
  python3 visibilidad.py importar-txt --archivo captura_aio_m2.txt --corrida m2 --motor aio --modo manual
  python3 visibilidad.py analizar     --respuestas datos/visibilidad/respuestas_<fecha>_<corrida>.csv
  python3 visibilidad.py metricas     --corrida m1 [--sin-reporte]
  python3 visibilidad.py calibrar     --manual m1 --api a1
  python3 visibilidad.py importar-gsc --csv export_gsc.csv [--aplicar]
  python3 visibilidad.py fusionar     --corrida m1 --salida salidas/tmp/m1/subagente_visibilidad.json

Cada corrida lleva modo (manual | api) y los modos nunca se mezclan en una serie. AI Overviews solo por captura manual.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geomql import RAIZ_PROYECTO, RUTA_SALIDAS, contexto as contexto_mod, motores, visibilidad  # noqa: E402

DIR = visibilidad.RUTA_VISIBILIDAD


def _ctx(args):
    ctx = contexto_mod.cargar(getattr(args, "contexto", None), modulo="visibilidad")
    if not ctx["valido"]:
        print("AVISO: contexto/negocio.md incompleto. Faltan campos críticos: " + ", ".join(ctx["faltantes_criticos"]), file=sys.stderr)
    return ctx


def _rutas(args):
    d = Path(getattr(args, "datos", None) or DIR)
    return {
        "dir": d,
        "prompts": Path(getattr(args, "prompts", None) or d / "prompts.csv"),
        "config": Path(getattr(args, "config", None) or d / "config.json"),
        "historial": d / "historial.csv",
        "resumen": d / "resumen.csv",
        "calibracion": d / "calibracion.csv",
    }


def _fecha(args) -> date:
    return date.fromisoformat(args.fecha) if getattr(args, "fecha", None) else date.today()


def cmd_prompts(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    filas = visibilidad.prompts_desde_contexto(ctx)
    if not filas:
        print("El contexto no tiene preguntas_descubrimiento, preguntas_consideracion ni preguntas_decision.", file=sys.stderr)
        return 1
    n = visibilidad.escribir_prompts(r["prompts"], filas)
    todas = visibilidad.cargar_prompts(r["prompts"])
    print(f"Panel: {r['prompts']} ({len(todas)} prompts; {n} nuevas desde el contexto, origen=contexto)")
    for p in todas:
        print(f"  {p['id']} [{p['etapa']}/{p['intencion']}/{p['origen']}] {p['prompt']}")
    return 0


def cmd_config(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    if r["config"].exists() and not args.forzar:
        print(f"Ya existe {r['config']}; usa --forzar para regenerarla desde el contexto.")
        return 0
    cfg = visibilidad.config_desde_contexto(ctx)
    r["config"].parent.mkdir(parents=True, exist_ok=True)
    r["config"].write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Config: {r['config']}")
    print(f"  user_location: {cfg['user_location']} · idioma: {cfg['idioma']} · repeticiones: {cfg['repeticiones']} · search_context_size: {cfg['search_context_size']}")
    for s in cfg["supuestos"]:
        print(f"  supuesto: {s}")
    return 0


def _motores(args, cfg, modo):
    pedidos = [m.strip() for m in (args.motores or "").split(",") if m.strip()] or None
    return visibilidad.motores_para(modo, pedidos, cfg)


def cmd_captura(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    cfg = visibilidad.cargar_config(r["config"], ctx)
    prompts = visibilidad.cargar_prompts(r["prompts"])
    if not prompts:
        print("No hay panel; corre primero `visibilidad.py prompts`.", file=sys.stderr)
        return 1
    motores_ = _motores(args, cfg, "manual")
    hoja = visibilidad.hoja_captura(prompts, cfg, motores=motores_, repeticiones=args.repeticiones or cfg["repeticiones"], fecha=_fecha(args), corrida=args.corrida)
    rutas = visibilidad.escribir_captura(hoja, r["dir"], fecha=_fecha(args))
    print(f"Hoja de captura: {rutas['md']}")
    print(f"CSV para pegar respuestas: {rutas['csv']} ({len(hoja['filas'])} filas; columnas respuesta, urls_citadas y notas vacías)")
    ejemplo = [p["id"] for p in prompts if p.get("origen") == "ejemplo"]
    if ejemplo:
        print("AVISO: el panel incluye filas origen=ejemplo: " + ", ".join(ejemplo))
    return 0


def cmd_correr(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    cfg = visibilidad.cargar_config(r["config"], ctx)
    prompts = visibilidad.cargar_prompts(r["prompts"])
    if not prompts:
        print("No hay panel; corre primero `visibilidad.py prompts`.", file=sys.stderr)
        return 1
    motores_ = _motores(args, cfg, "api")
    llaves = motores.leer_env(Path(args.env or RAIZ_PROYECTO / ".env"))
    con_llave = [m for m in motores_ if m in motores.motores_con_llave(llaves)]
    sin_llave = [m for m in motores_ if m not in con_llave]
    reps = args.repeticiones or cfg["repeticiones"]
    costo = motores.costo_estimado(n_prompts=len(prompts), motores=con_llave, repeticiones=reps)
    print(f"Motores con llave: {', '.join(con_llave) or 'ninguno'}" + (f" · sin llave: {', '.join(sin_llave)}" if sin_llave else ""))
    print(f"Costo estimado: {costo['respuestas']} respuestas, {costo['busquedas']} búsquedas, USD {costo['usd_busquedas_maximo']} máximo por búsquedas (tokens aparte).")
    if args.solo_costo or not con_llave:
        return 0 if con_llave else 1
    res = visibilidad.correr_api(prompts, cfg, motores_activos=con_llave, repeticiones=reps, llaves=llaves, dir_datos=r["dir"], corrida=args.corrida, fecha=_fecha(args))
    print(f"Respuestas: {res['csv']} ({res['filas']} filas, modo=api). Crudo en {res['raw']}.")
    for e in res["errores"]:
        print(f"  error: {e}", file=sys.stderr)
    return 0


def cmd_importar_captura(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    prompts = visibilidad.cargar_prompts(r["prompts"])
    res = visibilidad.importar_captura(args.csv, prompts, corrida=args.corrida, fecha=_fecha(args))
    v = res["validacion"]
    destino = Path(args.destino) if args.destino else r["dir"] / f"respuestas_{_fecha(args).isoformat()}_{args.corrida}.csv"
    print(f"Filas: {v['n_filas']} · motores: {', '.join(v['motores'])} · prompt_id distintos: {len(v['prompt_ids'])}")
    if v["prompt_ids_desconocidos"]:
        print("prompt_id que no existen en el panel: " + ", ".join(v["prompt_ids_desconocidos"]))
    if v["combinaciones_faltantes"]:
        print("Combinaciones prompt × motor faltantes: " + ", ".join(f"{m}/{p}" for m, p in v["combinaciones_faltantes"]))
    for x in v["preguntas_no_coinciden"]:
        print(f"Pregunta distinta al panel en {x['motor']}/{x['prompt_id']}: archivo «{x['pregunta_archivo']}» · panel «{x['pregunta_panel']}» (no se sustituye)")
    for x in v["sin_respuesta"]:
        print(f"SIN_RESPUESTA en {x['motor']}/{x['prompt_id']}: {x['nota'] or '(sin nota)'}")
    if v["prompt_ids_desconocidos"] and not args.forzar:
        print("No se escribe el CSV: hay prompt_id desconocidos. Usa --forzar para escribirlo de todos modos.", file=sys.stderr)
        return 2
    if destino.exists() and any((f.get("respuesta") or "").strip() for f in visibilidad._leer_csv(destino)) and not args.forzar:
        print(f"{destino} ya tiene respuestas; usa --forzar para sobrescribirlo.", file=sys.stderr)
        return 2
    visibilidad.escribir_respuestas(destino, res["filas"])
    print(f"Escrito: {destino} ({len(res['filas'])} filas; corrida {args.corrida}, modo manual, repetición 1, modelo '{visibilidad.MODELO_MANUAL}')")
    print("Validación: " + ("completa" if res["completa"] else "con observaciones (ver arriba)"))
    return 0


def cmd_importar_txt(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    prompts = visibilidad.cargar_prompts(r["prompts"])
    ruta = Path(args.archivo)
    fecha = date.fromisoformat(args.fecha) if args.fecha else date.fromtimestamp(ruta.stat().st_mtime)
    res = visibilidad.importar_txt(ruta, prompts, corrida=args.corrida, motor=args.motor, modo=args.modo, fecha=fecha)
    v = res["validacion"]
    destino = Path(args.destino) if args.destino else r["dir"] / f"respuestas_{fecha.isoformat()}_{args.corrida}_{args.motor}.csv"
    print(f"Bloques: {v['n_filas']} · motor: {args.motor} · modo: {args.modo} · fecha: {fecha.isoformat()} · URLs: {v['n_urls']} ({v['n_urls_opacas']} opacas google.com/goto)")
    if v["prompt_ids_desconocidos"]:
        print("prompt_id que no existen en el panel: " + ", ".join(v["prompt_ids_desconocidos"]))
    if v["combinaciones_faltantes"]:
        print("Prompts del panel sin bloque: " + ", ".join(p for _, p in v["combinaciones_faltantes"]))
    for x in v["preguntas_no_coinciden"]:
        print(f"Pregunta distinta al panel en {x['prompt_id']}: archivo «{x['pregunta_archivo']}» · panel «{x['pregunta_panel']}» (no se sustituye)")
    print(f"SIN_AIO: {len(v['sin_aio'])} ({', '.join(v['sin_aio']) or 'ninguno'}) · SIN_RESPUESTA: {len(v['sin_respuesta'])}")
    if v["prompt_ids_desconocidos"] and not args.forzar:
        print("No se escribe el CSV: hay prompt_id desconocidos. Usa --forzar.", file=sys.stderr)
        return 2
    if destino.exists() and not args.forzar:
        print(f"{destino} ya existe; usa --forzar para sobrescribirlo.", file=sys.stderr)
        return 2
    visibilidad.escribir_respuestas(destino, res["filas"])
    print(f"Escrito: {destino} ({len(res['filas'])} filas)")
    return 0


def cmd_analizar(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    prompts = visibilidad.cargar_prompts(r["prompts"])
    filas = visibilidad.analizar(args.respuestas, ctx, prompts)
    if not filas:
        print("El CSV no tiene respuestas llenas (columna `respuesta`).", file=sys.stderr)
        return 1
    n = visibilidad.anexar_historial(r["historial"], filas)
    corridas = sorted({f["corrida"] for f in filas})
    print(f"Historial: {r['historial']} (+{n} filas; corrida(s) {', '.join(corridas)}, modo {', '.join(sorted({f['modo'] for f in filas}))})")
    return 0


def cmd_metricas(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    prompts = visibilidad.cargar_prompts(r["prompts"])
    filas = [f for f in visibilidad._leer_csv(r["historial"]) if f.get("corrida") == args.corrida]
    if not filas:
        print(f"No hay filas de la corrida {args.corrida} en {r['historial']}; corre `analizar` primero.", file=sys.stderr)
        return 1
    m = visibilidad.metricas(filas, corrida=args.corrida, resumen_previo=r["resumen"], ctx=ctx)
    n = visibilidad.anexar_resumen(r["resumen"], visibilidad.filas_resumen(m, fecha=_fecha(args)))
    g = m["global"]
    print(f"Corrida {args.corrida} ({m['modo']}): share of answers {visibilidad._pct(g['share_of_answers'])} · tasa de citación {visibilidad._pct(g['tasa_citacion'])} · share of voice {visibilidad._pct(g['share_of_voice'])} · acuerdo de mención {visibilidad._pct(m['variabilidad']['acuerdo_mencion'])}")
    print(f"Resumen: {r['resumen']} (+{n} filas)")
    if m["con_prompts_ejemplo"]:
        print("AVISO: se midió con prompts origen=ejemplo: " + ", ".join(m["prompts_ejemplo"]))
    if m["faltantes"]["total"]:
        print(f"Respuestas faltantes fuera del denominador: {m['faltantes']['total']} " + str(m["faltantes"]["por_motor"]))
    if not args.sin_reporte:
        payload = visibilidad.construir_reporte(m, filas, ctx, prompts, fecha=_fecha(args))
        rutas = visibilidad.escribir_reporte(payload, directorio=args.salidas or RUTA_SALIDAS, corrida=args.corrida)
        print(f"Reporte: {rutas['md']}")
        print(f"Vector para geo-visibilidad: {rutas['vector']}")
        print(payload["titular"])
    return 0


def cmd_calibrar(args) -> int:
    r = _rutas(args)
    filas = visibilidad._leer_csv(r["historial"])
    cal = visibilidad.calibrar(filas, corrida_manual=args.manual, corrida_api=args.api)
    if not cal["por_motor"]:
        print("Sin motores en común entre las dos corridas (o alguna no está en el historial).", file=sys.stderr)
        return 1
    visibilidad.anexar_calibracion(r["calibracion"], visibilidad.filas_calibracion(cal, fecha=_fecha(args)))
    for m, c in cal["por_motor"].items():
        print(f"{m}: {c['n_prompts']} prompts · Jaccard {c['jaccard_medio']} · acuerdo de mención {c['acuerdo_mencion']} · {c['veredicto']}")
    print(f"Calibración: {r['calibracion']}")
    return 0


def cmd_importar_gsc(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    propuestas = visibilidad.importar_gsc(args.csv, ctx)
    if not propuestas:
        print("Ninguna consulta con forma de pregunta, comparación o decisión.")
        return 0
    print(f"{len(propuestas)} consultas propuestas (origen=gsc):")
    for p in propuestas:
        print(f"  [{p['etapa']}/{p['intencion']}] {p['prompt']}")
    if args.aplicar:
        n = visibilidad.escribir_prompts(r["prompts"], propuestas)
        print(f"Añadidas {n} al panel {r['prompts']} (sin sobrescribir las existentes).")
    else:
        print("Usa --aplicar para añadirlas al panel.")
    return 0


def cmd_fusionar(args) -> int:
    ctx = _ctx(args)
    r = _rutas(args)
    prompts = visibilidad.cargar_prompts(r["prompts"])
    salida = json.loads(Path(args.salida).read_text(encoding="utf-8"))
    errores = visibilidad.validar_salida_subagente(salida)
    if errores:
        print("Salida rechazada: " + "; ".join(errores), file=sys.stderr)
        return 2
    payload = visibilidad.fusionar(r["historial"], salida, corrida=args.corrida, ctx=ctx, prompts=prompts, fecha=_fecha(args), directorio=args.salidas or RUTA_SALIDAS, resumen_previo=r["resumen"])
    print(f"Reporte actualizado: {payload['meta']['archivos']['md']}")
    print(f"Precisión: {payload['metricas']['precision']}")
    print(payload["titular"])
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="geo-mql-auditor · módulo visibilidad")
    p.add_argument("--contexto", help="ruta a contexto/negocio.md")
    p.add_argument("--datos", help="directorio de datos de visibilidad (por defecto datos/visibilidad)")
    p.add_argument("--prompts", help="ruta al panel prompts.csv")
    p.add_argument("--config", help="ruta a config.json")
    p.add_argument("--fecha", help="AAAA-MM-DD (por defecto hoy)")
    p.add_argument("--salidas", help="directorio de reportes (por defecto salidas/)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompts", help="genera o completa el panel desde el contexto (origen=contexto)").set_defaults(fn=cmd_prompts)
    c = sub.add_parser("config", help="genera config.json desde el contexto")
    c.add_argument("--forzar", action="store_true")
    c.set_defaults(fn=cmd_config)
    cap = sub.add_parser("captura", help="hoja de captura manual y CSV para pegar respuestas")
    cap.add_argument("--corrida", required=True)
    cap.add_argument("--motores", help="lista separada por coma; por defecto los activos en config (incluye aio)")
    cap.add_argument("--repeticiones", type=int)
    cap.set_defaults(fn=cmd_captura)
    co = sub.add_parser("correr", help="modo API con las llaves presentes en .env")
    co.add_argument("--corrida", required=True)
    co.add_argument("--motores")
    co.add_argument("--repeticiones", type=int)
    co.add_argument("--env", help="ruta al .env (por defecto el de la raíz)")
    co.add_argument("--solo-costo", action="store_true", help="solo imprime el costo estimado")
    co.set_defaults(fn=cmd_correr)
    ic = sub.add_parser("importar-captura", help="convierte un CSV externo (motor, prompt_id, pregunta, respuesta, urls_citadas, notas) a la plantilla de respuestas y lo valida")
    ic.add_argument("--csv", required=True)
    ic.add_argument("--corrida", required=True)
    ic.add_argument("--destino", help="por defecto datos/visibilidad/respuestas_<fecha>_<corrida>.csv")
    ic.add_argument("--forzar", action="store_true")
    ic.set_defaults(fn=cmd_importar_captura)
    it = sub.add_parser("importar-txt", help="convierte una captura manual en texto (bloques ### Pnnn con PREGUNTA, RESPUESTA, URLS, NOTAS) a la plantilla de respuestas")
    it.add_argument("--archivo", required=True)
    it.add_argument("--corrida", required=True)
    it.add_argument("--motor", required=True, choices=list(visibilidad.MOTORES))
    it.add_argument("--modo", default="manual", choices=list(visibilidad.MODOS))
    it.add_argument("--destino")
    it.add_argument("--forzar", action="store_true")
    it.set_defaults(fn=cmd_importar_txt)
    a = sub.add_parser("analizar", help="analiza un CSV de respuestas y lo anexa al historial")
    a.add_argument("--respuestas", required=True)
    a.set_defaults(fn=cmd_analizar)
    m = sub.add_parser("metricas", help="métricas de una corrida, resumen.csv y reporte")
    m.add_argument("--corrida", required=True)
    m.add_argument("--sin-reporte", action="store_true")
    m.set_defaults(fn=cmd_metricas)
    ca = sub.add_parser("calibrar", help="overlap manual vs API por motor")
    ca.add_argument("--manual", required=True)
    ca.add_argument("--api", required=True)
    ca.set_defaults(fn=cmd_calibrar)
    g = sub.add_parser("importar-gsc", help="propone prompts desde un export de Search Console")
    g.add_argument("--csv", required=True)
    g.add_argument("--aplicar", action="store_true")
    g.set_defaults(fn=cmd_importar_gsc)
    f = sub.add_parser("fusionar", help="aplica la salida del subagente geo-visibilidad y regenera el reporte")
    f.add_argument("--corrida", required=True)
    f.add_argument("--salida", required=True)
    f.set_defaults(fn=cmd_fusionar)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
