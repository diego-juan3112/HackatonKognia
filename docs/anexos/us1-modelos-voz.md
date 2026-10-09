# US1 — Identificar modelos de voz

> Cierra el issue #1. Alimenta la decisión de **AGENTS.md §1.1**.
> Precios y disponibilidad verificados el **20/09/2026**. Todos los servicios
> listados se comprobaron activos ese día.
> Criterios de §1.1, en orden: **costo → latencia → calidad en español**.

## 1. Resumen ejecutivo

> **Estado al 06/10/2026: Azure ya está medido (§4.4).** Emite visemas en
> `es-CO` —138 eventos, 15 IDs distintos en 10 s de audio— y su TTFA en caliente
> va de 214 a 551 ms, dentro del criterio de 1 s. En frío (conexión nueva)
> **incumple**: 791 a 1514 ms. Cartesia sigue sin medir: falta su clave.

| | |
|---|---|
| **Recomendado** | **Azure AI Speech (estándar)** — $0 con el tier F0, y **verificado el 06/10/2026**: es el único candidato que emite **visemas en `es-CO`**, lo que resuelve también US2 |
| **Si queremos nuestra propia voz** | **Cartesia Pro ($5/mes)** o **ElevenLabs Starter ($6/mes)** — son los dos únicos caminos realistas a voz clonada |
| **Descartado por costo** | Azure Voice Live (sin tier gratuito), OpenAI Realtime |
| **Descartado por velocidad (medido)** | Clonación local con Chatterbox: **sí cabe** en la GTX 1650 (3.15 GB pico de 4.00), pero corre a **2.6x más lento que tiempo real** — ver §3.1 |

## 2. Opciones por API

### Azure AI Speech (estándar) — recomendado

- **Costo:** tier **F0 gratuito y permanente**: 5 h de speech-to-text y
  0.5 M caracteres de TTS neural al mes. Para un reto de 6 h sobra.
- **Visemas: sí — verificado el 06/10/2026 con `es-CO-SalomeNeural` (§4.4).**
  Emite `viseme_id` (0–21) con `audio_offset`, y el volcado de `measure.py` tiene
  exactamente la forma del `VisemeFrame` de `src/models/conversation.py`
  (`viseme_id`, `audio_offset_ms`). Era el supuesto del que colgaba toda la
  recomendación, y se cumple.
- **Voz propia:** no por esta vía. Custom/Personal Voice es *acceso restringido*
  (requiere solicitud y aprobación) y además cobra hosting del endpoint
  (~$4.04/h), así que no es viable antes del 9 de octubre.
- **Encaje:** el despliegue ya está fijado en Azure (§1), así que no suma un
  proveedor nuevo.

### Azure Voice Live — coherente con §1.3, se mantiene descartado

Se documenta aquí porque el equipo pidió ver todas las opciones con precios.
Integra STT + LLM + TTS + avatar en una sola conexión, pero **no tiene tier
gratuito** (precios vigentes desde el 01/07/2025):

| Tier | Modelos | Audio entrada | Audio salida |
|---|---|---|---|
| Pro | gpt-realtime, gpt-4o, gpt-5 | $35.20 /M tokens | $70.40 /M tokens |
| Standard | gpt-realtime-mini, gpt-5-mini | $11.00 /M tokens | — |
| Lite | gpt-5-nano, phi4-mm-realtime | $4.00 /M tokens | — |

Custom voice y avatar se facturan aparte (hosting de voz personalizada
~$4.04/h). **Confirma la decisión de §1.3.**

### OpenAI Realtime

`gpt-realtime-2.1`: **$32/M** tokens de audio de entrada y **$64/M** de salida.
La variante mini baja a **$10/M** y **$20/M**. STT suelto `gpt-4o-transcribe`
a **$0.006/min**. No emite visemas y no clona voces. Sin tier gratuito.

### Gemini Live (3.8 Live / 3.1 Flash Live)

**Tiene tier gratuito en AI Studio** — es la opción $0 más potente después de
Azure F0. Pagado: **$0.005/min** de audio de entrada y **$0.018/min** de salida.
Contras: no emite visemas, no clona voces, y al ser speech-to-speech de punta a
punta tiende a quedarse con el control del turno, lo que roza la regla de §8
("el LLM nunca decide transiciones de estado"). Usable, pero obliga a diseñar
con cuidado quién manda: el grafo o el modelo.

### Deepgram

**$200 de crédito gratis al registrarse, sin tarjeta** — en la práctica es
gratis para el reto. STT Nova-3 a **$0.0048/min** (monolingüe) o $0.0058
(multilingüe); TTS Aura-2 a **$0.030/1k caracteres**; Voice Agent API a
**$0.075/min**. Su STT es el punto fuerte; el TTS es más nuevo. Sin visemas.

### Cartesia

Plan **Free: 20k créditos/mes** (uso personal, un solo agente). **Pro: $5/mes**
con 100k créditos e **Instant Voice Cloning**. Sonic 3 declara ~90 ms al primer
audio (Turbo ~40 ms) y soporta 40+ idiomas. **La opción más barata para tener
nuestra voz.** Sin visemas.

### ElevenLabs

Free: 10k créditos/mes, **sin clonación y sin licencia comercial** — inservible
para el reto. **Starter: $6/mes**, 30k créditos, **Instant Voice Cloning y
licencia comercial**. Creator: $22/mes con clonación profesional. Mejor calidad
percibida, un dólar más caro que Cartesia. Sin visemas.

## 3. Opciones locales (contra la GTX 1650, 4 GB)

| Modelo | Licencia | VRAM | ¿Clona? | Veredicto |
|---|---|---|---|---|
| Kokoro / HeadTTS | Libre | ~0.4 GB | No | Entra cómodo, pero no da voz propia |
| Piper | Libre | CPU | No | Útil como respaldo offline |
| XTTS-v2 | **Coqui CPML — no comercial** | ~2 GB FP16, **recomiendan 6 GB+** | Sí | La licencia lo descarta en un reto cuyo premio es un contrato |
| Chatterbox Multilingual | **MIT** (comercial OK), `es` soportado, clona con ~10 s | **3.15 GB — medido** | Sí | **Cabe en la 1650, pero es 2.6x más lento que tiempo real.** Descartado por velocidad, no por memoria |
| faster-whisper | MIT | ~1 GB | — | STT local gratis, buen respaldo |
| Web Speech API | Gratis (navegador) | 0 | — | STT gratis sin backend; depende de Chrome |

### 3.1 Medición de Chatterbox — 20/09/2026

Medido de verdad, no estimado. GTX 1650 (4.00 GB), driver 555.97,
`chatterbox-tts` 0.1.7 con `torch 2.6.0+cu124`, modelo
`ChatterboxMultilingualTTS`, `language_id="es"`.

| Medida | Valor |
|---|---|
| VRAM tras cargar el modelo | **3.00 GB** |
| **VRAM pico durante la síntesis** | **3.15 GB de 4.00 GB** |
| Tiempo de carga | 16.6 s |
| RTF, 1ª generación (en frío) | 6.42x |
| **RTF en caliente** (3 corridas: 2.88x · 2.43x · 2.57x) | **~2.6x** |

**La estimación previa estaba equivocada y hay que corregirla: Chatterbox sí
cabe en 4 GB.** No hubo *out of memory* por ningún lado; sobran ~0.85 GB. Lo que
lo descalifica es otra cosa.

**Lo descalifica la velocidad.** Un RTF de 2.6x significa que generar 4 segundos
de respuesta cuesta unos 10 segundos de cómputo. El criterio de aceptación de
§1.1 es **menos de 1 s al primer audio**: Chatterbox local se queda un orden de
magnitud lejos, y ni siquiera hay streaming que permita empezar a reproducir
antes de terminar.

> **Corrección al resumen ejecutivo (§1) y a `AGENTS.md` §1.1:** donde decía
> "descartado por hardware / la GTX 1650 no da margen", el motivo correcto es
> **descartado por velocidad**. La memoria alcanza; el throughput no. La
> diferencia importa: si mañana conseguimos una GPU más rápida con la misma
> VRAM, la opción vuelve a la mesa.

### 3.2 Dos trampas de instalación que costaron la medición

Ambas están documentadas en `spikes/local_tts/README.md`:

1. **`chatterbox-tts` fija `torch==2.6.0` y pip lo resuelve desde PyPI**, que en
   Windows es el build **de CPU**. Con eso `torch.cuda.is_available()` da
   `False` y se mide CPU creyendo medir GPU. Hay que forzar el wheel cu124.
2. **`perth` (la marca de agua de Resemble) importa `pkg_resources`**, que
   setuptools eliminó en su versión 81 y que los venv de Python 3.12 ya no
   traen. El paquete se traga el `ImportError` y deja
   `PerthImplicitWatermarker = None`, así que Chatterbox muere con un
   `TypeError: 'NoneType' object is not callable` **que no tiene nada que ver
   con VRAM**. Se arregla con `pip install "setuptools<81"`.

**Conclusión, ahora medida:** la clonación de voz local en esta máquina queda
descartada **por velocidad**. La voz propia sale por API de pago —
Cartesia Pro ($5) o ElevenLabs Starter ($6)— o no sale.

## 4. Lo que falta medir — intento del 20/09/2026

`spikes/voice_latency/measure.py` mide, con la misma frase en español:

1. **TTFA** por proveedor — criterio de aceptación: **< 1 s**.
2. Si Azure efectivamente emite `VisemeReceived` en `es-CO`. Es el supuesto del
   que cuelga la recomendación; si fallara, la ruta sigue viva pero el lip-sync
   pasa a derivarse del audio (ver US2).
3. Calidad de voz en español, a oído, comparando los `.wav` que deja en `out/`.

### 4.1 Estado al 20/09/2026: no se pudo medir nada de Azure *(superado por §4.4)*

| Medida | Resultado |
|---|---|
| TTFA de Azure AI Speech | **No medido** |
| Visemas `VisemeReceived` en `es-CO` | **No confirmado** |
| TTFA de Cartesia / Deepgram / ElevenLabs | **No medido** (sin claves) |
| `out/azure_visemes.json` | **No existe** — el directorio `out/` nunca se creó |

Causa verificada el 20/09/2026, en este orden:

1. `AZURE_SPEECH_KEY` y `AZURE_SPEECH_REGION` **no están definidas** en ningún
   ámbito de Windows: ni proceso, ni usuario, ni máquina.
2. No hay archivo `.env` en la raíz del repo — solo `.env.example`.
3. **La CLI `az` no está instalada** en la máquina.
4. Los comandos `az` que se intentaron correr fallaron en el analizador de
   PowerShell (llevaban continuaciones de línea `\` de bash), así que el grupo
   de recursos y el recurso Speech **nunca llegaron a crearse**.

**Conclusión honesta: el recurso de Azure AI Speech F0 no existe todavía.** No
hay ningún número que reportar y el supuesto de §1.1 sigue siendo una lectura
de documentación, no una observación.

### 4.2 Qué significa esto para la recomendación

La recomendación de §5 descansa sobre dos patas, y **solo una está en pie**:

| Pata | Estado |
|---|---|
| Costo $0 con tier F0 | Verificado en la página de precios (documental) |
| **Visemas nativos en `es-CO`** | **Sin verificar — es el riesgo abierto** |
| Latencia < 1 s | Sin verificar |

El supuesto de los visemas es el que justifica elegir Azure *por encima* de
Cartesia o Deepgram. Si resultara falso, Azure sigue siendo defendible por
costo, pero pierde su ventaja diferencial y la decisión de §1.1 debería
reabrirse contra Deepgram ($200 de crédito) y Cartesia (voz propia por $5).

**Mitigación ya demostrada:** `spikes/avatar_lipsync` confirmó que el driver por
audio (`wawa-lipsync`) funciona sin ningún dato del proveedor de voz
(`us2-avatar-3d.md` §4.1). El avatar no depende de que este supuesto sea cierto.

### 4.3 Cómo desbloquearlo

Ver `spikes/voice_latency/README.md`. Resumen: instalar la CLI de Azure, crear
el recurso Speech F0, exportar las dos variables y correr `measure.py`. Son
unos 10 minutos. Hasta entonces §1.1 **no se puede cerrar con evidencia**.

### 4.4 Medición del 06/10/2026 — Azure, ya con recurso

**Recurso:** `kognia-speech`, tier **F0**, región **`canadacentral`**, grupo
`rg-kognia-voz`. Voz `es-CO-SalomeNeural`.

Crearlo destapó dos restricciones de la suscripción **Azure for Students** que
no estaban documentadas:

1. **Regiones permitidas:** la política *Allowed resource deployment regions*
   solo deja `spaincentral`, `westus`, `canadacentral`, `belgiumcentral` y
   `chilecentral`. `eastus`, que era la que asumía toda la documentación, la
   rechaza con `RequestDisallowedByAzure`. De esas cinco, **Speech F0 solo
   existe en `westus` y `canadacentral`**. Se eligió Canadá midiendo desde
   Colombia: TCP ~100 ms en ambas, pero handshake TLS **~400 ms contra ~720 ms**.
2. **Proveedor no registrado:** hubo que correr
   `az provider register --namespace Microsoft.CognitiveServices` antes de poder
   crear el recurso (`MissingSubscriptionRegistration`). Es gratis y es una vez.

**Visemas en `es-CO`: confirmados.**

| | Resultado |
|---|---|
| Eventos `VisemeReceived` en la frase de prueba (10 s de audio) | **138** |
| IDs distintos | **15** de 22: `0 2 4 6 7 8 12 13 14 15 17 18 19 20 21` |
| Forma del volcado | `{viseme_id, audio_offset_ms}` — idéntica a `VisemeFrame` |

**TTFA: depende de si la conexión está caliente.**

| Escenario | TTFA | ¿Cumple < 1 s? |
|---|---|---|
| Frío: proceso nuevo, conexión nueva (`measure.py`, 4 corridas) | 791 · 1092 · 1349 · 1514 ms | **No** — 3 de 4 lo pasan |
| Caliente: sintetizador reusado, script aislado (5 frases) | 220 – 981 ms · mediana **606** | Sí, las 5 |
| Caliente: a través de `spikes/demo_voz_avatar` (7 turnos) | 214 – 551 ms · mediana **308** | Sí, los 7 |

El frío es la conexión WebSocket + TLS hacia `canadacentral`. En una
conversación solo se paga una vez, y se puede pagar antes de que el usuario
hable: la demo hace una síntesis de calentamiento al arrancar, y por eso hasta
su primer turno sale en caliente. **Esto es un requisito para el adaptador
real:** reusar el sintetizador y calentarlo al abrir la sesión. Crear uno por
turno incumple el criterio de §1.1.

**Cartesia: sin medir.** Falta `CARTESIA_API_KEY`. `measure.py` y la demo ya
usan la API vigente (versión `2026-08-14`, auth con `Bearer`); la llamada que
tenía el spike usaba la API de 2024 y habría fallado.

## 5. Decisión propuesta

**Azure AI Speech (F0) como proveedor base**, por costo cero, encaje con el
despliegue Azure ya fijo, y visemas nativos en español que abaratan US2.

**Voz clonada como mejora opcional** con Cartesia Pro ($5) si después de tener
el pipeline corriendo sobra tiempo. Como `VoicePort` aísla al proveedor
(§5), ese cambio toca únicamente `src/integrations/voice/`.

## 6. Propuesta de cierre de `AGENTS.md` §1.1 — actualizada 06/10/2026

Azure ya cumple los tres criterios de §1.1 en la parte que se puede medir con
números:

| Criterio de §1.1 | Azure AI Speech F0 | Respaldo |
|---|---|---|
| Costo | **$0** | Tier F0, recurso creado y funcionando |
| Latencia (< 1 s al primer audio) | **Cumple en caliente** (mediana 308 ms en la demo); **incumple en frío** | §4.4 |
| Calidad en español | Pendiente de oído | `spikes/demo_voz_avatar` permite oírla contra Cartesia |
| *(Visemas — el desempate)* | **Verificado** en `es-CO` | §4.4 |

**Lo que queda abierto no es Azure, es si vale la pena la voz propia.** El equipo
decidió el 06/10/2026 comparar Azure contra **Cartesia con voz clonada** antes
de cerrar, con un tope de 5–10 USD. Esa comparación es de oído y la resuelve
`spikes/demo_voz_avatar` (botón *🔁 con la otra voz*: misma frase, ambos
proveedores).

### Redacción propuesta para §1.1, a aplicar cuando termine la comparación

> **Voz — decidida (fecha).** **Azure AI Speech F0** como base: gratis, TTFA de
> ~300 ms con la conexión caliente y visemas nativos en `es-CO`, verificados.
> El adaptador debe reusar el sintetizador y calentarlo al abrir la sesión: una
> conexión nueva por turno pasa de 1 s. [**Cartesia Pro** como voz alternativa
> si el equipo prefiere la voz clonada: sin visemas, lip-sync por audio.]

El corchete se queda o se va según lo que el equipo oiga. Esta propuesta no se
aplicó a `AGENTS.md`: el 06/10 se acordó que el `AGENTS.md` del repo remoto manda.

## Fuentes

- [Azure Speech — precios](https://azure.microsoft.com/en-us/pricing/details/speech/)
- [Azure — visemas y blend shapes](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis-viseme)
- [Azure Voice Live — overview](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live)
- [OpenAI — precios de API](https://developers.openai.com/api/docs/pricing)
- [Gemini — precios de la API](https://ai.google.dev/gemini-api/docs/pricing)
- [Deepgram — precios](https://deepgram.com/pricing)
- [Cartesia — precios](https://www.eesel.ai/blog/cartesia-sonic-3-pricing)
- [ElevenLabs — precios](https://elevenlabs.io/pricing)
- [Chatterbox Multilingual (MIT)](https://www.resemble.ai/learn/models/chatterbox-multilingual)
- [XTTS-v2 — requisitos de VRAM](https://gigagpu.com/xtts-v2-vram-requirements/)
