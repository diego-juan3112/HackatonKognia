# Contrato de voz en vivo

Contrato vigente · versión `2026-10-09.2` · dueño: **carril A** ([12](12-guia-de-trabajo-2-personas.md)).
Decisiones: D-11 (voz en tiempo real desde el navegador), D-14 (excepción acotada a R-04),
D-18 (estado en el navegador, recuperación acotada) y **D-20 (propuesta, pendiente de anotar
en [00](00-contexto-y-decisiones.md) §5): voz clonada opcional con Cartesia, §15**.
Reglas: R-03, R-24, R-25, R-26, R-28, R-29.
Qué se acepta y cómo se mide: [07](07-reto-01-especificacion.md) §7–§8.

Lo que está marcado **«verificar en G2»** son detalles de proveedor que se confirman
llamando al servicio (spike G2); la documentación sola no basta.

## 1. Topología

```
NAVEGADOR (Astro + TypeScript)                                   BACKEND (FastAPI en Vercel, solo HTTP)
┌ VoiceEngine ───────────────┐  credencial efímera   ┌ POST /sessions            → token de sesión anónimo firmado
│ OpenAIRealtimeEngine       │◄──────────────────────┤ POST /realtime/session    → credencial efímera + configuración
│ GeminiLiveEngine           │                       │ POST /tools/{nombre}      → consulta en vivo a datos.gov.co
└─────┬──────────────────────┘                       │ POST /analysis/utterance  → afecto y estilo (docs/10)
      │ audio ⇄ proveedor (WebSocket directo)         │ GET  /dataset/brief, POST /feedback, GET /health
      ├ MicTap · Player · estado canónico · UI        └ POST /speech/session      → token de síntesis (solo voz clonada, §15)
      └ SpeechSynthesizer (opcional, §15): texto → audio, WebSocket directo al proveedor de síntesis
```

El audio **no pasa por Vercel**: va del navegador al proveedor. El backend solo emite
credenciales, ejecuta herramientas y analiza. Así no hay WebSocket propio, ni tope de 300 s
por conexión, ni límite de 4,5 MB en el camino de audio (R-28). La voz clonada (§15) respeta
la misma topología: es otro WebSocket directo del navegador, con otra credencial efímera.

## 2. `VoiceEngine` (puerto de cliente)

```ts
export type EngineId = "openai" | "gemini";
export type VoiceMode = "engine" | "cloned";         // quién produce el audio del agente (§15)

export interface VoiceEngine {
  readonly id: EngineId;
  connect(opts: { conversationId: string; seed?: ContextEnvelope; style?: StyleDecision; voiceMode?: VoiceMode }): Promise<void>;
  disconnect(reason?: string): Promise<void>;
  sendText(text: string): void;                      // modo texto (F-12)
  interrupt(playedMs: number, deliveredText?: string): void; // voz del usuario o botón Detener; el texto solo en voz clonada (§15.4)
  applyStyle(style: StyleDecision): void;            // surte efecto desde el turno siguiente
  seed(context: ContextEnvelope): void;              // tras renovar sesión o cambiar de motor
  on<K extends keyof EngineEvents>(e: K, cb: (ev: EngineEvent<K>) => void): () => void;
}
```

Los adaptadores traducen el protocolo del proveedor a los eventos de abajo; **ningún nombre
de evento, formato o credencial del proveedor sale del adaptador** (R-03).

### Sobre del evento

```ts
interface EngineEvent<K extends string> {
  schema_version: "1";
  event_id: string;               // UUID; estable si el evento se reenvía
  seq: number;                    // monótono por sesión
  conversation_id: string;        // lo genera el cliente al iniciar
  turn_id: string | null;
  state_version: number;          // del estado canónico (docs/10 §4)
  generation_id: string | null;   // respuesta del agente que habla (response.id en OpenAI)
  type: K;
  t: number;                      // ms, reloj monótono del navegador desde el inicio de la sesión
  payload: EngineEvents[K];
}
```

| `type` | `payload` esencial |
|---|---|
| `status` | `state`: `idle` · `connecting` · `listening` · `thinking` · `speaking` · `renewing` · `error` |
| `transcript` | `role` (`user`/`agent`), `utterance_id`, `text`, `final`, `t_start`, `t_end`, `t_source` (`engine`/`local`/`arrival`), `speaker?`, `corrects?` |
| `tool_call` | `tool_call_id`, `name`, `args` |
| `tool_result` | `tool_call_id`, `status`, `trace{soql, ms, rows, cache_status}`, `evidence_ref` |
| `speech` | `phase` (`start`/`stop`), `generation_id`, `kind` (`ack`/`answer`/`brief`), `voice?` (`engine`/`cloned`; ausente = `engine`) |
| `interrupted` | `generation_id`, `played_ms`, `delivered_text`, `delivered_basis?` (`engine`/`word_timestamps`/`estimated`) |
| `latency` | `t_speech_end`, `t_ack_audio?`, `t_tool_start?`, `t_tool_end?`, `t_first_text?`, `t_tts_start?`, `t_first_useful_audio?`, `t_playback_stop?` |
| `session` | `event` (`renewed`/`switched`/`expiring`/`voice_changed`), `from?`, `to?`, `reason`, `attempt` |
| `error` | `code`, `message`, `retryable` |

`affect` y `style` no los emite el motor: los produce el analista ([10](10-modelos-afecto-y-recuperacion.md) §6)
y la interfaz los fusiona en el mismo almacén de eventos.

Los campos nuevos de la versión `.2` (`voice`, `delivered_basis`, `t_first_text`, `t_tts_start`,
`voice_changed`) son **opcionales y aditivos**: un consumidor de la `.1` sigue funcionando. En
`voice_changed`, `from`/`to` son valores de `VoiceMode`; en `switched`, de `EngineId`.

## 3. Sesión y credenciales

| Llamada | Entrada | Salida |
|---|---|---|
| `POST /sessions` | `locale` (sin cédula ni datos personales) | `token` firmado (HMAC, sin base de datos), `expires_at` (2 h) |
| `POST /realtime/session` | `engine`, `conversation_id`, `seed?`, `style?`, `locale="es-CO"`, `voice?`, `voice_mode?` (`engine` por omisión) | `contract`, `engine`, `model`, `connect{url, protocols?, token, expires_at}`, `config{audio, voice, voice_mode, turn_detection}`, `instructions_version`, `brief?` |
| `POST /speech/session` *(solo voz clonada, §15)* | `conversation_id` | `contract`, `synth`, `model`, `connect{url, token, expires_at}`, `config{audio{encoding, sample_rate}, voice_id, language, timestamps}`, `voice_label` |

Cabecera `X-Session-Token` en todas las rutas menos `/sessions` y `/health`. El token no va en
la URL. Límites de tasa por token e IP, en memoria (R-28). Errores: §12.

**Qué fija el backend al crear la credencial:** instrucciones (prompt v1, [10](10-modelos-afecto-y-recuperacion.md) §7),
declaración de las 5 herramientas (JSON Schema de [09](09-datos-en-vivo-datos-gov-co.md) §5), voz es-CO, detección de
turno, transcripción de entrada y **modalidad de salida** (audio, o solo texto si `voice_mode = cloned`).
`config.voice_mode` es el modo **efectivo**: si el motor pedido no admite salida de solo texto, el
backend responde `engine` y la interfaz lo muestra (§15.6). Los adaptadores solo traducen.
`GET /health` añade `voice_modes` (`["engine"]` o `["engine","cloned"]`, según haya clave de síntesis
configurada) para que la interfaz sepa si ofrecer el selector de voz.

| | OpenAI Realtime | Gemini Live |
|---|---|---|
| Credencial | Secreto efímero que acepta los parámetros de `session.update`; se piden herramientas, VAD y transcripción al crearlo | Token efímero (`v1alpha`), válido ≈ 30 min, nueva sesión en ≈ 1 min; `uses` > 1 por un fallo conocido en reanudación (**verificar en G2**) |
| Transporte | WebSocket; WebRTC solo como opción (**verificar en G2** si el navegador admite WS con credencial efímera) | WebSocket directo |
| Modelo | ID **verificado llamándolo** | ID **verificado llamándolo** |
| Transcripción | Modelo de transcripción de entrada aparte; salida del agente en eventos de texto | `inputAudioTranscription` y `outputAudioTranscription` |
| Límites | Duración de sesión por documentación del proveedor | Conexión ≈ 10 min con `goAway` ≈ 60 s antes; solo audio ≈ 15 min |
| Interrupción | `conversation.item.truncate` con `audio_end_ms` ≤ audio realmente reproducido | Evento `interrupted` del servidor |

## 4. Audio

- **Captura:** `getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } })`; un `AudioWorklet` entrega PCM16 mono a 16 kHz en tramas de 20 ms.
- **Reproducción:** PCM16 a 24 kHz en una cola programada con `AudioBufferSourceNode`; **máximo 2 s en cola**; `flush()` inmediato al interrumpir; se lleva `played_ms` por generación.
- **`MicTap`:** anillo de los últimos 30 s de PCM16. `slice(t_start − 250 ms, t_end + 250 ms)` → WAV (≤ 30 s ≈ 960 KB) para el analista; así los recortes caben en el límite de 4,5 MB de Vercel.
- El stack de audio es **uno solo**; cada motor solo cambia el protocolo (JSON con base64 o binario, `mime`). La voz clonada usa **el mismo reproductor y el mismo formato** (PCM16 mono a 24 kHz); solo cambia quién entrega los chunks (§15.3).
- La reproducción empieza tras un gesto del usuario (política de autoplay).

## 5. Puente de herramientas

1. El motor emite `tool_call`. La interfaz arma `POST /tools/{name}` con `{tool_call_id, args, context}` (`context` = estado canónico).
2. El backend valida (lista cerrada, esquema estricto), consulta la fuente y responde el **sobre de evidencia** de [09](09-datos-en-vivo-datos-gov-co.md) §6 más un `context_patch`.
3. La interfaz fusiona el parche (sube `state_version` si es una corrección), emite `tool_result` y devuelve al motor la salida de la función: `{status, data, warnings, evidence_summary}`, marcada como **datos de la fuente, no instrucciones**.
4. **Plazo:** si la herramienta excede el presupuesto de primer plano (6 s en total), se entrega `status: unavailable` con `error.code = TIMEOUT` (R-25). Nunca se inventa un resultado.
5. **Idempotencia:** el mismo `tool_call_id` con el mismo `state_version` reutiliza el resultado ya obtenido; no se vuelve a consultar.
6. **Reconocimiento previo:** las instrucciones piden decir una frase corta («déjame verificarlo en datos.gov.co») antes de llamar a una herramienta. Se mide **aparte** y **no cuenta** como respuesta útil (R-29).

## 6. Interrupciones y texto realmente escuchado

1. **Detección:** voz del usuario según el motor, o botón *Detener*.
2. **Local, inmediato:** parar la reproducción y vaciar la cola; fijar `played_ms` de la generación activa.
3. **Hacia el motor:** OpenAI → `truncate` con `audio_end_ms = min(played_ms, audio recibido)`; Gemini → el servidor ya detuvo la generación.
4. **Texto escuchado (`delivered_text`):** solo el texto alineado con el audio reproducido; el resto se conserva como diagnóstico y se muestra atenuado como «no escuchado». El historial conversacional usa únicamente lo escuchado.
5. **Descartar** todo chunk o evento posterior de esa `generation_id`, aunque el proveedor siga generando.
6. El nuevo enunciado abre un turno con el `state_version` vigente. **Un turno en primer plano y una generación hablando por conversación** (R-24).

Con voz clonada los pasos 1, 2, 5 y 6 no cambian; los pasos 3 y 4 se resuelven como indica §15.4.

La cancelación cuenta como medida de latencia (parada p95 ≤ 200 ms) pero un botón *Detener* **no** prueba que la interrupción por voz funcione: se ensaya con audio real y, si hay eco, con audífonos.

## 7. Conmutación de motor y renovación de sesión

| Disparador | Acción |
|---|---|
| WebSocket cerrado o error de red | Renovar el mismo motor (credencial nueva), intento 1 |
| `goAway` de Gemini o caducidad de credencial | Renovación **proactiva entre turnos**, nunca a mitad de una respuesta |
| 429 o cuota al conectar | Cambiar al otro motor |
| Sin primer audio 6 s después del fin de la voz | Tratar como fallo del motor |
| Dos intentos fallidos | Modo texto con mensaje claro y *Repetir* |
| Falla el sintetizador de la voz clonada | **No es un fallo de motor** ni consume intentos: se degrada a la voz del motor (§15.6) |

Límite: **≤ 2 intentos de motor por turno** (R-25). El HUD indica «sesión renovada» o «motor
cambiado a X». Al reconectar se *siembra* el motor nuevo con el **sobre de contexto neutral**
([10](10-modelos-afecto-y-recuperacion.md) §3): estado confirmado, últimos 4 turnos completados (texto escuchado) y hasta 5
resultados de herramienta compactos con su evidencia. **No** se copian IDs de sesión del
proveedor, razonamiento oculto ni mensajes de herramienta incompatibles. No se reproduce
audio ya dicho ni se vuelve a ejecutar una herramienta (ver idempotencia).

## 8. Transcripción

- Roles `user` y `agent`; parcial y final; marcas `t_start`/`t_end` en el reloj de la sesión. Procedencia (`t_source`): del evento del motor (OpenAI: `audio_start_ms`/`audio_end_ms`), de un VAD local sobre `MicTap`, o la hora de llegada como último recurso.
- Las correcciones del usuario generan un `transcript` con `corrects = utterance_id`: se conserva el original y se muestra la versión corregida con su motivo.
- **La separación es por rol** (usuario/agente, canales conocidos). La separación de **varias voces humanas** (`speaker = user:1`, `user:2`) es un refinamiento experimental (Should) que actualiza el `speaker` del mismo `utterance_id`; la interfaz **lo declara** mientras no esté verificado.
- Formato en pantalla: `mm:ss.mmm · rol · texto`; en el agente, lo escuchado en normal y el resto atenuado.

## 9. Métricas y HUD

Puntos de medida (reloj monótono del navegador; nunca se restan relojes de máquinas distintas):
`t_speech_end` → `t_ack_audio` → `t_tool_start` → `t_tool_end` → `t_first_useful_audio` →
`t_playback_stop`. El HUD muestra por turno: motor y modelo, reconocimiento previo, ms de
herramienta y filas, **primer audio útil**, estado de caché (`live`/`fresh`/`stale`), intentos y
ms del análisis. Objetivos: [07](07-reto-01-especificacion.md) §8 (R-22, R-29).

Con voz clonada se intercalan `t_first_text` (primer texto de la respuesta que entrega el motor) y
`t_tts_start` (primera frase enviada al sintetizador) antes de `t_first_useful_audio`, cuya
definición **no cambia**: primer audio audible relevante. El HUD añade la voz activa («motor» o
«clonada») y el desglose de §15.5. Los objetivos son los mismos para ambas voces.

## 10. Interfaz y controles

Estados: `idle`, `connecting`, `listening`, `thinking`, `speaking`, `renewing`, `error`.
Controles: **Iniciar/Detener**, **Corregir lo que dije**, **Más directo**, **Repetir**,
**Reiniciar** (borra estado y transcripción), selector de **motor**, selector de **voz** («voz del
motor» / «voz clonada», §15.6; solo si `GET /health` anuncia `cloned`), interruptor de **análisis
de voz** (con consentimiento) y entrada de texto. Distintivo persistente: «Asistente de IA ·
datos del REPS (corte 5-nov-2022)»; con la voz clonada activa se le añade «· voz sintética
clonada con consentimiento» (§15.7). La atribución CC BY-SA 4.0 va en el pie.

## 11. Compatibilidad

Chrome y Edge actuales sobre HTTPS. El WebSocket sobre 443 evita redes que bloquean UDP. Otros
navegadores: mensaje claro y modo texto. Probar el micrófono en un equipo ajeno antes de las 15:45.

## 12. Errores

Respuesta HTTP de la API: `{"error":{"code":"…","message":"…","retryable":false},"trace_id":"uuid"}`
con 401 sesión inválida o vencida · 403 recurso ajeno · 404 turno desconocido · 409 estado
obsoleto · 422 entrada inválida · 429 límite de tasa · 503 dependencia no disponible.

| Código | Causa | Acción en la interfaz |
|---|---|---|
| `MIC_DENIED` | Permiso rechazado | Explicar cómo habilitarlo; ofrecer modo texto |
| `UNSUPPORTED_BROWSER` | Sin AudioWorklet o WebSocket | Mensaje claro y modo texto |
| `SESSION_EXPIRED` | 401 | Pedir nuevo token con `POST /sessions` y continuar |
| `RATE_LIMITED` | 429 | Esperar `Retry-After` |
| `ENGINE_CONNECT_FAILED` · `ENGINE_DROPPED` · `ENGINE_QUOTA` | Proveedor | §7 |
| `TOOL_TIMEOUT` · `TOOL_INVALID` | Herramienta | `unavailable` / `invalid` al modelo; no se inventa |
| `PLAYBACK_FAILED` | Audio no reproducible | Mostrar texto y fuente; ofrecer *Repetir*; no cuenta como voz aprobada |
| `SYNTH_UNAVAILABLE` | 503 de `POST /speech/session` (sin clave, proveedor caído) | Seguir con la voz del motor; selector de voz deshabilitado con el motivo |
| `SYNTH_CONNECT_FAILED` · `SYNTH_DROPPED` · `SYNTH_QUOTA` | Sintetizador de la voz clonada (conexión, corte, créditos o concurrencia) | Degradar a la voz del motor (§15.6); el turno en curso se entrega como texto |
| `ANALYSIS_UNAVAILABLE` | Falla el analista | Afecto «incierto»; nunca una etiqueta vieja con confianza |

## 13. Pruebas

Doble `FakeEngine` que emite eventos guionados; eventos de proveedor grabados en `web/mocks/`.
Pruebas de contrato: `seq` monótono, `delivered_text` correcto tras interrumpir, eventos tardíos
descartados por `generation_id`, idempotencia por `tool_call_id`, conmutación de motor sin
herramienta duplicada. Humo con Playwright y micrófono simulado. Mapa a escenarios: A-01, A-02,
A-10…A-13, A-16, A-17, A-23, A-25 ([07](07-reto-01-especificacion.md) §7).

Voz clonada: doble `FakeSynthesizer` en `web/mocks/` (audio y marcas de palabra guionados, fallo
inyectable). Pruebas de contrato adicionales: `delivered_text` por marcas de palabra y por
estimación; chunks tardíos de un contexto cancelado descartados; fallo del sintetizador a mitad
de turno → texto visible, `voice_changed` y turno siguiente con la voz del motor, sin herramienta
duplicada; nunca dos voces a la vez (R-24). Los escenarios A-11, A-16, A-23 y A-25 se ensayan
**también** con la voz clonada activa.

## 14. Versionado del contrato

`contract` viaja en `GET /health`, en `POST /realtime/session` y en `POST /speech/session`. Un
cambio incompatible (R-30): doc + esquema en un commit pequeño, push, aviso al otro carril,
`pull --rebase`.

| Versión | Cambio |
|---|---|
| `2026-10-09.1` | Contrato inicial |
| `2026-10-09.2` | Voz clonada opcional (§15): `VoiceMode`, puerto `SpeechSynthesizer`, `POST /speech/session`, `voice_mode` en `/realtime/session`, `voice_modes` en `/health`, campos opcionales en `speech`, `interrupted`, `latency` y `session`, errores `SYNTH_*`. **Aditivo:** con `voice_mode` ausente todo se comporta como en la `.1` |

## 15. Voz clonada (Cartesia)

El equipo contrató **Cartesia** el 2026-10-09 para que el agente pueda hablar con una voz clonada
propia. Es una voz **opcional**: D-11 no cambia (el motor en tiempo real sigue escuchando,
decidiendo el turno, llamando herramientas y redactando la respuesta) y la voz nativa del motor
sigue siendo la base y el respaldo. Lo que cambia, solo cuando se elige «voz clonada», es **quién
convierte el texto de la respuesta en audio**.

Cada afirmación sobre el proveedor lleva su estado: **[doc]** = leída en la documentación oficial
de Cartesia el 2026-10-09; **[G2]** = sin verificar, se confirma llamando al servicio (§15.8).
Nada de esto se ha medido todavía con la clave del equipo.

### 15.1 Diseños considerados

| | A · Motor en solo texto + `SpeechSynthesizer` de cliente (**recomendado para la voz clonada**) | B · Voz nativa del motor (**base y respaldo**) |
|---|---|---|
| Quién habla | El motor entrega texto; el navegador lo envía por frases a Cartesia y reproduce el audio | El motor entrega audio (contrato `.1` sin cambios) |
| Voz | Clonada, la misma con cualquier motor | La de catálogo del motor |
| Latencia | Suma: esperar la primera frase + primer audio de la síntesis + una conexión más. Resta: el motor no genera audio | La mejor disponible |
| Interrupciones | Las resuelve el cliente: cortar, cancelar el contexto, calcular lo escuchado (§15.4) | Las resuelve el motor |
| Texto del agente | Exacto (es el texto que se sintetiza) | Transcripción del audio |
| Costo | Créditos de Cartesia (1 por carácter **[doc]**) a cambio de no pagar audio de salida del motor | Audio de salida del motor |
| Riesgo | Un proveedor y una conexión más; depende de que el motor admita salida de solo texto **[G2]** | Ninguno nuevo |

Descartados: **sintetizar en el backend** (el audio pasaría por Vercel, contra §1) y **silenciar
el audio del motor y sintetizar su transcripción** (se paga dos veces y la transcripción llega
después del audio: la peor latencia). Este último solo se reconsidera si un motor no admite
salida de solo texto y el equipo quiere la voz clonada también ahí.

**Recomendación:** implementar A detrás de un puerto y dejar B como voz inicial y como
degradación automática. La voz clonada pasa a ser la voz por omisión **solo** si G2 confirma
los tres puntos críticos de §15.8 (solo texto, latencia dentro de objetivos, lo escuchado).

### 15.2 Puerto `SpeechSynthesizer` (cliente)

```ts
export interface SpeechSynthesizer {
  readonly id: string;                                // "cartesia"; solo para el HUD
  connect(): Promise<void>;                           // pide credencial, abre y deja caliente la conexión
  speak(generationId: string, text: string, opts: { final: boolean }): void; // frases completas, en orden
  cancel(generationId: string): void;                 // deja de pedir audio y descarta lo tardío
  disconnect(): Promise<void>;
  on<K extends keyof SynthEvents>(e: K, cb: (ev: SynthEvents[K]) => void): () => void;
}

interface SynthEvents {
  audio: { generation_id: string; pcm: Int16Array };                 // PCM16 mono 24 kHz
  words: { generation_id: string; words: { text: string; start_ms: number; end_ms: number }[] };
  done:  { generation_id: string };
  error: { code: "SYNTH_CONNECT_FAILED" | "SYNTH_DROPPED" | "SYNTH_QUOTA"; retryable: boolean };
}
```

- Adaptador `CartesiaSynthesizer` y doble `FakeSynthesizer` (R-09), en `web/src/voice/` y `web/mocks/`.
- **La composición es un decorador:** `withSynthesizer(engine, synth)` devuelve un `VoiceEngine`.
  Por dentro conecta el motor con `voiceMode: "cloned"`, pasa el texto del agente al
  sintetizador, alimenta el reproductor y emite los **mismos** eventos de §2 (`speech`,
  `interrupted`, `latency`, `transcript`). La interfaz, el HUD y el puente de herramientas no
  distinguen una voz de otra salvo por los campos opcionales de la `.2`.
- R-03 se mantiene: nombres de mensajes, `context_id`, base64, URL y token de Cartesia no salen
  del adaptador. Cambiar de proveedor de síntesis es escribir otro adaptador.
- En el backend, la emisión del token vive en `integrations/realtime/` junto a las de los motores (carril B).

### 15.3 Credenciales, audio y envío del texto

**Credenciales (R-28).** `POST /speech/session` (§3) emite un **token de acceso** de Cartesia:
el backend llama a `POST https://api.cartesia.ai/access-token` con la clave del equipo,
`grants: { tts: true }` y `expires_in` de **600 s** (el máximo es 3600 s) **[doc]**. El
navegador abre `wss://api.cartesia.ai/tts/websocket` con el token en el parámetro
`access_token` y la versión en `cartesia_version` **[doc]** (un navegador no puede poner
cabeceras en un WebSocket). La clave `CARTESIA_API_KEY` **nunca** llega al navegador. El token
vive solo en memoria: ni `localStorage` ni `sessionStorage`. Es la única excepción a «el token
no va en la URL» de §3 y la impone el proveedor; por eso el token es corto y de alcance mínimo
(solo síntesis). El `voice_id` lo fija el backend desde `CARTESIA_VOICE_ID`; el cliente no
acepta un `voice_id` de ninguna otra procedencia.

**Audio.** Se pide `output_format { container: "raw", encoding: "pcm_s16le", sample_rate: 24000 }`
**[doc]**: es el formato del reproductor de §4, así que la cola programada, el tope de 2 s,
`flush()` y `played_ms` por generación **no cambian**. `language: "es"` (el español está entre
los 44 idiomas de `sonic-3.6` **[doc]**); el acento lo aporta la grabación clonada, no un
parámetro. El modelo se fija por ID verificado llamándolo, igual que los motores **[G2]**.

**Envío del texto, por frases.** El decorador acumula los fragmentos de texto del motor y llama
a `speak` en cada cierre de frase (`.`, `?`, `!`, `:` o salto de línea), conservando espacios y
puntuación. El adaptador usa **un contexto por generación**: mismo `context_id`, `continue: true`
en cada frase y `continue: false` al terminar **[doc]**. Cartesia recomienda cerrar cada envío en
fin de frase y no tocar `max_buffer_delay_ms` (3000 ms por omisión) **[doc]**; se deja así y se
mide si retiene la primera frase **[G2]**. Un contexto **expira 1 s después de su último audio**
**[doc]**: si llega más texto de la misma generación tras una pausa (por ejemplo, después de una
herramienta), el adaptador abre un contexto nuevo sin que el decorador lo note. El orden de
salida dentro de un contexto está garantizado **[doc]**.

**Calentamiento.** La conexión se abre en `connect()`, tras el gesto del usuario, y se reutiliza
toda la sesión: una conexión nueva por turno fue lo que hizo incumplir el objetivo a Azure en
frío ([anexo US1](anexos/us1-modelos-voz.md) §4.4). El tiempo de inactividad que tolera el
WebSocket no está documentado **[G2]**.

### 15.4 Interrupciones y texto realmente escuchado

Sustituye a los pasos 3 y 4 de §6 cuando la voz es clonada:

1. **Detección.** La sigue haciendo el motor, que recibe el micrófono igual que antes. Si el
   motor ya terminó de redactar (el texto va por delante de la voz) y no avisa de la
   interrupción, el adaptador usa su señal de inicio de voz del usuario; como último recurso, el
   VAD local sobre `MicTap` de §8 **[G2]**.
2. **Local, inmediato** (igual que §6.2): parar, vaciar la cola y fijar `played_ms`.
3. **Hacia el sintetizador:** `cancel(generation_id)`. En Cartesia el mensaje `cancel` **solo
   detiene lo que aún no empezó a generarse**; lo que ya está en curso sigue llegando hasta
   terminar **[doc]**. Por eso la regla de §6.5 es la que protege: todo chunk de una generación
   cancelada se descarta al llegar.
4. **`delivered_text`.** Se pide `add_timestamps: true`; Cartesia devuelve mensajes
   `timestamps` con `word_timestamps { words, start, end }` en segundos **[doc]**. Lo escuchado
   son las palabras cuyo `end_ms ≤ played_ms` (`delivered_basis = "word_timestamps"`). Si las
   marcas no llegan en español o llegan tarde **[G2]**, se estima: frases cuyo audio se
   reprodujo entero más la parte proporcional de la frase en curso, recortada a palabra
   completa (`delivered_basis = "estimated"`, y la transcripción lo rotula). Nunca se da por
   escuchado un texto cuyo audio no salió.
5. **Hacia el motor:** `interrupt(playedMs, deliveredText)`. El motor redactó la respuesta
   completa, pero la persona oyó solo una parte: el adaptador cancela la respuesta si sigue en
   curso y deja en el historial del motor únicamente lo escuchado (sustituyendo el mensaje o,
   si el motor no lo permite, con una nota de contexto «[Interrumpido] La persona solo escuchó:
   …») **[G2]**. El historial de la interfaz y el sobre de contexto ya usan solo lo escuchado (§6.4).

El objetivo de parada (p95 ≤ 200 ms) no cambia y es **local**: no depende de que Cartesia responda.

### 15.5 Latencia: qué se suma y cómo se ve

```
t_speech_end ─► t_first_text ─► t_tts_start ─► t_first_useful_audio
               (motor)          (1.ª frase)    (síntesis + red + cola)
```

- **Se suma:** el tiempo hasta completar la primera frase y el primer audio de la síntesis. La
  cifra de ~90 ms al primer audio que recoge el [anexo US1](anexos/us1-modelos-voz.md) viene de
  una fuente secundaria y la documentación vigente no publica ninguna: **no se usa como dato**
  hasta medirla **[G2]**.
- **Se resta:** el motor no genera audio. El saldo neto no se conoce hasta medirlo.
- **HUD:** voz activa y, con la clonada, tres tramos por turno: «texto» (`t_first_text −
  t_speech_end`), «frase» (`t_tts_start − t_first_text`) y «síntesis» (`t_first_useful_audio −
  t_tts_start`). El reconocimiento previo se mide igual y sigue sin contar como respuesta (R-29).
- **Benchmark:** el protocolo de [07](07-reto-01-especificacion.md) §8 registra la voz junto al motor y el modelo; las
  dos voces se reportan por separado. **Los objetivos no se relajan para la voz clonada:** si
  los incumple, se reporta y la voz por omisión sigue siendo la del motor.
- **Plazo de primer plano:** los 6 s de R-25 incluyen la síntesis. Si pasan 3 s desde
  `t_tts_start` sin audio, se trata como fallo del sintetizador (§15.6), no del motor.

### 15.6 Selector de voz, conmutación y degradación (R-25)

**Selector.** «Voz del motor» / «Voz clonada», junto al selector de motor. Aparece solo si
`GET /health` anuncia `cloned`. Cambiar de voz surte efecto **entre turnos**: la sesión del motor
se renueva con el `voice_mode` nuevo y el sobre de contexto (§7), sin repetir audio ni
herramientas. Se emite `session.voice_changed` con `reason = "user"`.

**Conmutación de motor.** El sintetizador es independiente del motor: al cambiar de motor la
voz clonada **se conserva** (misma conexión de síntesis) siempre que el motor nuevo admita
salida de solo texto. Si no la admite, `config.voice_mode` vuelve como `engine`, se emite
`voice_changed` con `reason = "engine_unsupported"` y el selector lo refleja. Los modelos de
audio nativo de Gemini Live podrían estar en este caso **[G2]**.

**Degradación automática a la voz del motor:**

| Momento del fallo | Qué pasa |
|---|---|
| Al conectar (`/speech/session` falla, o el WebSocket no abre en 3 s) | La sesión arranca con `voice_mode = "engine"`; aviso discreto «voz clonada no disponible» |
| A mitad de una respuesta | Se detiene el audio; el resto de **ese** turno se entrega como texto con su fuente y *Repetir* (igual que `PLAYBACK_FAILED`: no cuenta como voz aprobada). **No** se regenera la respuesta ni se repite la herramienta |
| Entre turnos (conexión caída) | Un intento de reconexión; si falla, degradación |
| Créditos agotados o tope de concurrencia | Degradación directa, sin reintento |

Tras degradar, la sesión del motor se renueva entre turnos con `voice_mode = "engine"` y el
sobre de contexto; se emite `voice_changed` con `reason = "synth_failed"` (o `"quota"`) y el HUD
muestra «voz cambiada a la del motor». La degradación es **pegajosa**: no se vuelve sola a la
voz clonada; la persona puede volver a elegirla. Un fallo del sintetizador **no consume** los
dos intentos de motor del turno (§7) ni abre una segunda generación, de modo que R-24 y R-25 se
cumplen sin multiplicar reintentos. Corresponde a la fila «Falla la síntesis de voz» de
[10](10-modelos-afecto-y-recuperacion.md) §5.

### 15.7 Salvaguardas

- **Consentimiento de quien presta la voz.** Solo se clona la voz de una persona del equipo, con
  su consentimiento expreso y por escrito para este uso (demo del Reto 01), revocable. El
  `voice_id` se elimina de Cartesia cuando esa persona lo pida y, en todo caso, al cerrar el
  reto si no se acuerda otra cosa. El README lo declara.
- **No se clonan voces de terceros:** ni de usuarios, ni de jurados, ni de figuras públicas. El
  audio del micrófono (`MicTap`) **nunca** se envía a Cartesia ni se usa para clonar; a Cartesia
  solo va el **texto** de las respuestas del agente.
- **Aviso de voz sintética.** El aviso de IA de A-25 (visible y hablado) se mantiene, y con la voz
  clonada el distintivo añade «voz sintética clonada con consentimiento» (§10). El agente se
  presenta como asistente de IA y **nunca** como la persona cuya voz usa. El AI Act (art. 50)
  exige avisar que se interactúa con una IA y que el contenido de audio sintético se identifique
  como tal (fuentes secundarias; no es asesoría legal, igual que en [10](10-modelos-afecto-y-recuperacion.md) §6).
- **Sin efecto sobre el afecto (R-26):** el analista sigue recibiendo solo la voz del usuario. Los
  controles de emoción y velocidad de la síntesis **no se usan** hoy; el estilo sigue
  aplicándose al texto (`applyStyle`).
- **Abuso y costo:** token de 10 min con alcance de solo síntesis, límites de tasa en
  `/speech/session` por token e IP, y tope del plan ([11](11-despliegue.md) §10).

### 15.8 Verificado y por verificar

**Leído en la documentación oficial de Cartesia el 2026-10-09** (no medido con nuestra clave):

| Tema | Lo que dice |
|---|---|
| Síntesis en streaming | `wss://api.cartesia.ai/tts/websocket`; petición con `model_id`, `transcript`, `voice`, `output_format`, `context_id`, `continue`, `language`, `add_timestamps`; respuestas `chunk` (audio en base64), `timestamps`, `done`, `flush_done`, `error` |
| Formatos | Contenedor `raw`; `pcm_s16le`, `pcm_f32le`, `pcm_mulaw`, `pcm_alaw`; 8000–48000 Hz, incluido 24000 |
| Token de cliente | `POST /access-token`, `grants { tts, stt, agent }`, `expires_in` ≤ 3600 s; en WebSocket va en `access_token`. «Never ship a Cartesia API key in browser code» |
| Contextos | Entradas en orden; expiran 1 s tras el último audio; entre envíos solo pueden cambiar `transcript` y `continue` |
| Cancelación | `{ context_id, cancel: true }` detiene solo lo que no empezó a generarse |
| Modelo e idiomas | `sonic-3.6` (instantánea estable `sonic-3.6-2026-08-27`); 44 idiomas, español incluido; versión de API `2026-08-14` |
| Clonación | Instantánea desde ~10 s de audio (hasta 60 s recomendados con `sonic-3.6`), archivo ≤ 16 MB, un idioma por clon |
| Plan y costo | 1 crédito = 1 carácter (≈ 750–800 créditos por minuto de audio). Pro: 5 USD/mes, 100.000 créditos, clonación instantánea, **3 síntesis concurrentes**. Free: sin clonación |

**Verificar en G2** (llamando al servicio; hasta entonces la voz por omisión es la del motor):

1. **Salida de solo texto** en cada motor, con herramientas y detección de turno activas: OpenAI Realtime y cada modelo de Gemini Live. *Crítico.*
2. **Latencia real** de «texto», «frase» y «síntesis» en español desde Colombia, en caliente y en frío, y si `max_buffer_delay_ms` retiene la primera frase. *Crítico.*
3. **Marcas por palabra en español:** si llegan, con qué retraso respecto del audio y si `start`/`end` son relativos al inicio del contexto. *Crítico para `delivered_text`.*
4. Corrección del historial del motor tras interrumpir (sustituir el mensaje o nota de contexto) y detección de la interrupción cuando el motor ya terminó de redactar.
5. ID de modelo vigente (una síntesis real con el `voice_id` clonado, no el catálogo) y calidad de la voz clonada en español colombiano, a oído.
6. Si el token se valida solo al abrir el WebSocket o también durante la conexión; tiempo de inactividad tolerado; si el alcance `tts` impide gestionar o clonar voces.
7. Qué cuenta para el tope de concurrencia (conexiones o contextos) y qué error devuelve al superarlo o al agotar créditos. La prueba de 3 sesiones concurrentes de [07](07-reto-01-especificacion.md) §8 queda **justo en el tope** del plan Pro.
8. Si `language` acepta `es-CO` además de `es`.
