# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

## [0.4.2] - 2026-10-07

### Changed
- **Contratos del proyecto reorganizados.** `AGENTS.md` pasa de 293 líneas a
  un índice corto: qué documento leer antes de cada tarea y las reglas en una
  línea cada una. El detalle vive en `docs/` numerados:
  `00-contexto-y-decisiones`, `01-arquitectura` (antes `ARCHITECTURE.md`),
  `02-puertos`, `03-api` (antes `API.md`), `04-rag`, `05-pruebas` y
  `06-flujo-y-convenciones`.
- **Reglas y decisiones con código rastreable**: `R-01` a `R-21` para reglas
  duras y `D-01` a `D-08` para decisiones tomadas. Código, comentarios, READMEs
  y configuración citan ahora el código en vez de `AGENTS.md §N`. No se agregó
  ninguna regla nueva: solo se reubicaron y numeraron las existentes.

### Added
- `docs/00-contexto-y-decisiones.md` registra las mediciones del 2026-10-06
  con la key del proyecto: TTS (`gemini-3.8-flash-*-tts`, ~2.5-3 s), STT
  (`gemini-3.5-transcribe`, 2 s), visión, tool calling y embeddings de Gemini;
  y los modelos que responden 404.

## [0.4.1] - 2026-09-29

### Added
- **`API.md`**: guía de los endpoints para el frontend. Explica en qué orden
  llamarlos, qué significa cada campo de la respuesta (incluido `route`) y qué
  hacer con cada código de error.
- **Swagger documenta todos los errores.** `src/api/errors.py` declara, ruta
  por ruta, los 401/403/404/409/502/503 que antes aparecían en `/docs` como
  *Undocumented*. `/docs` abre con el flujo mínimo (crear usuario, login, chat).
  Dos tests lo protegen.

### Fixed
- **El ejemplo de `POST /chat` en Swagger daba 404 al ejecutarlo tal cual.**
  Swagger rellenaba `conversation_id` con un UUID inventado. Ahora el ejemplo
  por defecto no lo trae, y un segundo ejemplo muestra cómo continuar una
  conversación.
- `src/api/main.py` reportaba la versión 0.3.0 y documentaba un comando de
  arranque (`uvicorn` directo) que falla en Windows.

### Removed
- `src/integrations/tools/` (calculadora y búsqueda web con Tavily): nada lo
  usaba, y estaba roto porque leía `tavily_api_key`, que ya no existe en la
  configuración.
- El directorio `.chroma/` y su línea en `.gitignore`, restos de Chroma, y el
  comentario de Tavily en `requirements.txt`.
- 41 paquetes del entorno virtual que ningún requisito de `requirements.txt`
  necesita (`chromadb` y sus dependencias, `tiktoken`, `jiter`, `aiohttp`,
  entre otros). Ninguna prueba cambió: 71 offline y 19 de integración en verde,
  y un turno real con Gemini respondiendo.

## [0.4.0] - 2026-09-28

### Changed
- **LLM: NVIDIA sale, entra Gemini** (`gemini-3.5-flash-lite`, `thinking_level=minimal`).
  Elegido midiendo a través de nuestro propio factory, con las tres formas de
  prompt del grafo: ~1 s por llamada y 15/15 correctas. Con NVIDIA un turno
  costaba 9-20 s; con Gemini, 1-3.5 s. Los `gemini-2.5-*` aparecen en la lista
  de modelos pero responden 404 para keys nuevas; `gemini-3.8-flash` fue más
  lento (8.5 s) y se topó con límites de cuota.
- **Se eliminan NVIDIA, OpenAI y Azure OpenAI** del código, la configuración y
  el Terraform. El factory ya no tiene proveedores de respaldo.
- **Stack migrado a la línea 1.x**: `langchain-core` 1.6, `langgraph` 1.2,
  `langchain-text-splitters` 1.1, `langchain-google-genai` 4.4. La integración
  actual de Gemini lo exige. La migración sola no rompió ningún test.
- **La lógica `fake` sale del producto.** La app siempre usa Gemini y E5 reales.
  `FakeChatModel` y `HashingEmbedder` se mudan a `tests/doubles/`, único lugar
  donde existen; `MODEL_PROVIDER` y `EMBEDDING_PROVIDER` desaparecen.
- **`/auth/identify` se reemplaza por `POST /users` y `POST /auth/login`.**
  Crear un usuario (409 si ya existe) e iniciar sesión (404 si no está
  registrado) son operaciones separadas: el login ya no da de alta a nadie.
- `respond` envía los últimos turnos de **ambos** lados de la conversación.
  Antes solo enviaba los del usuario: un modelo real veía a alguien hablando
  solo, sin saber qué había respondido ya.
- `config.py` ya no contiene contraseñas en sus valores por defecto (AGENTS.md §8).

### Added
- **El agente sabe con quién habla.** `chat_service` inyecta en el estado del
  grafo el nombre y los últimos 4 dígitos de la cédula; `respond` los usa. La
  cédula completa **nunca** llega al LLM, y un test lo garantiza revisando
  todos los prompts.
- **Base de pruebas separada (`kognia_test`)**, creada y migrada
  automáticamente. Los tests de integración se niegan a vaciar cualquier base
  cuyo nombre no termine en `_test`.
- `scripts/seed.py`: 2 usuarios demo y el corpus embebido con E5. Idempotente.
- La app **se niega a arrancar** si hay migraciones pendientes, con el comando
  exacto para resolverlo.
- Cuota de Gemini agotada → **503 con `Retry-After`**; otro fallo del modelo →
  502. Se capturan las excepciones genéricas de `langchain-core`, no las de
  Google, así que la API no sabe qué proveedor hay detrás.
- `src/integrations/db/migrations.py`: la lógica de migraciones, compartida por
  el CLI (`scripts/migrate.py`, ahora con `--test`), los tests y el arranque.

### Fixed
- **El footgun de los tests.** `pytest -m integration` vaciaba la base de
  desarrollo con `TRUNCATE ... CASCADE`: borró el corpus tres veces y una vez a
  los usuarios. Verificado: los conteos de desarrollo ya no cambian al correrlos.
  Efecto colateral: dejan de generarse checkpoints huérfanos por esa vía.
- Los nodos leían `str(response.content)`. En `langchain-core` 1.x una
  respuesta puede ser una lista de bloques, y `str()` de esa lista no es la
  respuesta: ahora se usa `.text`.
- `collect_data` tolera JSON envuelto en bloques de código markdown, que Gemini
  suele agregar. Sin esto, un dato bien extraído se leía como "no encontrado" y
  el agente lo volvía a pedir.
- `E5Embedder` carga primero desde la caché local. Antes consultaba a Hugging
  Face en cada arranque, incluso con el modelo ya descargado.
- Se usa `get_embedding_dimension` (renombrado en sentence-transformers 6.x),
  con respaldo para versiones anteriores.

### Verificado con modelos reales
- 69 tests offline y 19 de integración en verde.
- Por HTTP: crear usuario (201) y duplicado (409); login de cédula no
  registrada (404) y de usuario sembrado (200); la pregunta "¿a qué hora puedo
  ir el fin de semana?" —sin palabras en común con el documento, que dice
  "sábados"— respondida correctamente y por su nombre; seguimiento de la
  conversación; extracción real del radicado como JSON; las ramas de
  recolección y escalamiento; y el historial sobrevive a reiniciar el servidor.

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
