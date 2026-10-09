# Guía de la API — para quien construye el frontend

Todo lo necesario para hablar con el agente desde el panel Astro. La referencia
interactiva está en **http://localhost:8000/docs** (Swagger) y el contrato en
bruto en **http://localhost:8000/openapi.json**. Este documento explica lo que
Swagger no dice: en qué orden llamar, qué significa cada campo y qué hacer con
cada error.

## El flujo, en tres llamadas

```
POST /users          (una sola vez por persona)
      │
POST /auth/login     → guarda session_id
      │
POST /chat           header X-Session-Id: <session_id>
      │                primer turno: SIN conversation_id
      │                → guarda conversation_id
      ▼
POST /chat           mismo header + conversation_id guardado
      ...            (así el agente recuerda los turnos anteriores)
```

## Reglas generales

- **Formato:** JSON de entrada y de salida.
- **Sesión:** todas las rutas, salvo `/health`, `/users` y `/auth/login`, exigen
  el header `X-Session-Id` con el `session_id` del login. La sesión dura
  12 horas (`SESSION_TTL_HOURS`). Cuando vence, la API responde 401: vuelve a
  hacer login.
- **Errores:** siempre llegan como `{"detail": "<explicación en español>"}`,
  salvo el 422 de validación de FastAPI, que trae una lista (ver abajo).
- **Tiempos:** un turno de chat tarda 1 a 3.5 s, porque llama a Gemini. Muestra
  un indicador de "escribiendo".
- **No es autenticación real:** cualquiera que conozca una cédula registrada
  puede iniciar sesión con ella. No hay contraseña (D-06, [01-arquitectura.md](01-arquitectura.md) §8).

## Endpoints

### `GET /health` — ¿está viva la app?

El nombre es una convención de la industria, no un estándar formal. Kubernetes,
Azure Container Apps y los balanceadores consultan una ruta así cada pocos
segundos para saber si reiniciar el contenedor o enviarle tráfico.

| Campo | Qué significa |
|---|---|
| `status` | `ok` si todo funciona; `degraded` si la API vive pero la base no responde; `starting` mientras arranca |
| `llm_model`, `embedding_model` | Modelos en uso |
| `domain`, `intents` | Dominio cargado y sus intenciones |
| `database` | `ok` o el tipo de error |
| `indexed_chunks` | Fragmentos de documentos disponibles para el RAG. Si es 0, el agente no tiene conocimiento: correr `python -m scripts.seed` |

### `POST /users` — crear una persona

```json
{"cedula": "1053812345", "display_name": "Ana"}
```

- `cedula`: 6 a 10 dígitos. Se aceptan puntos, espacios y guiones
  (`1.053.812.345`); se guardan sin ellos.
- `display_name`: el nombre con el que el agente llamará a la persona.

| Código | Significa | Qué hacer |
|---|---|---|
| 201 | Creada. Devuelve `id`, `cedula`, `display_name`, `created_at` | Pasar al login |
| 409 | Ya existe esa cédula | Hacer login directamente |
| 422 | Cédula con formato inválido o campo vacío | Mostrar el `detail` junto al campo |

### `POST /auth/login` — iniciar sesión

```json
{"cedula": "1000000001"}
```

| Código | Significa | Qué hacer |
|---|---|---|
| 200 | Devuelve `session_id`, `user_id`, `cedula`, `display_name`, `expires_at` | **Guardar `session_id`** y enviarlo en cada llamada siguiente |
| 404 | La cédula no está registrada | Ofrecer el registro (`POST /users`) |
| 422 | Formato de cédula inválido | Mostrar el `detail` |

Usuarios del seed: `1000000001` (Ana Demo) y `1000000002` (Beto Demo).

### `POST /chat` — un turno de conversación

Header obligatorio: `X-Session-Id: <session_id>`.

```json
{"message": "a que hora puedo ir el fin de semana?"}
```

| Campo | Qué es |
|---|---|
| `message` | Lo que escribió o dijo la persona. No puede ir vacío |
| `conversation_id` | **Omitir en el primer turno.** En los siguientes, el que devolvió el primer turno. Un UUID inventado da 404 |

Respuesta 200:

| Campo | Qué significa | Uso en la interfaz |
|---|---|---|
| `reply` | La respuesta del agente | El texto que se muestra (o que se pasará a voz) |
| `conversation_id` | La conversación a la que pertenece el turno | **Guardarlo** para el siguiente turno y para el historial |
| `route` | Qué decidió el grafo: `answer`, `collect` o `escalate` | Ver la tabla de abajo |
| `intent` | La intención que detectó el agente (`horario`, `canales`, etc.) | Opcional: etiqueta o analítica |
| `missing_fields` | Datos que el agente está pidiendo (p. ej. `["numero_radicado"]`) | Si no está vacío, el siguiente mensaje de la persona debería traer ese dato |
| `sources` | Documentos que se consultaron para responder | Opcional: mostrar "fuentes" |
| `thread_id` | Clave interna de la memoria de LangGraph | Ignorar: el frontend no lo necesita |

Qué significa cada `route`:

| `route` | Qué pasó | Sugerencia de interfaz |
|---|---|---|
| `answer` | Buscó en los documentos y Gemini redactó la respuesta | Mostrar la respuesta normal |
| `collect` | Falta un dato obligatorio; `reply` lo pide | Resaltar que el agente espera un dato |
| `escalate` | El caso necesita una persona (p. ej. "esto es un fraude") | Mostrar un aviso de "te transferimos con un asesor" |

Errores:

| Código | Significa | Qué hacer |
|---|---|---|
| 401 | Falta `X-Session-Id`, no es un UUID o la sesión venció | Volver al login |
| 403 | El `conversation_id` es de otra persona | Empezar una conversación nueva (sin `conversation_id`) |
| 404 | No existe ese `conversation_id` | Omitirlo para empezar una nueva |
| 422 | `message` vacío o `conversation_id` que no es UUID | Validar antes de enviar |
| 502 | Gemini falló | Reintentar; si persiste, avisar |
| 503 | Cuota de Gemini agotada, o la app aún arranca | Esperar los segundos del header `Retry-After` y reintentar |

### `GET /conversations` — mis conversaciones

Lista las conversaciones de la persona de la sesión, primero las que tuvieron
actividad más reciente. Sirve para un panel lateral de "conversaciones anteriores".
401 si la sesión no es válida.

### `POST /conversations` — crear una conversación vacía

Opcional: `POST /chat` sin `conversation_id` ya crea una. Úsalo solo si la
interfaz necesita el `id` antes del primer mensaje. Devuelve 201.

### `GET /conversations/{conversation_id}/messages` — historial

Todos los turnos de una conversación, en orden. Cada mensaje trae `role`
(`user` o `agent`), `content` y, en los del agente, `intent`, `route` y
`sources`. Sirve para repintar el chat al recargar la página.
Errores: 401, 403 (es de otra persona) y 404 (no existe).

## El 422 de validación

Cuando el cuerpo no cumple el esquema, FastAPI responde así:

```json
{"detail": [{"loc": ["body", "message"], "msg": "String should have at least 1 character", "type": "string_too_short"}]}
```

`loc` indica el campo con problema. Es el único error cuyo `detail` es una
lista y no un texto.

## Pendiente antes de conectar el frontend

- **CORS no está configurado.** Si el panel Astro corre en otro origen (por
  ejemplo `http://localhost:4321`), el navegador bloqueará las llamadas. Hay que
  agregar `CORSMiddleware` en `src/api/main.py` con los orígenes permitidos,
  y esa decisión aún no está tomada.
- **Tipos para TypeScript:** se pueden generar desde `/openapi.json` con
  herramientas como `openapi-typescript`, en vez de escribirlos a mano. Agregar
  esa dependencia al frontend es una decisión aparte (R-10).

---

## Reto 01 — API de voz (`api/app_voice.py`, versión `2026-10-09.1`)

Lo anterior describe la API de la base genérica (chat con cédula). La app de Reto 01 es
**solo HTTP**, sin base de datos ni cédula; el audio no pasa por ella
([08](08-contrato-voz-en-vivo.md) §1). Todas las rutas, salvo `POST /sessions` y
`GET /health`, exigen la cabecera `X-Session-Token`. CORS: solo el origen del frontend
(`ALLOWED_ORIGINS`). Cuerpos ≤ 4,5 MB (límite de Vercel).

| Método y ruta | Entrada | Salida | Detalle |
|---|---|---|---|
| `GET /health` | — | `status` (`ok`/`degraded`), `contract`, motores configurados, estado de la fuente (`ok`, `ms`), perfiles de LLM | No llama a proveedores de pago |
| `POST /sessions` | `locale` | 201 con `token` firmado y `expires_at` (2 h) | Anónima; sin cédula ni datos personales |
| `POST /realtime/session` | `engine`, `conversation_id`, `seed?`, `style?`, `locale`, `voice?` | `connect{url, protocols?, token, expires_at}`, `config`, `model`, `instructions_version`, `brief?` | [08](08-contrato-voz-en-vivo.md) §3 |
| `GET /dataset/brief` | — | Brief en vivo con preguntas sugeridas y `trace` | [09](09-datos-en-vivo-datos-gov-co.md) §8 |
| `POST /tools/{nombre}` | `tool_call_id`, `turn_id?`, `args`, `context` | Sobre de evidencia + `context_patch` | `nombre` ∈ `search_ips`, `get_ips_details`, `aggregate_ips`, `compare_ips`, `correct_context` ([09](09-datos-en-vivo-datos-gov-co.md) §4–§5) |
| `POST /analysis/utterance` | multipart: `meta` (JSON: texto, `t_start`/`t_end`, señales, historial de afecto, consentimiento) y `audio` WAV opcional | `AffectEstimate` + `StyleDecision` | [10](10-modelos-afecto-y-recuperacion.md) §6; plazo 3 s; el audio no se guarda |
| `POST /feedback` | `turn_id`, `kind` (`correction`/`tone`/`repeat`), `text?`, `state_version` | 202 | Va a LangSmith; sin base de datos |

Error de la API: `{"error":{"code":"…","message":"…","retryable":false},"trace_id":"uuid"}` con
401 sesión inválida o vencida · 403 recurso ajeno · 404 turno desconocido · 409 estado
obsoleto · 422 entrada inválida · 429 límite de tasa (con `Retry-After`) · 503 dependencia no
disponible. Los 422 se traducen a este formato; no cambian los de la API genérica. Los límites
de tasa por token e IP viven en memoria (R-28).
