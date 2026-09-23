# Arquitectura del proyecto — Kognia Voice Agent

Este documento explica **qué hace cada archivo y por qué existe**. Está escrito
para que alguien que llega nuevo entienda el sistema completo sin tener que leer
todo el código.

Última actualización: 2026-09-22 (versión 0.3.0).

---

## 1. Qué es esto, en una frase

Un agente conversacional genérico sobre **LangGraph**, expuesto por **FastAPI**,
que responde consultas usando documentos indexados en **PostgreSQL + pgvector**,
con usuarios identificados por cédula.

**No sabemos todavía cuál será el reto** (PQR o atención financiera, por voz o
video). Por eso el núcleo modela *capacidades genéricas* y toda la parte
específica del negocio entra como configuración. Ver AGENTS.md §0.

---

## 2. El mapa mental, antes del detalle

Imagina un empleado nuevo que atiende un chat:

| Pieza del sistema | Su equivalente humano |
|---|---|
| `services/graph/` | El empleado: piensa y decide qué hacer |
| `config/domains/*.yaml` | El manual de reglas sobre su escritorio |
| PostgreSQL + pgvector | El archivero que consulta antes de responder |
| El LLM (NVIDIA) | Su capacidad de leer y redactar |
| `api/` | El mostrador donde el cliente le habla |
| `integrations/` | Los cables que lo conectan al mundo real |

**La regla que sostiene todo el diseño:** el empleado sigue un procedimiento
fijo escrito por nosotros. El LLM redacta y clasifica, pero **nunca decide el
camino de la conversación**. Eso es AGENTS.md §8, y es la razón de que el grafo
esté construido a mano en vez de usar un agente ReAct prefabricado.

---

## 3. Las capas y su regla de dependencia

```
api/           ->  services/  ->  integrations/
                        \            /
                         \          /
                          models/  (transversal: todos pueden importarlo)
```

- `api/` **nunca** llama directo a `integrations/`. La única excepción
  documentada es `api/dependencies.py`, que es el *composition root*: su trabajo
  literal es ensamblar el objeto grafo.
- `services/` **nunca** importa psycopg, chromadb, NVIDIA ni FastAPI. Solo
  conoce los `Protocol` de `models/ports.py`.
- `models/` no tiene comportamiento: estructuras de datos y contratos.

Esto se puede verificar mecánicamente:

```bash
grep -rn "^from integrations\|^import integrations" src/services/ src/models/
# no debe devolver nada
```

---

## 4. Archivo por archivo

### 4.1 Raíz del repositorio

| Archivo | Rol |
|---|---|
| `AGENTS.md` | **Fuente única de verdad.** Reglas de arquitectura, stack, prohibiciones. Se lee antes de escribir código. |
| `CLAUDE.md` | Específico de Claude Code: MCP, plugins, skills. No reemplaza AGENTS.md. |
| `ARCHITECTURE.md` | Este documento. |
| `README.md` | Arranque rápido y comandos. |
| `CHANGELOG.md` | Historial de cambios por versión (exigido por AGENTS.md §7). |
| `docker-compose.yml` | Levanta PostgreSQL 17 + pgvector en el puerto **5433**. Puerto distinto al 5432 a propósito, para no tocar un Postgres nativo que ya exista. |
| `pyproject.toml` | Configuración de pytest (incluido `pythonpath = ["src"]`, sin el cual nada importa), ruff y mypy. |
| `requirements.txt` | Dependencias, agrupadas y comentadas con el porqué de cada grupo. |
| `.env.example` | Plantilla de variables. Se copia a `.env`, que está en `.gitignore`. |
| `Dockerfile` | Imagen de la aplicación para Azure Container Apps. |

### 4.2 `migrations/` — el esquema de la base

| Archivo | Rol |
|---|---|
| `001_init.sql` | Crea la extensión `vector` y las 6 tablas. **No se edita después de aplicado**; los cambios van en `002_...sql`. |

Se escribió SQL plano en vez de SQLAlchemy + Alembic a propósito: el esquema son
seis tablas y la prioridad es que cualquiera pueda leer el archivo y saber
exactamente cómo es la base, sin un ORM de por medio.

**Las tablas del checkpointer de LangGraph no están aquí** — las crea la propia
librería al arrancar, con `.setup()`.

### 4.3 `scripts/` — comandos operativos

| Archivo | Rol |
|---|---|
| `migrate.py` | Aplica las migraciones pendientes. Lleva registro en la tabla `schema_migrations`, así que es idempotente: correrlo dos veces no hace daño. Cada migración va en su propia transacción. |
| `ingest.py` | Indexa documentos en la base de conocimiento. Es el comando que se corre el día del evento apuntando a lo que nos entreguen. Soporta `.md`, `.txt`, `.csv`, `.pdf`. |
| `serve.py` | **Arranca el servidor. Úsalo en vez de invocar `uvicorn` directamente** — ver §4.4. |

### 4.4 `src/platform_compat.py` — el problema de Windows

Este archivo existe por un solo motivo, pero no es opcional.

**psycopg3 se niega a correr sobre el `ProactorEventLoop`**, que es el event
loop por defecto de Windows desde Python 3.8:

```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'
to run in async mode.
```

El síntoma es engañoso: el pool de conexiones simplemente **nunca termina de
abrir** y expira por timeout, mientras que una conexión síncrona a la misma
base funciona perfecto. Por eso `scripts/migrate.py` (síncrono) funcionaba y
todo lo async fallaba.

Y hay una segunda capa: **uvicorn 0.36+ construye su loop con un
`loop_factory`, que ignora la política del event loop.**

```python
# uvicorn/server.py
return asyncio_run(self.serve(sockets=sockets),
                   loop_factory=self.config.get_loop_factory())
```

Es decir, llamar a `asyncio.set_event_loop_policy(...)` antes de `uvicorn.run()`
**no sirve de nada**. La vía soportada es pasar la factory por la opción `loop`
de uvicorn, que acepta un import string — y eso es lo que hace `scripts/serve.py`:

```python
uvicorn.run(..., loop="platform_compat:new_selector_event_loop")
```

El módulo expone tres cosas:

| Función | Para qué |
|---|---|
| `ensure_psycopg_compatible_event_loop()` | Cambia la política. La llaman `tests/conftest.py` y `scripts/ingest.py`, que sí crean su loop vía `asyncio.run`. |
| `new_selector_event_loop()` | La factory que consume uvicorn. Funciona también para los subprocesos de `--reload`. |
| `assert_event_loop_is_usable()` | Se llama al arrancar la app. Si alguien corre `uvicorn api.main:app` a mano, falla de inmediato con un mensaje que explica qué hacer, en vez de colgarse en un timeout opaco. |

En Linux y macOS las tres son no-ops: el loop por defecto ya es compatible.

### 4.5 `src/config.py` — configuración centralizada

Único lugar donde se leen variables de entorno. Usa `pydantic-settings`, que
llena cada campo desde el entorno o desde `.env`, y valida los valores (un
`MODEL_PROVIDER=azuree` falla al arrancar, no en mitad de la demo).

Expone también `EMBEDDING_DIMENSIONS = 768`, que es la constante que debe
coincidir con la columna `document_chunks.embedding vector(768)`.

`database_url_safe` devuelve la URL con la contraseña enmascarada, para poder
mostrarla en `/health` y en errores sin filtrar credenciales.

### 4.6 `src/models/` — datos y contratos (capa transversal)

| Archivo | Rol |
|---|---|
| `ports.py` | **El archivo más importante del diseño.** Define los `Protocol` que `services/` usa para hablar con el mundo: `LLMPort`, `RetrievalPort`, `UserRepositoryPort`, `ConversationRepositoryPort`, y los aún no implementados `VoicePort` y `AvatarPort`. Ningún nombre de proveedor aparece aquí. |
| `auth.py` | `User`, `Session`, `Identification`, `Conversation`, `MessageRecord`. |
| `conversation.py` | `Utterance`, `AudioChunk`, `SpeechChunk`, `VisemeFrame`, `RouteDecision`, `TurnResult`. Los tipos de audio existen aunque no haya proveedor de voz: son el contrato que ese proveedor tendrá que cumplir. |
| `retrieval.py` | `Document`, `Chunk`, `RetrievedChunk`, `IngestionReport`. |
| `domain_config.py` | `DomainSpec`, `IntentSpec`, `FieldSpec`. La descripción declarativa de un dominio de negocio. |

Los puertos viven aquí y no en `services/` por una razón concreta: si vivieran
en `services/`, entonces `integrations/` tendría que importar hacia arriba y se
rompería la regla de dependencia.

### 4.7 `src/services/` — la lógica de negocio

#### `graph/` — el agente

| Archivo | Rol |
|---|---|
| `state.py` | `ConversationState`: lo que viaja entre nodos (mensajes, intención, datos recolectados, campos faltantes, ruta, contexto recuperado, número de turno). Ningún campo lleva nombre de un dominio de negocio. |
| `builder.py` | Ensambla y compila el grafo. Recibe LLM, retriever, dominio y checkpointer **por inyección** — por eso los mismos nodos corren contra Postgres en producción y contra memoria en los tests. |
| `edges.py` | Las transiciones. `after_route` es una **función pura** que lee `state["route"]` y nada más. Aquí no hay LLM, no hay I/O, no hay reloj. |
| `nodes/intake.py` | Recibe el turno: cuenta el turno y limpia el estado del turno anterior. |
| `nodes/classify_intent.py` | Mapea el mensaje a una intención del catálogo del YAML. Usa el LLM, pero **valida la respuesta contra el catálogo** — nunca propaga una intención inventada. |
| `nodes/collect_data.py` | Mira qué campos declarados faltan e intenta extraerlos de la conversación. |
| `nodes/route.py` | **Decide el camino, sin LLM.** Reglas en orden: intención marcada como escalamiento → faltan datos → límite de turnos → responder. |
| `nodes/retrieve_context.py` | Pide contexto al `RetrievalPort`. No sabe que detrás hay pgvector. |
| `nodes/respond.py` | Redacta. Dos de las tres ramas (pedir dato, escalar) son deterministas y no gastan una llamada al modelo. |

#### Servicios de aplicación

| Archivo | Rol |
|---|---|
| `domain_loader.py` | Carga un `DomainSpec` desde YAML. Único lugar que lee ese archivo. |
| `auth_service.py` | Identificación por cédula: normaliza el formato (`1.053.812.345` y `1053812345` son la misma persona), busca o crea el usuario, abre sesión, valida vencimiento. |
| `chat_service.py` | Orquesta un turno completo: resolver conversación → correr el grafo → persistir ambos mensajes. Vive aquí y no en el router porque decidir qué significa un turno es lógica de negocio. También impone que **nadie lea ni escriba en la conversación de otro**. |

### 4.8 `src/integrations/` — el mundo exterior

| Archivo | Rol |
|---|---|
| `db/pool.py` | Pool async de conexiones, uno por proceso. Registra el tipo `vector` de pgvector para que psycopg convierta listas de Python automáticamente. Se construye sin conectar (`open=False`) para que importar no toque la red. |
| `db/user_repository.py` | Todo el SQL de identidad. |
| `db/conversation_repository.py` | Todo el SQL de conversaciones e historial. Guarda el mensaje y mueve `updated_at` **en la misma transacción**. |
| `retrieval/pgvector_retriever.py` | Implementa `RetrievalPort` sobre pgvector. Usa el operador `<=>` (distancia coseno), que es para el que está construido el índice HNSW. Una transacción por documento: reingestar reemplaza atómicamente. |
| `retrieval/embeddings.py` | `HashingEmbedder` (determinista, offline, para tests) y `E5Embedder` (`multilingual-e5-base`, local). La interfaz es **asimétrica** (`embed_documents` / `embed_query`) porque E5 exige prefijos `passage:` y `query:`; olvidarlos degrada notablemente la recuperación. |
| `retrieval/loaders.py` | Un cargador por formato. Agregar un formato nuevo es una función y una entrada en un diccionario. |
| `llm/factory.py` | Único archivo que sabe qué proveedor responde. Los imports están dentro de cada rama para que elegir `fake` no exija tener instalado el SDK de NVIDIA. |
| `llm/fake_llm.py` | Modelo determinista que **lee el prompt y responde en la forma que el nodo espera** (clasificar, extraer, responder citando contexto). No es un mock que devuelve una cadena fija: permite ejercitar el grafo completo sin gastar un token. |
| `tools/` | Herramientas del agente (calculadora offline, búsqueda web opcional con Tavily). |
| `voice/README.md` | **Vacío a propósito.** AGENTS.md §8 prohíbe implementar un proveedor de voz mientras no se decida cuál. |
| `avatar/README.md` | **Vacío a propósito**, por la misma razón. |

### 4.9 `src/api/` — la capa HTTP

| Archivo | Rol |
|---|---|
| `main.py` | La app y su `lifespan`. **Nada se construye al importar**: el contenedor se arma al arrancar y se libera al apagar. Eso es lo que permite que los tests importen la app sin base de datos. |
| `dependencies.py` | El *composition root*. Abre el pool, prepara el checkpointer, arma el grafo y los servicios. También define `current_user`, la dependencia que valida el header `X-Session-Id`. |
| `routers/auth.py` | `POST /auth/identify` |
| `routers/chat.py` | `POST /chat` |
| `routers/conversations.py` | `GET/POST /conversations`, `GET /conversations/{id}/messages` |

### 4.10 `tests/`

| Ruta | Rol |
|---|---|
| `conftest.py` | Fixtures compartidas. **Ninguna** requiere credencial, red ni base de datos. |
| `doubles/` | Implementaciones en memoria de cada puerto. No son mocks que cuentan llamadas: respetan las mismas invariantes que la base (cédula única, cascada, `updated_at`), así que un test que pasa aquí es evidencia real. |
| `services/` | Enrutamiento, grafo completo, auth y chat. |
| `integrations/` | Cargadores, embeddings y ranking. |
| `api/` | Contrato HTTP, códigos de estado, y que nadie lea la conversación de otro. |
| `integration/` | **Requieren PostgreSQL vivo.** Se saltan solos si no hay base. Se corren con `pytest -m integration`. |

---

## 5. El flujo de una petición, paso a paso

```
POST /auth/identify {"cedula": "1.053.812.345"}
  │
  ├─ auth_service.normalize_cedula  -> "1053812345"
  ├─ users.find_by_cedula           -> None
  ├─ users.create                   -> INSERT INTO users
  ├─ users.create_session           -> INSERT INTO sessions
  └─ 200 {user_id, session_id, expires_at}

POST /chat  header X-Session-Id: <uuid>
  │
  ├─ current_user           valida sesión, vencimiento, revocación
  ├─ chat_service.send
  │   ├─ _resolve           obtiene o crea la conversación
  │   │                     (y verifica que sea del usuario)
  │   ├─ append_message     INSERT mensaje del usuario
  │   ├─ graph.ainvoke      config {thread_id}
  │   │   │
  │   │   ├─ intake              turn_count += 1
  │   │   ├─ classify_intent     LLM -> intención (validada contra el catálogo)
  │   │   ├─ collect_data        ¿faltan campos declarados?
  │   │   ├─ route               DECISIÓN DETERMINISTA, sin LLM
  │   │   │    ├─ ANSWER   -> retrieve_context -> respond
  │   │   │    ├─ COLLECT  -> respond (pregunta por el dato)
  │   │   │    └─ ESCALATE -> respond (mensaje del YAML)
  │   │   │
  │   │   └─ el checkpointer persiste el estado en PostgreSQL
  │   │
  │   └─ append_message     INSERT respuesta + intent + route + sources
  │
  └─ 200 TurnResult
```

---

## 6. Por qué la conversación se guarda en dos sitios

No es duplicación por descuido. Son dos preguntas distintas:

| | Checkpointer de LangGraph | Tabla `messages` |
|---|---|---|
| **Qué guarda** | Estado interno del grafo, serializado | Historial legible |
| **Para qué sirve** | Reanudar exactamente donde iba | Mostrar, auditar, hacer `JOIN` |
| **Quién crea las tablas** | LangGraph, con `.setup()` | Nuestra migración `001_init.sql` |
| **Consultable en SQL** | No, en la práctica | Sí |

---

## 7. Los puertos y su estado

| Puerto | Proveedor | Estado |
|---|---|---|
| `LLMPort` | NVIDIA NIM (respaldo: Azure/OpenAI) | Implementado |
| `RetrievalPort` | PostgreSQL + pgvector | Implementado |
| `UserRepositoryPort` | PostgreSQL | Implementado |
| `ConversationRepositoryPort` | PostgreSQL | Implementado |
| `VoicePort` | **Sin decidir** — ver AGENTS.md §1.1 | Declarado, sin implementar |
| `AvatarPort` | **Sin decidir** — ver AGENTS.md §1.2 | Declarado, sin implementar |

La migración de Chroma a pgvector fue la prueba de que los puertos estaban bien
definidos: se reemplazó el adaptador completo y **ningún nodo del grafo cambió**.

---

## 8. Advertencias importantes

### El LLM gratuito es lento y variable

Un turno que pasa por el RAG cuesta **dos llamadas** al modelo (`classify_intent`
y `respond`). En el tier gratuito de NVIDIA eso son **9-20 segundos** medidos,
con bastante varianza. Para un chat de texto es tolerable; **para el agente de
voz que queremos, no lo es** — habrá que atacarlo antes de esa fase.

Lo que ya se hizo: `NVIDIA_REASONING_EFFORT=low` bajó la mediana por llamada de
19.4s a 3.3s. Lo que queda por explorar: clasificar la intención localmente (sin
LLM) para eliminar una de las dos llamadas, o usar
`nvidia/nemotron-3-super-120b-a12b` (1.1s) con reintentos, tolerando sus 503.

### Al elegir modelo de NVIDIA, no confíes en el catálogo de la librería

`ChatNVIDIA.get_available_models()` devuelve una lista **desactualizada**: enumera
modelos que ya están en end-of-life y responden `410 Gone`. Nos pasó con
`meta/llama-3.3-70b-instruct`, que figuraba como disponible y estaba muerto.

La fuente de verdad es la API:

```bash
curl -H "Authorization: Bearer $NVIDIA_API_KEY" \
     https://integrate.api.nvidia.com/v1/models
```

Y aun así, estar en esa lista no garantiza que responda: de 11 candidatos
probados, 4 dieron timeout y 4 dieron 404. **Hay que probar antes de elegir.**

### La autenticación no es autenticación

La identificación por cédula **no verifica nada**. Cualquiera que conozca una
cédula obtiene una sesión válida para esa persona. Fue una decisión consciente
de alcance para la demo. **No expongas datos sensibles detrás de esto** sin
agregar antes una verificación de credencial real (contraseña con hash, o un
proveedor de identidad).

### La dimensión del embedding está clavada en el esquema

`document_chunks.embedding` es `vector(768)`, que corresponde a
`multilingual-e5-base`. Cambiar de modelo a uno de otra dimensión exige una
migración nueva y reindexar todo. `E5Embedder` valida esto al arrancar y falla
con un mensaje claro en vez de dejar que Postgres rechace cada inserción.

### El modelo `fake` no razona

Clasifica por solapamiento de palabras y, al responder, cita el contexto
recuperado. Es una herramienta de diagnóstico: si la respuesta repite el corpus,
la recuperación funcionó. No es representativo de la calidad real.

### `EMBEDDING_PROVIDER=fake` no es semántico

Es una bolsa de palabras con hashing. Encuentra documentos que comparten
vocabulario, no que comparten significado. Para calidad real, `local`.

---

## 9. Comandos

```bash
# Levantar la base
docker compose up -d
python -m scripts.migrate

# Indexar documentos
python -m scripts.ingest --path docs/faq_demo --reset

# Pruebas
pytest                  # 55 tests, sin red ni Docker
pytest -m integration   # 16 tests contra PostgreSQL real

# Servidor  (NO uses uvicorn directamente en Windows, ver 4.4)
python -m scripts.serve
python -m scripts.serve --reload --port 8080
```

---

## 10. Qué hay que hacer el día del reto

1. **Dominio:** escribir `config/domains/<reto>.yaml` con el catálogo de
   intenciones y el esquema de campos. Apuntar `DOMAIN_CONFIG_PATH` ahí.
2. **Conocimiento:** `python -m scripts.ingest --path <carpeta> --reset`.
3. **Modelo:** `MODEL_PROVIDER=nvidia` con la API key en `.env`.
4. **Embeddings:** `EMBEDDING_PROVIDER=local`.
5. **Voz/avatar:** implementar el adaptador en `integrations/voice/` o
   `integrations/avatar/` — y **solo** ahí.

Borrar `config/domains/faq_demo.yaml` y `docs/faq_demo/` cuando el dominio real
esté listo: son desechables por diseño (AGENTS.md §4).
