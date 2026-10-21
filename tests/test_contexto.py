"""Campos opcionales del contexto: área dueña del sitio y zona horaria (IANA)."""
from __future__ import annotations

from geomql import contexto

BASE = """## Negocio
- nombre: Marca Ejemplo
- dominio: marca.example
- descripcion_oficial: Software ficticio para pruebas.
## Oferta
- productos_servicios: A; B
## Mercado
- geografia: México, Ciudad Ejemplo
- idiomas: es
## ICP y personas
- icp: Empresas medianas
## Competidores
- competidor: CompetidorA | https://competidora.example
"""


def test_area_duena_y_zona_horaria_se_leen_y_no_son_criticos(tmp_path):
    vacios = tmp_path / "vacios.md"
    vacios.write_text(BASE + "## Entregables\n- area_duena_sitio: (opcional; área dueña del sitio, por ejemplo Marketing)\n- zona_horaria: (opcional; zona horaria IANA, por ejemplo America/Mexico_City)\n", encoding="utf-8")
    ctx = contexto.cargar(vacios)
    assert ctx["valido"], ctx["faltantes_criticos"]
    assert ctx["opcionales"] == {"area_duena_sitio": "", "zona_horaria": ""}
    llenos = tmp_path / "llenos.md"
    llenos.write_text(BASE + "## Entregables\n- area_duena_sitio: Marketing\n- zona_horaria: America/Mexico_City\n", encoding="utf-8")
    ctx = contexto.cargar(llenos)
    assert ctx["valido"] and ctx["opcionales"] == {"area_duena_sitio": "Marketing", "zona_horaria": "America/Mexico_City"}
    for modulo in (None, "visibilidad", "mql"):
        assert not set(contexto.OPCIONALES) & set(contexto.criticos_para(modulo)), modulo
    assert contexto.cargar(tmp_path / "no-existe.md")["opcionales"] == {"area_duena_sitio": "", "zona_horaria": ""}
