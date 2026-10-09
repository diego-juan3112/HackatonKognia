# Puertos intercambiables

Un puerto es un contrato (`Protocol` en `src/models/ports.py`) entre el núcleo
y el mundo exterior. Existen porque varios proveedores **todavía no están
decididos**: el contrato permite avanzar hoy y enchufar el proveedor después.

| Puerto | Responsabilidad | Proveedor | Estado |
|---|---|---|---|
| `LLMPort` | Chat model | Gemini (D-03) | Implementado |
| `RetrievalPort` | Ingesta y recuperación de conocimiento (RAG) | PostgreSQL + pgvector, E5 (D-02, D-05) | Implementado |
| `UserRepositoryPort` | Usuarios y sesiones | PostgreSQL | Implementado |
| `ConversationRepositoryPort` | Conversaciones e historial legible | PostgreSQL | Implementado |
| `VoicePort` | STT y TTS: audio del usuario → texto, texto → audio | **Por decidir** ([00](00-contexto-y-decisiones.md) §3) | Declarado, sin implementar |
| `AvatarPort` | Renderizado 3D + lip-sync sincronizado con el audio | **Por decidir** ([00](00-contexto-y-decisiones.md) §4) | Declarado, sin implementar |

## Reglas

- **R-03.** Cambiar el proveedor de cualquier puerto exige editar **solo
  `integrations/`**. Si un cambio de proveedor obliga a tocar `services/` o
  `api/`, el puerto está mal definido: se corrige el puerto, no se propaga el
  cambio.
- **R-03 (consecuencias).** Ningún tipo del SDK de un proveedor cruza la
  frontera de `integrations/`. Lo que sale son tipos de `models/` (`AudioChunk`,
  `Utterance`, `VisemeFrame`…), no objetos de Cartesia ni de Deepgram. Nombres
  de eventos, formatos de audio, `base64` y claves de API viven dentro del
  adaptador.
- **R-09.** Cada puerto tiene un doble en memoria en `tests/doubles/`, para
  probar `services/` sin red, sin micrófono y sin credenciales. Los dobles
  (`FakeChatModel`, `HashingEmbedder`, repositorios y retriever en memoria)
  viven **solo** ahí: el producto siempre corre con Gemini y E5 reales.
- **R-08.** No se implementa un adaptador concreto de voz ni de avatar mientras
  su proveedor siga abierto. Se escriben el puerto y su doble; el adaptador
  espera a la decisión. `integrations/voice/` e `integrations/avatar/` están
  vacíos a propósito.

## Evidencia de que los puertos funcionan

Ya se cambiaron dos proveedores: Chroma → pgvector y NVIDIA → Gemini. En
ninguno de los dos casos un nodo del grafo cambió de responsabilidad. Los
ajustes que sí hubo en los nodos (leer `.text`, tolerar JSON envuelto en
bloques de código) fueron de robustez, no de proveedor.

## Cómo agregar un adaptador (el día que se decida)

1. Implementar el `Protocol` en `src/integrations/<puerto>/`.
2. Traducir dentro del adaptador todo tipo del SDK a tipos de `src/models/`.
3. Conectarlo en el composition root (`src/api/dependencies.py`).
4. Registrar la decisión como `D-xx` en [00-contexto-y-decisiones.md](00-contexto-y-decisiones.md)
   y la versión en `CHANGELOG.md`.
