# US2 — Identificar modelos 3D que se acoplen a los modelos de voz

> Cierra el issue #2. Alimenta la decisión de **AGENTS.md §1.2**.
> Verificado el **20/09/2026**.

## 0. Corrección al AGENTS.md

**§1.2 lista Ready Player Me como candidato probable para la malla. Ya no
existe.** Netflix lo compró a finales de 2025 y el 31/01/2026 dieron de baja el
creador público, PlayerZero y todas las APIs de desarrollo. Cualquier tutorial o
repo que encuentren asumiendo RPM está desactualizado — incluida la propia
librería TalkingHead, que todavía lo menciona en su README.

## 1. El acople es el problema real, no la malla

"Que se acople a los modelos de voz" se traduce en una sola pregunta técnica:
**de dónde salen los visemas**. Hay dos caminos, y el proveedor de voz decide
cuál está disponible:

| Driver | Cómo funciona | Requisito | Idioma |
|---|---|---|---|
| **A · Visemas del TTS** | El proveedor emite `viseme_id` + timestamps; el avatar solo los traduce a morph targets | Que el TTS los emita — **hoy solo Azure** | Español soportado (`es-CO`, `es-MX`, `es-ES`) |
| **B · Análisis de audio** | `wawa-lipsync` analiza la onda en el navegador y deduce la forma de boca | Ninguno: sirve con cualquier audio | **Agnóstico al idioma** |
| ~~C · Texto → fonemas~~ | TalkingHead deriva visemas del texto | — | **Sin módulo de español** (en, de, fr, fi, lt) |

El camino C queda descartado para un agente que habla español, salvo que
escribamos nosotros el módulo fonético.

**Consecuencia para §1.2:** el driver B funciona pase lo que pase, así que el
avatar **no bloquea** la decisión de voz. Si se elige Azure, ganamos el driver A
como mejora de precisión sin costo.

## 2. Opciones de malla

| Opción | Costo | Semejanza | Visemas | Estado |
|---|---|---|---|---|
| **Microsoft RocketBox** | **Gratis (MIT)** | Genérico — 115 personajes | **15 visemas + 48 FACS** | Activo |
| **Open Source Avatars** | **Gratis (CC0)**, 300+ GLB | Genérico | Variable, verificar por modelo | Activo |
| **VRoid Studio** | **Gratis**, offline | Estilizado / anime | VRM; hay pack comunitario de 52 ARKit | Activo |
| **Avatar SDK / MetaPerson** | **1er avatar gratis** + prueba Pro de 7 días; después $800/mes | **Su rostro, desde una selfie** | GLB rigged con blendshapes | Activo |
| Avaturn | $800/mes, sin plan gratuito | Su rostro | ARKit + visemas | Activo |
| HeyGen LiveAvatar | Free: 10 créditos, sesión ≤2 min, 1 concurrencia; Starter $19/mes | Su rostro (1 imagen o 2 min de video) | — **no es 3D**: video 2D en streaming | Activo |
| ~~Ready Player Me~~ | — | — | — | **Cerrado 31/01/2026** |

### Sobre "queremos nuestro rostro"

Hay dos rutas realistas y ninguna es gratis del todo:

1. **MetaPerson Creator** — el primer avatar sale gratis, y es el sucesor
   directo de RPM (mismo formato GLB). Táctica: generar los dos avatares del
   equipo ahora, o activar la prueba Pro de 7 días alrededor del 6 de octubre
   para que cubra el día del reto.
2. **HeyGen LiveAvatar** — el más parecido a un humano real, pero es **video 2D
   en tiempo real**, no un modelo 3D: no hay malla, ni Three.js, ni control de
   cámara. Cambia la arquitectura del frontend por completo. El plan gratuito
   además limita las sesiones a 2 minutos, lo que es un riesgo serio en una
   demo en vivo ante jurado.

Recomendación: **empezar con RocketBox** (gratis, con los 15 visemas ya
incluidos, sin trámites) para tener el pipeline corriendo, y sustituir la malla
por una de MetaPerson al final si el tiempo alcanza. La malla es un archivo
`.glb`: cambiarla no toca código.

## 3. Renderizado — la duda abierta de §1.2

`AGENTS.md` §1.2 pregunta si react-three-fiber obliga a una isla React en Astro.
**Sí, la obligaría** (`@astrojs/react` + `client:only="react"`), pero se puede
evitar: **Three.js plano no necesita React**, y el spike lo demuestra — son
~200 líneas de JavaScript de módulo. Para un panel que solo muestra un avatar y
reproduce audio, meter React suma dependencia sin ganar nada.

## 4. Cómo se prueba

`spikes/avatar_lipsync/` — página estática que carga un `.glb`, reproduce un
audio y mueve la boca con **A o B**, para comparar lado a lado. Trae un
`demo_es.wav` para probar sin credenciales y acepta micrófono en vivo.
`three` y `wawa-lipsync` están vendorizados: **corre sin internet**, que es lo
que queremos el día del reto.

Criterio de aceptación: la boca sigue al audio en español de forma creíble, y
el panel de diagnóstico confirma que el avatar trae los 15 visemas Oculus.

## 4.1 Resultados medidos — 20/09/2026

Medido con `python -m http.server 8000` sobre `spikes/avatar_lipsync/` y
verificado con Playwright (Edge headless: Chromium no se pudo instalar y
`playwright install chrome` exige administrador).

### El spike no arrancaba — corregido

**Tal como estaba escrito, la página no ejecutaba una sola línea.**
`vendor/jsm/loaders/GLTFLoader.js` importa dos archivos que no se habían
vendorizado:

```
GET /vendor/jsm/utils/BufferGeometryUtils.js  404
GET /vendor/jsm/utils/SkeletonUtils.js        404
```

Al ser imports estáticos de un módulo ES, los 404 tumban el grafo completo: no
se creaba el canvas de Three.js, no se registraba ningún listener y el botón
**Reproducir quedaba deshabilitado de forma permanente**. El README afirmaba
"corre sin internet"; no corría de ninguna manera.

Corregido vendorizando ambos archivos desde `three@0.186.0`, la misma revisión
que el resto de `vendor/` (`REVISION = '186'`). Los dos solo importan del
especificador `three`, que el importmap ya resuelve.

### Modo B · `wawa-lipsync` por audio — **funciona**

| Medida | Valor |
|---|---|
| Assets con error tras el arreglo | 0 (solo `favicon.ico`, cosmético) |
| Errores de página / excepciones JS | 0 |
| Canvas de Three.js | 812 × 609 px, renderizando |
| Audio de prueba | `demo/demo_es.wav`, **10.96 s** |
| Bucle de render | **144 fps** |
| Visemas distintos activados | **8 de 15**: `sil` `PP` `DD` `kk` `aa` `E` `I` `O` |

Traza de visema activo contra el tiempo del audio:

```
0.15s:E  0.61s:E  1.08s:sil  1.54s:I  2.04s:E  2.55s:E  3.04s:E  3.52s:I
3.99s:kk 4.45s:E  4.92s:DD   5.42s:E  5.90s:E  6.36s:E  6.84s:E
```

La boca sigue al audio y distingue vocales de oclusivas sin ningún dato del
proveedor de voz. El sesgo hacia `E` es esperable: `demo_es.wav` se generó con
espeak-ng, que es muy plano. **Hay que repetir la medición con un `.wav` de TTS
neural real antes de dar por buena la calidad percibida**; lo que esta corrida
demuestra es que el driver funciona y a qué costo de render, no que suene bien.

### Modo A · visemas de Azure — **no medido**

No se pudo ejecutar. Requiere `spikes/voice_latency/out/azure_visemes.json`, que
no existe porque US1 sigue sin recurso de Azure Speech creado (ver
`us1-modelos-voz.md` §4). El botón "A · Visemas Azure" permanece deshabilitado
sin ese archivo, que es el comportamiento correcto del spike.

**Consecuencia:** la comparación A contra B que pide §1.2 está a medias. Lo que
sí quedó demostrado es lo que importa para no bloquear: **B funciona solo**, sin
credenciales y sin proveedor decidido.

### Los 15 visemas Oculus — **no verificado**

No hay ningún `.glb` en el repo, así que la escena usó la boca de prueba de
respaldo. El panel de diagnóstico no pudo confirmar morph targets de un avatar
real. Falta descargar una malla de RocketBox u Open Source Avatars y repetir.

## 5. Decisión propuesta

- **Malla:** Microsoft RocketBox (MIT, gratis, con visemas). MetaPerson como
  mejora si queremos nuestro rostro.
- **Renderizado:** Three.js plano dentro de Astro, sin isla React.
- **Lip-sync:** driver **A** (visemas de Azure) si US1 se cierra con Azure;
  driver **B** (`wawa-lipsync`) como respaldo universal — y obligatorio si
  terminamos usando voz clonada.

Con eso, `AvatarPort.visemes_for()` queda trivial en el caso A (traducir IDs) y
en el caso B ni siquiera toca el backend: el navegador deriva los visemas del
audio que ya está reproduciendo.

## 6. Propuesta de cierre de `AGENTS.md` §1.2

Con lo medido el 20/09/2026, **§1.2 se puede cerrar en dos de sus tres filas**.

| Pieza de §1.2 | ¿Cerrable hoy? | Respaldo |
|---|---|---|
| **Renderizado** | **Sí — Three.js plano, sin isla React** | Medido: el spike renderiza a 812×609 y **144 fps** con `three@0.186.0` puro, sin React en ninguna parte |
| **Lip-sync** | **Sí — `wawa-lipsync` (driver B) como base** | Medido: 8 visemas distintos sobre 10.96 s de audio en español, sin datos del proveedor de voz. Funciona pase lo que pase en §1.1 |
| **Malla del avatar** | **No todavía** | RocketBox sigue siendo la recomendación documental, pero **no se ha cargado un solo `.glb`**: los 15 visemas Oculus están sin verificar |

### Redacción propuesta para §1.2

> **Avatar 3D — decidido parcialmente (20/09/2026).**
> **Renderizado: Three.js plano** dentro de Astro, sin isla React — medido a
> 144 fps en `spikes/avatar_lipsync/`.
> **Lip-sync: `wawa-lipsync`** (driver por audio) como base, medido en español y
> **agnóstico al proveedor de voz**. Los visemas nativos de Azure quedan como
> mejora opcional **si** §1.1 se cierra con Azure y **si** se confirma que los
> emite en `es-CO` — hoy ese supuesto sigue sin verificar.
> **Malla: pendiente.** RocketBox es la candidata; falta cargar un `.glb` real y
> confirmar los 15 visemas Oculus.

**Lo que esto desbloquea:** elegir `wawa-lipsync` como base **quita la
dependencia cruzada** que §1.2 tenía con §1.1. El avatar ya no espera a que se
decida la voz. Ese era el punto del spike y quedó demostrado con números.

**Lo que falta, en orden:** (1) descargar una malla de RocketBox y verificar sus
morph targets; (2) repetir la medición del driver B con un `.wav` de TTS neural
en vez del `demo_es.wav` de espeak-ng, que es demasiado plano para juzgar
calidad percibida.

## Fuentes

- [Ready Player Me — cierre (Wikipedia)](https://en.wikipedia.org/wiki/Ready_Player_Me)
- [Microsoft RocketBox (MIT)](https://github.com/microsoft/Microsoft-Rocketbox)
- [Open Source Avatars — GLB CC0](https://www.opensource3dassets.com/en/gallery)
- [Avatar SDK / MetaPerson — precios](https://avatarsdk.com/pricing-cloud/)
- [Avaturn — precios](https://avaturn.me/pricing)
- [HeyGen LiveAvatar](https://www.liveavatar.com/)
- [wawa-lipsync](https://wawasensei.dev/tuto/real-time-lipsync-web)
- [TalkingHead](https://github.com/met4citizen/TalkingHead)
- [Azure — visemas](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis-viseme)
