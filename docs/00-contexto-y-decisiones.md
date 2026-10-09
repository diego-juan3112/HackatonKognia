# Contexto, stack y decisiones

Qué estamos construyendo, con qué, y qué ya quedó decidido. Las decisiones
llevan código `D-xx` para poder citarlas desde código, commits y PR. Una
decisión no se revierte en silencio: se agrega una nueva que la reemplace y se
marca la anterior como **Reemplazada por D-yy**.

## 1. Contexto del reto

**No conocemos el reto exacto hasta el día del evento.** Los escenarios
probables son un agente de PQR (peticiones, quejas, reclamos) o un agente de
atención financiera, por canal de voz o de video.

Objetivo de la fase actual:

> Construir una **base genérica adaptable**, no el agente final. El día del
> reto solo debemos tener que conectar la lógica específica del negocio y el
> proveedor de voz/avatar ya decidido.

Corolario: **no se invierte tiempo en lógica de negocio de un dominio que quizá
no sea el correcto** (regla R-06).

### Dominio de juguete

El repo trae un dominio trivial (un FAQ: `config/domains/faq_demo.yaml` y
`docs/faq_demo/`) cuyo único propósito es **validar que el pipeline corre de
punta a punta**. No es el producto (regla R-07):

- Vive separado y marcado como desechable.
- Nunca se le agregan features "por si acaso".
- El día del reto se reemplaza, no se extiende.

## 2. Stack

| Capa | Tecnología | Estado |
|---|---|---|
| Orquestación de agente | LangGraph (grafo con estado, checkpointer) | Fijo |
| API | FastAPI | Fijo |
| LLM | Gemini `gemini-3.5-flash-lite` (Google AI Studio) | D-03 |
| Voz (STT/TTS) | **Pendiente** — ver §3 | Abierto |
| Avatar 3D | **Pendiente** — ver §4 | Abierto |
| RAG | PostgreSQL + pgvector — ver [04-rag.md](04-rag.md) | D-02 |
| Base relacional | PostgreSQL 17 (contenedor, puerto 5433) | D-02 |
| Embeddings | `intfloat/multilingual-e5-base`, local, 768 dims | D-05 |
| Frontend | Astro (panel de chat/voz, estado del grafo) | Fijo |
| Infraestructura como código | Terraform | Fijo |
| Despliegue | Azure Container Apps | Fijo |
| Observabilidad | LangSmith (tracing) | Fijo |
| Testing | pytest | Fijo |

No se agregan dependencias fuera de esta lista sin discutirlo (regla R-10).

## 3. Voz — candidatos en evaluación

Ninguno elegido. Azure AI Voice Live quedó descartado (D-01).

| Candidato | A favor | En contra / a verificar |
|---|---|---|
| Cartesia | Latencia de TTS muy baja, voces clonables | Costo y cupo del plan gratuito sin verificar |
| Deepgram | STT fuerte, API simple, tier gratuito generoso | TTS menos maduro que el STT |
| OpenAI Realtime | Speech-to-speech en una sola conexión | Costo por minuto; agregaría un segundo proveedor de IA |
| Azure AI Speech (estándar) | Encaja con el despliegue en Azure, precio por carácter | STT+TTS por separado: nosotros orquestamos la latencia |
| Gemini (TTS + transcribe) | Misma key y proveedor que el LLM | Live API por WebSocket sin probar |

Criterios de decisión, en orden: costo para la duración del reto, latencia
percibida y calidad de voz en español.

**Mediciones con la key del proyecto (2026-10-06, llamadas reales):**

| Capacidad | Modelo | Resultado |
|---|---|---|
| TTS | `gemini-3.8-flash-lite-tts`, `gemini-3.8-flash-tts`, `gemini-3.1-flash-tts-preview` | OK, ~2.5–3 s para ~3.7 s de audio en español |
| TTS | `gemini-2.5-flash-preview-tts` | OK pero 47 s: inservible en tiempo real |
| STT | `gemini-3.5-transcribe` | OK, 2.0 s, transcripción correcta |
| Visión | `gemini-3.5-flash-lite` | OK, 2.0 s |
| Tool calling | `gemini-3.5-flash-lite` | OK, 0.9 s |
| Embeddings | `gemini-embedding-001`, `gemini-embedding-2` | OK, 3072 dims (no encaja con `vector(768)`, ver D-05) |
| Texto | `gemini-3.5-pro`, `gemini-2.5-flash`, `text-embedding-004` | 404 |

Sin probar todavía: los modelos de tiempo real (`gemini-3.8-live`,
`gemini-3.5-transcribe-live`, `native-audio`), que van por WebSocket.

## 4. Avatar 3D — candidatos en evaluación

Objetivo: avatar con nuestra imagen y voz. Ninguna pieza está decidida.

| Pieza | Candidato probable | Alternativas / dudas abiertas |
|---|---|---|
| Malla del avatar | Ready Player Me | Avatar propio en Blender si RPM no da la semejanza |
| Renderizado | Three.js o react-three-fiber | r3f es React; el frontend es Astro → confirmar isla React |
| Lip-sync | TalkingHead | Visemas del proveedor de TTS, si los expone |

**Dependencia cruzada:** el lip-sync depende del proveedor de voz. Si el
proveedor emite visemas o timestamps por palabra, el lip-sync es casi gratis;
si no, hay que derivarlo del audio.

## 5. Decisiones tomadas

| Código | Decisión | Motivo | Fecha |
|---|---|---|---|
| D-01 | **Azure AI Voice Live descartado.** La skill `.claude/skills/azure-voice-live/` queda como material histórico: su patrón puerto/adaptador sigue siendo la base de `VoicePort`, sus detalles de protocolo (eventos WebSocket, `session.update`) ya no aplican | Costo | Antes de 0.4.0 |
| D-02 | **PostgreSQL + pgvector** (`pgvector/pgvector:pg17`, puerto 5433) como base relacional y vector store. Chroma descartado | Un chat agéntico necesita datos relacionales junto a los vectores; dos almacenes son dos almacenes que sincronizar | 2026-09-22 (0.3.0) |
| D-03 | **LLM: Gemini `gemini-3.5-flash-lite`** con `thinking_level=minimal`. Sin proveedores de respaldo en el factory: NVIDIA, OpenAI y Azure OpenAI salen | Medido con nuestro factory: ~1 s por llamada y 15/15 correctas en las tres formas de prompt del grafo. NVIDIA tardaba 9-20 s por turno | 2026-09-28 (0.4.0) |
| D-04 | **LangChain/LangGraph línea 1.x** (`langchain-core` 1.6, `langgraph` 1.2) | La integración actual de Gemini lo exige | 2026-09-28 (0.4.0) |
| D-05 | **Embeddings `intfloat/multilingual-e5-base`**, local, 768 dims. Descartados los modelos en inglés (all-MiniLM, bge-base-en, msmarco, e5-base) y LaBSE | El corpus es en español: los modelos en inglés fallarían en silencio; LaBSE está optimizado para emparejar traducciones, no para recuperación | 2026-09-22 (0.3.0) |
| D-06 | **Identificación por cédula sin contraseña.** **No es autenticación real** ([01-arquitectura.md](01-arquitectura.md) §8) | Alcance de la demo | 2026-09-22 (0.3.0) |
| D-07 | **Grafo escrito a mano** (`StateGraph`) en vez de `create_react_agent` | En un agente ReAct el LLM controla el bucle vía tool-calls, lo que incumple R-04 | 2026-09-17 (0.2.0) |
| D-08 | **Migraciones en SQL plano**, sin ORM ni Alembic | Seis tablas: cualquiera debe poder leer el archivo y saber cómo es la base | 2026-09-22 (0.3.0) |
