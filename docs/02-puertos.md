# Puertos intercambiables

Un puerto es un contrato entre el núcleo y el mundo exterior: un `Protocol` en
`src/models/ports.py` (Python) o una interfaz TypeScript en `web/src/voice/` (el
cliente). Existen para poder cambiar de proveedor editando solo el adaptador.

## Puertos de la base genérica

| Puerto | Responsabilidad | Proveedor | Estado |
|---|---|---|---|
| `LLMPort` | Chat model | Perfiles Gemini / OpenAI (D-10) | Implementado (un solo proveedor) → registro de perfiles |
| `RetrievalPort` | Ingesta y recuperación de conocimiento (RAG) | PostgreSQL + pgvector, E5 (D-02, D-05) | Implementado — **no lo usa Reto 01** |
| `UserRepositoryPort` | Usuarios y sesiones | PostgreSQL | Implementado — **no lo usa Reto 01** |
| `ConversationRepositoryPort` | Conversaciones e historial legible | PostgreSQL | Implementado — **no lo usa Reto 01** |
| `VoicePort` | STT y TTS en cascada: audio del usuario → texto, texto → audio | Por decidir | Declarado, sin implementar — **fase 2** (motor 3) |
| `AvatarPort` | Renderizado 3D + lip-sync sincronizado con el audio | Aplazado (D-17) | Declarado, sin implementar |

## Puertos de Reto 01

| Puerto | Responsabilidad | Adaptadores | Estado |
|---|---|---|---|
| `VoiceEngine` *(cliente, TypeScript)* | Audio en tiempo real navegador ↔ proveedor, eventos neutrales, herramientas, interrupción y estilo ([08](08-contrato-voz-en-vivo.md) §2) | OpenAI Realtime, Gemini Live (D-11) | Planeado |
| `SpeechSynthesizer` *(cliente, TypeScript)* | Texto de la respuesta → audio PCM16 a 24 kHz en streaming, con marcas por palabra y cancelación; solo se usa con la voz clonada y se compone sobre un `VoiceEngine` en modo solo texto ([08](08-contrato-voz-en-vivo.md) §15.2) | Cartesia (D-20); doble `FakeSynthesizer` en `web/mocks/` | Planeado |
| `RealtimeSessionPort` | Emitir credenciales efímeras y la configuración de sesión de cada motor (instrucciones, herramientas, voz, `voice_mode` efectivo) | `integrations/realtime/{openai,gemini}` | En curso (carril B) |
| `SpeechSessionPort` | Emitir el token de acceso de síntesis de la voz clonada (`POST /speech/session`, 600 s, alcance `tts`) | `integrations/realtime/cartesia` (D-20) | En curso (carril B) |
| `DatasetPort` | Ejecutar consultas de **solo lectura** ya armadas por el servidor, con plazo, reintento acotado y caché etiquetada ([09](09-datos-en-vivo-datos-gov-co.md)) | `integrations/datasets/socrata_client` (SODA3) | En curso (carril B) |
| `AffectModelPort` | Una estimación de afecto con esquema de salida, por texto o por audio + texto | `integrations/llm/affect_models` (Gemini `fast`, OpenAI `deep`, REST con `httpx`) | En curso (carril B) |
| `AnalystPort` | Estimar afecto (texto ∥ voz), fusionar y decidir el estilo ([10](10-modelos-afecto-y-recuperacion.md) §6) | Servicio: grafo LangGraph en `services/analyst/` sobre `AffectModelPort` | En curso (carril B) |
| `FeedbackPort` | Registrar un evento de feedback (`POST /feedback`) sin base de datos | `integrations/feedback` (registro estructurado; LangSmith pendiente) | En curso (carril B) |

Firmas (el contrato exacto vive en `src/models/ips.py`, `src/models/voice.py` y
`src/models/analysis.py`, y se versiona con `contract`):

```python
class DatasetPort(Protocol):   # la SoQL la arma services/ips con columnas y funciones permitidas (R-23)
    async def query(self, soql: str, *, deadline: Deadline, bypass_cache: bool = False) -> QueryResult: ...

class RealtimeSessionPort(Protocol):
    async def create(self, req: RealtimeSessionRequest, setup: EngineSetup) -> RealtimeSession: ...

class SpeechSessionPort(Protocol):
    async def create(self, req: SpeechSessionRequest) -> SpeechSession: ...

class AffectModelPort(Protocol):
    async def estimate(self, text: str, audio_wav: bytes | None, *, timeout_s: float) -> AffectLabels: ...

class AnalystPort(Protocol):
    async def analyze(self, req: UtteranceAnalysisRequest, audio_wav: bytes | None) -> AnalysisResult: ...  # AffectEstimate + StyleDecision
```

`services/` arma el **sobre de evidencia** a partir de `QueryResult`: el adaptador solo
ejecuta y mide, nunca decide grano, unidad ni `warnings`.

## Reglas

- **R-03.** Cambiar el proveedor de cualquier puerto exige editar **solo
  `integrations/`** (y, en el cliente, solo el adaptador del motor). Si un cambio
  de proveedor obliga a tocar `services/` o `api/`, el puerto está mal definido:
  se corrige el puerto, no se propaga el cambio.
- **R-03 (consecuencias).** Ningún tipo del SDK de un proveedor cruza la
  frontera de `integrations/`. Lo que sale son tipos de `models/` (`AudioChunk`,
  `Utterance`, `ToolEnvelope`…), no objetos de OpenAI ni de Google. Nombres de
  eventos, formatos de audio, `base64`, URL del proveedor y claves de API viven
  dentro del adaptador.
- **R-09.** Cada puerto tiene un doble en memoria, para probar `services/` y la
  interfaz sin red, sin micrófono y sin credenciales. Los dobles viven **solo** en
  `tests/doubles/` (Python: `FakeChatModel`, `FakeDataset`, `FakeAffectModel`,
  `FakeRealtimeSession`, `FakeSpeechSession`, `FakeFeedback`…) y en `web/mocks/`
  (`FakeEngine`, `FakeSynthesizer`). El producto siempre corre con los proveedores reales.
- **R-08. Retirada (D-11).** Ya no se espera una decisión de voz: el proveedor se
  decidió. Los adaptadores de voz viven en `integrations/realtime/` y
  `web/src/voice/`; `integrations/voice/` e `integrations/avatar/` siguen vacíos
  (fase 2).

## Evidencia de que los puertos funcionan

Ya se cambiaron dos proveedores: Chroma → pgvector y NVIDIA → Gemini. En
ninguno de los dos casos un nodo del grafo cambió de responsabilidad. Los
ajustes que sí hubo en los nodos (leer `.text`, tolerar JSON envuelto en
bloques de código) fueron de robustez, no de proveedor. Reto 01 pone a prueba
el mismo principio con dos motores de voz intercambiables en vivo.

## Cómo agregar un adaptador

1. Implementar el `Protocol` en `src/integrations/<puerto>/` (o la interfaz
   `VoiceEngine` en `web/src/voice/`).
2. Traducir dentro del adaptador todo tipo del SDK a tipos de `src/models/` o a
   los eventos neutrales de [08](08-contrato-voz-en-vivo.md).
3. Conectarlo en el composition root (`src/api/dependencies.py`, o
   `src/api/app_voice.py` para Reto 01).
4. Pasar los chequeos de capacidad y esquema **antes** de recibir tráfico (R-27).
5. Registrar la decisión como `D-xx` en [00-contexto-y-decisiones.md](00-contexto-y-decisiones.md)
   y la versión en `CHANGELOG.md`.
