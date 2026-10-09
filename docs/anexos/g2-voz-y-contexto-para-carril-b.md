# Spike G2 (voz) y contexto de voz clonada para el carril B

Fecha: 2026-10-09. Escrito por el carril A. Es **evidencia y traspaso**, no contrato: el contrato
vigente es [08](../08-contrato-voz-en-vivo.md) (versión `2026-10-09.2`, §15 para la voz clonada).
Etiquetas: **[M]** medido hoy contra el servicio · **[D]** leído en documentación oficial ·
**[NV]** no verificado. Muestras pequeñas (1–3 por caso), desde un equipo en Colombia.

## 1. Textos para pegar (los escribe el carril B, dueño de docs/00 y docs/02)

**Fila D-20 para [00](../00-contexto-y-decisiones.md) §5:**

```
| D-20 | **Voz clonada opcional con Cartesia.** Con «voz clonada» el motor en tiempo real (D-11) sigue escuchando, decidiendo el turno y llamando herramientas, pero entrega **solo texto**; el navegador lo sintetiza por frases con el puerto de cliente `SpeechSynthesizer` (adaptador Cartesia, token de acceso emitido por el backend, R-28) y lo reproduce con el mismo reproductor ([08](08-contrato-voz-en-vivo.md) §15). **La voz del motor sigue siendo la base y la degradación automática** (R-25); la clonada es la voz por omisión solo si G2 confirma salida de solo texto, latencia dentro de los objetivos de [07](07-reto-01-especificacion.md) §8 y texto escuchado fiable. Solo se clona la voz de una persona del equipo, con su consentimiento, y se avisa de que es voz sintética. *No reemplaza a D-11; levanta el «Won't: voz clonada» de [07](07-reto-01-especificacion.md) §4.* | El equipo contrató Cartesia para tener voz propia; hacerlo como puerto opcional evita que un proveedor más ponga en riesgo la demo | 2026-10-09 |
```

**Fila del puerto para [02](../02-puertos.md), tabla «Puertos de Reto 01»:**

```
| `SpeechSynthesizer` *(cliente, TypeScript)* | Texto de la respuesta → audio PCM16 a 24 kHz en streaming, con marcas por palabra y cancelación; solo se usa con la voz clonada y se compone sobre un `VoiceEngine` en modo solo texto ([08](08-contrato-voz-en-vivo.md) §15.2) | Cartesia (D-20); doble `FakeSynthesizer` en `web/mocks/` | Planeado |
```

Sugerencias: en docs/00 §2, fila «Voz», añadir «+ voz clonada opcional con Cartesia
(`SpeechSynthesizer`) — D-11, D-20»; en §3, Cartesia pasa a «contratada el 2026-10-09; medición
pendiente». En docs/02, fila `RealtimeSessionPort`, añadir «y el token de acceso de síntesis de la
voz clonada (`POST /speech/session`), adaptador `integrations/realtime/cartesia`»; en R-09, sumar
el doble del servidor (`FakeSpeechSession`) y el del cliente (`FakeSynthesizer`).

## 2. Respuestas a las preguntas del carril B

| Pregunta | Respuesta |
|---|---|
| Valores de `voice_mode` | `engine` (por omisión: el motor habla con su voz) y `cloned` (el motor responde en texto y Cartesia pone la voz). No son `native`/`cartesia` |
| ¿Quién oye y decide los turnos en `cloned`? | **El mismo motor en tiempo real.** No hay cascada STT→LLM→TTS (sigue en Won't). D-11 queda intacto; solo cambia quién produce el audio |
| ¿Con qué motores? | **Solo OpenAI** [M]: Gemini Live rechaza la salida de solo texto (`1007 … (TEXT) is not supported`). `/realtime/session` devuelve `config.voice_mode` **efectivo**: `cloned` pedido con Gemini vuelve como `engine` |
| Cómo se pide en OpenAI | Sesión con `output_modalities: ["text"]` [M] |
| Forma de `POST /speech/session` | La del contrato ([08](../08-contrato-voz-en-vivo.md) §3 y §15.3): entrada `{conversation_id}`; salida `{contract, synth, model, connect{url, token, expires_at}, config{audio{encoding, sample_rate}, voice_id, language, timestamps}, voice_label}`; 503 `SYNTH_UNAVAILABLE` sin clave o con Cartesia caída. La URL va en `connect`, igual que en `/realtime/session` |
| Otras piezas del backend | `voice_mode?` en `POST /realtime/session`; `voice_modes` en `GET /health` (`["engine"]` o `["engine","cloned"]`); `CARTESIA_API_KEY` y `CARTESIA_VOICE_ID` en `src/config.py` y `.env.example` |
| Eventos de `VoiceEngine` | Cambios **aditivos**, ya en el contrato: `connect` acepta `voiceMode?`; `interrupt(playedMs, deliveredText?)`; campos opcionales `speech.voice`, `interrupted.delivered_basis`, `latency.t_first_text`/`t_tts_start`, `session.voice_changed`; errores `SYNTH_*`. La interrupción del audio de Cartesia se resuelve en el cliente |
| D-11 | D-20 **no** lo reemplaza |
| docs/07 | Ya ajustado por el carril A: supuesto 5 y voz clonada en Should |
| R-09 | Doble del servidor en `tests/doubles/` (carril B); doble del cliente `FakeSynthesizer` en `web/mocks/` (carril A) |
| Audio para probar el analista por voz | Recomendación: sintetizarlo en el carril B; en producción lo envía el navegador como recorte WAV |
| ¿Registrar G3 en docs/00 §6? | Sí, junto con D-20 |

## 3. Cartesia, según su documentación [D] (no se llamó: aún no había clave)

- Token: `POST https://api.cartesia.ai/access-token`, `Authorization: Bearer <clave>`, cabecera `Cartesia-Version: 2026-08-14`, cuerpo `{"grants":{"tts":true},"expires_in":600}` → `{token}`. Máximo 3600 s.
- WebSocket: `wss://api.cartesia.ai/tts/websocket?cartesia_version=<fecha>&access_token=<token>`.
- Petición: `model_id` (`sonic-3.6`), `transcript`, `voice{id}`, `language` (`es`; no existe `es-CO`), `context_id`, `continue`, `output_format{container:"raw", encoding:"pcm_s16le", sample_rate:24000}`, `add_timestamps`.
- Respuestas: `chunk` (base64), `timestamps{words,start,end}`, `flush_done`, `done`, `error`. Cancelar: `{context_id, cancel:true}` (solo detiene lo que aún no empezó a generarse).
- Plan Pro: 3 síntesis concurrentes; 1 crédito por carácter. **[NV]:** latencia real en español, marcas por palabra en español, calidad de la voz clonada.

## 4. Motores de voz: resultado del spike [M]

**Motor 1 = OpenAI `gpt-realtime-2.1` · Motor 2 = Gemini `gemini-3.8-live`.** Ambos conectan desde un
navegador real por WebSocket con credencial efímera, sin WebRTC. Con esto queda cerrada D-11.

| | OpenAI Realtime | Gemini Live |
|---|---|---|
| Emitir credencial | 570–1440 ms | 225–450 ms |
| Pregunta hablada → llamada de herramienta | `gpt-realtime` 1302 / 1773 ms · `2.1` 2301 ms | `3.8-live` 1129 / 1137 ms |
| Pregunta hablada → primer audio útil | `gpt-realtime` 1761 / 2348 ms · `2.1` 3368 ms (reconocimiento previo a 1346 ms) | `3.8-live` 2172 / 1726 ms |
| Reconocimiento previo hablado sin pedirlo | `2.x` sí; `gpt-realtime` y `-mini` no | No apareció |
| Audio de entrada | PCM16 base64, **mínimo 24 kHz** (rechaza 16 kHz) | PCM16 base64, 16 kHz |
| Audio de salida | PCM16 24 kHz base64 | PCM16 24 kHz base64, en tramas binarias con JSON |
| Salida de solo texto | Sí | **No** |
| La credencial fija la configuración | **No** (el cliente pudo cambiarla con `session.update`) | **Sí** |
| Reutilizar la credencial | No (`ephemeral_token_already_used`) | Con `uses:1`, no |
| Duración | 60 min | Conexión ≈ 10 min con `goAway` [D] |

IDs con sesión real abierta: OpenAI `gpt-realtime`, `gpt-realtime-2`, `gpt-realtime-2.1`,
`gpt-realtime-2.1-mini`, `gpt-realtime-mini`; transcripción `gpt-4o-mini-transcribe`. Gemini
`gemini-3.8-live`, `gemini-3.1-flash-live-preview`, `gemini-2.5-flash-native-audio-latest` (este,
claramente más lento). `gemini-3.8-live-extended-thinking` falla sin nivel de pensamiento.

### Receta de credenciales para `integrations/realtime/`

**OpenAI** — `POST https://api.openai.com/v1/realtime/client_secrets`, `Authorization: Bearer <clave>`:

```json
{"expires_after":{"anchor":"created_at","seconds":600},
 "session":{"type":"realtime","model":"gpt-realtime-2.1","instructions":"…","output_modalities":["audio"],
  "audio":{"input":{"format":{"type":"audio/pcm","rate":24000},
                    "transcription":{"model":"gpt-4o-mini-transcribe","language":"es"},
                    "turn_detection":{"type":"server_vad","threshold":0.5,"prefix_padding_ms":300,"silence_duration_ms":500,"create_response":true,"interrupt_response":true}},
           "output":{"format":{"type":"audio/pcm","rate":24000},"voice":"marin"}},
  "tools":[{"type":"function","name":"aggregate_ips","description":"…","parameters":{}}],"tool_choice":"auto"}}
```

Respuesta: `{"value":"ek_…","expires_at":<epoch>,"session":{…}}`. El navegador abre
`wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1` con subprotocolos
`["realtime", "openai-insecure-api-key." + ek]`. Voces: `alloy, ash, ballad, coral, echo, sage,
shimmer, verse, marin, cedar` (ninguna específica de español: el acento se pide por instrucciones).

**Gemini** — `POST https://generativelanguage.googleapis.com/v1alpha/auth_tokens`, cabecera `x-goog-api-key`:

```json
{"uses":1,"expireTime":"<ISO +30 min>","newSessionExpireTime":"<ISO +2 min>",
 "bidiGenerateContentSetup":{"model":"models/gemini-3.8-live",
   "generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Kore"}}}},
   "systemInstruction":{"parts":[{"text":"…"}]},
   "tools":[{"functionDeclarations":[{"name":"aggregate_ips","description":"…","parameters":{}}]}],
   "inputAudioTranscription":{},"outputAudioTranscription":{},"sessionResumption":{},"contextWindowCompression":{"slidingWindow":{}}}}
```

Respuesta: `{"name":"auth_tokens/…"}`. El nombre `liveConnectConstraints` de la documentación falla
por REST (`400 Unknown name`). El navegador abre
`wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained?access_token=<name>`
y envía `{"setup":{"model":"models/gemini-3.8-live"}}`.

## 5. Correcciones pendientes al contrato 08 (carril A)

1. §4: OpenAI exige entrada a 24 kHz; el adaptador de OpenAI remuestrea (`MicTap` puede seguir a 16 kHz).
2. §3: el secreto de OpenAI es de un solo uso y no bloquea la configuración; cada renovación pide credencial nueva.
3. §6: en OpenAI la interrupción llega como `speech_started` más `response.done` con estado `cancelled`.
4. §7 y [10](../10-modelos-afecto-y-recuperacion.md) §6: en Gemini el estilo se aplica como turno `user` marcado «[NOTA DEL SISTEMA, no la respondas]»; un turno `system` cierra la conexión.

## 6. No verificado

Calidad y acento es-CO al oído; interrupción con micrófono real y eco; el `goAway` y el corte de
≈ 10 min de Gemini; reanudación de sesión; costos por minuto; toda la medición de Cartesia.
