# Anexo — Varios evaluadores a la vez (2026-10-09)

**Pregunta:** si varios jurados usan la demo pública al mismo tiempo, ¿cada uno tiene su propia
sesión, su propia conversación y sus propias respuestas? **Respuesta corta: sí.** No encontramos
ninguna fuga entre usuarios. Hay dos hallazgos menores (no cruzan usuarios) y un límite real: la
voz clonada de Cartesia a partir de 4 voces simultáneas.

- Backend: `feat/reto-01-api` en `55734fd`, levantado aparte en `127.0.0.1:8200`
  (`uvicorn api.app_voice:app --app-dir src`), con las claves reales del `.env`.
- Script re-ejecutable: [`scripts/load_evaluators.py`](../../scripts/load_evaluators.py).
- Corridas: 5 (run1–run5). Las cifras de abajo son de **run5** (la última completa), salvo
  cuando se indica otra. Ningún token ni secreto se imprimió (solo longitudes).

```bash
# Local, todo (incluye ~3 conversaciones OpenAI y 6 síntesis Cartesia: centavos y ~1000 créditos)
python scripts/load_evaluators.py --base-url http://127.0.0.1:8200 --users 8 --engines --cartesia --cartesia-n 6
# Contra la URL pública: barato y sin dañar a nadie (no usar --ip-exhaust en producción)
python scripts/load_evaluators.py --base-url https://<api> --users 8 --no-engines --no-cartesia
```

## 1. Resultados

| # | Prueba | Resultado | Números |
|---|---|---|---|
| 1a | Aislamiento HTTP: 8 evaluadores en paralelo, mismo IP; cada uno: `/sessions` → `/dataset/brief` → 5 herramientas con filtros distintos (todos usan los mismos `tool_call_id` `call_1`…`call_6`) → `/analysis/utterance` → `/verify/answer` | **PASS** | 8 tokens distintos (120 caracteres); 0 respuestas con `tool_call_id`, `turn_id`, filtros, `site_key` o `state_version` de otro; 0 diferencias contra una referencia secuencial (ola en vivo y ola desde caché). `call_1` devuelve el conteo de **su** departamento: 837, 597, 1270, 285, 193, 312, 288, 312 (Boyacá y Tolima empatan de verdad: la referencia da lo mismo) |
| 1b | Brief, analista y verificación por evaluador | **PASS** | 8/8 brief con 9.320 prestadores; 8/8 `affect.turn_id` propio; 8/8 `grounded=true` con su propio sobre |
| 1c | Token ajeno o adulterado | **PASS** | `sid` de B con firma de A → 401; token basura → 401; sin token → 401 |
| 1d | Idempotencia por sesión | **PASS** (con hallazgo H1) | Reintento del mismo `call_1` → mismo sobre y mismo `turn_id`. Entre usuarios no se comparte (la clave lleva el `sid`) |
| 1e | Latencia `/tools` en vivo, 1 vs 8 usuarios | **PASS** | 1 usuario: p50 238 ms, p95 935 ms. 8 usuarios: p50 290 ms, p95 1.025 ms (n = 50). Desde caché: p50 12 ms, p95 18 ms. En otras corridas el p95 con 8 usuarios llegó a 1,8–3,3 s (variación de datos.gov.co), siempre por debajo del plazo de 6 s |
| 2a | Límite de tasa: 8 evaluadores del mismo IP a ~1 req/s durante 20 s + 1 sesión abusiva (200 req en ~12 s) | **PASS** | Normales: 160 OK, **0 × 429**. Abusiva: 120 OK y 80 × 429 (corta exactamente en 120/min por sesión) |
| 2b | Abusivo que **rota sesiones** desde el mismo IP (`--ip-exhaust`, solo local; run3) | **Informativo** (hallazgo H2) | 14 sesiones, 1.610 peticiones en 27 s: 1.500 OK y 110 × 429; después, un evaluador **del mismo IP** recibe 429 (60 s); uno de otro IP, 200 |
| 3a | 5 credenciales OpenAI + 5 Gemini a la vez | **PASS** | 5/5 y 5/5, todas distintas (longitudes 35 y 76), 4,9–10,8 s en total. En run3 (justo después de 2b) 3 de 5 OpenAI y 4 de 4 Cartesia dieron 503 transitorio; no se reprodujo en 3 intentos posteriores (ver §3) |
| 3b | 3 conversaciones OpenAI Realtime simultáneas en modo texto (`voice_mode=cloned`), herramientas ejecutadas por `/tools` con el token de cada evaluador | **PASS** (3 de 3 corridas) | «¿Cuántos prestadores…?» → `aggregate_ips{provider_count}` → **9.320**; «¿Cuántas camas…?» → `capacity_sum{CAMAS}` → **97.036**; «¿Cuántas IPS públicas…?» → `provider_count{nature: Pública}` → **998**. Ninguna respuesta contiene la cifra de otra. 6,4–11,2 s por conversación (incluye conexión) |
| 4 | Voz clonada Cartesia: 4 y luego 6 tokens a la vez + 6 WebSockets sintetizando simultáneamente (~170 caracteres, `pcm_s16le` 24 kHz) | **PASS con límite** | 4 a la vez: 4/4, primer audio 266–442 ms. **6 a la vez: 6/6 terminan, pero 3 esperan en cola**: primer audio 325/348/426 ms vs **2.542/3.787/4.528 ms**. Ningún error: Cartesia encola, no rechaza |
| 5 | datos.gov.co con 8 usuarios | **PASS** | Ola en vivo (`force_live`): 42 consultas, 0 `TIMEOUT`/`RATE_LIMITED`/`SOURCE_REJECTED`, 0 `unavailable`. Ola normal: 40/40 consultas desde caché `fresh` (100 %), idénticas a lo traído en vivo |
| 6 | Despliegue en Vercel (varias instancias) | **PASS por razonamiento** | §2: nada se filtra entre usuarios; lo que se debilita es idempotencia y límite de tasa, por instancia |

## 2. Por qué no hay estado compartido entre usuarios (y qué pasa en Vercel)

En el servidor **no hay estado por usuario**, salvo dos estructuras, y las dos están indexadas por
la sesión:

- **Idempotencia** — `IpsToolService._done`, clave `(sid, tool_call_id, state_version)`
  (`src/services/ips/tools.py` L96, L141–143, L161–164). Dos jurados con el mismo `call_1` no
  comparten resultado (medido en 1a).
- **Límite de tasa** — `RateLimiter._hits`, claves `sid:<sid>` e `ip:<ip>`
  (`src/services/session_service.py` L69–88, `src/api/app_voice.py` L128–135).

Lo demás es compartido **a propósito y solo con datos públicos**:

- **Caché de datos.gov.co** — `SocrataClient._cache`, clave = la SoQL exacta
  (`src/integrations/datasets/socrata_client.py` L66, L105–120). La SoQL se arma desde argumentos
  validados (`soql.assert_safe`, `tools.py` L206–208); la misma SoQL da las mismas filas públicas.
  Las filas en caché se comparten como lista, pero ningún manejador las muta (solo se cortan o se
  leen, `tools.py` L320–322, L355, L397–412). Medido: 40 aciertos de caché idénticos a la
  referencia en vivo.
- **`app.state.health_cache`** (`app_voice.py` L142–154): estado público de la fuente.
- La conversación, el estado canónico y el historial viven en el **navegador**; cada llamada trae
  su `context` (`models/ips.py` L104–117) y el servidor no lo guarda.

**Vercel (cada instancia con su memoria, [11](../11-despliegue.md) §3):**

| Pieza | Si las peticiones de un jurado caen en instancias distintas | ¿Cruza usuarios? |
|---|---|---|
| Token de sesión | HMAC sin estado (`session_service.py` L53–66); vale en todas las instancias porque todas leen el mismo `SESSION_SIGNING_KEY` | No |
| Cursores de `search_ips` | Firmados con la misma clave (`tools.py` L286–304): válidos en cualquier instancia | No |
| Idempotencia | Por instancia: un reintento que cae en otra instancia vuelve a consultar; el resultado es el mismo (consulta determinista) | No |
| Límite de tasa | Por instancia: el límite real es 120/min × instancias calientes. Más débil, no cruza usuarios | No |
| Caché de datos | Por instancia: más consultas en vivo tras un arranque en frío; mismo resultado | No (solo datos públicos) |
| Tareas en segundo plano (`background`, `app_voice.py` L81–85) | En serverless pueden congelarse al terminar la respuesta: el precalentamiento puede no completarse. Solo afecta latencia | No |

Requisito: `SESSION_SIGNING_KEY` **igual** en producción para todas las instancias (lo es: variable
de entorno de Vercel). Si faltara, el arranque falla (`SessionService.__init__`), no se degrada.

## 3. Hallazgos

**H1 — Idempotencia sin nombre ni argumentos (menor, no cruza usuarios).** En la **misma** sesión,
el mismo `tool_call_id` con el mismo `state_version` pero **otra herramienta u otros argumentos**
devuelve el sobre anterior. Reproducción (1d): `call_1` con `department: Antioquia` → 837; luego,
con el mismo token, `call_1` con `department: Santander` → **837 y filtros de Antioquia**. Los
motores generan `call_id` únicos por sesión, así que en la práctica no ocurre; pero un cliente con
ids reutilizados (p. ej. tras renovar la sesión del motor, [08](../08-contrato-voz-en-vivo.md) §7)
recibiría una respuesta ajena a su pregunta. Diff mínimo propuesto (`src/services/ips/tools.py`):

```diff
-        key = (scope, req.tool_call_id, req.context.state_version)
+        args_fp = hashlib.sha256(json.dumps(req.args, sort_keys=True, default=str).encode()).hexdigest()[:16]
+        key = (scope, name, req.tool_call_id, req.context.state_version, args_fp)
```

y `self._done: OrderedDict[tuple[str, str, str, int, str], ToolEnvelope]`.

**H2 — `POST /sessions` sin límite: un abusivo de la misma red puede dejar en 429 a todos
(bajo riesgo).** El límite por sesión (120/min) se esquiva pidiendo sesiones nuevas; entonces
manda el cupo por IP (1.500/min), que comparten todos los jurados de la red del evento. Reproducción
(2b, `--ip-exhaust`, run3): 14 sesiones × 115 peticiones a `/verify/answer` en 27 s → el cupo del
IP se agota y un evaluador legítimo del mismo IP recibe **429 durante 60 s**. Exige un ataque
deliberado de ~25 req/s desde dentro de la red; no hay fuga de datos. Diff mínimo propuesto
(`src/api/app_voice.py`), un tope de emisión por IP que reutiliza el limitador existente:

```diff
     @app.post("/sessions", status_code=201)
-    async def create_session(body: SessionCreateRequest | None = None,
+    async def create_session(request: Request, body: SessionCreateRequest | None = None,
                              c: VoiceContainer = Depends(container)) -> dict[str, str]:
+        fwd = request.headers.get("x-forwarded-for", "")
+        ip = fwd.split(",")[0].strip() or (request.client.host if request.client else "?")
+        wait = c.limiter.check(f"mint:{ip}")  # 120 sesiones/min por IP: sobra para un jurado
+        if wait is not None:
+            raise ApiError(429, "RATE_LIMITED", "Demasiadas sesiones.", True, {"Retry-After": str(int(wait))})
         token, expires_at = c.sessions.issue((body or SessionCreateRequest()).locale)
```

(Mitiga, no elimina: el remedio de fondo sería un límite por IP más fino o un captcha, fuera de
alcance antes del congelamiento.)

**H3 — `X-Forwarded-For` se toma tal cual (nota de despliegue).** `app_voice.py` L128–129 usa el
primer salto. Localmente cualquiera lo falsifica (el script lo usa para simular IPs). En Vercel la
plataforma fija esa cabecera con la IP real del cliente, según su documentación — **no verificado
hoy contra el despliegue**. En el plan B (contenedor detrás de un proxy que *añade* en vez de
sobrescribir) el límite por IP se podría esquivar. No cruza usuarios.

**H4 — 503 transitorios al emitir credenciales (no reproducido).** En run3, inmediatamente después
de la prueba 2b (1.610 peticiones locales), 3 de 5 `POST /realtime/session` (OpenAI) dieron
`ENGINE_CONNECT_FAILED` y 4 de 4 `POST /speech/session` dieron `SYNTH_UNAVAILABLE` (sin línea de
log de HTTP del proveedor, o sea excepción de red de `httpx`: tiempo agotado o conexión). En el
mismo intervalo el servidor registró 30 veces `dataset unavailable, serving stale cache` (precarga
en segundo plano). Tres reintentos posteriores (sonda aislada, run4, run5): 100 % OK. Lo atribuimos
a la red de este equipo, no al backend; la interfaz ya trata estos 503 como reintentables
([08](../08-contrato-voz-en-vivo.md) §12). Como endurecimiento opcional (no hecho): coalescer
consultas idénticas en vuelo en `SocrataClient.query` para que 8 precargas simultáneas al vencer
la caché de 60 s no lancen 8 veces la misma SoQL.

## 4. Límites encontrados

- **Cartesia (plan Pro, 3 síntesis concurrentes):** a partir de la 4.ª síntesis *realmente*
  simultánea, Cartesia **encola sin error**: el primer audio pasa de ~0,3 s a 2,5–4,5 s. Con 4 a la
  vez no se notó (266–442 ms) porque las síntesis cortas terminan y liberan cupo. Como no llega
  un error, **la degradación automática por error no se dispara**: la interfaz solo lo nota por
  latencia.
- **OpenAI Realtime:** 5 credenciales y 3 conversaciones simultáneas sin 429. No se probaron más.
- **Gemini Live:** 5 credenciales simultáneas sin 429; no se abrieron WebSockets de Gemini.
- **datos.gov.co:** 42 consultas en vivo en ~8 s con 8 usuarios, sin 429. La caché de 60 s absorbe
  el 100 % de las preguntas repetidas.

## 5. Recomendación para la demo

1. **Voz clonada: máximo 3 jurados hablando a la vez.** Si se espera más, que la interfaz degrade a
   la voz del motor cuando el primer audio de Cartesia tarde **> 1,5 s** (no solo ante error).
2. No hace falta cambiar nada para el aislamiento: es correcto con 8 jurados en la misma red.
3. Si da tiempo antes de las 14:30: aplicar el diff de H1 (2 líneas, sin riesgo). H2 es opcional.
4. Durante el jurado no correr `--ip-exhaust` contra producción (deja la red del evento en 429 60 s).
5. Correr el script contra la URL pública con `--no-engines --no-cartesia` en el calentamiento de
   las 15:25 (cuesta 0; verifica aislamiento, caché y límites en el despliegue real).

## 6. No verificado

- Contra el despliegue real de Vercel (instancias múltiples, arranque en frío, `X-Forwarded-For`).
- WebSockets de Gemini Live concurrentes; OpenAI con audio (solo modo texto); más de 3 conversaciones
  OpenAI o más de 6 síntesis Cartesia.
- Créditos de Cartesia restantes y si el comportamiento de cola cambia al agotarse.
- Carga sostenida (minutos) y renovación de sesión del motor durante la carga.
