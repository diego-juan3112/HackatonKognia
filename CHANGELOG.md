# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

## [0.3.0] - 2026-09-22

### Changed
- **Vector store: Chroma -> PostgreSQL + pgvector.** Un chat agéntico necesita
  usuarios, conversaciones e historial junto a los vectores; dos almacenes eran
  dos almacenes que sincronizar. `docker-compose.yml` levanta
  `pgvector/pgvector:pg17` en el puerto 5433, sin tocar un Postgres nativo.
- **LLM: NVIDIA NIM** pasa a ser el proveedor por defecto (tier gratuito).
  Azure y OpenAI se conservan en el factory como respaldo de pago.
- **Embeddings: `intfloat/multilingual-e5-base` local**, 768 dims, con los
  prefijos `query:`/`passage:` manejados dentro del adaptador.
- **`RetrievalPort` y los seis nodos del grafo pasan a async.** Con un pool de
  Postgres y FastAPI asíncronos, una llamada bloqueante habría detenido el
  event loop en cada consulta.
- **El checkpointer se inyecta** en vez de construirse en `build_graph`:
  producción usa `AsyncPostgresSaver`, los tests usan `MemorySaver`.
- `MODEL_PROVIDER` por defecto sigue en `fake`; `EMBEDDING_PROVIDER` ahora
  acepta `local` o `fake` (se elimina `openai`).

### Added
- Esquema relacional en `migrations/001_init.sql`: `users`, `sessions`,
  `conversations`, `messages`, `documents`, `document_chunks`. SQL plano, sin
  ORM ni Alembic, con runner idempotente en `scripts/migrate.py`.
- Identificación por cédula (`POST /auth/identify`) con normalización de
  formato y sesiones con vencimiento. **No es autenticación real** — no hay
  contraseña; documentado en ARCHITECTURE.md §8.
- Endpoints de conversaciones: listar, crear y consultar historial.
- Puertos `UserRepositoryPort` y `ConversationRepositoryPort` con sus
  adaptadores de PostgreSQL.
- `services/chat_service.py`: orquesta el turno y persiste ambos lados, con
  verificación de propiedad — nadie lee ni escribe la conversación de otro.
- Dobles en memoria de todos los puertos en `tests/doubles/`, lo que mantiene
  la suite por defecto sin red ni Docker.
- `tests/integration/` (16 tests) contra PostgreSQL real, marcados `integration`
  y deseleccionados por defecto.
- `ARCHITECTURE.md`: rol de cada archivo, flujo completo y advertencias.

### Fixed
- El `FakeChatModel` gana `_agenerate`, evitando que cada llamada del grafo
  pasara por un thread pool innecesario.
- **Compatibilidad con Windows** (`src/platform_compat.py`): psycopg se niega a
  correr sobre el `ProactorEventLoop`, el loop por defecto de Windows. El
  síntoma era un pool que nunca terminaba de abrir mientras la conexión
  síncrona funcionaba. Además, uvicorn 0.36+ construye su loop con un
  `loop_factory` que ignora la política de asyncio, así que hizo falta
  `scripts/serve.py` pasando la factory por la opción `loop`.
- **JSONB en el retriever de pgvector**: psycopg3 no adapta un `dict` crudo a
  un placeholder jsonb; hacía falta envolverlo en `Jsonb(...)`.
- **Cast explícito `%s::vector`** en la consulta de similitud: en un `INSERT`
  Postgres infiere el tipo de la columna destino, pero un operador no tiene de
  dónde inferirlo y fallaba con `operator does not exist: vector <=> unknown`.

### Verificado
- 55 tests offline y 16 de integración contra PostgreSQL real, en verde.
- Migración idempotente; `vector(768)` e índice HNSW `vector_cosine_ops`
  confirmados en la base.
- Flujo HTTP completo: identificación, las tres ramas del grafo, historial, y
  persistencia sobreviviendo un reinicio del servidor (4 mensajes acumulados,
  3 hilos y 30 checkpoints en Postgres).

### NVIDIA — verificado contra la API real (2026-09-23)
- **Modelo por defecto: `openai/gpt-oss-20b`** (era `meta/llama-3.3-70b-instruct`,
  que esta en end-of-life desde 2026-08-26 y devuelve `410 Gone`). Es un modelo
  de pesos abiertos servido por NVIDIA — no hay cuenta de OpenAI de por medio.
  Elegido midiendo: `nemotron-3-super-120b-a12b` es mas rapido (1.1s) pero
  fallo 3 de 6 llamadas con `503`; `gpt-oss-20b` no fallo ninguna y acerto las
  tres formas de prompt (intencion, JSON, espanol).
- **`NVIDIA_REASONING_EFFORT=low`**: sobre 5 llamadas iguales, sin el parametro
  la mediana era 19.4s con 100 tokens de salida; con el, 3.3s con 27 tokens.
  El modelo gastaba ~73 tokens por llamada razonando de mas.
- **Se retira `langchain-nvidia-ai-endpoints`.** Descartaba silenciosamente
  `reasoning_effort` (verificado contando tokens: 100 con y sin el parametro).
  NVIDIA habla el protocolo de OpenAI, asi que se usa `ChatOpenAI` apuntando a
  `integrate.api.nvidia.com`, que si lo transmite (27 tokens). De paso se elimina
  la deuda del pin `<1.0` que existia por el conflicto con langchain-core.
- **No confiar en `ChatNVIDIA.get_available_models()`**: su catalogo esta
  desactualizado y lista modelos muertos. La fuente de verdad es
  `GET https://integrate.api.nvidia.com/v1/models`.

### Por hacer
- [ ] Probar `EMBEDDING_PROVIDER=local` (descarga ~1.1 GB la primera vez).
- [ ] Reducir latencia: un turno con RAG cuesta 2 llamadas al LLM y en el tier
      gratuito eso son 9-20s. Opciones: reemplazar `classify_intent` por
      clasificacion local, o reintentar contra `nemotron-3-super-120b-a12b`
      (1.1s) tolerando sus 503.
- [ ] Decidir proveedor de voz (AGENTS.md §1.1) e implementar `VoicePort`.
- [ ] Decidir stack de avatar 3D (§1.2) e implementar `AvatarPort`.
- [ ] Arquitectura híbrida CAG: que el agente consulte tablas de negocio.

## [0.2.0] - 2026-09-17

### Changed
- **Refactor de capas** a la estructura que declara AGENTS.md §2:
  `src/{api,services,integrations,models}`. Se elimina `src/agent_core/`.
- **El grafo se reescribe a mano** (`StateGraph`) en lugar de
  `create_react_agent`. Motivo: en un agente ReAct el LLM controla el bucle vía
  tool-calls, lo que incumple AGENTS.md §8 ("el LLM nunca decide transiciones").
  Ahora las aristas son funciones puras de estado en `services/graph/edges.py`.
- `api/main.py` ya no construye el agente en tiempo de import: se usa
  `lifespan` + un composition root en `api/dependencies.py`. Antes, importar la
  app exigía credenciales reales y rompía tests y CI.
- `AGENTS.md`: voz y avatar 3D pasan a PENDIENTE DE DECISIÓN con candidatos
  documentados; se añaden el principio de núcleo genérico (§3), los puertos
  intercambiables (§5) y el diseño del RAG (§6).

### Added
- Seis nodos genéricos, uno por archivo, en `services/graph/nodes/`: intake,
  classify_intent, collect_data, route, retrieve_context, respond.
- Puertos `VoicePort`, `AvatarPort` y `RetrievalPort` en `src/models/ports.py`.
  Voz y avatar quedan **declarados sin implementación** hasta decidir proveedor.
- Dominio declarativo en YAML (`config/domains/faq_demo.yaml`) con catálogo de
  intenciones y esquema de campos. Los nodos no conocen su contenido.
- RAG sobre Chroma: `integrations/retrieval/` con cargadores (`.md`, `.txt`,
  `.csv`, `.pdf`), embeddings intercambiables y `scripts/ingest.py`.
- `MODEL_PROVIDER=fake` y `EMBEDDING_PROVIDER=fake`: el pipeline completo corre
  sin credenciales ni red.
- `pyproject.toml` con `pythonpath = ["src"]`. Sin esto la suite nunca había
  podido importar el paquete.
- Suite de 22 tests por capas (`tests/{services,integrations,api}/`).

### Fixed
- `classify_intent` no pasaba los `examples` del catálogo al prompt, perdiendo
  la señal más fuerte de clasificación.
- El embedder de desarrollo no filtraba palabras vacías: la consulta "cual es
  el horario de atencion" devolvía `solicitudes.md` antes que `horarios.md`.
  Añadidos stopwords y frecuencia sublineal, con test de regresión sobre el
  corpus real.

### Por hacer
- [ ] Decidir proveedor de voz (AGENTS.md §1.1) e implementar `VoicePort`.
- [ ] Decidir stack de avatar 3D (§1.2) e implementar `AvatarPort`.
- [ ] Frontend Astro.
- [ ] Sustituir el dominio de juguete por el del reto real.

## [0.1.0-base] - 2026-09-14

### Added
- Estructura hexagonal inicial del agente (`domain` / `application` / `infrastructure`).
- Agente general tipo ReAct sobre LangGraph (`create_react_agent`) con memoria en `MemorySaver`.
- Adaptador de LLM intercambiable: `openai` (dev local) <-> `azure` (Azure OpenAI / AI Foundry).
- Herramienta `calculator` (offline, para tests) y hook opcional de búsqueda web (Tavily).
- API FastAPI con `/health` y `/chat`.
- Test de humo (`tests/test_agent_smoke.py`) que corre sin credenciales reales.
- Esqueleto de Terraform para desplegar en Azure Container Apps + Azure OpenAI.

### Por hacer durante el reto
- [ ] Conectar `MODEL_PROVIDER=azure` con el recurso real de Azure OpenAI/Foundry.
- [ ] Definir y agregar las herramientas específicas del caso de uso elegido.
- [ ] Ajustar el prompt de sistema al dominio del reto.
- [ ] Aplicar Terraform contra la suscripción del hackathon y desplegar la imagen.
- [ ] (Opcional) Cambiar `MemorySaver` por un checkpointer persistente si el demo lo requiere.

## [0.1.0] - 2026-09-14
### Added
- Primera versión del agente base para el Kognia Challenge 2026.
