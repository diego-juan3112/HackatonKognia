# CLAUDE.md
Este proyecto sigue las reglas de @AGENTS.md — léelo completo antes de
cualquier acción, y el documento de `docs/` que indique para la tarea.
Lo de abajo es específico de Claude Code, no reemplaza nada de AGENTS.md.

## Herramientas activas en este entorno
- MCP: Azure MCP, Context7 — se usan automáticamente cuando la tarea lo
  requiere, no hace falta invocarlos por nombre.
- Plugins: `superpowers`, `frontend-design`, `security-guidance`,
  `playwright` — `security-guidance` corre en segundo plano (hooks), los
  demás se invocan según la tarea.

## Reto 01 (2026-10-09)
- Entrega 2026-10-09 16:00. Lee [docs/07](docs/07-reto-01-especificacion.md) y, si trabajas
  de a dos, [docs/12](docs/12-guia-de-trabajo-2-personas.md): cada sesión de Claude tiene su
  worktree y su carril (A front y voz, B API, datos y análisis); no edites el carril del otro.
- Las sesiones **no comparten memoria**: las sincronizan los contratos versionados
  (`docs/08`, `docs/09`, `src/models/`, `web/src/voice/types.ts`).
- La base genérica (chat con identificación, base de datos, recuperación, grafo de chat)
  y la skill de Azure Voice Live se retiraron del repo (D-23, D-01); quedan en el
  historial de git. Mandan `docs/00–13`.

## Notas de sesión
- Si `security-guidance` bloquea una escritura, revisar el motivo antes de
  forzar — no ignorar el aviso sin leerlo.
