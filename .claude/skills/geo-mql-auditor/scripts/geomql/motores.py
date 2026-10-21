"""Clientes del modo API del módulo visibilidad (solo urllib).

Endpoints, autenticación, modelos y forma de las citas verificados el 2026-09-10 (spec 4.5):
ChatGPT (Responses API con web_search), Claude (Messages API con web_search_20250305),
Perplexity (Agent API con web_search) y Gemini (generateContent con google_search).
AI Overviews no tiene API oficial: solo captura manual.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

LLAVES = {"chatgpt": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "perplexity": "PERPLEXITY_API_KEY", "gemini": "GEMINI_API_KEY"}
MOTORES_API = tuple(LLAVES)

# Tarifas declaradas por cada proveedor el 2026-09-10 (USD por búsqueda web, además de tokens).
TARIFAS_BUSQUEDA_USD = {"chatgpt": 10 / 1000, "claude": 10 / 1000, "perplexity": None, "gemini": 0.0}
NOTAS_TARIFA = {
    "chatgpt": "OpenAI cobra USD 10 por cada 1,000 búsquedas web más tokens.",
    "claude": "Anthropic cobra USD 10 por cada 1,000 búsquedas web más tokens.",
    "perplexity": "Perplexity no publica una tarifa por búsqueda en la documentación verificada; se cobra por tokens y por peticiones del Agent API.",
    "gemini": "Gemini incluye una cuota gratuita diaria de grounding con Google Search; por encima de ella cobra por petición.",
}

_ENV_RE = re.compile(r"^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$")


def leer_env(ruta: Path | str) -> dict[str, str]:
    """Parser propio de .env: KEY=valor, comillas opcionales, comentarios con #, `export` opcional. Omite valores vacíos."""
    ruta = Path(ruta)
    out: dict[str, str] = {}
    if not ruta.exists():
        return out
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        m = _ENV_RE.match(linea)
        if not m:
            continue
        clave, valor = m.group(1), m.group(2)
        if valor and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        if valor:
            out[clave] = valor
    return out


def motores_con_llave(llaves: dict[str, str]) -> list[str]:
    return [m for m in MOTORES_API if llaves.get(LLAVES[m])]


def _ubicacion(cfg: dict[str, Any], campos: tuple[str, ...]) -> dict[str, Any] | None:
    u = cfg.get("user_location") or {}
    out = {k: u[k] for k in campos if u.get(k)}
    return out or None


def construir_peticion(motor: str, prompt: str, cfg: dict[str, Any], llave: str = "") -> dict[str, Any]:
    """URL, cabeceras y cuerpo de la petición para un motor, con búsqueda web activada y ubicación del contexto."""
    modelo = (cfg.get("motores", {}).get(motor) or {}).get("modelo", "")
    tamano = cfg.get("search_context_size", "medium")
    if motor == "chatgpt":
        tool: dict[str, Any] = {"type": "web_search", "search_context_size": tamano}
        u = _ubicacion(cfg, ("country", "city", "region", "timezone"))
        if u:
            tool["user_location"] = {"type": "approximate"} | u
        return {
            "motor": motor,
            "url": "https://api.openai.com/v1/responses",
            "cabeceras": {"Authorization": f"Bearer {llave}", "Content-Type": "application/json"},
            "cuerpo": {"model": modelo, "input": prompt, "tools": [tool], "include": ["web_search_call.action.sources"]},
        }
    if motor == "claude":
        tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
        u = _ubicacion(cfg, ("country", "city", "region", "timezone"))
        if u:
            tool["user_location"] = {"type": "approximate"} | u
        return {
            "motor": motor,
            "url": "https://api.anthropic.com/v1/messages",
            "cabeceras": {"x-api-key": llave, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            "cuerpo": {"model": modelo, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}], "tools": [tool]},
        }
    if motor == "perplexity":
        tool = {"type": "web_search", "search_context_size": tamano}
        u = _ubicacion(cfg, ("country", "region", "city"))
        if u:
            tool["user_location"] = u
        return {
            "motor": motor,
            "url": "https://api.perplexity.ai/v1/agent",
            "cabeceras": {"Authorization": f"Bearer {llave}", "Content-Type": "application/json"},
            "cuerpo": {"model": modelo, "input": prompt, "tools": [tool]},
        }
    if motor == "gemini":
        return {
            "motor": motor,
            "url": f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
            "cabeceras": {"x-goog-api-key": llave, "Content-Type": "application/json"},
            "cuerpo": {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]},
        }
    raise ValueError(f"motor sin API: {motor}")


def enviar(peticion: dict[str, Any], *, timeout: int = 90) -> dict[str, Any]:
    """POST JSON y devuelve el JSON de respuesta. Los errores HTTP se devuelven como {'error': ...}."""
    datos = json.dumps(peticion["cuerpo"]).encode("utf-8")
    req = urllib.request.Request(peticion["url"], data=datos, headers=peticion["cabeceras"], method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:500]
        return {"error": f"HTTP {e.code}: {cuerpo}"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"error": f"red: {e}"}


def resolver_redireccion(url: str, *, timeout: int = 15) -> str:
    """Sigue la redirección de una URL (para las citas de Gemini vía vertexaisearch) y devuelve la URL final."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "geo-mql-auditor"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except Exception:  # noqa: BLE001
        return url


def _unicas(urls: list[str]) -> list[str]:
    out: list[str] = []
    for u in urls:
        if u and u not in out:
            out.append(u)
    return out


def extraer_respuesta(motor: str, datos: dict[str, Any], *, resolver: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Texto, URLs citadas (en orden) y fuentes consultadas a partir del JSON crudo de cada motor."""
    if datos.get("error"):
        return {"texto": "", "urls_citadas": [], "fuentes_consultadas": [], "titulos": {}, "error": datos["error"]}
    texto_partes: list[str] = []
    citadas: list[str] = []
    fuentes: list[str] = []
    titulos: dict[str, str] = {}
    if motor in ("chatgpt", "perplexity"):
        for item in datos.get("output", []):
            if item.get("type") == "web_search_call":
                for s in (item.get("action") or {}).get("sources") or []:
                    fuentes.append(s.get("url", ""))
            elif item.get("type") == "search_results":
                for s in item.get("results") or []:
                    fuentes.append(s.get("url", ""))
                    if s.get("title"):
                        titulos[s["url"]] = s["title"]
            elif item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        texto_partes.append(c.get("text", ""))
                        for a in c.get("annotations", []) or []:
                            if a.get("type") == "url_citation" and a.get("url"):
                                citadas.append(a["url"])
                                if a.get("title"):
                                    titulos[a["url"]] = a["title"]
    elif motor == "claude":
        for bloque in datos.get("content", []):
            if bloque.get("type") == "web_search_tool_result":
                for r in bloque.get("content") or []:
                    if isinstance(r, dict) and r.get("url"):
                        fuentes.append(r["url"])
                        if r.get("title"):
                            titulos[r["url"]] = r["title"]
            elif bloque.get("type") == "text":
                texto_partes.append(bloque.get("text", ""))
                for c in bloque.get("citations") or []:
                    if c.get("type") == "web_search_result_location" and c.get("url"):
                        citadas.append(c["url"])
                        if c.get("title"):
                            titulos[c["url"]] = c["title"]
    elif motor == "gemini":
        cand = (datos.get("candidates") or [{}])[0]
        for p in (cand.get("content") or {}).get("parts", []):
            if p.get("text"):
                texto_partes.append(p["text"])
        for ch in (cand.get("groundingMetadata") or {}).get("groundingChunks", []):
            web = ch.get("web") or {}
            uri = web.get("uri", "")
            if uri:
                final = resolver(uri) if resolver and "vertexaisearch" in uri else uri
                citadas.append(final)
                if web.get("title"):
                    titulos[final] = web["title"]
        fuentes = list(citadas)
    return {"texto": "\n".join(t for t in texto_partes if t).strip(), "urls_citadas": _unicas(citadas), "fuentes_consultadas": _unicas(fuentes), "titulos": titulos}


def costo_estimado(*, n_prompts: int, motores: list[str], repeticiones: int, busquedas_por_respuesta: int = 1) -> dict[str, Any]:
    """Costo máximo declarado por búsquedas web de una corrida; los tokens se cobran aparte y no se estiman."""
    respuestas = n_prompts * len(motores) * repeticiones
    busquedas = respuestas * busquedas_por_respuesta
    usd = 0.0
    por_motor = {}
    for m in motores:
        tarifa = TARIFAS_BUSQUEDA_USD.get(m)
        b = n_prompts * repeticiones * busquedas_por_respuesta
        costo = round(b * tarifa, 4) if tarifa else (None if tarifa is None else 0.0)
        por_motor[m] = {"busquedas": b, "usd_busquedas": costo, "nota": NOTAS_TARIFA.get(m, "")}
        usd += costo or 0.0
    return {
        "respuestas": respuestas,
        "busquedas": busquedas,
        "usd_busquedas_maximo": round(usd, 4),
        "por_motor": por_motor,
        "nota": "Estimación del costo por búsquedas web con las tarifas declaradas por cada proveedor el 2026-09-10; los tokens de entrada y salida se cobran aparte y no se estiman.",
    }
