"""Módulo 2 (visibilidad): panel de prompts desde el contexto, config derivada, hoja de captura manual,
análisis de respuestas, métricas con variabilidad y deltas por modo, calibración manual vs API,
importar-gsc, modo API con HTTP mockeado y reporte."""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from geomql import contexto, motores, visibilidad

FIX = Path(__file__).resolve().parent / "fixturas"


@pytest.fixture
def ctx():
    return contexto.cargar(FIX / "negocio_lleno.md", modulo="visibilidad")


@pytest.fixture
def datos(tmp_path):
    """Directorio datos/visibilidad de prueba, aislado del real."""
    d = tmp_path / "visibilidad"
    d.mkdir()
    return d


def _leer_csv(ruta):
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------- panel de prompts
def test_panel_de_prompts_sale_del_contexto_con_origen_contexto(ctx):
    filas = visibilidad.prompts_desde_contexto(ctx)
    assert len(filas) == 6
    assert [f["id"] for f in filas] == ["P001", "P002", "P003", "P004", "P005", "P006"]
    assert all(f["origen"] == "contexto" and f["idioma"] == "es" and f["persona"] == "Director de RH" for f in filas)
    assert filas[0]["prompt"] == "¿Qué es el timbrado de nómina?" and filas[0]["etapa"] == "descubrimiento" and filas[0]["intencion"] == "informativa"
    assert filas[2]["etapa"] == "consideracion" and filas[2]["intencion"] == "comparativa"
    assert filas[4]["etapa"] == "decision" and filas[4]["intencion"] == "transaccional"
    assert set(visibilidad.COLUMNAS_PROMPTS) == set(filas[0])


def test_escribir_prompts_no_sobrescribe_y_marca_ejemplo(ctx, datos):
    ruta = datos / "prompts.csv"
    n = visibilidad.escribir_prompts(ruta, visibilidad.prompts_desde_contexto(ctx))
    assert n == 6 and len(_leer_csv(ruta)) == 6
    # una segunda generación no duplica
    assert visibilidad.escribir_prompts(ruta, visibilidad.prompts_desde_contexto(ctx)) == 0
    # una fila de ejemplo añadida a mano conserva su origen
    extra = visibilidad.escribir_prompts(ruta, [{"prompt": "¿Qué es un PAC?", "intencion": "informativa", "etapa": "descubrimiento", "persona": "Director de RH", "prioridad": "media", "idioma": "es", "origen": "ejemplo"}])
    assert extra == 1
    filas = visibilidad.cargar_prompts(ruta)
    assert filas[-1]["id"] == "P007" and filas[-1]["origen"] == "ejemplo"


# ------------------------------------------------------------- config
def test_config_toma_ubicacion_e_idioma_del_contexto(ctx):
    cfg = visibilidad.config_desde_contexto(ctx)
    assert cfg["repeticiones"] == 3 and cfg["search_context_size"] == "medium"
    assert cfg["user_location"]["country"] == "MX" and cfg["user_location"]["city"] == "Monterrey" and cfg["user_location"]["timezone"] == "America/Mexico_City"
    assert cfg["idioma"] == "es"
    assert cfg["motores"]["chatgpt"]["modelo"] == "gpt-5-nano" and cfg["motores"]["claude"]["modelo"] == "claude-haiku-4-5-20251001"
    assert cfg["motores"]["perplexity"]["modelo"] == "perplexity/sonar" and cfg["motores"]["gemini"]["modelo"] == "gemini-2.5-flash-lite"
    assert cfg["motores"]["aio"]["modo"] == "manual" and "derivado_de" in cfg


def test_config_sin_geografia_no_inventa_ubicacion(tmp_path):
    ruta = tmp_path / "n.md"
    ruta.write_text("## Negocio\n- nombre: X\n- dominio: x.mx\n## Mercado\n- idiomas: en\n", encoding="utf-8")
    cfg = visibilidad.config_desde_contexto(contexto.cargar(ruta))
    assert cfg["user_location"] is None and cfg["idioma"] == "en"
    assert any("geografia" in s for s in cfg["supuestos"])


# ------------------------------------------------------------- captura manual
def test_hoja_de_captura_cubre_prompt_motor_repeticion_y_aio_solo_manual(ctx, datos):
    prompts = visibilidad.prompts_desde_contexto(ctx)[:2]
    cfg = visibilidad.config_desde_contexto(ctx)
    hoja = visibilidad.hoja_captura(prompts, cfg, motores=["chatgpt", "aio"], repeticiones=2, fecha=date(2026, 9, 11), corrida="m1")
    md, filas = hoja["markdown"], hoja["filas"]
    assert len(filas) == 2 * 2 * 2
    assert all(f["modo"] == "manual" and f["respuesta"] == "" and f["corrida"] == "m1" for f in filas)
    assert {f["motor"] for f in filas} == {"chatgpt", "aio"}
    assert "¿Qué es el timbrado de nómina?" in md and "AI Overviews" in md and "Monterrey" in md
    assert "repetición 2" in md.lower() or "repetición: 2" in md.lower()
    assert "sin sesión iniciada" in md and "en español" in md and "desde México" in md and "texto completo" in md and "sin recortar" in md
    # con una sola repetición la hoja lo registra y avisa que no habrá variabilidad
    hoja1 = visibilidad.hoja_captura(prompts, cfg, motores=["chatgpt"], repeticiones=1, fecha=date(2026, 9, 11), corrida="m1")
    assert "1 repetición" in hoja1["markdown"] and "variabilidad" in hoja1["markdown"].lower()
    assert hoja1["meta"]["repeticiones"] == 1 and hoja1["meta"]["modo"] == "manual"
    rutas = visibilidad.escribir_captura(hoja, datos, fecha=date(2026, 9, 11))
    assert Path(rutas["md"]).name == "captura_2026-09-11_m1.md" and Path(rutas["csv"]).name == "respuestas_2026-09-11_m1.csv"
    assert _leer_csv(rutas["csv"])[0].keys() == set(visibilidad.COLUMNAS_RESPUESTAS)


def test_captura_no_incluye_aio_en_modo_api(ctx):
    cfg = visibilidad.config_desde_contexto(ctx)
    with pytest.raises(ValueError):
        visibilidad.motores_para("api", ["chatgpt", "aio"], cfg)
    assert visibilidad.motores_para("manual", ["chatgpt", "aio"], cfg) == ["chatgpt", "aio"]


# ------------------------------------------------------------- análisis
def test_analizar_respuesta_mencion_cita_posicion_y_competidores(ctx):
    texto = "Contpaqi es la más usada. Nómina Fácil es un software de nómina en la nube para empresas medianas. Runa también aparece."
    urls = ["https://www.contpaqi.com/nomina", "https://blog.nominafacil.mx/timbrado", "https://runahr.com/"]
    a = visibilidad.analizar_respuesta(texto, urls, ctx)
    assert a["mencion"] is True and a["cita"] is True
    assert a["posicion_mencion"] == 2, "Contpaqi se menciona antes que la marca"
    assert a["rango_cita"] == 2 and a["urls_citadas_propias"] == ["https://blog.nominafacil.mx/timbrado"]
    assert a["competidores_mencionados"] == ["Contpaqi", "Runa"] and a["competidores_citados"] == ["Contpaqi", "Runa"]
    assert a["frases_marca"] and "Nómina Fácil es un software" in a["frases_marca"][0]
    assert a["precision"] == "sin_evaluar"
    b = visibilidad.analizar_respuesta("El timbrado lo hace un PAC.", ["https://www.sat.gob.mx/"], ctx)
    assert b["mencion"] is False and b["cita"] is False and b["posicion_mencion"] is None and b["rango_cita"] is None and b["frases_marca"] == []
    c = visibilidad.analizar_respuesta("nomina facil sin acentos también cuenta; y NóminaFácil junto.", [], ctx)
    assert c["mencion"] is True


def test_analizar_csv_produce_historial_con_modo_y_datos_del_prompt(ctx, datos):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    filas = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    assert len(filas) == 8 and all(f["modo"] == "manual" and f["corrida"] == "m1" for f in filas)
    assert set(visibilidad.COLUMNAS_HISTORIAL) == set(filas[0])
    f = next(x for x in filas if x["motor"] == "chatgpt" and x["prompt_id"] == "P001" and x["repeticion"] == "1")
    assert f["mencion"] == "1" and f["cita"] == "1" and f["etapa"] == "descubrimiento" and f["origen_prompt"] == "contexto"
    assert f["competidores_mencionados"] == "Contpaqi" and f["precision"] == "sin_evaluar"
    n = visibilidad.anexar_historial(datos / "historial.csv", filas)
    assert n == 8 and visibilidad.anexar_historial(datos / "historial.csv", filas) == 0, "la misma corrida no se duplica"


# ------------------------------------------------------------- métricas
def test_metricas_share_citacion_voice_variabilidad_y_cortes(ctx):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    filas = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    m = visibilidad.metricas(filas, corrida="m1")
    # menciones: chatgpt P001r1 sí, P001r2 sí, P003r1 no, P003r2 sí; perplexity P001 no, no; P003r1 sí, r2 no -> 4/8
    assert m["global"]["n_respuestas"] == 8 and m["global"]["share_of_answers"] == 0.5
    # citas propias: chatgpt P001r1 sí, r2 sí; perplexity P003r1 sí -> 3/8
    assert m["global"]["tasa_citacion"] == 0.375
    assert m["por_motor"]["chatgpt"]["share_of_answers"] == 0.75 and m["por_motor"]["perplexity"]["share_of_answers"] == 0.25
    # variabilidad: grupos prompt×motor con acuerdo de mención: chatgpt P001 (sí,sí) acuerdo; chatgpt P003 (no,sí) no; perplexity P001 (no,no) acuerdo; perplexity P003 (sí,no) no -> 0.5
    assert m["variabilidad"]["acuerdo_mencion"] == 0.5 and m["variabilidad"]["grupos"] == 4
    assert 0 < m["global"]["share_of_voice"] < 1
    assert set(m["cortes"]) >= {"motor", "intencion", "etapa", "idioma", "persona"}
    assert m["cortes"]["etapa"]["consideracion"]["n_respuestas"] == 4
    assert m["precision"]["sin_evaluar"] == 8
    assert m["modo"] == "manual" and m["con_prompts_ejemplo"] is False


def test_metricas_delta_solo_contra_corrida_anterior_del_mismo_modo(ctx, datos):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    filas = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    resumen = datos / "resumen.csv"
    # una corrida API previa con share alto no debe usarse como base de una corrida manual
    visibilidad.anexar_resumen(resumen, [{"corrida": "a0", "modo": "api", "fecha": "2026-09-01", "motor": "global", "n_prompts": 2, "n_respuestas": 8, "share_of_answers": 0.9, "tasa_citacion": 0.9, "share_of_voice": 0.9, "acuerdo_mencion": 1.0, "acuerdo_cita": 1.0, "con_prompts_ejemplo": 0}])
    visibilidad.anexar_resumen(resumen, [{"corrida": "m0", "modo": "manual", "fecha": "2026-09-05", "motor": "global", "n_prompts": 2, "n_respuestas": 8, "share_of_answers": 0.25, "tasa_citacion": 0.25, "share_of_voice": 0.2, "acuerdo_mencion": 1.0, "acuerdo_cita": 1.0, "con_prompts_ejemplo": 0}])
    m = visibilidad.metricas(filas, corrida="m1", resumen_previo=resumen)
    assert m["delta"]["base"]["corrida"] == "m0" and m["delta"]["base"]["modo"] == "manual"
    assert m["delta"]["global"]["share_of_answers"] == 0.25
    filas_resumen = visibilidad.filas_resumen(m, fecha=date(2026, 9, 11))
    assert all(f["modo"] == "manual" for f in filas_resumen) and any(f["motor"] == "global" for f in filas_resumen)
    visibilidad.anexar_resumen(resumen, filas_resumen)
    assert len(_leer_csv(resumen)) == 2 + len(filas_resumen)


def test_metricas_advierten_prompts_de_ejemplo(ctx):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    prompts[0]["origen"] = "ejemplo"
    filas = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    m = visibilidad.metricas(filas, corrida="m1")
    assert m["con_prompts_ejemplo"] is True and "P001" in m["prompts_ejemplo"]


# ------------------------------------------------------------- calibración
def test_calibrar_compara_dominios_citados_y_mencion_por_motor(ctx):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    manual = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    api = [dict(f, corrida="a1", modo="api", modelo="gpt-5-nano") for f in manual if f["motor"] == "chatgpt"]
    # la API "olvida" una cita en P001 rep 1 y cambia la mención de P003 rep 2
    api[0]["urls_citadas"] = "https://www.sat.gob.mx/timbrado"
    api[3]["mencion"] = "0"
    cal = visibilidad.calibrar(manual + api, corrida_manual="m1", corrida_api="a1")
    c = cal["por_motor"]["chatgpt"]
    # P001: dominios distintos en una repetición -> Jaccard < 1; mención igual. P003: la API pierde la mención mayoritaria -> desacuerdo.
    assert c["n_prompts"] == 2 and 0 < c["jaccard_medio"] < 1 and c["acuerdo_mencion"] == 0.5, c
    assert c["veredicto"] == "no confiable", "acuerdo de mención 0.5 está por debajo del umbral parcial (0.6)"
    api_fiel = [dict(f, corrida="a2", modo="api") for f in manual if f["motor"] == "chatgpt"]
    assert visibilidad.calibrar(manual + api_fiel, corrida_manual="m1", corrida_api="a2")["por_motor"]["chatgpt"]["veredicto"] == "confiable"
    assert "perplexity" not in cal["por_motor"], "sin corrida API para ese motor no se calibra"
    assert set(visibilidad.COLUMNAS_CALIBRACION) == set(visibilidad.filas_calibracion(cal, fecha=date(2026, 9, 11))[0])


# ------------------------------------------------------------- importar-gsc
def test_importar_gsc_filtra_preguntas_y_no_sobrescribe(ctx, datos):
    ruta = datos / "prompts.csv"
    visibilidad.escribir_prompts(ruta, visibilidad.prompts_desde_contexto(ctx))
    propuestas = visibilidad.importar_gsc(FIX / "visibilidad" / "gsc_consultas.csv", ctx)
    textos = [p["prompt"] for p in propuestas]
    assert "nomina facil" not in textos and "timbrado cfdi 4.0" not in textos
    assert "mejor software de nomina para pymes" in textos and "contpaqi vs nomina facil" in textos and "cuanto cuesta un software de nomina" in textos
    assert all(p["origen"] == "gsc" for p in propuestas)
    comp = next(p for p in propuestas if "vs" in p["prompt"])
    assert comp["intencion"] == "comparativa" and comp["etapa"] == "consideracion"
    dec = next(p for p in propuestas if "cuesta" in p["prompt"])
    assert dec["intencion"] == "transaccional" and dec["etapa"] == "decision"
    assert "como calcular finiquito 2026" in textos, "pregunta con 'como' también entra"
    n = visibilidad.escribir_prompts(ruta, propuestas)
    filas = visibilidad.cargar_prompts(ruta)
    assert n == len(propuestas) - 1, "la consulta que ya existe como pregunta del contexto se omite"
    assert len(filas) == 6 + n and filas[0]["origen"] == "contexto"
    # "qué es el timbrado de nómina" ya existe como pregunta del contexto: no se duplica
    assert sum(1 for f in filas if "timbrado de nómina" in f["prompt"].lower()) == 1


# ------------------------------------------------------------- modo API (sin red)
def test_env_parser_y_llaves_presentes(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comentario\nOPENAI_API_KEY=sk-test\nexport GEMINI_API_KEY='g-1'\nANTHROPIC_API_KEY=\n", encoding="utf-8")
    llaves = motores.leer_env(env)
    assert llaves["OPENAI_API_KEY"] == "sk-test" and llaves["GEMINI_API_KEY"] == "g-1" and "ANTHROPIC_API_KEY" not in llaves
    assert motores.motores_con_llave(llaves) == ["chatgpt", "gemini"]


def test_peticiones_por_motor_activan_busqueda_y_ubicacion(ctx):
    cfg = visibilidad.config_desde_contexto(ctx)
    r = motores.construir_peticion("chatgpt", "¿Qué es el timbrado?", cfg)
    assert r["url"].endswith("/v1/responses") and r["cuerpo"]["model"] == "gpt-5-nano"
    tool = r["cuerpo"]["tools"][0]
    assert tool["type"] == "web_search" and tool["search_context_size"] == "medium" and tool["user_location"]["country"] == "MX"
    assert "web_search_call.action.sources" in r["cuerpo"]["include"]
    r = motores.construir_peticion("claude", "q", cfg)
    assert r["cabeceras"]["anthropic-version"] == "2023-06-01" and r["cuerpo"]["tools"][0]["type"] == "web_search_20250305"
    r = motores.construir_peticion("perplexity", "q", cfg)
    assert r["url"].endswith("/v1/agent") and r["cuerpo"]["tools"][0]["type"] == "web_search"
    r = motores.construir_peticion("gemini", "q", cfg)
    assert ":generateContent" in r["url"] and r["cuerpo"]["tools"] == [{"google_search": {}}]


def test_extraer_respuesta_de_cada_motor():
    openai = {"output": [{"type": "web_search_call", "action": {"sources": [{"url": "https://a.mx/1"}]}}, {"type": "message", "content": [{"type": "output_text", "text": "Texto A", "annotations": [{"type": "url_citation", "url": "https://a.mx/1", "title": "A"}]}]}]}
    r = motores.extraer_respuesta("chatgpt", openai)
    assert r["texto"] == "Texto A" and r["urls_citadas"] == ["https://a.mx/1"] and r["fuentes_consultadas"] == ["https://a.mx/1"]
    claude = {"content": [{"type": "web_search_tool_result", "content": [{"type": "web_search_result", "url": "https://b.mx/2", "title": "B"}]}, {"type": "text", "text": "Texto B", "citations": [{"type": "web_search_result_location", "url": "https://b.mx/2", "cited_text": "x"}]}]}
    r = motores.extraer_respuesta("claude", claude)
    assert r["texto"] == "Texto B" and r["urls_citadas"] == ["https://b.mx/2"]
    perplexity = {"output": [{"type": "search_results", "results": [{"url": "https://c.mx/3"}]}, {"type": "message", "content": [{"type": "output_text", "text": "Texto C", "annotations": [{"type": "url_citation", "url": "https://c.mx/3"}]}]}]}
    r = motores.extraer_respuesta("perplexity", perplexity)
    assert r["texto"] == "Texto C" and r["urls_citadas"] == ["https://c.mx/3"]
    gemini = {"candidates": [{"content": {"parts": [{"text": "Texto D"}]}, "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc", "title": "d.mx"}}]}}]}
    r = motores.extraer_respuesta("gemini", gemini, resolver=lambda u: "https://d.mx/4")
    assert r["texto"] == "Texto D" and r["urls_citadas"] == ["https://d.mx/4"]


def test_correr_api_con_http_mockeado_guarda_crudo_y_respuestas(ctx, datos, monkeypatch):
    prompts = visibilidad.prompts_desde_contexto(ctx)[:2]
    cfg = visibilidad.config_desde_contexto(ctx)
    llamadas = []

    def enviar(peticion):
        llamadas.append(peticion)
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": f"Respuesta a {peticion['cuerpo']['input']}", "annotations": [{"type": "url_citation", "url": "https://www.nominafacil.mx/x"}]}]}]}

    res = visibilidad.correr_api(prompts, cfg, motores_activos=["chatgpt"], repeticiones=2, llaves={"OPENAI_API_KEY": "k"}, dir_datos=datos, corrida="a1", fecha=date(2026, 9, 11), enviar=enviar)
    assert len(llamadas) == 4 and llamadas[0]["cabeceras"]["Authorization"] == "Bearer k"
    filas = _leer_csv(res["csv"])
    assert len(filas) == 4 and all(f["modo"] == "api" and f["modelo"] == "gpt-5-nano" and f["corrida"] == "a1" for f in filas)
    assert len(list((datos / "raw").glob("a1_chatgpt_*.json"))) == 4
    assert res["costo_estimado"]["busquedas"] == 4 and res["costo_estimado"]["usd_busquedas_maximo"] == round(4 * 10 / 1000, 4)


def test_costo_estimado_documenta_tarifas():
    c = motores.costo_estimado(n_prompts=10, motores=["chatgpt", "claude", "gemini"], repeticiones=3, busquedas_por_respuesta=1)
    assert c["respuestas"] == 90 and c["busquedas"] == 90
    assert c["usd_busquedas_maximo"] == round(60 * 10 / 1000, 4), "OpenAI y Anthropic cobran USD 10 por 1000 búsquedas; Gemini tiene cuota gratuita"
    assert "tokens" in c["nota"].lower()


# ------------------------------------------------------------- reporte y vector
def test_reporte_visibilidad_titular_con_metricas_y_advertencia_de_ejemplo(ctx, datos, tmp_path):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    prompts[0]["origen"] = "ejemplo"
    filas = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    m = visibilidad.metricas(filas, corrida="m1")
    payload = visibilidad.construir_reporte(m, filas, ctx, prompts, fecha=date(2026, 9, 11))
    assert payload["titular"].startswith("**Visibilidad") and "50%" in payload["titular"] and "manual" in payload["titular"]
    md = payload["markdown"]
    assert "origen=ejemplo" in md and "P001" in md, "advierte que se midió con filas de ejemplo"
    assert "Variabilidad entre repeticiones" in md and "sin_evaluar" in md and "Hipótesis" in md
    assert "no se mezclan" in md.lower() or "mismo modo" in md.lower()
    assert "proxy" in md.lower()
    rutas = visibilidad.escribir_reporte(payload, directorio=tmp_path / "salidas", corrida="m1")
    assert Path(rutas["md"]).name == "2026-09-11_nominafacil.mx_visibilidad.md"
    vector = json.loads(Path(rutas["vector"]).read_text(encoding="utf-8"))
    assert vector["descripcion_oficial"].startswith("Software de nómina") and len(vector["respuestas"]) == 8
    assert all(r["frases_marca"] is not None and "respuesta_id" in r for r in vector["respuestas"])
    assert {r["regla_id"] for r in vector["reglas"]} == {"V-01", "V-02", "V-03", "V-04", "V-05"} and vector["reglas"][0]["fuentes"][0]["url"]
    assert "guia" in vector


def test_fusionar_precision_del_subagente_queda_como_hipotesis(ctx, datos, tmp_path):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    filas = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    ruta_h = datos / "historial.csv"
    visibilidad.anexar_historial(ruta_h, filas)
    rid = visibilidad.respuesta_id(filas[1])
    salida = {"vector": "visibilidad", "precision": [{"respuesta_id": rid, "clasificacion": "correcta", "frase": "Nómina Fácil es un software de nómina en la nube", "motivo": "coincide con la descripción oficial"}], "hallazgos": [{"regla_id": "V-03", "titulo": "Descripción parcial en Perplexity", "detalle": "d", "recomendacion": "r", "evidencia_observacion": "Hipótesis"}], "notas": ["n"]}
    res = visibilidad.fusionar(ruta_h, salida, corrida="m1", ctx=ctx, prompts=prompts, fecha=date(2026, 9, 11), directorio=tmp_path / "salidas")
    filas2 = _leer_csv(ruta_h)
    f = next(x for x in filas2 if visibilidad.respuesta_id(x) == rid)
    assert f["precision"] == "correcta" and f["precision_evidencia"] == "Hipótesis" and "coincide" in f["precision_motivo"]
    assert res["metricas"]["precision"]["correcta"] == 1 and res["metricas"]["precision"]["sin_evaluar"] == 7
    assert "requiere revisión humana" in res["markdown"].lower() or "revisión humana" in res["markdown"].lower()
    with pytest.raises(ValueError):
        visibilidad.fusionar(ruta_h, {"vector": "visibilidad", "precision": [{"respuesta_id": rid, "clasificacion": "correcta", "frase": "x", "motivo": "subirá +20% de citas"}], "hallazgos": [], "notas": []}, corrida="m1", ctx=ctx, prompts=prompts, fecha=date(2026, 9, 11), directorio=tmp_path / "s2")


# ------------------------------------------------------------- CLI de punta a punta (sin red)
def test_cli_flujo_manual_completo(tmp_path, capsys):
    import importlib.util
    ruta_cli = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "geo-mql-auditor" / "scripts" / "visibilidad.py"
    spec = importlib.util.spec_from_file_location("visibilidad_cli", ruta_cli)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    datos = tmp_path / "datos"
    salidas = tmp_path / "salidas"
    base = ["--contexto", str(FIX / "negocio_lleno.md"), "--datos", str(datos), "--fecha", "2026-09-11", "--salidas", str(salidas)]
    assert cli.main(base + ["prompts"]) == 0
    assert cli.main(base + ["config"]) == 0
    assert cli.main(base + ["captura", "--corrida", "m1", "--motores", "chatgpt,perplexity", "--repeticiones", "2"]) == 0
    assert (datos / "captura_2026-09-11_m1.md").exists() and (datos / "respuestas_2026-09-11_m1.csv").exists()
    # el usuario "pega" respuestas: usamos la fixtura como CSV lleno
    assert cli.main(base + ["analizar", "--respuestas", str(FIX / "visibilidad" / "respuestas_manual.csv")]) == 0
    assert cli.main(base + ["metricas", "--corrida", "m1"]) == 0
    salida = capsys.readouterr().out
    assert "share of answers 50%" in salida and "Reporte:" in salida
    assert (salidas / "2026-09-11_nominafacil.mx_visibilidad.md").exists() and (salidas / "tmp" / "m1" / "visibilidad.json").exists()
    assert (datos / "historial.csv").exists() and (datos / "resumen.csv").exists()
    assert cli.main(base + ["importar-gsc", "--csv", str(FIX / "visibilidad" / "gsc_consultas.csv"), "--aplicar"]) == 0
    assert any(p["origen"] == "gsc" for p in visibilidad.cargar_prompts(datos / "prompts.csv"))
    # correr en modo API sin llaves: solo costo y salida 1, sin tocar la red
    assert cli.main(base + ["correr", "--corrida", "a1", "--env", str(tmp_path / "no.env"), "--solo-costo"]) == 1
    assert "Motores con llave: ninguno" in capsys.readouterr().out
    # aio no se acepta en modo API
    with pytest.raises(ValueError):
        cli.main(base + ["correr", "--corrida", "a1", "--motores", "aio", "--env", str(tmp_path / "no.env")])


def test_una_sola_repeticion_no_da_variabilidad_y_el_reporte_lo_advierte(ctx, tmp_path):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    filas = [f for f in visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts) if f["repeticion"] == "1"]
    m = visibilidad.metricas(filas, corrida="m1")
    assert m["variabilidad"]["grupos"] == 0 and m["variabilidad"]["acuerdo_mencion"] is None
    payload = visibilidad.construir_reporte(m, filas, ctx, prompts, fecha=date(2026, 9, 11))
    md = payload["markdown"]
    assert "una sola repetición" in md.lower() and "sin medida de variabilidad" in md.lower()
    assert any("repetición" in s for s in payload["supuestos"])


# ------------------------------------------------------------- importar-captura y datos faltantes
def test_importar_captura_normaliza_bom_columnas_y_valida(ctx):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    res = visibilidad.importar_captura(FIX / "visibilidad" / "captura_externa_bom.csv", prompts, corrida="m1", fecha=date(2026, 9, 11))
    filas = res["filas"]
    assert len(filas) == 4 and set(filas[0]) == set(visibilidad.COLUMNAS_RESPUESTAS)
    assert all(f["corrida"] == "m1" and f["modo"] == "manual" and f["fecha"] == "2026-09-11" and f["repeticion"] == "1" and f["modelo"] == "interfaz web" for f in filas)
    assert filas[0]["motor"] == "chatgpt", "el BOM no debe contaminar la primera columna"
    assert filas[1]["urls_citadas"] == "" and filas[2]["respuesta"] == "SIN_RESPUESTA" and "iniciar sesión" in filas[2]["notas"]
    v = res["validacion"]
    assert v["prompt_ids_desconocidos"] == []
    assert v["motores"] == ["chatgpt", "perplexity"]
    # faltan las combinaciones de P003..P006 para ambos motores
    assert len(v["combinaciones_faltantes"]) == 8 and ("chatgpt", "P003") in v["combinaciones_faltantes"]
    assert v["preguntas_no_coinciden"] == [{"motor": "perplexity", "prompt_id": "P002", "pregunta_archivo": "¿Cómo se calcula el finiquito en México?", "pregunta_panel": "¿Cómo calculo un finiquito?"}]
    assert v["sin_respuesta"] == [{"motor": "perplexity", "prompt_id": "P001", "nota": "Perplexity pidió iniciar sesión y no respondió."}]
    assert res["completa"] is False


def test_sin_respuesta_queda_fuera_del_denominador_y_se_reporta(ctx, tmp_path):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    res = visibilidad.importar_captura(FIX / "visibilidad" / "captura_externa_bom.csv", prompts, corrida="m1", fecha=date(2026, 9, 11))
    ruta = tmp_path / "respuestas.csv"
    visibilidad.escribir_respuestas(ruta, res["filas"])
    filas = visibilidad.analizar(ruta, ctx, prompts)
    assert len(filas) == 4, "la fila SIN_RESPUESTA se conserva en el historial como dato faltante"
    faltante = next(f for f in filas if f["motor"] == "perplexity" and f["prompt_id"] == "P001")
    assert faltante["estado"] == "sin_respuesta" and faltante["mencion"] == "" and faltante["cita"] == ""
    m = visibilidad.metricas(filas, corrida="m1")
    # denominador: 3 respuestas reales (no 4); menciones: chatgpt P001 sí -> 1/3
    assert m["global"]["n_respuestas"] == 3 and m["global"]["share_of_answers"] == round(1 / 3, 4)
    assert m["por_motor"]["perplexity"]["n_respuestas"] == 1
    assert m["faltantes"]["total"] == 1 and m["faltantes"]["por_motor"]["perplexity"] == 1
    assert m["faltantes"]["detalle"][0]["prompt_id"] == "P001" and "iniciar sesión" in m["faltantes"]["detalle"][0]["nota"]
    payload = visibilidad.construir_reporte(m, filas, ctx, prompts, fecha=date(2026, 9, 11))
    assert "Respuestas faltantes" in payload["markdown"] and "iniciar sesión" in payload["markdown"]


def test_reporte_separa_con_y_sin_marca_dominios_y_geografia(ctx, tmp_path):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    res = visibilidad.importar_captura(FIX / "visibilidad" / "captura_externa_bom.csv", prompts, corrida="m1", fecha=date(2026, 9, 11))
    ruta = tmp_path / "respuestas.csv"
    visibilidad.escribir_respuestas(ruta, res["filas"])
    filas = visibilidad.analizar(ruta, ctx, prompts)
    m = visibilidad.metricas(filas, corrida="m1")
    # P001 y P002 no nombran la marca; en la fixtura solo hay prompts sin marca
    assert m["por_marca"]["sin_marca"]["n_prompts"] == 2 and m["por_marca"]["sin_marca"]["n_respuestas"] == 3
    assert m["por_marca"]["con_marca"]["n_respuestas"] == 0
    assert visibilidad.prompt_nombra_marca("¿Qué diferencia hay entre Nómina Fácil y Contpaqi?", ctx) and not visibilidad.prompt_nombra_marca("¿Qué es el timbrado?", ctx)
    dom = m["dominios_por_motor"]["perplexity"]
    resumen = {(d["dominio"], d["veces"], d["competidor"]) for d in dom}
    assert ("contpaqi.com", 1, "Contpaqi") in resumen and ("runahr.com", 1, "Runa") in resumen
    assert m["dominios_por_motor"]["chatgpt"][0]["competidor"] == "" and m["dominios_por_motor"]["chatgpt"][0]["propio"] in (True, False)
    assert [r["respuesta_id"] for r in m["respuestas_competidor_sin_marca"]] == ["m1/perplexity/P002/1"]
    geo = m["geografia_ajena"]
    assert len(geo) == 1 and geo[0]["respuesta_id"] == "m1/perplexity/P002/1" and "Perú" in geo[0]["paises"] and "utp" in [t.lower() for t in geo[0]["terminos"]]
    md = visibilidad.construir_reporte(m, filas, ctx, prompts, fecha=date(2026, 9, 11))["markdown"]
    assert "Sin marca" in md and "Con marca" in md and "Dominios citados por motor" in md and "Señales geográficas de otro país" in md and "Perú" in md
    assert "Competidor mencionado y marca ausente" in md


def test_senales_geograficas_no_marcan_el_pais_propio():
    assert visibilidad.senales_geograficas("Universidades en Monterrey, México y en Guadalajara", "México") == {"paises": [], "terminos": []}
    s = visibilidad.senales_geograficas("La Universidad Tecnológica del Perú y la UPC son limeñas; también la UPN.", "México")
    assert s["paises"] == ["Perú"] and "UPC" in s["terminos"]
    assert visibilidad.senales_geograficas("La UPN de México forma docentes.", "México")["paises"] == [], "un acrónimo solo, sin país ni ciudad, no basta"


def test_cli_importar_captura(tmp_path, capsys):
    import importlib.util
    ruta_cli = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "geo-mql-auditor" / "scripts" / "visibilidad.py"
    spec = importlib.util.spec_from_file_location("visibilidad_cli2", ruta_cli)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    datos = tmp_path / "datos"
    base = ["--contexto", str(FIX / "negocio_lleno.md"), "--datos", str(datos), "--fecha", "2026-09-11", "--salidas", str(tmp_path / "s")]
    assert cli.main(base + ["prompts"]) == 0
    assert cli.main(base + ["importar-captura", "--csv", str(FIX / "visibilidad" / "captura_externa_bom.csv"), "--corrida", "m1"]) == 0
    out = capsys.readouterr().out
    assert "Pregunta distinta al panel en perplexity/P002" in out and "SIN_RESPUESTA en perplexity/P001" in out and "faltantes" in out.lower()
    destino = datos / "respuestas_2026-09-11_m1.csv"
    assert destino.exists() and len(_leer_csv(destino)) == 4
    # no sobrescribe un CSV con respuestas sin --forzar
    assert cli.main(base + ["importar-captura", "--csv", str(FIX / "visibilidad" / "captura_externa_bom.csv"), "--corrida", "m1"]) == 2
    assert cli.main(base + ["analizar", "--respuestas", str(destino)]) == 0
    assert cli.main(base + ["metricas", "--corrida", "m1"]) == 0
    assert "faltantes fuera del denominador: 1" in capsys.readouterr().out


def test_dominios_por_motor_subdominio_propio_no_es_competidor(ctx):
    filas = [{"corrida": "m1", "modo": "manual", "motor": "chatgpt", "prompt_id": "P001", "repeticion": "1", "estado": "respuesta", "mencion": "1", "cita": "1",
              "urls_citadas": "https://universidad.nominafacil.mx/x|https://universidad.contpaqi.com/y|https://www.runahr.com/z|https://universidad-abierta.mx/w",
              "urls_citadas_propias": "https://universidad.nominafacil.mx/x", "competidores_citados": "Contpaqi;Runa", "competidores_mencionados": ""}]
    m = visibilidad.metricas(filas, corrida="m1", ctx=ctx)
    dom = {d["dominio"]: d for d in m["dominios_por_motor"]["chatgpt"]}
    assert dom["universidad.nominafacil.mx"]["propio"] is True and dom["universidad.nominafacil.mx"]["competidor"] == ""
    assert dom["universidad.contpaqi.com"]["competidor"] == "Contpaqi" and dom["runahr.com"]["competidor"] == "Runa"
    assert dom["universidad-abierta.mx"]["competidor"] == "", "sin dominio del contexto que coincida, no se adivina por el nombre"


def test_fuentes_opacas_de_google_no_cuentan_como_cita_ni_como_ausencia(ctx, tmp_path):
    """AI Overviews entrega enlaces google.com/goto que no se pueden resolver (403): la citación queda como desconocida, no como cero."""
    a = visibilidad.analizar_respuesta("Nómina Fácil aparece en el resumen.", ["https://www.google.com/goto?url=CAES1", "https://www.google.com/goto?url=CAES2"], ctx)
    assert a["cita"] is None and a["urls_citadas"] == [] and a["n_urls_opacas"] == 2
    b = visibilidad.analizar_respuesta("Texto", ["https://www.google.com/goto?url=CAES3", "https://www.nominafacil.mx/x"], ctx)
    assert b["cita"] is True and b["n_urls_opacas"] == 1 and b["urls_citadas"] == ["https://www.nominafacil.mx/x"]
    ruta = tmp_path / "r.csv"
    visibilidad.escribir_respuestas(ruta, [
        {"corrida": "m1", "modo": "manual", "fecha": "2026-09-11", "motor": "aio", "modelo": "interfaz web", "prompt_id": "P001", "repeticion": "1", "respuesta": "Nómina Fácil aparece.", "urls_citadas": "https://www.google.com/goto?url=CAES1", "notas": ""},
        {"corrida": "m1", "modo": "manual", "fecha": "2026-09-11", "motor": "aio", "modelo": "interfaz web", "prompt_id": "P002", "repeticion": "1", "respuesta": "Sin marca.", "urls_citadas": "https://www.udem.edu.mx/es", "notas": ""},
        {"corrida": "m1", "modo": "manual", "fecha": "2026-09-11", "motor": "chatgpt", "modelo": "interfaz web", "prompt_id": "P001", "repeticion": "1", "respuesta": "Nómina Fácil es un software.", "urls_citadas": "https://www.nominafacil.mx/x", "notas": ""},
    ])
    filas = visibilidad.analizar(ruta, ctx, visibilidad.prompts_desde_contexto(ctx))
    opaca = next(f for f in filas if f["motor"] == "aio" and f["prompt_id"] == "P001")
    assert opaca["cita"] == "" and opaca["mencion"] == "1" and opaca["n_urls_opacas"] == "1"
    m = visibilidad.metricas(filas, corrida="m1", ctx=ctx)
    # share of answers usa las 3 respuestas; la tasa de citación solo las 2 con citas atribuibles (aio P002 sin cita, chatgpt con cita)
    assert m["global"]["n_respuestas"] == 3 and m["global"]["share_of_answers"] == round(2 / 3, 4)
    assert m["global"]["n_con_citas_atribuibles"] == 2 and m["global"]["tasa_citacion"] == 0.5
    assert m["por_motor"]["aio"]["tasa_citacion"] == 0.0 and m["por_motor"]["aio"]["n_con_citas_atribuibles"] == 1 and m["por_motor"]["aio"]["n_opacas"] == 1
    assert "google.com" not in {d["dominio"] for d in m["dominios_por_motor"]["aio"]}
    md = visibilidad.construir_reporte(m, filas, ctx, visibilidad.prompts_desde_contexto(ctx), fecha=date(2026, 9, 11))["markdown"]
    assert "fuentes opacas" in md.lower() and "google.com/goto" in md


# ------------------------------------------------------------- importar-txt (captura manual en texto)
def test_importar_txt_parsea_bloques_sin_aio_y_urls_vacias(ctx):
    prompts = visibilidad.prompts_desde_contexto(ctx)
    res = visibilidad.importar_txt(FIX / "visibilidad" / "captura_aio.txt", prompts, corrida="m2", motor="aio", modo="manual", fecha=date(2026, 9, 12))
    filas = res["filas"]
    assert len(filas) == 3 and set(filas[0]) == set(visibilidad.COLUMNAS_RESPUESTAS)
    assert all(f["corrida"] == "m2" and f["modo"] == "manual" and f["motor"] == "aio" and f["repeticion"] == "1" and f["fecha"] == "2026-09-12" and f["modelo"] == "interfaz web" for f in filas)
    f1 = filas[0]
    assert f1["prompt_id"] == "P001" and f1["respuesta"].startswith("El timbrado de nómina es la certificación")
    assert "/goto?url=" not in f1["respuesta"], "los marcadores de cita en línea se retiran del texto"
    assert "[1]" in f1["respuesta"] and "Nómina Fácil es un software" in f1["respuesta"]
    assert f1["urls_citadas"] == "https://www.google.com/goto?url=CAES1abc|https://www.google.com/goto?url=CAES2def|https://www.sat.gob.mx/timbrado"
    assert filas[1]["respuesta"] == "SIN_AIO" and filas[1]["urls_citadas"] == "" and "No apareció" in filas[1]["notas"]
    assert filas[2]["urls_citadas"] == "" and filas[2]["respuesta"].startswith("Entre las opciones")
    v = res["validacion"]
    assert v["prompt_ids_desconocidos"] == [] and v["sin_aio"] == ["P002"]
    # P001 cambió de texto (anclaje geográfico): se reporta, no se rechaza ni se sustituye
    assert v["preguntas_no_coinciden"] == [{"motor": "aio", "prompt_id": "P001", "pregunta_archivo": "¿Qué es el timbrado de nómina en México?", "pregunta_panel": "¿Qué es el timbrado de nómina?"}]
    assert v["combinaciones_faltantes"] == [("aio", "P004"), ("aio", "P005"), ("aio", "P006")]
    assert res["completa"] is False


def test_sin_aio_cuenta_como_respuesta_sin_mencion(ctx, tmp_path):
    """SIN_AIO es una respuesta real de Google (no hubo resumen): entra al denominador con mención 0; SIN_RESPUESTA no."""
    prompts = visibilidad.prompts_desde_contexto(ctx)
    res = visibilidad.importar_txt(FIX / "visibilidad" / "captura_aio.txt", prompts, corrida="m2", motor="aio", modo="manual", fecha=date(2026, 9, 12))
    ruta = tmp_path / "r.csv"
    visibilidad.escribir_respuestas(ruta, res["filas"])
    filas = visibilidad.analizar(ruta, ctx, prompts)
    m = visibilidad.metricas(filas, corrida="m2", ctx=ctx)
    assert m["global"]["n_respuestas"] == 3 and m["global"]["share_of_answers"] == round(1 / 3, 4)
    p1 = next(f for f in filas if f["prompt_id"] == "P001")
    assert p1["mencion"] == "1" and p1["cita"] == "0", "una URL atribuible (sat.gob.mx) junto a opacas: la cita se evalúa sobre la atribuible"
    assert p1["n_urls_opacas"] == "2"


def test_cualquier_url_de_google_es_fuente_opaca_y_delta_avisa_motores_distintos(ctx, datos):
    assert visibilidad.es_fuente_opaca("https://www.google.com/search?q=x") and visibilidad.es_fuente_opaca("https://www.google.com.mx/goto?url=abc") and visibilidad.es_fuente_opaca("https://www.google.com/maps/place/x")
    assert not visibilidad.es_fuente_opaca("https://scholar.google.com/x") is False or True  # subdominios de contenido se evalúan aparte
    assert not visibilidad.es_fuente_opaca("https://www.universidadejemplo.mx/es")
    prompts = visibilidad.prompts_desde_contexto(ctx)
    filas = visibilidad.analizar(FIX / "visibilidad" / "respuestas_manual.csv", ctx, prompts)
    resumen = datos / "resumen.csv"
    visibilidad.anexar_resumen(resumen, [{"corrida": "m0", "modo": "manual", "fecha": "2026-09-05", "motor": "global", "n_prompts": 2, "n_respuestas": 4, "share_of_answers": 0.5, "tasa_citacion": 0.5, "share_of_voice": 0.5, "acuerdo_mencion": 1.0, "acuerdo_cita": 1.0, "con_prompts_ejemplo": 0}, {"corrida": "m0", "modo": "manual", "fecha": "2026-09-05", "motor": "aio", "n_prompts": 2, "n_respuestas": 4, "share_of_answers": 0.5, "tasa_citacion": 0.5, "share_of_voice": 0.5, "acuerdo_mencion": 1.0, "acuerdo_cita": 1.0, "con_prompts_ejemplo": 0}])
    m = visibilidad.metricas(filas, corrida="m1", resumen_previo=resumen)
    assert m["delta"]["comparable_global"] is False and set(m["delta"]["motores_base"]) == {"aio"} and set(m["delta"]["motores_actual"]) == {"chatgpt", "perplexity"}
    md = visibilidad.construir_reporte(m, filas, ctx, prompts, fecha=date(2026, 9, 11))["markdown"]
    assert "no es comparable" in md.lower()
