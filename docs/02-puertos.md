# Puertos intercambiables

Un puerto es un contrato entre el núcleo y el mundo exterior: un `Protocol` en
`src/models/ports.py` (Python) o una interfaz TypeScript en `web/src/voice/` (el
cliente). Existen para poder cambiar de proveedor editando solo el adaptador.

> **Limpieza (D-23).** Los puertos de la base genérica (`LLMPort`, `RetrievalPort`,
> `UserRepositoryPort`, `ConversationRepositoryPort`, `VoicePort`, `AvatarPort`) se
> retiraron junto con ella; quedan en el historial de git (último commit con ellos:
> `0a5a625`). Los de abajo son los únicos vigentes.

## Puertos vigentes

| Puerto | Responsabilidad | Adaptadores | Estado |
|---|---|---|---|
| `VoiceEngine` *(cliente, TypeScript)* | Audio en tiempo real navegador ↔ proveedor, eventos neutrales, herramientas, interrupción y estilo ([08](08-contrato-voz-en-vivo.md) §2) | `web/src/voice/openai-engine.ts`, `gemini-engine.ts` (D-11) | Implementado |
| `SpeechSynthesizer` *(cliente, TypeScript)* | Texto de la respuesta → audio PCM16 a 24 kHz en streaming, con marcas por palabra y cancelación; solo se usa con la voz clonada y se compone sobre un `VoiceEngine` en modo solo texto ([08](08-contrato-voz-en-vivo.md) §15.2) | `web/src/voice/cartesia-synth.ts` (D-20) | Implementado |
| `RealtimeSessionPort` | Emitir credenciales efímeras y la configuración de sesión de cada motor (instrucciones, herramientas, voz, `voice_mode` efectivo) | `integrations/realtime/{openai,gemini}_session` | Implementado |
| `SpeechSessionPort` | Emitir el token de acceso de síntesis de la voz clonada (`POST /speech/session`, 600 s, alcance `tts`) | `integrations/realtime/cartesia_session` (D-20) | Implementado |
| `DatasetPort` | Ejecutar consultas de **solo lectura** ya armadas por el servidor, con plazo, reintento acotado y caché etiquetada ([09](09-datos-en-vivo-datos-gov-co.md)) | `integrations/datasets/socrata_client` (SODA3) | Implementado |
| `AffectModelPort` | Una estimación de afecto con esquema de salida, por texto o por audio + texto | `integrations/llm/affect_models` (Gemini `fast`, OpenAI `deep`, REST con `httpx`) | Implementado |
| `AnalystPort` | Estimar afecto (texto ∥ voz), fusionar y decidir el estilo ([10](10-modelos-afecto-y-recuperacion.md) §6) | Servicio: grafo LangGraph en `services/analyst/` sobre `AffectModelPort` | Implementado |
| `FeedbackPort` | Registrar un evento de feedback (`POST /feedback`) sin base de datos | `integrations/feedback/log_feedback` (registro estructurado; LangSmith pendiente) | Implementado |

Firmas (el contrato exacto vive en `src/models/ports.py`, con los tipos de
`src/models/ips.py`, `src/models/voice.py` y `src/models/analysis.py`, y se
versiona con `contract`):

```python
class DatasetPort(Protocol):   # la SoQL la arma services/ips con columnas y funciones permitidas (R-23)
    async def query(self, soql: str, *, deadline: Deadline, bypass_cache: bool = False) -> QueryResult: ...

class RealtimeSessionPort(Protocol):
    async def create(self, req: RealtimeSessionRequest, setup: EngineSetup) -> RealtimeSession: ...

class SpeechSessionPort(Protocol):
    async def create(self, req: SpeechSessionRequest) -> SpeechSession: ...

class AffectModelPort(Protocol):
    async def estimate(self, text: str, audio_wav: bytes | None, *, timeout_s: float,
                       prosody: str | None = None) -> AffectLabels: ...

class AnalystPort(Protocol):
    async def analyze(self, req: UtteranceAnalysisRequest, audio_wav: bytes | None) -> AnalysisResult: ...  # AffectEstimate + StyleDecision

class FeedbackPort(Protocol):
    async def record(self, event: FeedbackEvent) -> None: ...
```

`services/` arma el **sobre de evidencia** a partir de `QueryResult`: el adaptador solo
ejecuta y mide, nunca decide grano, unidad ni `warnings`.

## Reglas

- **R-03.** Cambiar el proveedor de cualquier puerto exige editar **solo
  `integrations/`** (y, en el cliente, solo el adaptador del motor). Si un cambio
  de proveedor obliga a tocar `services/` o `api/`, el puerto está mal definido:
  se corrige el puerto, no se propaga el cambio.
- **R-03 (consecuencias).** Ningún tipo del SDK de un proveedor cruza la
  frontera de `integrations/`. Lo que sale son tipos de `models/` (`QueryResult`,
  `RealtimeSession`, `AffectLabels`…), no objetos de OpenAI ni de Google. Nombres de
  eventos, formatos de audio, `base64`, URL del proveedor y claves de API viven
  dentro del adaptador.
- **R-09.** Cada puerto tiene un doble en memoria, para probar `services/` y la
  interfaz sin red, sin micrófono y sin credenciales. En Python los dobles viven
  **solo** en `tests/doubles/`: `fake_dataset.py` (`FakeDataset`) y `fake_voice.py`
  (`FakeRealtimeSession`, `FakeSpeechSession`, `FakeAffectModel`, `FakeAnalyst`,
  `FakeFeedback`). En el cliente, `web/mocks/` guarda respuestas JSON de ejemplo y el
  motor simulado `FakeEngine` vive en `web/src/voice/fake-engine.ts` porque el front lo
  ofrece como modo de demostración (`?engine=fake` o `PUBLIC_VOICE_ENGINE=fake`); es
  una excepción conocida a «solo en `tests/doubles/`». El producto corre por omisión
  con los proveedores reales.
- **R-08. Retirada (D-11).** Ya no se espera una decisión de voz: el proveedor se
  decidió. Los adaptadores de voz viven en `integrations/realtime/` y
  `web/src/voice/`.

## Evidencia de que los puertos funcionan

Reto 01 pone a prueba el principio con dos motores de voz intercambiables en vivo
(OpenAI Realtime y Gemini Live detrás de `VoiceEngine` y `RealtimeSessionPort`) y con
dos modelos del analista (`fast` y `deep`) detrás de `AffectModelPort`. Antes, en la
base genérica ya retirada (D-23), se habían cambiado Chroma → pgvector y NVIDIA →
Gemini sin mover responsabilidades del grafo.

## Cómo agregar un adaptador

1. Implementar el `Protocol` en `src/integrations/<puerto>/` (o la interfaz
   `VoiceEngine` en `web/src/voice/`).
2. Traducir dentro del adaptador todo tipo del SDK a tipos de `src/models/` o a
   los eventos neutrales de [08](08-contrato-voz-en-vivo.md).
3. Conectarlo en la raíz de composición (`src/api/voice_container.py`).
4. Agregar su doble en `tests/doubles/` (R-09).
5. Pasar los chequeos de capacidad y esquema **antes** de recibir tráfico (R-27).
6. Registrar la decisión como `D-xx` en [00-contexto-y-decisiones.md](00-contexto-y-decisiones.md)
   y la versión en `CHANGELOG.md`.
