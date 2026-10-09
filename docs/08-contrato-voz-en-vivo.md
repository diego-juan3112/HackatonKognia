# Contrato de voz en vivo

Contrato vigente · versión `2026-10-09.1` · dueño: **carril A** ([12](12-guia-de-trabajo-2-personas.md)).
Decisiones: D-11 (voz en tiempo real desde el navegador), D-14 (excepción acotada a R-04),
D-18 (estado en el navegador, recuperación acotada). Reglas: R-24, R-25, R-28, R-29.
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
      │ audio ⇄ proveedor (WebSocket directo)         └ GET  /dataset/brief, POST /feedback, GET /health
      └ MicTap · Player · estado canónico · UI
```

El audio **no pasa por Vercel**: va del navegador al proveedor. El backend solo emite
credenciales, ejecuta herramientas y analiza. Así no hay WebSocket propio, ni tope de 300 s
por conexión, ni límite de 4,5 MB en el camino de audio (R-28).

## 2. `VoiceEngine` (puerto de cliente)

```ts
export type EngineId = "openai" | "gemini";

export interface VoiceEngine {
  readonly id: EngineId;
  connect(opts: { conversationId: string; seed?: ContextEnvelope; style?: StyleDecision }): Promise<void>;
  disconnect(reason?: string): Promise<void>;
  sendText(text: string): void;                      // modo texto (F-12)
  interrupt(playedMs: number): void;                 // voz del usuario o botón Detener
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
| `speech` | `phase` (`start`/`stop`), `generation_id`, `kind` (`ack`/`answer`/`brief`) |
| `interrupted` | `generation_id`, `played_ms`, `delivered_text` |
| `latency` | `t_speech_end`, `t_ack_audio?`, `t_tool_start?`, `t_tool_end?`, `t_first_useful_audio?`, `t_playback_stop?` |
| `session` | `event` (`renewed`/`switched`/`expiring`), `from?`, `to?`, `reason`, `attempt` |
| `error` | `code`, `message`, `retryable` |

`affect` y `style` no los emite el motor: los produce el analista ([10](10-modelos-afecto-y-recuperacion.md) §6)
y la interfaz los fusiona en el mismo almacén de eventos.

## 3. Sesión y credenciales

| Llamada | Entrada | Salida |
|---|---|---|
| `POST /sessions` | `locale` (sin cédula ni datos personales) | `token` firmado (HMAC, sin base de datos), `expires_at` (2 h) |
| `POST /realtime/session` | `engine`, `conversation_id`, `seed?`, `style?`, `locale="es-CO"`, `voice?` | `contract`, `engine`, `model`, `connect{url, protocols?, token, expires_at}`, `config{audio, voice, turn_detection}`, `instructions_version`, `brief?` |

Cabecera `X-Session-Token` en todas las rutas menos `/sessions` y `/health`. El token no va en
la URL. Límites de tasa por token e IP, en memoria (R-28). Errores: §12.

**Qué fija el backend al crear la credencial:** instrucciones (prompt v1, [10](10-modelos-afecto-y-recuperacion.md) §7),
declaración de las 5 herramientas (JSON Schema de [09](09-datos-en-vivo-datos-gov-co.md) §5), voz es-CO, detección de
turno y transcripción de entrada. Los adaptadores solo traducen.

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
- El stack de audio es **uno solo**; cada motor solo cambia el protocolo (JSON con base64 o binario, `mime`).
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

La cancelación cuenta como medida de latencia (parada p95 ≤ 200 ms) pero un botón *Detener* **no** prueba que la interrupción por voz funcione: se ensaya con audio real y, si hay eco, con audífonos.

## 7. Conmutación de motor y renovación de sesión

| Disparador | Acción |
|---|---|
| WebSocket cerrado o error de red | Renovar el mismo motor (credencial nueva), intento 1 |
| `goAway` de Gemini o caducidad de credencial | Renovación **proactiva entre turnos**, nunca a mitad de una respuesta |
| 429 o cuota al conectar | Cambiar al otro motor |
| Sin primer audio 6 s después del fin de la voz | Tratar como fallo del motor |
| Dos intentos fallidos | Modo texto con mensaje claro y *Repetir* |

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

## 10. Interfaz y controles

Estados: `idle`, `connecting`, `listening`, `thinking`, `speaking`, `renewing`, `error`.
Controles: **Iniciar/Detener**, **Corregir lo que dije**, **Más directo**, **Repetir**,
**Reiniciar** (borra estado y transcripción), selector de **motor**, interruptor de **análisis
de voz** (con consentimiento) y entrada de texto. Distintivo persistente: «Asistente de IA ·
datos del REPS (corte 5-nov-2022)». La atribución CC BY-SA 4.0 va en el pie.

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
| `ANALYSIS_UNAVAILABLE` | Falla el analista | Afecto «incierto»; nunca una etiqueta vieja con confianza |

## 13. Pruebas

Doble `FakeEngine` que emite eventos guionados; eventos de proveedor grabados en `web/mocks/`.
Pruebas de contrato: `seq` monótono, `delivered_text` correcto tras interrumpir, eventos tardíos
descartados por `generation_id`, idempotencia por `tool_call_id`, conmutación de motor sin
herramienta duplicada. Humo con Playwright y micrófono simulado. Mapa a escenarios: A-01, A-02,
A-10…A-13, A-16, A-17, A-23, A-25 ([07](07-reto-01-especificacion.md) §7).

## 14. Versionado del contrato

`contract` viaja en `GET /health` y en `POST /realtime/session`. Un cambio incompatible
(R-30): doc + esquema en un commit pequeño, push, aviso al otro carril, `pull --rebase`.
