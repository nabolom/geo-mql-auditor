"""Render con JavaScript mediante Playwright, opcional. Sin Playwright no bloquea nada."""
from __future__ import annotations

from typing import Any

from .html import Documento, contar_palabras


def disponible() -> bool:
    try:
        import playwright.sync_api  # noqa: F401

        return True
    except ImportError:
        return False


UA_RENDER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 geo-mql-auditor"


def renderizar(url: str, *, timeout_ms: int = 30000, espera_ms: int = 6000, locale: str = "es-MX") -> dict[str, Any]:
    """Devuelve {disponible, html, palabras_principal, palabras_visibles, error}. Nunca lanza.

    Carga hasta domcontentloaded y espera `espera_ms` para que el JavaScript pinte el contenido
    (networkidle no llega en sitios con analítica o chat que nunca dejan de pedir). Registra también
    las palabras visibles según el navegador (innerText del body) por si el parser propio difiere."""
    if not disponible():
        return {"disponible": False, "html": "", "palabras_principal": 0, "palabras_visibles": 0, "error": "playwright no instalado (pip install playwright && playwright install chromium)"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            navegador = p.chromium.launch(headless=True)
            pagina = navegador.new_page(user_agent=UA_RENDER, locale=locale)
            pagina.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            pagina.wait_for_timeout(espera_ms)
            html = pagina.content()
            try:
                visibles = len(pagina.inner_text("body").split())
            except Exception:  # noqa: BLE001
                visibles = 0
            navegador.close()
        doc = Documento(html, url)
        return {"disponible": True, "html": html, "palabras_principal": contar_palabras(doc.texto_principal()), "palabras_visibles": visibles, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"disponible": False, "html": "", "palabras_principal": 0, "palabras_visibles": 0, "error": f"render falló: {e}"}
