# integrations/voice — vacío a propósito

No hay adaptador aquí y **no debe haberlo todavía**. AGENTS.md §8 prohíbe
implementar un proveedor concreto de voz mientras §1.1 siga abierto.

El contrato ya existe: `VoicePort` en `src/models/ports.py`.

## Cuando se decida el proveedor

1. Crear `<proveedor>_voice.py` con una clase que satisfaga `VoicePort`.
2. Traducir los tipos del SDK a `AudioChunk` / `Utterance` / `SpeechChunk`
   (`src/models/conversation.py`) **dentro** del adaptador. Ningún tipo del
   proveedor sale de esta carpeta.
3. Registrarlo en el composition root (`src/api/dependencies.py`).
4. No tocar `services/` ni `api/routers/`. Si hiciera falta, el puerto está
   mal definido y se corrige el puerto.

Candidatos en evaluación y criterios: AGENTS.md §1.1.

## Material de referencia

`.claude/skills/azure-voice-live/` documenta el patrón puerto/adaptador para
voz en tiempo real. Azure Voice Live quedó **descartado por costo**, así que
sus detalles de protocolo ya no aplican; lo que sigue siendo válido es la
estructura (traducción de eventos en la frontera, barge-in manejado en dos
niveles, audio que nunca llega al dominio).
