# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

### Fixed — producción (2026-10-09 ≈ 15:25)
- **Texto del sistema mostrado como si lo dijera el usuario e interrupciones:** la pista de contexto
  del transcriptor de OpenAI (añadida en `3f14414`) se devolvía como transcripción ante ruido o silencio
  y abría turnos fantasma. Se quitó (`6fdf7fa`).
- **Turnos fantasma por ruido** («公主。», «Gracias por ver el video»): el front descarta transcripciones
  inverosímiles (otros alfabetos, < 2 letras, frases típicas de alucinación), cancela la respuesta del
  motor y no las analiza (`web/src/voice/transcript-filter.ts`, 200 pruebas de front).
- **Falso «cifra no verificada»:** el verificador ahora reconoce los dígitos de teléfonos y direcciones
  leídos de la fuente. `include_contact` solo a pedido expreso (prompt `reto01-ips-v9`).
- Verificado en caliente con el motor real y voz clonada: respuesta completa sin interrupciones; con ráfagas
  de ruido como micrófono, 0 detecciones de voz y 0 turnos fantasma.

### Removed — Limpieza (rama `chore/limpieza-repo`, 2026-10-09, D-23)
- **Base genérica retirada:** chat con cédula (rutas `auth`, `chat`, `conversations`, `users`,
  `api/main.py`, `dependencies.py`), PostgreSQL + pgvector (`integrations/db`, `migrations/`,
  `docker-compose.yml`), RAG con E5 (`integrations/retrieval`, `scripts/ingest.py`), grafo de chat
  genérico (`services/graph`), dominio de juguete `faq_demo`, `platform_compat.py`, scripts
  `migrate`/`seed`/`serve`, `infra/terraform`, sus pruebas y dobles (`tests/integration`, `FakeChatModel`…).
- **Documentación retirada:** `docs/04-rag.md`, `docs/sdd_ips/`, `docs/diagrams/`, `docs/faq_demo/`,
  la skill `.claude/skills/azure-voice-live` y el anexo de restricciones de Azure OpenAI para estudiantes.
- `requirements-base.txt` pasa a `requirements-dev.txt` (runtime + pruebas + scripts de medición).
- **Todo queda en el historial de git** (último commit con la base: `0a5a625`).

### Changed — Limpieza de documentación (D-23)
- `docs/00`: nueva decisión **D-23**; D-02, D-05, D-06, D-08 y la parte del grafo genérico de D-07,
  retiradas; §1 y §2 sin base genérica ni Terraform.
- `AGENTS.md`: R-07, R-12 a R-15, R-18, R-19 y R-21 marcadas **Retiradas (D-23)** sin renumerar;
  R-02 y R-16 reescritas para la app actual; sin la fila de `docs/04`.
- `CLAUDE.md` sin la skill de Azure Voice Live ni las notas de Docker/Terraform MCP.
- `docs/02` solo con los puertos vigentes y los dobles reales; `docs/05` con R-16/R-17, sondas en vivo
  y `npm test`; `docs/06`, `07`, `09`–`13` y `docs/anexos/README.md` sin referencias a lo retirado
  (plan B = contenedor con el `Dockerfile` en cualquier host).
- `vercel.json`, `.vercelignore` y `.dockerignore` sin los patrones de `migrations/`, `infra/` y
  `docker-compose.yml` (ya no existen; el comportamiento no cambia).

### Integración en `main` (2026-10-09 ≈ 14:15) — backend completo + front de los carriles A y B
- **Front:** consentimiento explícito «Usar mi voz» (R-26), la conversación se corta al salir de la consola,
  transcripción parcial del agente, `for_model` como salida de herramienta, sin `forceLive` en la primera
  consulta, la pregunta escrita mientras conecta ya no se pierde, regla de 1 s contra el ruido (también con
  voz clonada), verificación de cifras con autocorrección, herramientas en el panel de administrador, un solo
  `POST /sessions`, aviso único con «Reintentar» si el backend cae. Voz clonada con Cartesia (carril A).
- **Backend:** prompt `reto01-ips-v8` (agente con herramientas, trato de usted, contacto de hasta 5 sedes,
  continúa tras una pausa), VAD 0,65 con `noise_reduction` y sin corte automático, `/health` con `tools`,
  `default_voice_mode` y `cloned_voice_engines`, `.gitignore` para cualquier `.env.*`.
- **Verificado:** 155 pruebas de backend y 134 de front en verde; build estático; prueba en caliente en Edge
  (pregunta durante el saludo → `aggregate_ips` desde la precarga → «97.036 camas en total», voz clonada con
  148 trozos de Cartesia, `for_model` entregado al motor, 0 errores); ráfagas de ruido de 0,3 s como
  micrófono: 0 detecciones de voz en OpenAI; 8 evaluadores simultáneos sin fugas entre usuarios.
- **Pendiente:** despliegue en Vercel (D-15) y smoke contra la URL pública; A-21 con voz humana; regla de 1 s
  con ruido real de micrófono; Gemini en el navegador.

### Added — Reto 01, herramientas de agente (2026-10-09, rama `feat/reto-01-api-tools`, contrato datos `2026-10-09.3`)
- `verify_registration`, `area_profile`, `compare_areas` y `dataset_info` en `POST /tools/{nombre}` y en las
  declaraciones de herramientas ([09](docs/09-datos-en-vivo-datos-gov-co.md) §4). Porcentajes, diferencias y
  razones se calculan en Python a partir de la fuente (R-22); `dataset_info` no consulta la fuente.
- `search_ips` acepta `capacity_group`/`capacity_type` (sedes con esa capacidad instalada registrada, con
  `NOT_AVAILABILITY`). Advertencias nuevas: `DERIVED_FROM_SOURCE`, `NOT_PER_CAPITA`.

### Fixed
- Idempotencia de `IpsToolService.run`: la clave incluye herramienta y huella de argumentos (H1).

### Added — Reto 01, carril B (2026-10-09, rama `feat/reto-01-api`)
- **Backend de voz implementado** (`src/api/app_voice.py`, contrato `2026-10-09.2`): `GET /health`
  (con `voice_modes`), `POST /sessions` (token HMAC anónimo, R-28), `POST /realtime/session`
  (OpenAI `gpt-realtime-2.1` y Gemini `gemini-3.8-live`, `voice_mode` efectivo), `POST /speech/session`
  (token de Cartesia de 600 s, D-20), `GET /dataset/brief`, `POST /tools/{nombre}` (las 5 herramientas),
  `POST /analysis/utterance` (JSON con WAV en base64, no multipart) y `POST /feedback`.
- **Datos en vivo** (D-12, D-13): cliente SODA3 con plazo común, un reintento, token descartado
  ante 403 y caché fresca/`stale`; SoQL con lista cerrada; léxico `data/lexicon.json` con
  homónimos y distritos (`scripts/build_lexicon.py`); sobre de evidencia siempre presente.
- **Analista** (D-16): grafo LangGraph `prepare → text ∥ acoustic → fuse → style_policy`, perfiles
  `fast` → `deep` (D-10), prosodia local y política de estilo determinista con suavizado
  (`config/style_policy.yaml`); prompt versionado `reto01-ips-v1` (`config/domains/reto01_ips.yaml`).
- D-20 en `docs/00`; IDs de D-10 y D-11 cerrados; mediciones de G3 y del token de Cartesia.

### Verificado
- 121 pruebas offline en verde (`pytest`, sin red ni claves).
- En vivo (G3, 2026-10-09): números dorados de `docs/09` §9 exactos; analista por texto 3/3 en
  esquema; token de Cartesia 200 en ≈ 1 s.

### Added — contra alucinaciones y latencia (2026-10-09, tarde)
- **Mundo cerrado (R-22):** prompt `reto01-ips-v5` (solo vale lo que devuelve una herramienta; lista
  de lo que la fuente no contiene), `for_model` determinista y compacto en cada sobre (cifra, unidad,
  corte, ≤ 3 filas) y verificador de cifras `POST /verify/answer` (sin LLM).
- **Evaluación de grounding** (`scripts/eval_grounding.py`, `docs/anexos/eval-grounding-2026-10-09.md`):
  `gpt-realtime-2.1` en vivo, **0 alucinaciones en 20 casos**, 5/5 cifras doradas, 10/10 rechazos
  fuera de alcance. La corrección «no, dije Melgar» fallaba: `correct_context` pasa a `field` + `value`.
- **Latencia:** muletilla «Un momento.», herramienta antes del aviso de IA, respuesta en una frase;
  `VOICE_OPENAI_MODEL` y VAD configurables; conexión caliente y precarga de los agregados probables;
  dos intentos de 3,5 s + 2 s; 4xx intermitente reintentable. Banco `scripts/bench_models.py`.
- G1: `requirements.txt` mínimo (63 MB), `vercel.json` (`iad1`), Dockerfile de respaldo; smoke
  `scripts/smoke_public.py` y sondas `tests/live/`.
- D-21 (avatar 3D VRM en el MVP) y dependencias del frontend registradas (R-10).

### Changed
- **R-26:** análisis de voz activo por defecto, con indicador visible e interruptor; se mantiene el
  aviso de IA mínimo (RETO-P1/P3, A-25). Riesgo de Ley 1581 registrado en `docs/10` §6.
- `docs/09` §6: la primera consulta de la sesión puede salir de la precarga `fresh`; solo
  «Reconsultar» fuerza en vivo.

### Verificado
- Smoke local 20/20 P0; 136 pruebas offline; 8 sondas en vivo; escaneo de secretos del historial
  (56 commits, todas las ramas): sin coincidencias.
- Banco de latencia (`scripts/bench_models.py`, n = 10): primer audio útil con consulta p50 **9,0 → 3,9 s**
  (OpenAI) y **13,4 → 4,2 s** (Gemini); p95 4,7 s y 6,9 s: **la meta de 4,0 s aún no se cumple**. Se
  mantienen `gpt-realtime-2.1`, `server_vad` y 500 ms (`docs/00` §6). Precarga ampliada a 10 agregados;
  `for_model` aclara que ante `invalid` la fuente sí respondió.
- Prueba en caliente: front de `main` (006d6c1) + este backend + `gpt-realtime-2.1` en Edge con
  micrófono simulado: brief en vivo, «Un momento.», `aggregate_ips` en vivo y «9.320»; 0 errores.

### Pendiente
- **A-21 sin verificar:** con voz sintética el modelo no distinguió tono tenso de calmado; falta
  una grabación humana real. Feedback a LangSmith (hoy: registro estructurado). Despliegue en
  Vercel (G1, D-15 abierta).

### Changed
- `docs/09` §2: plazo de conexión de 2 s → 4 s (la primera conexión midió 0,8–2,7 s).
- `docs/03`: `/analysis/utterance` pasa de multipart a JSON para no sumar `python-multipart` (R-10).

### Added
- **Contratos de Reto 01 (2026-10-09), solo documentación: sin código ni despliegue.**
  Especificación (`docs/07`), contrato de voz en vivo (`08`), datos en vivo de
  datos.gov.co (`09`), modelos, afecto y recuperación (`10`), despliegue (`11`), guía de
  trabajo para dos personas (`12`) y diferenciadores y backlog (`13`). `docs/00` registra
  D-09…D-19 y `AGENTS.md` las reglas R-22…R-31.
- `docs/sdd_ips/` (paquete de planeación generado por GPT) entra como **insumo**, con la
  reconciliación en `docs/07` §3; `docs/anexos/` conserva la evidencia de los spikes de voz
  y avatar.
- Mediciones del 2026-10-09 contra la API real: SODA3 anónimo 200 en 0,57 s; 41.427 filas,
  9.320 IPS, 10.921 códigos de sede; nivel de atención vacío en el 89% de las IPS.

### Changed
- **R-04 (alcance, excepción acotada D-14), R-06, R-07, R-08 (retirada) y R-10
  reformuladas; D-03 reemplazada por D-10.** D-02, D-05 y D-06 siguen vigentes para la base
  genérica pero **no aplican a Reto 01**, que no usa base de datos, RAG, embeddings ni cédula.
- `docs/01` (§11), `03`, `05` y `06` añaden la app de voz, su API, sus pruebas y el flujo de
  dos personas con `main` como rama de integración y de producción (D-19).

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
- **R-05 alineada con el código:** las variables de entorno se leen solo en
  `src/config.py` (antes decía "solo en `integrations/`", que el código nunca
  cumplió). Verificado: ningún otro módulo de `src/` ni `scripts/` lee el entorno.
- Los diagramas de `archify` viven en `docs/diagrams/` dentro del repo; se
  abandona `../HackatonKognia-docs/`.

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
