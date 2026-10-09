# Avatar 3D (VRM)

Modelos que carga `web/src/avatar/`. Licencias en [`LICENSE.md`](./LICENSE.md).

| Archivo | Modelo | Formato | Tamaño |
|---|---|---|---|
| `avatar-sample-c.vrm` | AvatarSample_C (pixiv / VRoid), masculino — **por defecto** | VRM 0.x | 13,1 MB |
| `avatar-sample-a.vrm` | AvatarSample_A (pixiv / VRoid), femenino — alternativa | VRM 0.x | 15,1 MB |
| `seed-san.vrm` | Seed-san (VirtualCast) — alternativa, crédito obligatorio | VRM 1.0 | 10,9 MB |

## Cambiar de modelo

Sin tocar código. En `web/.env`:

```
PUBLIC_AVATAR_URL=/avatars/seed-san.vrm
```

Sirve cualquier `.vrm` (0.x o 1.0), local o por URL con CORS. También se puede
pasar por código: `mountAvatar(canvas, { modelUrl })`. Orden de prioridad:
`opts.modelUrl` → `PUBLIC_AVATAR_URL` → `avatars/avatar-sample-c.vrm`.

Un modelo exportado desde VRoid Studio funciona tal cual: copiarlo aquí y
apuntar `PUBLIC_AVATAR_URL` a él. Receta para crear uno propio en ~30 min:
[`CREAR-AVATAR-VROID.md`](./CREAR-AVATAR-VROID.md). Si solo se va a usar uno, borrar el otro
`.vrm` para no cargar el repo.

## API

```ts
const { mountAvatar } = await import("../avatar"); // carga perezosa
const avatar = await mountAvatar(canvas, { onProgress: (p) => {} }); // p: 0..1

avatar.setState("listening"); // idle | connecting | listening | thinking | speaking | renewing | error
avatar.setMouthLevel(0.6);    // 0..1; hay que enviarlo de forma continua, decae solo en ~0,2 s
avatar.attachAnalyser(node);  // AnalyserNode del audio que suena: boca por espectro
avatar.resetCamera();         // vuelve al encuadre de busto tras arrastrar
avatar.dispose();             // libera GPU, observers y listeners

// Extras opcionales
avatar.setDemoSpeech?.(true); // boca con un patrón sintético, sin audio
avatar.wave?.();              // repite el saludo
avatar.getDebugInfo?.();      // fps, triángulos, pesos de boca, expresiones
```

El `<canvas>` debe tener tamaño por CSS (ancho y alto); el búfer de dibujo lo
sigue con `ResizeObserver`. El fondo es transparente.

Si WebGL no existe o el modelo no carga, `mountAvatar` rechaza con un
`AvatarError` (`code`: `webgl-unavailable`, `model-load-failed` o
`invalid-model`).

## Cómo probarlo

**Dónde se ejecuta:** en PowerShell, dentro de `C:\dev\kognia\A-front\web`.

```powershell
cd C:\dev\kognia\A-front\web
npm run dev
```

Abrir la consola en http://localhost:4321/consola y:

- Añadir `?avatarDemo` a la URL para ver la boca moverse sin micrófono.
- Mover el puntero: los ojos y la cabeza lo siguen. Arrastrar sobre el avatar
  orbita la cámara.
- Desde la consola del navegador, si la página guarda el handle, llamar a
  `setState("thinking")`, `setState("error")`, etc.

## Qué hace

- Reposo procedural: respiración, balanceo de cadera, torso y cabeza,
  micro-movimientos de la mirada, dedos relajados.
- Parpadeo aleatorio (a veces doble).
- Saludo con la mano derecha al montar.
- Huesos de resorte (pelo y ropa) del propio VRM.
- Expresiones por estado, siempre interpoladas.
- Lip-sync con las cinco vocales VRM (`aa ih ou ee oh`).
- Se pausa cuando la pestaña está oculta o el canvas sale de pantalla.
- Con `prefers-reduced-motion`: sin saludo, sin seguimiento del puntero y con
  el balanceo reducido al 20 %. El parpadeo y la boca se mantienen.
