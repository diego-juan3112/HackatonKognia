# Guía de la API — Kognia Voice Agent

La API del agente de voz (`src/api/app_voice.py`). En Vercel vive bajo `/api` (Vercel Services,
[11](11-despliegue.md)); en local, en la raíz. Referencia interactiva: `/docs` (Swagger) y
`/openapi.json`.

## API de voz (contrato `2026-10-09.2`)

Es la única API del repo: la API de chat de la base genérica se retiró con D-23 (queda en el
historial). La app de Reto 01 es **solo HTTP**, sin base de datos ni datos personales; el audio no pasa por ella
([08](08-contrato-voz-en-vivo.md) §1). Todas las rutas, salvo `POST /sessions` y
`GET /health`, exigen la cabecera `X-Session-Token`. CORS: solo el origen del frontend
(`ALLOWED_ORIGINS`). Cuerpos ≤ 4,5 MB (límite de Vercel).

| Método y ruta | Entrada | Salida | Detalle |
|---|---|---|---|
| `GET /health` | — | `status` (`ok`/`degraded`), `contract`, `engines` configurados, `voice_modes` (`["engine"]` o `["engine","cloned"]`), `default_voice_mode` (`cloned` si hay síntesis, D-22), `cloned_voice_engines` (`["openai"]`), estado de la fuente (`ok`, `ms`), perfiles de LLM | No llama a proveedores de pago |
| `POST /sessions` | `locale` | 201 con `token` firmado y `expires_at` (2 h) | Anónima; sin documento de identidad ni datos personales |
| `POST /realtime/session` | `engine`, `conversation_id`, `seed?`, `style?`, `locale`, `voice?`, `voice_mode?` (`engine` por omisión) | `contract`, `engine`, `model`, `connect{url, protocols?, token, expires_at}`, `config{audio, voice, voice_mode, turn_detection}`, `instructions_version`, `brief?` | [08](08-contrato-voz-en-vivo.md) §3; `config.voice_mode` es el **efectivo** (`cloned` con Gemini vuelve `engine`) |
| `POST /speech/session` | `conversation_id` | `contract`, `synth`, `model`, `connect{url, token, expires_at}`, `config{audio{encoding, sample_rate}, voice_id, language, timestamps}`, `voice_label` | Solo voz clonada ([08](08-contrato-voz-en-vivo.md) §15.3); token de 600 s con alcance `tts`; 503 `SYNTH_UNAVAILABLE` sin clave o con el proveedor caído |
| `GET /dataset/brief` | — | Brief en vivo con preguntas sugeridas y `trace` | [09](09-datos-en-vivo-datos-gov-co.md) §8 |
| `POST /tools/{nombre}` | `tool_call_id`, `turn_id?`, `args`, `context` | Sobre de evidencia + `context_patch` | `nombre` ∈ `search_ips`, `get_ips_details`, `aggregate_ips`, `compare_ips`, `correct_context` ([09](09-datos-en-vivo-datos-gov-co.md) §4–§5) |
| `POST /analysis/utterance` | JSON: `turn_id`, `state_version`, `text`, `t_start?`/`t_end?`, `signals?`, `affect_history?` (≤ 3), `tone_preference?`, `current_style?`, `turn_index`, `voice_consent`, `audio_wav_b64?` (WAV ≤ 30 s, solo con consentimiento) | `{affect: AffectEstimate, style: StyleDecision, ms}` | [10](10-modelos-afecto-y-recuperacion.md) §6; plazo 3 s; el audio no se guarda. **JSON y no multipart** (contrato `.2`): multipart exigiría `python-multipart`, una dependencia nueva (R-10); 30 s de WAV en base64 ≈ 1,3 MB, bajo el límite de 4,5 MB |
| `POST /verify/answer` | `turn_id`, `text` (lo que dijo el agente), `tool_results` (≤ 10 sobres del turno) | `grounded`, `numbers`, `unsupported`, `checked` | Verificador de cifras determinista (sin LLM): toda cifra ≥ 10 debe estar en la evidencia del turno; la interfaz marca «cifra no verificada». No parsea números en palabras |
| `POST /feedback` | `turn_id`, `kind` (`correction`/`tone`/`repeat`), `text?`, `state_version` | 202 | Va a LangSmith; sin base de datos |

Error de la API: `{"error":{"code":"…","message":"…","retryable":false},"trace_id":"uuid"}` con
401 sesión inválida o vencida · 403 recurso ajeno · 404 turno desconocido · 409 estado
obsoleto · 422 entrada inválida · 429 límite de tasa (con `Retry-After`) · 503 dependencia no
disponible. Los 422 se traducen a este formato; no cambian los de la API genérica. Los límites
de tasa por token e IP viven en memoria (R-28).
