"""Configuración compartida de pytest: rutas del skill y fixturas HTML."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / ".claude" / "skills" / "geo-mql-auditor" / "scripts"
FIXTURAS = Path(__file__).resolve().parent / "fixturas"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture(scope="session")
def fixturas() -> Path:
    return FIXTURAS


@pytest.fixture(scope="session")
def html_de():
    def _leer(nombre: str) -> str:
        return (FIXTURAS / nombre).read_text(encoding="utf-8")

    return _leer


@pytest.fixture(scope="session")
def url_de():
    def _url(nombre: str) -> str:
        return (FIXTURAS / nombre).resolve().as_uri()

    return _url


@pytest.fixture
def sin_red(monkeypatch):
    """Bloquea cualquier descarga real; las pruebas deben usar file:// o mocks."""
    from geomql import fetch

    def _bloqueada(url, *a, **k):
        if url.startswith("file://"):
            return fetch._descargar_local(url)
        return fetch._resultado_vacio(url, error="red bloqueada en pruebas")

    monkeypatch.setattr(fetch, "descargar", _bloqueada)
    return _bloqueada
