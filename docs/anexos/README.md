# Anexos: evidencia histórica de los spikes

Estos documentos salieron de la rama `spike/demo-voz-avatar` (septiembre y octubre de 2026) y
se conservan como **evidencia**, no como contrato. Sus referencias a `AGENTS.md §1.1`, `§1.2` o
`§8` pertenecen a la versión anterior de las reglas; hoy mandan los códigos `R-xx` y `D-xx`.

| Documento | Qué aporta | Estado frente a Reto 01 |
|---|---|---|
| [us1-modelos-voz.md](us1-modelos-voz.md) | Comparación de proveedores de voz con precios y mediciones de Azure Speech (TTFA, visemas en `es-CO`) | Plan B de voz (D-11 eligió voz en tiempo real); Azure F0 permite 1 STT concurrente |
| [us2-avatar-3d.md](us2-avatar-3d.md) | Candidatos de avatar 3D, `wawa-lipsync` y Three.js plano | Aplazado (D-17); Ready Player Me ya no existe |
| [bench-latencia-2026-10-09.md](bench-latencia-2026-10-09.md) | Banco de latencia con consulta, por turno y con fallos literales | Vigente ([00](../00-contexto-y-decisiones.md) §6) |
| [concurrencia-2026-10-09.md](concurrencia-2026-10-09.md) | Varios evaluadores a la vez: aislamiento de sesiones, conversaciones y respuestas | Vigente |
| [eval-grounding-2026-10-09.md](eval-grounding-2026-10-09.md) | Evaluación de alucinaciones (cifras sin evidencia) | Vigente |
| [g2-voz-y-contexto-para-carril-b.md](g2-voz-y-contexto-para-carril-b.md) | Spike G2: motores de voz en tiempo real verificados con sesión real | Cerró D-11 |

El anexo sobre las restricciones de Azure for Students con Azure OpenAI se retiró con D-23 (la app
ya no usa Azure OpenAI, D-10); queda en el historial de git.

El código de esos spikes (`spikes/`) sigue solo en la rama `spike/demo-voz-avatar`. Sus menciones a
`VoicePort`, `AvatarPort` o `src/integrations/voice/` son de la base genérica, retirada con D-23;
los puertos vigentes están en [02](../02-puertos.md).
