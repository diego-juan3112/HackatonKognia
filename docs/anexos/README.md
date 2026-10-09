# Anexos: evidencia histórica de los spikes

Estos documentos salieron de la rama `spike/demo-voz-avatar` (septiembre y octubre de 2026) y
se conservan como **evidencia**, no como contrato. Sus referencias a `AGENTS.md §1.1`, `§1.2` o
`§8` pertenecen a la versión anterior de las reglas; hoy mandan los códigos `R-xx` y `D-xx`.

| Documento | Qué aporta | Estado frente a Reto 01 |
|---|---|---|
| [us1-modelos-voz.md](us1-modelos-voz.md) | Comparación de proveedores de voz con precios y mediciones de Azure Speech (TTFA, visemas en `es-CO`) | Plan B de voz (D-11 eligió voz en tiempo real); Azure F0 permite 1 STT concurrente |
| [us2-avatar-3d.md](us2-avatar-3d.md) | Candidatos de avatar 3D, `wawa-lipsync` y Three.js plano | Aplazado (D-17); Ready Player Me ya no existe |
| [restriccion-azure-openai-students.md](restriccion-azure-openai-students.md) | Azure for Students no despliega modelos de Azure OpenAI y restringe regiones | Histórico: la base ya no usa Azure OpenAI (D-03/D-10) |

El código de esos spikes (`spikes/`) sigue solo en la rama `spike/demo-voz-avatar`.
