# geo-mql-auditor

Skill de Claude Code para auditar y medir visibilidad en motores de respuesta con IA. Todo en español.

## Reglas del proyecto

- El skill vive en `.claude/skills/geo-mql-auditor/`; su flujo está en `SKILL.md` y no se salta.
- Nunca aplica cambios en producción: solo escribe en `salidas/`.
- Cada hallazgo lleva dos etiquetas: evidencia de la observación (Confirmado, Probable, Hipótesis) y fuerza de la regla con tipo de evidencia (A, B, C). Ver `referencias/etiquetas-confianza.md`.
- Nunca se presenta impacto proyectado numérico. Si un subagente lo produce, se corrige la salida, no el validador.
- Toda regla nueva en `reglas/rulebook.yaml` lleva fuente leída, `fuerza`, `tipo_evidencia` y `verificado_el`. Una fuente vista solo por snippet vale como máximo C.
- No se elige una URL ni un sitio por cuenta propia: se usa la que da el usuario o las fixturas de `tests/fixturas/`.
- Las fixturas de prueba son inventadas. No se agregan fixturas descargadas de sitios reales.
- `contexto/negocio.md` es una plantilla; los datos de un cliente no se versionan.

## Comandos

```bash
.venv/bin/python -m pytest -q
.venv/bin/python .claude/skills/geo-mql-auditor/scripts/contexto.py validar
.venv/bin/python .claude/skills/geo-mql-auditor/scripts/audit.py correr --url https://dominio.com/
.venv/bin/python .claude/skills/geo-mql-auditor/scripts/visibilidad.py --help
```

## Estilo

- Python 3.11 o superior, solo biblioteca estándar en los colectores. `pyyaml` y Playwright son opcionales.
- Nombres de funciones, variables y archivos en español, sin acentos en identificadores.
- Las pruebas usan `file://` o descargas simuladas; ninguna prueba sale a la red.
