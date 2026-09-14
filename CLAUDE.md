# CLAUDE.md
Este proyecto sigue las reglas de @AGENTS.md — léelo completo antes de
cualquier acción. Lo de abajo es específico de Claude Code, no reemplaza
nada de AGENTS.md.

## Herramientas activas en este entorno
- MCP: Azure MCP, Terraform MCP, Context7 — se usan automáticamente
  cuando la tarea lo requiere, no hace falta invocarlos por nombre.
- Plugins: `superpowers`, `frontend-design`, `security-guidance`,
  `playwright` — `security-guidance` corre en segundo plano (hooks), los
  demás se invocan según la tarea.

## Skill propia del proyecto
- `~/.claude/skills/azure-voice-live/SKILL.md` — patrón de integración
  con Voice Live API destilado del módulo de Microsoft Learn
  "Develop a voice live agent". Consultar antes de tocar `integrations/voice/`.

## Notas de sesión
- Verificar que Docker esté corriendo antes de tareas que usen Terraform MCP.
- Si `security-guidance` bloquea una escritura, revisar el motivo antes de
  forzar — no ignorar el aviso sin leerlo.