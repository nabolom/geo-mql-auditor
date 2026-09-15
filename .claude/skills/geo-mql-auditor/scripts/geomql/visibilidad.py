"""Módulo 2: visibilidad en motores de respuesta con IA.

Panel de prompts (desde el contexto de negocio o Search Console), captura manual, modo API,
análisis de respuestas (mención, cita, posición, competidores, frases de marca), métricas con
variabilidad entre repeticiones y deltas dentro del mismo modo, calibración manual vs API,
historial y reporte. La precisión de la descripción de marca queda `sin_evaluar` hasta que el
subagente geo-visibilidad o una persona la clasifique; la clasificación del subagente es Hipótesis.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from . import RUTA_DATOS, RUTA_PLANTILLAS, RUTA_SALIDAS, VERSION, contexto as contexto_mod, motores, referencias, reporte
from .html import oraciones
from .reglas import cargar_rulebook, indice

RUTA_VISIBILIDAD = RUTA_DATOS / "visibilidad"

COLUMNAS_PROMPTS = ["id", "prompt", "intencion", "etapa", "persona", "prioridad", "idioma", "origen"]
COLUMNAS_RESPUESTAS = ["corrida", "modo", "fecha", "motor", "modelo", "prompt_id", "repeticion", "respuesta", "urls_citadas", "notas"]
COLUMNAS_HISTORIAL = [
    "corrida", "modo", "fecha", "motor", "modelo", "prompt_id", "prompt", "intencion", "etapa", "persona", "idioma", "origen_prompt", "repeticion",
    "mencion", "cita", "urls_citadas", "urls_citadas_propias", "n_urls_citadas", "posicion_mencion", "rango_cita",
    "competidores_mencionados", "competidores_citados", "frase_marca", "precision", "precision_evidencia", "precision_motivo",
    "estado", "nota", "prompt_con_marca", "geografia_ajena_paises", "geografia_ajena_terminos", "n_urls_opacas",
]
# Enlaces envueltos por el motor que no se pueden atribuir a un dominio (Google AI Overviews entrega google.com/goto y responde 403 al resolverlos).
_OPACA_RE = re.compile(r"^(www\.)?google\.[a-z.]+$")


def es_fuente_opaca(url: str) -> bool:
    """Enlaces del propio buscador (google.com, google.com.mx: goto, url, search, maps…) no son citas atribuibles a una fuente."""
    u = urlparse(url.strip())
    return bool(_OPACA_RE.match((u.netloc or "").lower()))
SIN_RESPUESTA = "SIN_RESPUESTA"
SIN_AIO = "SIN_AIO"
MODELO_MANUAL = "interfaz web"

# Señales geográficas: país -> marcadores fuertes (país, gentilicio, ciudades) y débiles (siglas de universidades, que solo cuentan con un marcador fuerte).
_GEO = {
    "México": (["México", "mexicana", "mexicano", "mexicanas", "mexicanos", "Ciudad de México", "CDMX", "Monterrey", "Guadalajara"], []),
    "Perú": (["Perú", "peruana", "peruano", "peruanas", "peruanos", "Lima", "limeña", "limeñas", "limeño", "limeños"], ["UTP", "UPC", "UPN", "PUCP", "USIL"]),
    "Colombia": (["Colombia", "colombiana", "colombiano", "colombianas", "colombianos", "Bogotá", "Medellín"], ["Uniandes", "EAFIT"]),
    "Chile": (["Chile", "chilena", "chileno", "chilenas", "chilenos", "Santiago de Chile"], ["PUC", "UDD"]),
    "Argentina": (["Argentina", "argentina", "argentino", "argentinas", "argentinos", "Buenos Aires"], ["UBA", "UCA"]),
    "España": (["España", "española", "español", "españolas", "españoles", "Madrid", "Barcelona"], ["UOC", "UNIR"]),
    "Estados Unidos": (["Estados Unidos", "EE. UU.", "EEUU", "estadounidense"], []),
    "Ecuador": (["Ecuador", "ecuatoriana", "ecuatoriano", "Quito", "Guayaquil"], ["USFQ"]),
    "Guatemala": (["Guatemala", "guatemalteca", "guatemalteco"], []),
    "Costa Rica": (["Costa Rica", "costarricense", "San José de Costa Rica"], []),
    "Panamá": (["Panamá", "panameña", "panameño"], []),
    "Venezuela": (["Venezuela", "venezolana", "venezolano", "Caracas"], []),
    "Brasil": (["Brasil", "brasileña", "brasileño", "São Paulo"], []),
}
COLUMNAS_RESUMEN = [
    "corrida", "modo", "fecha", "motor", "n_prompts", "n_respuestas", "share_of_answers", "tasa_citacion", "share_of_voice",
    "acuerdo_mencion", "acuerdo_cita", "precision_correcta", "precision_parcial", "precision_incorrecta", "precision_sin_evaluar", "con_prompts_ejemplo",
]
COLUMNAS_CALIBRACION = ["fecha", "motor", "corrida_manual", "corrida_api", "n_prompts", "jaccard_medio", "acuerdo_mencion", "veredicto"]

MOTORES = {"chatgpt": "ChatGPT", "claude": "Claude", "perplexity": "Perplexity", "gemini": "Gemini", "aio": "Google AI Overviews"}
MOTORES_SOLO_MANUAL = ("aio",)
ETAPAS = {"descubrimiento": "informativa", "consideracion": "comparativa", "decision": "transaccional"}
PRECISIONES = ("correcta", "parcial", "incorrecta", "sin_evaluar")
MODOS = ("manual", "api")

PAISES = {
    "mexico": ("MX", "America/Mexico_City"), "méxico": ("MX", "America/Mexico_City"), "colombia": ("CO", "America/Bogota"), "espana": ("ES", "Europe/Madrid"), "españa": ("ES", "Europe/Madrid"),
    "argentina": ("AR", "America/Argentina/Buenos_Aires"), "chile": ("CL", "America/Santiago"), "peru": ("PE", "America/Lima"), "perú": ("PE", "America/Lima"),
    "estados unidos": ("US", "America/New_York"), "united states": ("US", "America/New_York"), "ecuador": ("EC", "America/Guayaquil"), "guatemala": ("GT", "America/Guatemala"),
    "costa rica": ("CR", "America/Costa_Rica"), "panama": ("PA", "America/Panama"), "panamá": ("PA", "America/Panama"), "uruguay": ("UY", "America/Montevideo"),
    "republica dominicana": ("DO", "America/Santo_Domingo"), "república dominicana": ("DO", "America/Santo_Domingo"), "brasil": ("BR", "America/Sao_Paulo"),
}
MODELOS_POR_DEFECTO = {"chatgpt": "gpt-5-nano", "claude": "claude-haiku-4-5-20251001", "perplexity": "perplexity/sonar", "gemini": "gemini-2.5-flash-lite"}

_IMPACTO_RE = re.compile(r"\+\s?\d+\s?(%|puntos)|impacto proyectado", re.I)


# ------------------------------------------------------------------ utilidades
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _leer_csv(ruta: Path | str) -> list[dict[str, str]]:
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return [{(k or "").lstrip("\ufeff").strip(): v for k, v in r.items()} for r in csv.DictReader(f)]


def _escribir_csv(ruta: Path | str, columnas: list[str], filas: list[dict[str, Any]], *, anexar: bool = False) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not (anexar and ruta.exists() and ruta.stat().st_size > 0)
    with open(ruta, "a" if anexar else "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        if nuevo:
            w.writeheader()
        for fila in filas:
            w.writerow({c: ("" if fila.get(c) is None else fila.get(c, "")) for c in columnas})


def _host(url: str) -> str:
    return (urlparse(url.strip()).netloc or "").lower().removeprefix("www.")


def _pct(x: float | None) -> str:
    return "sin dato" if x is None else f"{round(100 * x)}%"


# ------------------------------------------------------------------ panel de prompts
def prompts_desde_contexto(ctx: dict[str, Any]) -> list[dict[str, str]]:
    """Panel inicial: preguntas de descubrimiento, consideración y decisión del contexto, con origen=contexto."""
    campos = ctx.get("campos", {})
    personas = contexto_mod.lista_pc(campos, "personas")
    persona = personas[0] if personas else ""
    idiomas = contexto_mod.lista(campos, "idiomas")
    idioma = idiomas[0] if idiomas else "es"
    filas: list[dict[str, str]] = []
    for etapa, intencion in ETAPAS.items():
        for pregunta in contexto_mod.lista_pc(campos, f"preguntas_{etapa}"):
            filas.append({"id": f"P{len(filas) + 1:03d}", "prompt": pregunta, "intencion": intencion, "etapa": etapa, "persona": persona, "prioridad": "alta", "idioma": idioma, "origen": "contexto"})
    return filas


def cargar_prompts(ruta: Path | str) -> list[dict[str, str]]:
    return _leer_csv(ruta)


def escribir_prompts(ruta: Path | str, nuevas: list[dict[str, Any]]) -> int:
    """Anexa filas al panel sin sobrescribir ni duplicar (por texto normalizado); asigna ids consecutivos. Devuelve cuántas añadió."""
    existentes = cargar_prompts(ruta)
    vistos = {_norm(f["prompt"]) for f in existentes}
    maximo = 0
    for f in existentes:
        m = re.match(r"P(\d+)", f.get("id", ""))
        if m:
            maximo = max(maximo, int(m.group(1)))
    agregadas = []
    for f in nuevas:
        clave = _norm(f.get("prompt", ""))
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        maximo += 1
        agregadas.append({c: f.get(c, "") for c in COLUMNAS_PROMPTS} | {"id": f"P{maximo:03d}", "origen": f.get("origen") or "manual"})
    if agregadas:
        _escribir_csv(ruta, COLUMNAS_PROMPTS, existentes + agregadas)
    elif not Path(ruta).exists():
        _escribir_csv(ruta, COLUMNAS_PROMPTS, [])
    return len(agregadas)


# ------------------------------------------------------------------ configuración
def _relativa(ruta: str) -> str:
    from . import RAIZ_PROYECTO
    try:
        return str(Path(ruta).resolve().relative_to(RAIZ_PROYECTO))
    except ValueError:
        return str(ruta)


def config_desde_contexto(ctx: dict[str, Any]) -> dict[str, Any]:
    """Modelos, search_context_size (medium), repeticiones (3), user_location e idioma derivados del contexto; nada hardcodeado."""
    campos = ctx.get("campos", {})
    supuestos: list[str] = []
    geografia = [g.strip() for g in (campos.get("geografia") or "").split(",") if g.strip()]
    user_location = None
    if geografia:
        pais = PAISES.get(_norm(geografia[0]))
        if pais:
            user_location = {"country": pais[0], "timezone": pais[1]}
            if len(geografia) > 1:
                user_location["city"] = geografia[1]
            if len(geografia) > 2:
                user_location["region"] = geografia[2]
        else:
            supuestos.append(f"No se reconoció el país '{geografia[0]}' de geografia; añade su código ISO en user_location.country a mano.")
    else:
        supuestos.append("Sin geografia en contexto/negocio.md: las consultas se harán sin user_location (los motores asumirán su ubicación por defecto).")
    idiomas = contexto_mod.lista(campos, "idiomas")
    idioma = idiomas[0] if idiomas else "es"
    if not idiomas:
        supuestos.append("Sin idiomas en contexto/negocio.md: se asume 'es'.")
    return {
        "version": VERSION,
        "derivado_de": _relativa(ctx.get("ruta", "contexto/negocio.md")),
        "generado_el": date.today().isoformat(),
        "repeticiones": 3,
        "search_context_size": "medium",
        "nota_search_context_size": "Con 'low' el motor cita menos fuentes y subestima la citación; 'medium' es el valor por defecto de la serie.",
        "idioma": idioma,
        "user_location": user_location,
        "motores": {m: {"modelo": MODELOS_POR_DEFECTO[m], "activo": True} for m in MODELOS_POR_DEFECTO} | {"aio": {"modo": "manual", "activo": True, "nota": "Sin API oficial; solo captura manual."}},
        "costos_declarados": motores.NOTAS_TARIFA,
        "supuestos": supuestos,
    }


def cargar_config(ruta: Path | str, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    ruta = Path(ruta)
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    if ctx is None:
        raise FileNotFoundError(str(ruta))
    cfg = config_desde_contexto(ctx)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def motores_para(modo: str, pedidos: list[str] | None, cfg: dict[str, Any]) -> list[str]:
    if modo not in MODOS:
        raise ValueError(f"modo inválido: {modo}")
    activos = [m for m, v in cfg.get("motores", {}).items() if v.get("activo", True)]
    if pedidos:
        elegidos = [m for m in pedidos if m in MOTORES]
        if modo == "api":
            malos = [m for m in elegidos if m in MOTORES_SOLO_MANUAL]
            if malos:
                raise ValueError("solo captura manual para: " + ", ".join(malos))
        return elegidos
    # sin lista explícita: en modo API se omiten en silencio los motores solo manuales (AI Overviews)
    return [m for m in activos if m in MOTORES and (modo == "manual" or m not in MOTORES_SOLO_MANUAL)]


# ------------------------------------------------------------------ captura manual
def hoja_captura(prompts: list[dict[str, str]], cfg: dict[str, Any], *, motores: list[str], repeticiones: int, fecha: date, corrida: str) -> dict[str, Any]:
    """Hoja Markdown con un bloque por prompt × motor × repetición y el CSV vacío donde se pegan las respuestas."""
    u = cfg.get("user_location") or {}
    lugar = ", ".join(x for x in (u.get("city"), u.get("region"), u.get("country")) if x) or "sin ubicación definida"
    filas: list[dict[str, str]] = []
    pais = {"MX": "México", "CO": "Colombia", "ES": "España", "AR": "Argentina", "CL": "Chile", "PE": "Perú", "US": "Estados Unidos"}.get(u.get("country", ""), u.get("country", "") or "el país del contexto")
    idioma_nombre = {"es": "español", "en": "inglés", "pt": "portugués"}.get(cfg.get("idioma", "es"), cfg.get("idioma", "es"))
    total = len(prompts) * len(motores) * repeticiones
    nota_reps = (
        f"Repeticiones por prompt y motor: {repeticiones}."
        if repeticiones > 1
        else "Repeticiones por prompt y motor: 1 repetición. Con una sola repetición no habrá medida de variabilidad entre repeticiones; el reporte lo advertirá y los deltas frente a corridas futuras deben leerse con esa reserva."
    )
    lineas = [
        f"# Hoja de captura manual · corrida {corrida} · {fecha.isoformat()}",
        "",
        f"Modo: **manual**. {nota_reps} Esta serie no se mezcla con corridas por API.",
        "",
        "## Cómo capturar",
        "",
        f"1. Consulta **sin sesión iniciada** (ventana privada o de invitado, sin cuenta y sin memoria activada) para evitar personalización. Ubicación al consultar: {lugar}, es decir, desde {pais}. Idioma: {idioma_nombre}; los prompts van en {idioma_nombre} tal como están.",
        "2. Pega el prompt tal cual, sin añadir contexto ni preguntas de seguimiento. Una repetición es una conversación nueva.",
        "3. Pega el **texto completo de la respuesta sin recortar** en la columna `respuesta` del CSV, y las URLs citadas o enlazadas en `urls_citadas`, separadas por `|`, en el orden en que aparecen.",
        "4. Para AI Overviews: busca el prompt en Google (en español, desde México, sin sesión iniciada); si no aparece resumen con IA, escribe `SIN_AIO` en `respuesta` y deja `urls_citadas` vacío. Las fuentes del panel lateral van en `urls_citadas`.",
        "5. Si el motor pide aclaración o no responde, escribe `SIN_RESPUESTA` y anota el motivo en `notas`.",
        "",
        f"Motores: {', '.join(MOTORES[m] for m in motores)}. Prompts: {len(prompts)}. Total de respuestas a capturar: {total}.",
        "",
    ]
    for p in prompts:
        lineas.append(f"## {p['id']} · {p['prompt']}")
        lineas.append("")
        lineas.append(f"Etapa: {p.get('etapa', '')} · intención: {p.get('intencion', '')} · persona: {p.get('persona', '')} · idioma: {p.get('idioma', '')} · origen: {p.get('origen', '')}")
        lineas.append("")
        for m in motores:
            for r in range(1, repeticiones + 1):
                lineas.append(f"- [ ] {MOTORES[m]} · repetición {r} → fila `{corrida},{m},{p['id']},{r}` del CSV")
                filas.append({"corrida": corrida, "modo": "manual", "fecha": fecha.isoformat(), "motor": m, "modelo": MODELO_MANUAL, "prompt_id": p["id"], "repeticion": str(r), "respuesta": "", "urls_citadas": "", "notas": ""})
        lineas.append("")
    return {"markdown": "\n".join(lineas), "filas": filas, "corrida": corrida, "meta": {"corrida": corrida, "modo": "manual", "repeticiones": repeticiones, "motores": list(motores), "n_prompts": len(prompts), "n_filas": len(filas), "fecha": fecha.isoformat()}}


def escribir_captura(hoja: dict[str, Any], directorio: Path | str, *, fecha: date) -> dict[str, str]:
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    md = directorio / f"captura_{fecha.isoformat()}_{hoja['corrida']}.md"
    csv_ = directorio / f"respuestas_{fecha.isoformat()}_{hoja['corrida']}.csv"
    md.write_text(hoja["markdown"], encoding="utf-8")
    _escribir_csv(csv_, COLUMNAS_RESPUESTAS, hoja["filas"])
    return {"md": str(md), "csv": str(csv_)}


# ------------------------------------------------------------------ importar captura externa
def _geo_marcadores(texto: str) -> dict[str, list[str]]:
    tn = " " + _norm(texto) + " "
    encontrados: dict[str, list[str]] = {}
    for pais, (fuertes, debiles) in _GEO.items():
        f = [m for m in fuertes if re.search(r"(?<![a-z0-9])" + re.escape(_norm(m)) + r"(?![a-z0-9])", tn)]
        if not f:
            continue
        d = [m for m in debiles if re.search(r"(?<![a-z0-9])" + re.escape(_norm(m)) + r"(?![a-z0-9])", tn)]
        encontrados[pais] = f + d
    return encontrados


def senales_geograficas(texto: str, pais_propio: str) -> dict[str, list[str]]:
    """Países distintos al propio con señal fuerte (país, gentilicio o ciudad); las siglas de universidades solo suman con una señal fuerte del mismo país."""
    propio = _norm(pais_propio)
    encontrados = {p: t for p, t in _geo_marcadores(texto).items() if _norm(p) != propio}
    return {"paises": sorted(encontrados), "terminos": [t for p in sorted(encontrados) for t in encontrados[p]]}


def pais_del_contexto(ctx: dict[str, Any]) -> str:
    geografia = [g.strip() for g in (ctx.get("campos", {}).get("geografia") or "").split(",") if g.strip()]
    return geografia[0] if geografia else ""


def prompt_nombra_marca(prompt: str, ctx: dict[str, Any]) -> bool:
    return _primera_aparicion(_norm(prompt), contexto_mod.variantes_de_marca(ctx)) is not None


def importar_captura(ruta: Path | str, prompts: list[dict[str, str]], *, corrida: str, fecha: date, modo: str = "manual", repeticion: int = 1) -> dict[str, Any]:
    """Convierte un CSV externo (motor, prompt_id, pregunta, respuesta, urls_citadas, notas; con o sin BOM) a la plantilla de respuestas y lo valida contra el panel."""
    origen = _leer_csv(ruta)
    por_id = {p["id"]: p for p in prompts}
    filas = []
    desconocidos = []
    no_coinciden = []
    sin_respuesta = []
    for r in origen:
        motor = (r.get("motor") or "").strip().lower()
        pid = (r.get("prompt_id") or "").strip()
        pregunta = (r.get("pregunta") or r.get("prompt") or "").strip()
        respuesta = (r.get("respuesta") or "").strip()
        notas = (r.get("notas") or "").strip()
        if pid not in por_id:
            desconocidos.append(pid)
        elif pregunta and _norm(pregunta) != _norm(por_id[pid]["prompt"]):
            no_coinciden.append({"motor": motor, "prompt_id": pid, "pregunta_archivo": pregunta, "pregunta_panel": por_id[pid]["prompt"]})
        if respuesta.upper() == SIN_RESPUESTA:
            sin_respuesta.append({"motor": motor, "prompt_id": pid, "nota": notas})
        filas.append({"corrida": corrida, "modo": modo, "fecha": fecha.isoformat(), "motor": motor, "modelo": MODELO_MANUAL if modo == "manual" else "", "prompt_id": pid, "repeticion": str(repeticion), "respuesta": respuesta, "urls_citadas": (r.get("urls_citadas") or "").strip(), "notas": notas})
    motores_presentes = sorted({f["motor"] for f in filas if f["motor"]})
    presentes = {(f["motor"], f["prompt_id"]) for f in filas}
    faltantes = [(m, p["id"]) for m in motores_presentes for p in prompts if (m, p["id"]) not in presentes]
    validacion = {
        "n_filas": len(filas),
        "motores": motores_presentes,
        "prompt_ids": sorted({f["prompt_id"] for f in filas}),
        "prompt_ids_desconocidos": sorted(set(desconocidos)),
        "combinaciones_faltantes": faltantes,
        "preguntas_no_coinciden": no_coinciden,
        "sin_respuesta": sin_respuesta,
    }
    completa = not desconocidos and not faltantes and not no_coinciden
    return {"filas": filas, "validacion": validacion, "completa": completa}


_BLOQUE_RE = re.compile(r"^###\s*(?P<id>P\d{3})\s*$", re.M)
_CITA_INLINE_RE = re.compile(r"\s*\(/goto\?url=[^)\s]*\)")


def parsear_txt_captura(texto: str) -> list[dict[str, str]]:
    """Bloques `### Pnnn` separados por `---` con PREGUNTA:, RESPUESTA: (puede ocupar varias líneas), URLS: (una por línea) y NOTAS:."""
    bloques = []
    partes = _BLOQUE_RE.split(texto)
    # partes: [preámbulo, id1, cuerpo1, id2, cuerpo2, ...]
    for i in range(1, len(partes) - 1, 2):
        pid, cuerpo = partes[i], partes[i + 1]
        cuerpo = cuerpo.split("\n---", 1)[0]
        campos = {"pregunta": "", "respuesta": "", "urls": [], "notas": ""}
        actual = None
        for linea in cuerpo.splitlines():
            m = re.match(r"^(PREGUNTA|RESPUESTA|URLS|NOTAS):\s*(.*)$", linea)
            if m:
                actual = m.group(1).lower()
                valor = m.group(2).strip()
                if actual == "urls":
                    if valor:
                        campos["urls"].append(valor)
                else:
                    campos[actual] = valor
                continue
            if actual is None:
                continue
            l = linea.strip()
            if actual == "urls":
                if l:
                    campos["urls"].append(l)
            elif l:
                campos[actual] = (campos[actual] + " " + l).strip() if campos[actual] else l
        respuesta = _CITA_INLINE_RE.sub("", campos["respuesta"]).strip()
        bloques.append({"prompt_id": pid, "pregunta": campos["pregunta"], "respuesta": respuesta, "urls": campos["urls"], "notas": campos["notas"]})
    return bloques


def importar_txt(ruta: Path | str, prompts: list[dict[str, str]], *, corrida: str, motor: str, modo: str = "manual", fecha: date, repeticion: int = 1) -> dict[str, Any]:
    """Convierte una captura manual en texto (un motor) a la plantilla de respuestas y la valida contra el panel."""
    texto = Path(ruta).read_text(encoding="utf-8-sig")
    bloques = parsear_txt_captura(texto)
    por_id = {p["id"]: p for p in prompts}
    filas, desconocidos, no_coinciden, sin_aio, sin_respuesta = [], [], [], [], []
    for b in bloques:
        pid = b["prompt_id"]
        if pid not in por_id:
            desconocidos.append(pid)
        elif b["pregunta"] and _norm(b["pregunta"]) != _norm(por_id[pid]["prompt"]):
            no_coinciden.append({"motor": motor, "prompt_id": pid, "pregunta_archivo": b["pregunta"], "pregunta_panel": por_id[pid]["prompt"]})
        if b["respuesta"].upper() == SIN_AIO:
            sin_aio.append(pid)
        if b["respuesta"].upper() == SIN_RESPUESTA:
            sin_respuesta.append({"motor": motor, "prompt_id": pid, "nota": b["notas"]})
        filas.append({"corrida": corrida, "modo": modo, "fecha": fecha.isoformat(), "motor": motor, "modelo": MODELO_MANUAL if modo == "manual" else "", "prompt_id": pid, "repeticion": str(repeticion), "respuesta": b["respuesta"], "urls_citadas": "|".join(b["urls"]), "notas": b["notas"]})
    presentes = {f["prompt_id"] for f in filas}
    faltantes = [(motor, p["id"]) for p in prompts if p["id"] not in presentes]
    validacion = {"n_filas": len(filas), "motores": [motor], "prompt_ids": sorted(presentes), "prompt_ids_desconocidos": sorted(set(desconocidos)), "combinaciones_faltantes": faltantes, "preguntas_no_coinciden": no_coinciden, "sin_aio": sin_aio, "sin_respuesta": sin_respuesta, "n_urls": sum(len(b["urls"]) for b in bloques), "n_urls_opacas": sum(1 for b in bloques for u in b["urls"] if es_fuente_opaca(u))}
    return {"filas": filas, "validacion": validacion, "completa": not desconocidos and not faltantes and not no_coinciden}


def escribir_respuestas(ruta: Path | str, filas: list[dict[str, Any]]) -> None:
    _escribir_csv(ruta, COLUMNAS_RESPUESTAS, filas)


# ------------------------------------------------------------------ análisis
def _competidores(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in ctx.get("competidores") or []:
        dominio = (c.get("dominio") or "").removeprefix("www.")
        etiqueta = dominio.split(".")[0] if dominio else ""
        variantes = {c.get("nombre", "")}
        if etiqueta and len(etiqueta) >= 3:
            variantes.add(etiqueta)
        out.append({"nombre": c.get("nombre", ""), "dominio": dominio, "variantes": [v for v in variantes if v]})
    return out


def _primera_aparicion(texto_norm: str, variantes: list[str]) -> int | None:
    posiciones = []
    for v in variantes:
        vn = _norm(v)
        if not vn:
            continue
        m = re.search(r"(?<![a-z0-9])" + re.escape(vn) + r"(?![a-z0-9])", texto_norm)
        if m:
            posiciones.append(m.start())
    return min(posiciones) if posiciones else None


def _es_propia(url: str, dominios: list[str]) -> bool:
    h = _host(url)
    return any(h == d or h.endswith("." + d) for d in dominios if d)


def analizar_respuesta(texto: str, urls: list[str], ctx: dict[str, Any]) -> dict[str, Any]:
    """Mención, cita, posición de la marca frente a competidores, competidores mencionados y citados y frases que describen la marca."""
    variantes = contexto_mod.variantes_de_marca(ctx)
    dominios = contexto_mod.dominios_propios(ctx)
    competidores = _competidores(ctx)
    texto = texto or ""
    tn = _norm(texto)
    pos_marca = _primera_aparicion(tn, variantes)
    posiciones = {"marca": pos_marca}
    comp_mencionados = []
    for c in competidores:
        p = _primera_aparicion(tn, c["variantes"])
        if p is not None:
            comp_mencionados.append(c["nombre"])
            posiciones[c["nombre"]] = p
    orden = sorted((p, n) for n, p in posiciones.items() if p is not None)
    posicion_mencion = next((i + 1 for i, (_, n) in enumerate(orden) if n == "marca"), None)
    todas = [u.strip() for u in urls if u and u.strip()]
    opacas = [u for u in todas if es_fuente_opaca(u)]
    urls = [u for u in todas if not es_fuente_opaca(u)]
    propias = [u for u in urls if _es_propia(u, dominios)]
    rango_cita = next((i + 1 for i, u in enumerate(urls) if _es_propia(u, dominios)), None)
    comp_citados = [c["nombre"] for c in competidores if c["dominio"] and any(_es_propia(u, [c["dominio"]]) for u in urls)]
    frases = []
    if pos_marca is not None:
        for o in oraciones(texto):
            if _primera_aparicion(_norm(o), variantes) is not None:
                frases.append(o.strip()[:400])
            if len(frases) >= 3:
                break
    return {
        "mencion": pos_marca is not None,
        # cita desconocida (None) cuando todas las fuentes son opacas: no es ausencia de cita
        "cita": (None if (opacas and not urls) else bool(propias)),
        "urls_citadas": urls,
        "n_urls_opacas": len(opacas),
        "urls_citadas_propias": propias,
        "n_urls_citadas": len(urls),
        "posicion_mencion": posicion_mencion,
        "rango_cita": rango_cita,
        "competidores_mencionados": comp_mencionados,
        "competidores_citados": comp_citados,
        "frases_marca": frases,
        "precision": "sin_evaluar",
    }


def respuesta_id(fila: dict[str, Any]) -> str:
    return f"{fila.get('corrida', '')}/{fila.get('motor', '')}/{fila.get('prompt_id', '')}/{fila.get('repeticion', '')}"


def analizar(ruta_respuestas: Path | str, ctx: dict[str, Any], prompts: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convierte un CSV de respuestas (manual o API) en filas de historial."""
    por_id = {p["id"]: p for p in prompts}
    pais = pais_del_contexto(ctx)
    filas = []
    for r in _leer_csv(ruta_respuestas):
        texto = (r.get("respuesta") or "").strip()
        if not texto:
            continue  # fila de plantilla sin llenar
        p = por_id.get(r.get("prompt_id", ""), {})
        urls = [u for u in (r.get("urls_citadas") or "").split("|") if u.strip()]
        faltante = texto.upper() == SIN_RESPUESTA
        a = analizar_respuesta("" if (faltante or texto.upper() == SIN_AIO) else texto, urls if not faltante else [], ctx)
        geo = senales_geograficas(texto, pais) if (pais and not faltante) else {"paises": [], "terminos": []}
        filas.append({
            "corrida": r.get("corrida", ""), "modo": r.get("modo", "manual"), "fecha": r.get("fecha", ""), "motor": r.get("motor", ""), "modelo": r.get("modelo", ""),
            "prompt_id": r.get("prompt_id", ""), "prompt": p.get("prompt", ""), "intencion": p.get("intencion", ""), "etapa": p.get("etapa", ""), "persona": p.get("persona", ""),
            "idioma": p.get("idioma", ""), "origen_prompt": p.get("origen", ""), "repeticion": str(r.get("repeticion", "")),
            "mencion": "" if faltante else ("1" if a["mencion"] else "0"), "cita": "" if (faltante or a["cita"] is None) else ("1" if a["cita"] else "0"),
            "urls_citadas": "|".join(a["urls_citadas"]), "urls_citadas_propias": "|".join(a["urls_citadas_propias"]), "n_urls_citadas": str(a["n_urls_citadas"]),
            "posicion_mencion": "" if a["posicion_mencion"] is None else str(a["posicion_mencion"]), "rango_cita": "" if a["rango_cita"] is None else str(a["rango_cita"]),
            "competidores_mencionados": ";".join(a["competidores_mencionados"]), "competidores_citados": ";".join(a["competidores_citados"]),
            "frase_marca": a["frases_marca"][0] if a["frases_marca"] else "", "precision": "sin_evaluar", "precision_evidencia": "", "precision_motivo": "",
            "estado": "sin_respuesta" if faltante else "respuesta", "nota": (r.get("notas") or "").strip(), "prompt_con_marca": "1" if prompt_nombra_marca(p.get("prompt", ""), ctx) else "0",
            "geografia_ajena_paises": ";".join(geo["paises"]), "geografia_ajena_terminos": ";".join(geo["terminos"]),
            "n_urls_opacas": str(a["n_urls_opacas"]),
        })
    return filas


def _reales(filas: list[dict[str, str]]) -> list[dict[str, str]]:
    """Respuestas reales: las filas SIN_RESPUESTA son dato faltante y quedan fuera de todo denominador."""
    return [f for f in filas if (f.get("estado") or "respuesta") != "sin_respuesta"]


def anexar_historial(ruta: Path | str, filas: list[dict[str, str]]) -> int:
    existentes = {respuesta_id(f) for f in _leer_csv(ruta)}
    nuevas = [f for f in filas if respuesta_id(f) not in existentes]
    if nuevas:
        _escribir_csv(ruta, COLUMNAS_HISTORIAL, nuevas, anexar=True)
    return len(nuevas)


# ------------------------------------------------------------------ métricas
def _tasa(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _bloque(filas: list[dict[str, str]]) -> dict[str, Any]:
    n = len(filas)
    menciones = sum(1 for f in filas if f.get("mencion") == "1")
    con_cita_conocida = [f for f in filas if f.get("cita") in ("0", "1")]
    citas = sum(1 for f in con_cita_conocida if f.get("cita") == "1")
    opacas = sum(1 for f in filas if f.get("cita") == "" and int(f.get("n_urls_opacas") or 0) > 0)
    comp = sum(len([c for c in (f.get("competidores_mencionados") or "").split(";") if c]) for f in filas)
    return {
        "n_prompts": len({f.get("prompt_id") for f in filas}),
        "n_respuestas": n,
        "n_con_citas_atribuibles": len(con_cita_conocida),
        "n_opacas": opacas,
        "share_of_answers": _tasa(menciones, n),
        "tasa_citacion": _tasa(citas, len(con_cita_conocida)),
        "share_of_voice": _tasa(menciones, menciones + comp) if (menciones + comp) else None,
        "menciones": menciones,
        "citas": citas,
        "menciones_competidores": comp,
    }


def _variabilidad(filas: list[dict[str, str]]) -> dict[str, Any]:
    grupos: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for f in filas:
        grupos[(f.get("motor", ""), f.get("prompt_id", ""))].append(f)
    con_reps = [g for g in grupos.values() if len(g) >= 2]
    acuerdo_m = sum(1 for g in con_reps if len({f.get("mencion") for f in g}) == 1)
    acuerdo_c = sum(1 for g in con_reps if len({f.get("cita") for f in g}) == 1)
    return {
        "grupos": len(con_reps),
        "acuerdo_mencion": _tasa(acuerdo_m, len(con_reps)),
        "acuerdo_cita": _tasa(acuerdo_c, len(con_reps)),
        "nota": "Acuerdo = proporción de pares prompt×motor cuyas repeticiones coinciden en mención (o en cita). Las respuestas no son deterministas; un acuerdo bajo pide más repeticiones antes de leer deltas.",
    }


def _base_previa(resumen_previo: Path | str | None, modo: str, corrida: str) -> dict[str, dict[str, Any]] | None:
    """Última corrida anterior del mismo modo en resumen.csv: {motor: fila}."""
    if not resumen_previo:
        return None
    filas = [f for f in _leer_csv(resumen_previo) if f.get("modo") == modo and f.get("corrida") != corrida]
    if not filas:
        return None
    ultima = max(filas, key=lambda f: (f.get("fecha", ""), f.get("corrida", "")))["corrida"]
    return {f["motor"]: f for f in filas if f["corrida"] == ultima}


def metricas(filas: list[dict[str, str]], *, corrida: str, resumen_previo: Path | str | None = None, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    todas = [f for f in filas if f.get("corrida") == corrida]
    modos = {f.get("modo") for f in todas}
    if len(modos) > 1:
        raise ValueError("una corrida no puede mezclar modos: " + ", ".join(sorted(m or "" for m in modos)))
    modo = next(iter(modos), "manual") or "manual"
    faltantes_filas = [f for f in todas if (f.get("estado") or "respuesta") == "sin_respuesta"]
    filas = _reales(todas)
    por_motor = {m: _bloque([f for f in filas if f.get("motor") == m]) for m in sorted({f.get("motor", "") for f in todas})}
    cortes = {}
    for dim in ("motor", "intencion", "etapa", "idioma", "persona", "origen_prompt"):
        valores = sorted({f.get(dim, "") for f in filas})
        cortes[dim] = {v: _bloque([f for f in filas if f.get(dim, "") == v]) for v in valores}
    precision = {p: sum(1 for f in filas if (f.get("precision") or "sin_evaluar") == p) for p in PRECISIONES}
    ejemplo = sorted({f.get("prompt_id", "") for f in filas if f.get("origen_prompt") == "ejemplo"})
    base = _base_previa(resumen_previo, modo, corrida)
    delta = None
    if base:
        motores_base = sorted(k for k in base if k != "global")
        motores_actual = sorted(por_motor)
        delta = {"base": {"corrida": next(iter(base.values()))["corrida"], "modo": modo, "fecha": next(iter(base.values())).get("fecha", "")}, "global": {}, "por_motor": {}, "motores_base": motores_base, "motores_actual": motores_actual, "comparable_global": motores_base == motores_actual}
        actual_global = _bloque(filas)
        if "global" in base:
            for k in ("share_of_answers", "tasa_citacion", "share_of_voice"):
                try:
                    delta["global"][k] = round((actual_global[k] or 0) - float(base["global"].get(k) or 0), 4)
                except (TypeError, ValueError):
                    delta["global"][k] = None
        for m, b in por_motor.items():
            if m in base:
                delta["por_motor"][m] = {k: round((b[k] or 0) - float(base[m].get(k) or 0), 4) for k in ("share_of_answers", "tasa_citacion")}
    return {
        "corrida": corrida,
        "modo": modo,
        "fecha": max((f.get("fecha", "") for f in filas), default=""),
        "global": _bloque(filas),
        "por_motor": por_motor,
        "cortes": cortes,
        "variabilidad": _variabilidad(filas),
        "precision": precision,
        "con_prompts_ejemplo": bool(ejemplo),
        "prompts_ejemplo": ejemplo,
        "delta": delta,
        "competidores": _tabla_competidores(filas),
        "observaciones": _observaciones(filas, por_motor),
        "faltantes": {
            "total": len(faltantes_filas),
            "por_motor": {m: sum(1 for f in faltantes_filas if f.get("motor") == m) for m in sorted({f.get("motor", "") for f in faltantes_filas})},
            "detalle": [{"motor": f.get("motor"), "prompt_id": f.get("prompt_id"), "prompt": f.get("prompt"), "nota": f.get("nota", "")} for f in faltantes_filas],
        },
        "por_marca": _por_marca(filas),
        "dominios_por_motor": _dominios_por_motor(filas, (ctx or {}).get("competidores")),
        "respuestas_competidor_sin_marca": [{"respuesta_id": respuesta_id(f), "motor": f.get("motor"), "prompt_id": f.get("prompt_id"), "prompt": f.get("prompt"), "competidores": f.get("competidores_mencionados", "")} for f in filas if f.get("competidores_mencionados") and f.get("mencion") == "0"],
        "geografia_ajena": [{"respuesta_id": respuesta_id(f), "motor": f.get("motor"), "prompt_id": f.get("prompt_id"), "prompt": f.get("prompt"), "paises": [x for x in (f.get("geografia_ajena_paises") or "").split(";") if x], "terminos": [x for x in (f.get("geografia_ajena_terminos") or "").split(";") if x]} for f in filas if f.get("geografia_ajena_paises")],
    }


def _por_marca(filas: list[dict[str, str]]) -> dict[str, Any]:
    """Share of answers y tasa de citación por separado para prompts que nombran la marca y los que no (nunca promediados)."""
    con = [f for f in filas if f.get("prompt_con_marca") == "1"]
    sin = [f for f in filas if f.get("prompt_con_marca") != "1"]
    return {"con_marca": _bloque(con), "sin_marca": _bloque(sin)}


def _dominios_por_motor(filas: list[dict[str, str]], competidores: list[dict[str, str]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Dominios citados por motor con conteo, marca propia y competidor (por dominio del contexto o, sin contexto, por nombre)."""
    nombres = sorted({c for f in filas for c in (f.get("competidores_citados") or "").split(";") if c})
    mapa = {(c.get("dominio") or "").removeprefix("www."): c.get("nombre", "") for c in (competidores or []) if c.get("dominio")}

    genericas = {"universidad", "instituto", "colegio", "grupo", "the", "la", "el", "de"}

    def competidor_de(host: str, propio: bool) -> str:
        if propio:
            return ""
        for dom, nombre in mapa.items():
            if host == dom or host.endswith("." + dom):
                return nombre
        if mapa:
            return ""  # con dominios del contexto no se adivina por nombre
        for n in nombres:
            partes = [x for x in _norm(n).split() if x not in genericas]
            if partes and partes[0] in host.replace("-", "").replace(".", " "):
                return n
        return ""

    out: dict[str, list[dict[str, Any]]] = {}
    for motor in sorted({f.get("motor", "") for f in filas}):
        conteo: dict[str, int] = defaultdict(int)
        propio: dict[str, bool] = {}
        for f in filas:
            if f.get("motor") != motor:
                continue
            propios = {_host(u) for u in (f.get("urls_citadas_propias") or "").split("|") if u.strip()}
            for u in (f.get("urls_citadas") or "").split("|"):
                h = _host(u)
                if h:
                    conteo[h] += 1
                    propio[h] = propio.get(h, False) or h in propios
        out[motor] = sorted(({"dominio": h, "veces": n, "competidor": competidor_de(h, propio.get(h, False)), "propio": propio.get(h, False)} for h, n in conteo.items()), key=lambda x: (-x["veces"], x["dominio"]))
    return out


def _tabla_competidores(filas: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"mencionado": 0, "citado": 0})
    for f in filas:
        for c in (f.get("competidores_mencionados") or "").split(";"):
            if c:
                out[c]["mencionado"] += 1
        for c in (f.get("competidores_citados") or "").split(";"):
            if c:
                out[c]["citado"] += 1
    return dict(out)


def _observaciones(filas: list[dict[str, str]], por_motor: dict[str, Any]) -> list[dict[str, Any]]:
    """Observaciones medidas sobre el panel (Confirmado: son conteos), sin juicio del modelo."""
    obs = []
    por_prompt: dict[str, list[dict[str, str]]] = defaultdict(list)
    for f in filas:
        por_prompt[f.get("prompt_id", "")].append(f)
    for pid, fs in sorted(por_prompt.items()):
        con_comp = sum(1 for f in fs if f.get("competidores_mencionados"))
        con_marca = sum(1 for f in fs if f.get("mencion") == "1")
        if con_comp and not con_marca:
            obs.append({"tipo": "competidor_sin_marca", "prompt_id": pid, "prompt": fs[0].get("prompt", ""), "etapa": fs[0].get("etapa", ""), "detalle": f"{con_comp} de {len(fs)} respuestas mencionan un competidor y ninguna menciona la marca.", "evidencia_observacion": "Confirmado"})
        con_cita = sum(1 for f in fs if f.get("cita") == "1")
        if con_marca and not con_cita:
            obs.append({"tipo": "mencion_sin_cita", "prompt_id": pid, "prompt": fs[0].get("prompt", ""), "etapa": fs[0].get("etapa", ""), "detalle": f"La marca se menciona en {con_marca} de {len(fs)} respuestas pero ninguna cita una URL propia.", "evidencia_observacion": "Confirmado"})
    for m, b in por_motor.items():
        if b["n_respuestas"] and b["tasa_citacion"] == 0:
            obs.append({"tipo": "motor_sin_citas", "motor": m, "detalle": f"{MOTORES.get(m, m)}: ninguna de {b['n_respuestas']} respuestas cita una URL propia.", "evidencia_observacion": "Confirmado"})
    return obs


def filas_resumen(m: dict[str, Any], *, fecha: date) -> list[dict[str, Any]]:
    def fila(motor: str, b: dict[str, Any]) -> dict[str, Any]:
        return {
            "corrida": m["corrida"], "modo": m["modo"], "fecha": fecha.isoformat(), "motor": motor,
            "n_prompts": b["n_prompts"], "n_respuestas": b["n_respuestas"], "share_of_answers": b["share_of_answers"], "tasa_citacion": b["tasa_citacion"], "share_of_voice": b["share_of_voice"],
            "acuerdo_mencion": m["variabilidad"]["acuerdo_mencion"], "acuerdo_cita": m["variabilidad"]["acuerdo_cita"],
            "precision_correcta": m["precision"]["correcta"], "precision_parcial": m["precision"]["parcial"], "precision_incorrecta": m["precision"]["incorrecta"], "precision_sin_evaluar": m["precision"]["sin_evaluar"],
            "con_prompts_ejemplo": 1 if m["con_prompts_ejemplo"] else 0,
        }
    return [fila("global", m["global"])] + [fila(motor, b) for motor, b in m["por_motor"].items()]


def anexar_resumen(ruta: Path | str, filas: list[dict[str, Any]]) -> int:
    existentes = {(f.get("corrida"), f.get("modo"), f.get("motor")) for f in _leer_csv(ruta)}
    nuevas = [f for f in filas if (f.get("corrida"), f.get("modo"), f.get("motor")) not in existentes]
    if nuevas:
        _escribir_csv(ruta, COLUMNAS_RESUMEN, nuevas, anexar=True)
    return len(nuevas)


# ------------------------------------------------------------------ calibración
def _dominios_citados(f: dict[str, str]) -> set[str]:
    return {_host(u) for u in (f.get("urls_citadas") or "").split("|") if u.strip()}


def _mayoria(valores: list[str]) -> str:
    return "1" if sum(1 for v in valores if v == "1") * 2 >= len(valores) and valores else "0"


def calibrar(filas: list[dict[str, str]], *, corrida_manual: str, corrida_api: str, umbrales: dict[str, float] | None = None) -> dict[str, Any]:
    """Para los mismos prompts, compara por motor los dominios citados (Jaccard) y la mención de marca (acuerdo) entre captura manual y API."""
    umbrales = umbrales or {"jaccard_confiable": 0.5, "acuerdo_confiable": 0.8, "jaccard_parcial": 0.3, "acuerdo_parcial": 0.6}
    manual = [f for f in filas if f.get("corrida") == corrida_manual and f.get("modo") == "manual"]
    api = [f for f in filas if f.get("corrida") == corrida_api and f.get("modo") == "api"]
    por_motor: dict[str, Any] = {}
    for motor in sorted({f["motor"] for f in manual} & {f["motor"] for f in api}):
        m_por_prompt: dict[str, list[dict[str, str]]] = defaultdict(list)
        a_por_prompt: dict[str, list[dict[str, str]]] = defaultdict(list)
        for f in manual:
            if f["motor"] == motor:
                m_por_prompt[f["prompt_id"]].append(f)
        for f in api:
            if f["motor"] == motor:
                a_por_prompt[f["prompt_id"]].append(f)
        comunes = sorted(set(m_por_prompt) & set(a_por_prompt))
        if not comunes:
            continue
        jaccards = []
        acuerdos = 0
        detalle = []
        for pid in comunes:
            dm = set().union(*(_dominios_citados(f) for f in m_por_prompt[pid]))
            da = set().union(*(_dominios_citados(f) for f in a_por_prompt[pid]))
            j = len(dm & da) / len(dm | da) if (dm | da) else 1.0
            jaccards.append(j)
            mm = _mayoria([f.get("mencion", "0") for f in m_por_prompt[pid]])
            ma = _mayoria([f.get("mencion", "0") for f in a_por_prompt[pid]])
            acuerdos += 1 if mm == ma else 0
            detalle.append({"prompt_id": pid, "jaccard": round(j, 3), "mencion_manual": mm, "mencion_api": ma, "dominios_manual": sorted(dm), "dominios_api": sorted(da)})
        jm = round(sum(jaccards) / len(jaccards), 4)
        am = round(acuerdos / len(comunes), 4)
        if jm >= umbrales["jaccard_confiable"] and am >= umbrales["acuerdo_confiable"]:
            veredicto = "confiable"
        elif jm >= umbrales["jaccard_parcial"] and am >= umbrales["acuerdo_parcial"]:
            veredicto = "parcial"
        else:
            veredicto = "no confiable"
        por_motor[motor] = {"n_prompts": len(comunes), "jaccard_medio": jm, "acuerdo_mencion": am, "veredicto": veredicto, "detalle": detalle}
    return {"corrida_manual": corrida_manual, "corrida_api": corrida_api, "umbrales": umbrales, "por_motor": por_motor, "nota": "La serie API es un proxy de lo que ve el usuario. 'confiable' exige Jaccard de dominios citados ≥ 0.5 y acuerdo de mención ≥ 0.8; 'parcial' ≥ 0.3 y ≥ 0.6."}


def filas_calibracion(cal: dict[str, Any], *, fecha: date) -> list[dict[str, Any]]:
    return [{"fecha": fecha.isoformat(), "motor": m, "corrida_manual": cal["corrida_manual"], "corrida_api": cal["corrida_api"], "n_prompts": v["n_prompts"], "jaccard_medio": v["jaccard_medio"], "acuerdo_mencion": v["acuerdo_mencion"], "veredicto": v["veredicto"]} for m, v in cal["por_motor"].items()]


def anexar_calibracion(ruta: Path | str, filas: list[dict[str, Any]]) -> int:
    if filas:
        _escribir_csv(ruta, COLUMNAS_CALIBRACION, filas, anexar=True)
    return len(filas)


# ------------------------------------------------------------------ importar-gsc
_PREGUNTA_RE = re.compile(r"^(que|qué|como|cómo|cual|cuál|cuales|cuáles|cuanto|cuánto|cuanta|cuánta|cuantos|cuántos|donde|dónde|por que|por qué|quien|quién|cuando|cuándo|what|how|which|where|why|who|when|is|are|can|does|do)\b", re.I)
_COMPARACION_RE = re.compile(r"\b(vs\.?|versus|mejor|mejores|comparar|comparativa|diferencia|alternativas?|best|top|compare|difference)\b", re.I)
_DECISION_RE = re.compile(r"\b(precio|precios|costo|costos|cuesta|cuánto cuesta|cuanto cuesta|opiniones|reseñas|reviews|admisi[oó]n|inscripci[oó]n|contratar|comprar|price|pricing|cost|buy)\b", re.I)


def clasificar_consulta(consulta: str) -> tuple[str, str] | None:
    """(intencion, etapa) si la consulta tiene forma de pregunta, comparación o decisión; None si es navegacional o de una palabra."""
    c = consulta.strip()
    if len(c.split()) < 3:
        return None
    if _DECISION_RE.search(c):
        return ("transaccional", "decision")
    if _COMPARACION_RE.search(c):
        return ("comparativa", "consideracion")
    if _PREGUNTA_RE.search(c):
        return ("informativa", "descubrimiento")
    return None


def importar_gsc(ruta_csv: Path | str, ctx: dict[str, Any]) -> list[dict[str, str]]:
    """Propone filas de panel (origen=gsc) a partir de un export de consultas de Search Console."""
    campos = ctx.get("campos", {})
    personas = contexto_mod.lista_pc(campos, "personas")
    idiomas = contexto_mod.lista(campos, "idiomas")
    filas = _leer_csv(ruta_csv)
    if not filas:
        return []
    col = next((c for c in filas[0] if c and _norm(c) in ("consulta", "query", "consultas principales", "top queries", "search query")), list(filas[0])[0])
    col_clics = next((c for c in filas[0] if c and _norm(c) in ("clics", "clicks")), None)

    def clics(f: dict[str, str]) -> float:
        try:
            return float((f.get(col_clics) or "0").replace(",", "")) if col_clics else 0.0
        except ValueError:
            return 0.0

    propuestas = []
    for f in sorted(filas, key=clics, reverse=True):
        consulta = (f.get(col) or "").strip()
        clas = clasificar_consulta(consulta)
        if not clas:
            continue
        propuestas.append({"prompt": consulta, "intencion": clas[0], "etapa": clas[1], "persona": personas[0] if personas else "", "prioridad": "alta" if clics(f) > 0 else "media", "idioma": idiomas[0] if idiomas else "es", "origen": "gsc"})
    return propuestas


# ------------------------------------------------------------------ modo API
def correr_api(prompts: list[dict[str, str]], cfg: dict[str, Any], *, motores_activos: list[str], repeticiones: int, llaves: dict[str, str], dir_datos: Path | str, corrida: str, fecha: date, enviar: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Consulta cada motor con llave, guarda el JSON crudo en raw/ y escribe el CSV de respuestas con modo=api."""
    enviar = enviar or motores.enviar
    dir_datos = Path(dir_datos)
    raw = dir_datos / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    filas: list[dict[str, str]] = []
    errores: list[str] = []
    usados = []
    for motor in motores_activos:
        llave = llaves.get(motores.LLAVES.get(motor, ""), "")
        if not llave:
            errores.append(f"{motor}: sin llave en .env; se omite")
            continue
        usados.append(motor)
        modelo = cfg["motores"][motor]["modelo"]
        for p in prompts:
            for r in range(1, repeticiones + 1):
                peticion = motores.construir_peticion(motor, p["prompt"], cfg, llave)
                crudo = enviar(peticion)
                (raw / f"{corrida}_{motor}_{p['id']}_{r}.json").write_text(json.dumps({"peticion": {k: v for k, v in peticion.items() if k != "cabeceras"}, "respuesta": crudo, "fecha": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")
                ex = motores.extraer_respuesta(motor, crudo, resolver=motores.resolver_redireccion if motor == "gemini" else None)
                if ex.get("error"):
                    errores.append(f"{motor} {p['id']} r{r}: {ex['error']}")
                filas.append({"corrida": corrida, "modo": "api", "fecha": fecha.isoformat(), "motor": motor, "modelo": modelo, "prompt_id": p["id"], "repeticion": str(r), "respuesta": ex["texto"] or ("SIN_RESPUESTA" if ex.get("error") else ""), "urls_citadas": "|".join(ex["urls_citadas"]), "notas": ex.get("error", "")})
    ruta_csv = dir_datos / f"respuestas_{fecha.isoformat()}_{corrida}.csv"
    _escribir_csv(ruta_csv, COLUMNAS_RESPUESTAS, filas)
    return {"csv": str(ruta_csv), "raw": str(raw), "filas": len(filas), "motores": usados, "errores": errores, "costo_estimado": motores.costo_estimado(n_prompts=len(prompts), motores=usados, repeticiones=repeticiones)}


# ------------------------------------------------------------------ reporte
def _md_tabla(encabezados: list[str], filas: list[list[Any]]) -> str:
    if not filas:
        return "_Sin datos._"
    out = ["| " + " | ".join(encabezados) + " |", "|" + "|".join("---" for _ in encabezados) + "|"]
    for f in filas:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in f) + " |")
    return "\n".join(out)


def _reglas_v() -> list[dict[str, Any]]:
    idx = indice(cargar_rulebook())
    out = []
    for rid, regla in idx.items():
        if regla["categoria"] != "visibilidad":
            continue
        out.append({"regla_id": rid, "enunciado": regla["enunciado"], "fuerza": regla.etiqueta_fuerza(), "tipo_evidencia": regla["tipo_evidencia"], "fuentes": [{"titulo": f.get("titulo", ""), "url": f.get("url", ""), "nota": f.get("nota", "")} for f in regla.get("fuentes") or []], "referencias": referencias.extractos_para(regla)})
    return out


def construir_reporte(m: dict[str, Any], filas: list[dict[str, str]], ctx: dict[str, Any], prompts: list[dict[str, str]], *, fecha: date, calibracion: dict[str, Any] | None = None, hallazgos_subagente: list[dict[str, Any]] | None = None, notas: list[str] | None = None) -> dict[str, Any]:
    campos = ctx.get("campos", {})
    dominio = reporte.dominio_de("https://" + (campos.get("dominio") or "local"))
    g = m["global"]
    titular = f"**Visibilidad ({m['modo']}, corrida {m['corrida']})**: share of answers {_pct(g['share_of_answers'])} · tasa de citación {_pct(g['tasa_citacion'])} · share of voice {_pct(g['share_of_voice'])} en {g['n_respuestas']} respuestas de {g['n_prompts']} prompts"
    supuestos = []
    if m["con_prompts_ejemplo"]:
        supuestos.append("Se midió con filas de origen=ejemplo (" + ", ".join(m["prompts_ejemplo"]) + "): son prompts añadidos por el skill, no consultas reales del negocio. Sustitúyelas con `importar-gsc` o con preguntas del equipo antes de tomar decisiones.")
    if not ctx.get("valido"):
        supuestos.append("Contexto de negocio incompleto; faltan: " + ", ".join(ctx.get("faltantes_criticos", [])) + ".")
    if m["variabilidad"]["grupos"] == 0:
        supuestos.append("Corrida con una sola repetición por prompt y motor: sin medida de variabilidad entre repeticiones. Las respuestas no son deterministas, así que los deltas frente a otras corridas deben leerse con esa reserva; para medir variabilidad usa al menos 3 repeticiones.")
    supuestos.append("La visibilidad medida por API es un proxy de lo que ve el usuario; las series manual y api no se mezclan y los deltas se calculan solo contra la corrida anterior del mismo modo.")
    supuestos.append(f"Precisión de la descripción de marca: {m['precision']['sin_evaluar']} respuestas sin_evaluar; las clasificaciones del subagente geo-visibilidad son Hipótesis hasta revisión humana.")
    supuestos.extend(f"Nota de subagente: {n}" for n in (notas or []))
    lineas = [f"# Reporte visibilidad · {dominio}", "", titular, "", f"- Fecha: {fecha.isoformat()}", f"- Dominio: {dominio}", "- Módulo: visibilidad", f"- Modo: {m['modo']}", f"- Corrida: {m['corrida']}", f"- Prompts medidos: {g['n_prompts']} · respuestas: {g['n_respuestas']}", ""]
    lineas += ["## Supuestos y contexto", ""] + [f"- {s}" for s in supuestos] + [""]
    lineas += ["## Métricas por motor", "", _md_tabla(["Motor", "Prompts", "Respuestas", "Share of answers", "Tasa de citación", "Respuestas con citas atribuibles", "Share of voice"], [[MOTORES.get(mo, mo), b["n_prompts"], b["n_respuestas"], _pct(b["share_of_answers"]), _pct(b["tasa_citacion"]), f"{b.get('n_con_citas_atribuibles', b['n_respuestas'])} de {b['n_respuestas']}", _pct(b["share_of_voice"])] for mo, b in m["por_motor"].items()]), ""]
    opacas_total = sum(b.get("n_opacas", 0) for b in m["por_motor"].values())
    if opacas_total:
        lineas += [f"{opacas_total} respuesta(s) traen solo **fuentes opacas** (enlaces `google.com/goto` que el motor envuelve y que responden 403 al resolverse): su citación es desconocida, no cero, y quedan fuera del denominador de la tasa de citación. Para atribuirlas hay que capturar la URL de destino al pasar el cursor o al abrir el enlace.", ""]
    v = m["variabilidad"]
    if v["grupos"] == 0:
        lineas += ["## Variabilidad entre repeticiones", "", "_Una sola repetición por prompt y motor: sin medida de variabilidad entre repeticiones. Lee cada métrica como una observación puntual, no como un promedio._", ""]
    else:
        lineas += ["## Variabilidad entre repeticiones", "", f"- Pares prompt×motor con repeticiones: {v['grupos']}", f"- Acuerdo de mención: {_pct(v['acuerdo_mencion'])}", f"- Acuerdo de cita: {_pct(v['acuerdo_cita'])}", f"- {v['nota']}", ""]
    if m.get("delta"):
        d = m["delta"]
        lineas += [f"## Delta contra la corrida anterior del mismo modo ({d['base']['corrida']}, {d['base']['fecha']})", ""]
        if not d.get("comparable_global", True):
            lineas += [f"El delta global **no es comparable**: la corrida base midió {', '.join(MOTORES.get(x, x) for x in d['motores_base'])} y esta corrida midió {', '.join(MOTORES.get(x, x) for x in d['motores_actual'])}. Lee solo el delta por motor.", ""]
        lineas += [_md_tabla(["Métrica", "Delta (puntos)"], [[k, f"{round(100 * val):+d}" if val is not None else "sin dato"] for k, val in d["global"].items()]), ""]
        if d.get("por_motor"):
            lineas += [_md_tabla(["Motor", "Share of answers", "Tasa de citación"], [[MOTORES.get(mo, mo), f"{round(100 * v['share_of_answers']):+d}", f"{round(100 * v['tasa_citacion']):+d}"] for mo, v in d["por_motor"].items()]), ""]
    else:
        lineas += ["## Delta contra la corrida anterior del mismo modo", "", "_Sin corrida anterior del mismo modo; este es el punto de partida de la serie._", ""]
    for dim, titulo in (("etapa", "Por etapa"), ("intencion", "Por intención"), ("idioma", "Por idioma"), ("persona", "Por persona")):
        lineas += [f"## {titulo}", "", _md_tabla([titulo.split()[-1].capitalize(), "Respuestas", "Share of answers", "Tasa de citación"], [[k or "(sin dato)", b["n_respuestas"], _pct(b["share_of_answers"]), _pct(b["tasa_citacion"])] for k, b in m["cortes"].get(dim, {}).items()]), ""]
    fal = m.get("faltantes") or {"total": 0, "por_motor": {}, "detalle": []}
    lineas += ["## Respuestas faltantes (fuera del denominador)", ""]
    if fal["total"]:
        lineas += [f"{fal['total']} consulta(s) no obtuvieron respuesta del motor (bloqueo, registro obligatorio o error). No cuentan como ausencia de mención: quedan fuera del denominador de share of answers y de la tasa de citación.", "", _md_tabla(["Motor", "Faltantes"], [[MOTORES.get(mo, mo), n] for mo, n in fal["por_motor"].items()]), "", _md_tabla(["Motor", "Prompt", "Motivo"], [[MOTORES.get(d["motor"], d["motor"]), d["prompt_id"], d.get("nota") or "(sin nota)"] for d in fal["detalle"]]), ""]
    else:
        lineas += ["_Ninguna: todas las consultas obtuvieron respuesta._", ""]
    pm = m.get("por_marca") or {}
    lineas += ["## Prompts con marca y sin marca (no se promedian)", "", "Los prompts que nombran la marca miden precisión y citación cuando el usuario ya la conoce; los que no la nombran miden si el motor la propone por sí mismo.", "", _md_tabla(["Grupo", "Prompts", "Respuestas", "Share of answers", "Tasa de citación", "Share of voice"], [["Sin marca", pm.get("sin_marca", {}).get("n_prompts", 0), pm.get("sin_marca", {}).get("n_respuestas", 0), _pct(pm.get("sin_marca", {}).get("share_of_answers")), _pct(pm.get("sin_marca", {}).get("tasa_citacion")), _pct(pm.get("sin_marca", {}).get("share_of_voice"))], ["Con marca", pm.get("con_marca", {}).get("n_prompts", 0), pm.get("con_marca", {}).get("n_respuestas", 0), _pct(pm.get("con_marca", {}).get("share_of_answers")), _pct(pm.get("con_marca", {}).get("tasa_citacion")), _pct(pm.get("con_marca", {}).get("share_of_voice"))]]), ""]
    lineas += ["## Dominios citados por motor", ""]
    for mo, doms in (m.get("dominios_por_motor") or {}).items():
        lineas += [f"### {MOTORES.get(mo, mo)}", "", _md_tabla(["Dominio", "Veces", "Propio", "Competidor"], [[d["dominio"], d["veces"], "sí" if d["propio"] else "", d["competidor"]] for d in doms[:25]]) if doms else "_Sin URLs citadas._", ""]
    csm = m.get("respuestas_competidor_sin_marca") or []
    lineas += ["## Competidor mencionado y marca ausente", "", _md_tabla(["Motor", "Prompt", "Pregunta", "Competidores"], [[MOTORES.get(r["motor"], r["motor"]), r["prompt_id"], r.get("prompt", ""), r["competidores"].replace(";", ", ")] for r in csm]) if csm else "_Ninguna respuesta menciona un competidor sin mencionar la marca._", ""]
    geo = m.get("geografia_ajena") or []
    lineas += ["## Señales geográficas de otro país", "", "Respuestas con país, gentilicio o ciudad distintos al del contexto (las siglas de universidades solo cuentan junto a una señal fuerte). Conteo medido; la lectura de si el motor confundió el mercado la hace el subagente y una persona.", "", _md_tabla(["Motor", "Prompt", "Países", "Términos"], [[MOTORES.get(g["motor"], g["motor"]), g["prompt_id"], ", ".join(g["paises"]), ", ".join(g["terminos"])] for g in geo]) if geo else "_Ninguna respuesta trae señales de otro país._", ""]
    lineas += ["## Competidores mencionados y citados", "", _md_tabla(["Competidor", "Mencionado", "Citado"], [[c, x["mencionado"], x["citado"]] for c, x in sorted(m["competidores"].items())]), ""]
    lineas += ["## Precisión de la descripción de marca", "", f"Descripción oficial: {campos.get('descripcion_oficial', '') or '(sin descripción oficial en el contexto)'}", "", _md_tabla(["Clasificación", "Respuestas"], [[p, m["precision"][p]] for p in PRECISIONES]), ""]
    frases = [[f["motor"], f["prompt_id"], f["repeticion"], f["frase_marca"], f.get("precision", "sin_evaluar") + (" (Hipótesis)" if f.get("precision_evidencia") == "Hipótesis" else "")] for f in filas if f.get("frase_marca")]
    lineas += ["Frases textuales que describen la marca (la clasificación es Hipótesis hasta revisión humana):", "", _md_tabla(["Motor", "Prompt", "Rep.", "Frase", "Precisión"], frases[:40]), ""]
    malas = [[f["motor"], f["prompt_id"], f["frase_marca"], f.get("precision"), f.get("precision_motivo", "")] for f in filas if f.get("precision") in ("parcial", "incorrecta")]
    lineas += ["### Descripciones parciales o incorrectas (Hipótesis, revisar)", "", _md_tabla(["Motor", "Prompt", "Frase textual", "Clasificación", "Motivo"], malas) if malas else "_Ninguna clasificada como parcial o incorrecta todavía._", ""]
    lineas += ["## Observaciones del panel", "", "Conteos medidos sobre las respuestas (Confirmado); no son juicio del modelo.", ""]
    lineas += [f"- [{o['evidencia_observacion']}] " + (f"{o['prompt_id']} ({o.get('etapa', '')}): " if o.get("prompt_id") else "") + o["detalle"] for o in m["observaciones"]] or ["_Sin observaciones._"]
    lineas.append("")
    if hallazgos_subagente:
        lineas += ["## Requieren revisión humana antes de actuar", "", "Hallazgos del subagente geo-visibilidad (Hipótesis).", ""]
        for h in hallazgos_subagente:
            lineas += [f"### {h.get('titulo', '')}", "", f"- Etiquetas: **{h.get('evidencia_observacion', 'Hipótesis')}** · regla {h.get('regla_id', '')}", f"- Qué se observó: {h.get('detalle', '')}", f"- Recomendación: {h.get('recomendacion', '')}", "- Requiere revisión humana antes de actuar.", ""]
    if calibracion and calibracion.get("por_motor"):
        lineas += ["## Calibración manual vs API", "", _md_tabla(["Motor", "Prompts", "Jaccard de dominios citados", "Acuerdo de mención", "Veredicto"], [[MOTORES.get(mo, mo), c["n_prompts"], c["jaccard_medio"], _pct(c["acuerdo_mencion"]), c["veredicto"]] for mo, c in calibracion["por_motor"].items()]), "", calibracion["nota"], ""]
    lineas += ["## Panel de prompts", "", _md_tabla(["Id", "Prompt", "Etapa", "Intención", "Origen"], [[p["id"], p["prompt"], p.get("etapa", ""), p.get("intencion", ""), p.get("origen", "")] for p in prompts if p["id"] in {f.get("prompt_id") for f in filas}]), ""]
    lineas += ["## Método", "", "Panel fijo de prompts por intención, etapa, persona e idioma (V-01); mención y cita se miden por separado (V-02); competidores y frases textuales por respuesta (V-03); AI Overviews solo por captura manual (V-04); AI Overviews y asistentes se miden por separado (V-05). Las respuestas no son deterministas: la variabilidad entre repeticiones acompaña a cada métrica. Nunca se presentan impactos proyectados numéricos.", "", "AI Overviews requiere captura humana (V-04, nota de método del 2026-09-12): una captura por agente automatizado devolvió 16 de 18 SIN_AIO con el mensaje «No se puede generar una Visión general creada por IA en este momento», mientras que la misma tanda capturada a mano en ventana de incógnito devolvió 18 de 18 con resumen. La ausencia de resumen en una captura automatizada no es evidencia de que Google no lo genere. Sus fuentes llegan como enlaces google.com/goto opacos: la citación de AIO queda como desconocida, no como cero, y sus dominios no entran al conteo; la mención se mide normal sobre el texto.", ""]
    payload = {
        "meta": {"fecha": fecha.isoformat(), "dominio": dominio, "modulo": "visibilidad", "version_skill": VERSION, "corrida": m["corrida"], "modo": m["modo"], "contexto_valido": ctx.get("valido", False)},
        "titular": titular,
        "supuestos": supuestos,
        "metricas": m,
        "calibracion": calibracion,
        "hallazgos_subagente": hallazgos_subagente or [],
        "kpis": {"share_of_answers": _pct(g["share_of_answers"]), "tasa_citacion": _pct(g["tasa_citacion"])},
        "marca": {"nombre": campos.get("nombre", ""), "descripcion_oficial": campos.get("descripcion_oficial", ""), "variantes": contexto_mod.variantes_de_marca(ctx), "productos_servicios": contexto_mod.lista_pc(campos, "productos_servicios"), "competidores": [c.get("nombre", "") for c in ctx.get("competidores") or []]},
        "prompts": [p for p in prompts if p["id"] in {f.get("prompt_id") for f in filas}],
        "respuestas": filas,
        "markdown": "\n".join(lineas),
    }
    return payload


def escribir_reporte(payload: dict[str, Any], *, directorio: Path | str | None = None, corrida: str) -> dict[str, str]:
    """Escribe el reporte (md y json) y el archivo de vector para geo-visibilidad en salidas/tmp/<corrida>/visibilidad.json."""
    directorio = Path(directorio) if directorio else RUTA_SALIDAS
    rutas = reporte.escribir(payload, directorio=directorio)
    dir_tmp = directorio / "tmp" / corrida
    dir_tmp.mkdir(parents=True, exist_ok=True)
    marca = payload.get("marca", {})
    filas = payload.get("respuestas", [])
    vector = {
        "vector": "visibilidad",
        "nota_lectura": "Este archivo es la única entrada del subagente geo-visibilidad: descripción oficial, variantes de marca, competidores, reglas V-* con fuentes y las respuestas con sus frases de marca. No abras ningún otro archivo.",
        "descripcion_oficial": marca.get("descripcion_oficial", ""),
        "nombre": marca.get("nombre", ""),
        "variantes": marca.get("variantes", []),
        "productos_servicios": marca.get("productos_servicios", []),
        "competidores": marca.get("competidores", []),
        "corrida": corrida,
        "modo": payload["meta"].get("modo", ""),
        "metricas_resumen": {"global": payload["metricas"]["global"], "por_motor": payload["metricas"]["por_motor"], "por_marca": payload["metricas"].get("por_marca"), "observaciones": payload["metricas"]["observaciones"], "faltantes": payload["metricas"].get("faltantes")},
        "a_verificar": {"geografia_ajena": payload["metricas"].get("geografia_ajena", []), "nota": "Conteos medidos de señales de otro país en las respuestas. Verifica leyendo las frases si el motor respondió para otro mercado y si el patrón se repite en prompts sin marca; si aplica, repórtalo como hallazgo de método (V-01, panel y ubicación) etiquetado Hipótesis."},
        "reglas": _reglas_v(),
        "guia": referencias.guia(),
        "respuestas": [{"respuesta_id": respuesta_id(f), "motor": f.get("motor"), "prompt_id": f.get("prompt_id"), "prompt": f.get("prompt"), "prompt_con_marca": f.get("prompt_con_marca") == "1", "etapa": f.get("etapa"), "repeticion": f.get("repeticion"), "mencion": f.get("mencion") == "1", "cita": f.get("cita") == "1", "competidores_mencionados": [c for c in (f.get("competidores_mencionados") or "").split(";") if c], "geografia_ajena": [x for x in (f.get("geografia_ajena_paises") or "").split(";") if x], "frases_marca": [f.get("frase_marca")] if f.get("frase_marca") else [], "precision_actual": f.get("precision", "sin_evaluar")} for f in filas if (f.get("estado") or "respuesta") != "sin_respuesta"],
    }
    ruta_vector = dir_tmp / "visibilidad.json"
    ruta_vector.write_text(json.dumps(vector, ensure_ascii=False, indent=2), encoding="utf-8")
    rutas["vector"] = str(ruta_vector)
    return rutas


# ------------------------------------------------------------------ fusión con el subagente
def validar_salida_subagente(salida: dict[str, Any]) -> list[str]:
    errores = []
    if not isinstance(salida, dict) or "precision" not in salida:
        return ["la salida debe ser un objeto con la clave 'precision'"]
    for i, p in enumerate(salida.get("precision") or []):
        if p.get("clasificacion") not in ("correcta", "parcial", "incorrecta"):
            errores.append(f"precision {i}: clasificacion inválida")
        if not p.get("respuesta_id"):
            errores.append(f"precision {i}: falta respuesta_id")
        if _IMPACTO_RE.search((p.get("motivo") or "") + (p.get("frase") or "")):
            errores.append(f"precision {i}: contiene impacto proyectado numérico (prohibido)")
    for i, h in enumerate(salida.get("hallazgos") or []):
        if h.get("evidencia_observacion") not in ("Hipótesis",):
            errores.append(f"hallazgo {i}: los hallazgos de visibilidad del subagente son Hipótesis")
        if _IMPACTO_RE.search((h.get("detalle") or "") + (h.get("recomendacion") or "")):
            errores.append(f"hallazgo {i}: contiene impacto proyectado numérico (prohibido)")
    return errores


def fusionar(ruta_historial: Path | str, salida: dict[str, Any], *, corrida: str, ctx: dict[str, Any], prompts: list[dict[str, str]], fecha: date, directorio: Path | str | None = None, resumen_previo: Path | str | None = None, calibracion: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aplica la clasificación de precisión del subagente (Hipótesis) al historial y regenera métricas y reporte."""
    errores = validar_salida_subagente(salida)
    if errores:
        raise ValueError("salida de subagente inválida: " + "; ".join(errores))
    filas = _leer_csv(ruta_historial)
    por_id = {p["respuesta_id"]: p for p in salida.get("precision") or []}
    for f in filas:
        p = por_id.get(respuesta_id(f))
        if p:
            f["precision"] = p["clasificacion"]
            f["precision_evidencia"] = "Hipótesis"
            f["precision_motivo"] = (p.get("motivo") or "")[:400]
    _escribir_csv(ruta_historial, COLUMNAS_HISTORIAL, filas)
    de_corrida = [f for f in filas if f.get("corrida") == corrida]
    m = metricas(de_corrida, corrida=corrida, resumen_previo=resumen_previo, ctx=ctx)
    payload = construir_reporte(m, de_corrida, ctx, prompts, fecha=fecha, calibracion=calibracion, hallazgos_subagente=salida.get("hallazgos") or [], notas=salida.get("notas") or [])
    rutas = escribir_reporte(payload, directorio=directorio, corrida=corrida)
    payload["meta"]["archivos"] = rutas
    return payload
