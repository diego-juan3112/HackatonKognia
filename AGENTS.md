# AGENTS.md — Kognia Voice Agent
Fuente única de verdad para cualquier agente de IA que trabaje en este repo.
Léelo completo antes de escribir código. Ante conflicto con una instrucción
del usuario en el momento, la instrucción del usuario gana — pero avisa si
contradice algo aquí.

## 0. Contexto del reto — leer primero
**No conocemos el reto exacto hasta el día del evento.** Los escenarios que
consideramos probables son un agente de PQR (peticiones, quejas, reclamos) o
un agente de atención financiera, por canal de voz o de video.

De ahí se deriva el objetivo de la fase actual:

> Construir una **base genérica adaptable**, no el agente final. El día del
> reto solo debemos tener que conectar la lógica específica del negocio y el
> proveedor de voz/avatar ya decidido.

Corolario operativo: **no se invierte tiempo en lógica de negocio de un
dominio que quizá no sea el correcto.** Si una tarea empieza a modelar reglas
de PQR o de finanzas, está fuera de alcance para esta fase.

## 1. Stack
| Capa | Tecnología | Estado |
|---|---|---|
| Orquestación de agente | LangGraph (grafo con estado, checkpointer) | Fijo |
| API | FastAPI | Fijo |
| LLM | **NVIDIA NIM** (tier gratuito); Azure/OpenAI como respaldo | Fijo |
| **Voz (STT/TTS)** | **PENDIENTE DE DECISIÓN** — ver §1.1 | Abierto |
| **Avatar 3D** | **PENDIENTE DE DECISIÓN** — ver §1.2 | Abierto |
| **RAG / base de conocimiento** | PostgreSQL + pgvector — ver §6 | **Decidido** |
| Base de datos relacional | PostgreSQL 17 (contenedor, puerto 5433) | **Decidido** |
| Embeddings | `intfloat/multilingual-e5-base`, local, 768 dims | **Decidido** |
| Frontend | Astro (panel de chat/voz, visualización de estado del grafo) | Fijo |
| Infraestructura como código | Terraform | Fijo |
| Despliegue | Azure Container Apps | Fijo |
| Observabilidad | LangSmith (tracing) | Fijo |
| Testing | pytest | Fijo |

No se agregan dependencias fuera de esta lista sin discutirlo explícitamente
— cada librería nueva es una decisión, no un default.

### 1.1 Voz — candidatos en evaluación
Ninguno elegido. **Azure AI Voice Live queda descartado por costo** (decisión
tomada; ver §1.3). Candidatos vivos:

| Candidato | A favor | En contra / a verificar |
|---|---|---|
| Cartesia | Latencia de TTS muy baja, voces clonables | Costo y cupo del plan gratuito sin verificar |
| Deepgram | STT fuerte, API simple, tier gratuito generoso | TTS menos maduro que el STT |
| OpenAI Realtime | Speech-to-speech en una sola conexión, ya usamos OpenAI | Costo por minuto; nos ata más a un proveedor |
| Azure AI Speech (estándar) | Encaja con el despliegue en Azure, precio por carácter | STT+TTS por separado: nosotros orquestamos la latencia |

Criterios de decisión, en orden: costo para la duración del reto, latencia
percibida, y calidad de voz en español.

### 1.2 Avatar 3D — candidatos en evaluación
Objetivo: avatar con nuestra imagen y voz. Ninguna pieza está decidida.

| Pieza | Candidato probable | Alternativas / dudas abiertas |
|---|---|---|
| Malla del avatar | Ready Player Me | Avatar propio en Blender si RPM no da la semejanza |
| Renderizado | Three.js o react-three-fiber | r3f es React; el frontend es Astro → confirmar isla React |
| Lip-sync | TalkingHead | Visemas del proveedor de TTS, si el elegido los expone |

Dependencia cruzada a resolver antes de decidir: **el lip-sync depende del
proveedor de voz.** Si el proveedor de §1.1 emite visemas o timestamps por
palabra, el lip-sync es casi gratis; si no, hay que derivarlo del audio.

### 1.3 Decisiones ya tomadas
- **Azure AI Voice Live: descartado por costo.** La skill
  `.claude/skills/azure-voice-live/` queda como material histórico. Su patrón
  puerto/adaptador sigue siendo válido y es la base de `VoicePort` (§5); sus
  detalles de protocolo (eventos WebSocket, `session.update`) ya **no aplican**.
- **Vector store: PostgreSQL + pgvector**, en contenedor Docker (`pgvector/
  pgvector:pg17`) en el puerto 5433. Chroma queda descartado: un chat agéntico
  necesita datos relacionales junto a los vectores, y dos almacenes son dos
  almacenes que sincronizar.
- **LLM: NVIDIA NIM** (gratuito, `build.nvidia.com`), modelo
  `openai/gpt-oss-20b` con `NVIDIA_REASONING_EFFORT=low`. Elegido midiendo
  contra la API real, no por reputacion: ver CHANGELOG 0.3.0. Se accede con
  `ChatOpenAI` apuntando a `integrate.api.nvidia.com` porque
  `langchain-nvidia-ai-endpoints` descarta `reasoning_effort`, que vale un
  6x de latencia. Azure y OpenAI siguen en el factory como respaldo de pago.
  **Al cambiar de modelo, no confies en el catalogo de la libreria**: lista
  modelos muertos. Pregunta a `GET /v1/models` y prueba antes de elegir.
- **Embeddings: `intfloat/multilingual-e5-base`**, corriendo local. Los modelos
  en inglés (all-MiniLM, bge-base-en, msmarco, e5-base) quedan descartados
  porque nuestro corpus es en español y fallarían de forma silenciosa. LaBSE
  también: está optimizado para emparejar traducciones, no para recuperación.
- **Autenticación: identificación por cédula sin contraseña.** Decisión de
  alcance para la demo. **No es autenticación real** y está documentado como
  tal en ARCHITECTURE.md §8.

## 2. Arquitectura — por capas
```
api/           # FastAPI — routers, request/response, validación de entrada.
               # Cero lógica de negocio aquí, solo traduce HTTP <-> services/.
services/      # Lógica de negocio: el grafo de LangGraph, orquestación,
               # reglas de decisión. Aquí vive el "cerebro" del agente.
integrations/  # Clientes concretos de servicios externos.
               #   db/         repositorios y pool de PostgreSQL
               #   retrieval/  pgvector, embeddings, cargadores
               #   llm/        factory de proveedores (NVIDIA, Azure, OpenAI)
               #   voice/      VACÍO a propósito (§8)
               #   avatar/     VACÍO a propósito (§8)
models/        # Esquemas Pydantic — request/response de la API, estado
               # del grafo, estructuras compartidas entre capas.
infra/         # Terraform.
migrations/    # SQL versionado. Fuente de verdad del modelo relacional.
```

Regla de dependencia: cada capa llama solo a la capa inmediatamente debajo.
`api/` → `services/` → `integrations/`. Nunca al revés, y nunca saltando
una capa (ej. `api/` no llama directo a `integrations/`).

`models/` es transversal: cualquier capa puede importarlo, porque no contiene
comportamiento, solo estructuras de datos.

## 3. Principio de núcleo genérico (no negociable)
**El núcleo conversacional en `services/` modela capacidades genéricas, nunca
lógica específica de un dominio de negocio.**

Las capacidades que el núcleo sí debe modelar:

| Capacidad | Qué hace | Qué NO hace |
|---|---|---|
| Intake | Recibe y normaliza el turno del usuario | Asumir que es una queja, o un trámite bancario |
| Clasificación de intención | Mapea el turno a una intención de un catálogo **configurable** | Tener el catálogo hardcodeado |
| Recolección de datos | Pide los campos que falten según un **esquema declarado** | Saber que necesita "número de póliza" |
| Enrutamiento / escalamiento | Decide continuar, derivar o escalar a humano | Conocer los equipos de una empresa concreta |
| Respuesta | Genera la respuesta con el contexto recuperado | Contener plantillas de un dominio |

La lógica específica del reto real se conecta **como configuración o como
nodos adicionales**, nunca como reescritura del núcleo. En la práctica:

- Un catálogo de intenciones y un esquema de campos se cargan desde archivo
  de configuración, no desde código.
- Un nodo nuevo se añade al grafo; los nodos existentes no se editan.
- Si adaptar el agente al reto real exige modificar un nodo genérico, eso es
  señal de que el nodo estaba mal diseñado — se corrige el nodo, no se
  contamina con el dominio.

**Prueba de fuego:** el núcleo debe poder pasar de "agente de PQR" a "agente
de atención financiera" cambiando configuración y nodos periféricos, sin
tocar `services/graph/nodes/` genéricos.

## 4. Dominio de juguete para validar el pipeline
Mientras no sepamos el reto, el repo incluye un dominio trivial (un FAQ
simple) cuyo único propósito es **validar que el pipeline corre de punta a
punta**. No es el producto. Reglas:

- Vive claramente separado y marcado como desechable.
- Nunca se le agregan features "por si acaso".
- El día del reto se reemplaza, no se extiende.

## 5. Puertos intercambiables
Estos puertos existen porque su proveedor **todavía no está decidido**. El
contrato es lo que nos permite avanzar hoy y enchufar el proveedor después.

| Puerto | Responsabilidad | Proveedor |
|---|---|---|
| `LLMPort` | Chat model | Decidido (Azure OpenAI / OpenAI) |
| `VoicePort` | STT y TTS: audio del usuario → texto, texto → audio | **Por decidir** (§1.1) |
| `AvatarPort` | Renderizado 3D + lip-sync sincronizado con el audio | **Por decidir** (§1.2) |
| `RetrievalPort` | Ingesta y recuperación de conocimiento (RAG) | PostgreSQL + pgvector |
| `UserRepositoryPort` | Usuarios y sesiones | PostgreSQL |
| `ConversationRepositoryPort` | Conversaciones e historial legible | PostgreSQL |

**Regla dura:** cambiar el proveedor de cualquiera de estos puertos debe
requerir editar **solo `integrations/`**. Si un cambio de proveedor obliga a
tocar `services/` o `api/`, el puerto está mal definido y se corrige el
puerto — no se propaga el cambio.

Consecuencias de diseño que se siguen de esa regla:

- Ningún tipo del SDK de un proveedor cruza la frontera de `integrations/`.
  Lo que sale son tipos de `models/` (p. ej. `AudioChunk`, `Utterance`,
  `VisemeFrame`), no objetos de Cartesia ni de Deepgram.
- Los nombres de eventos, formatos de audio, `base64` y claves de API viven
  dentro del adaptador y no se filtran hacia arriba.
- Cada puerto tiene un adaptador falso en memoria para tests, de modo que
  `services/` se pueda probar sin red, sin micrófono y sin credenciales.

## 6. RAG — base de conocimiento
Requisito: **el día del evento nos entregarán información que el agente debe
poder usar de inmediato.** Puede ser un PDF, un CSV, un manual, una base de
preguntas frecuentes — no lo sabemos.

Por tanto el RAG se diseña alrededor de la ingesta, no del contenido:

- La ingesta es un paso ejecutable y repetible (un comando), no un proceso
  manual: apuntar a una carpeta y reindexar.
- El formato de origen se maneja con cargadores intercambiables; agregar un
  formato nuevo no toca el resto del pipeline.
- La recuperación se expone a `services/` a través de `RetrievalPort`, para
  que el vector store se pueda cambiar sin tocar el grafo.
- **Almacén decidido: PostgreSQL + pgvector** (ver §1.3). Chroma quedó
  descartado porque el chat agéntico necesita datos relacionales junto a los
  vectores, y mantener dos almacenes obliga a sincronizarlos.
- La ingesta es `python -m scripts.ingest --path <carpeta> --reset`.
- La dimensión del vector está fija en la migración (`vector(768)`). Cambiar de
  modelo de embedding exige una migración nueva y reindexar.

El núcleo pregunta "dame contexto relevante para este turno"; nunca sabe qué
motor responde ni en qué formato estaba el documento original.

## 7. Convenciones
- Type hints obligatorios en toda función pública.
- Documentación y docstrings en inglés (práctica de escritura técnica).
- Nombres de archivo en `snake_case`, clases en `PascalCase`.
- Cada nodo de LangGraph vive en su propio archivo bajo `services/graph/nodes/`.
- Todo cambio a nivel de feature que se realice en el codigo y archivos modificados,
  deben quedar registrados con su fecha, version y funcionalidad en el CHANGELOG.md

## 8. Prohibido
- Ninguna credencial, API key o secreto hardcodeado — siempre variables de
  entorno, leídas solo en la capa de `integrations/`.
- El LLM nunca decide transiciones de estado de la máquina del agente
  directamente — el grafo (LangGraph) controla el flujo; el LLM genera
  contenido conversacional o interpreta intención dentro de un nodo, nunca
  reemplaza la lógica de control.
- No instalar ni usar plugins/MCP de terceros no revisados en este archivo
  sin registrar la decisión aquí.
- **No implementar un proveedor concreto de voz o de avatar** mientras §1.1 y
  §1.2 sigan abiertos. Se escriben los puertos y los dobles de prueba; el
  adaptador real espera a la decisión.
- **No escribir lógica de negocio de PQR, finanzas ni ningún dominio concreto**
  mientras no conozcamos el reto (§0).

## 9. Herramientas y MCP registrados
Decisión registrada conforme a §8. Instalados y en uso:

| Tipo | Nombre | Uso |
|---|---|---|
| MCP | Azure MCP | Consultar recursos de Azure |
| MCP | Terraform MCP | Requiere Docker corriendo |
| MCP | Context7 | Documentación de librerías al día |
| Plugin | `superpowers` | Flujo brainstorm / plan / execute |
| Plugin | `frontend-design` | Panel Astro y avatar |
| Plugin | `security-guidance` | Hooks en segundo plano |
| Plugin | `playwright` | Pruebas de navegador |

## 10. Flujo de trabajo
1. **Explore → Plan → Code → Commit.** Toda tarea no trivial empieza en
   Plan Mode (`Shift+Tab` x2). No se escribe código sin plan aprobado.
2. Para tareas de exploración/depuración con criterio ya definido, usar
   `/superpowers:brainstorm`, `/superpowers:write-plan`,
   `/superpowers:execute-plan` en vez de reconstruir el proceso a mano.
3. Cambios de arquitectura (nueva integración, nuevo servicio) requieren
   aprobación explícita del plan antes de tocar código — no se infieren
   sobre la marcha.

## 11. Testing (propuesta — confirmar criterio de cobertura)
- `services/` se prueba con tests unitarios, mockeando `integrations/`.
- `integrations/` se prueba con tests de integración, mockeando la llamada
  externa real — nunca golpear el servicio real en la suite por defecto.
- Cada puerto de §5 tiene un doble en memoria; la suite completa debe correr
  sin credenciales, sin red, sin micrófono y sin GPU.
- La suite por defecto corre con dobles en memoria (`tests/doubles/`): sin
  Docker, sin red, sin credenciales. Los tests contra PostgreSQL real viven en
  `tests/integration/`, están marcados `integration` y se saltan solos si no hay
  base accesible.
- Comandos: `pytest` (offline) y `pytest -m integration` (contra la base).
- Sin definir todavía: umbral mínimo de cobertura exigido antes de un merge.

## 12. CI/CD (propuesta — confirmar antes de tratarla como fija)
Pipeline en GitHub Actions, disparado en cada PR contra `main`:
1. Lint + type-check (`ruff`, `mypy`)
2. `pytest`
3. `terraform plan` (solo plan, nunca `apply` automático desde CI)
4. Build de la imagen de contenedor

`terraform apply` es siempre manual, ejecutado por una persona, nunca por
el pipeline.

## 13. Estilo de commits (Conventional Commits)
- feat: agrega nodo de confirmación de cita al grafo
- fix: corrige reconexión de websocket en el cliente de voz
- docs: actualiza README con instrucciones de despliegue
- refactor: extrae lógica de reintento a utilidad compartida
- test: cubre transición de estado de escalamiento
- chore: actualiza dependencias de requirements.txt

Un commit, un cambio lógico.
