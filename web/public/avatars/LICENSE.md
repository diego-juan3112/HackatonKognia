# Licencias de los modelos de avatar

Los archivos `.vrm` de esta carpeta **no** están cubiertos por la licencia del
repositorio. Cada uno conserva la licencia de su autor, que se resume abajo.
Si se reutiliza el repo, estas condiciones viajan con los archivos.

Verificado el 09/10/2026.

## `avatar-sample-a.vrm` — AvatarSample_A (modelo por defecto)

| | |
|---|---|
| Autor | pixiv Inc. (VRoid Project). Metadatos del archivo: `author: "VRoid"`, `title: "AvatarSample_A"` |
| Formato | VRM 0.x, 15 096 320 bytes |
| SHA-256 | `b86b0b8a66d48911431d6f920a5211a974226f83aa672eca3f3dfade58ac346e` |
| Página oficial del modelo | https://hub.vroid.com/en/characters/2843975675147313744/models/5644550979324015604 |
| Condiciones de uso (fuente oficial) | https://vroid.pixiv.help/hc/en-us/articles/4402394424089 |
| Resumen oficial de modelos de muestra | https://vroid.pixiv.help/hc/en-us/articles/4402614652569 |
| Copia descargada de | https://github.com/madjin/vrm-samples (`vroid/stable/AvatarSample_A.vrm`), sin modificar |

**No es CC0.** Es una licencia propia de pixiv ("conditions of use"). Texto
oficial relevante (en inglés, tal como lo publica pixiv):

> This model's .vroid and VRM files can be used by anyone in any kind of
> activity, be it for-profit or not. There is no need to credit the original
> creator when using this sample model.

> While copyright is not waived, you can alter, distribute, and do many more
> things with them.

> You can use this model in any way unless it is clearly prohibited under
> Prohibited Conduct.

Conductas prohibidas que nos afectan:

- Redistribuir el modelo declarándolo **CC0** (dominio público).
- Redistribuir el `.vrm` (o sus texturas) **a cambio de un pago**.
- Usar sus datos para construir un servicio de creación de personajes.
- Dar a entender que pixiv respalda o recomienda un producto o evento.
- Usos ilegales, discriminatorios, extremistas o de proselitismo político o
  religioso excesivo.

pixiv advierte que las condiciones pueden cambiar. Si se va a usar más allá de
la demo, volver a leer la fuente oficial.

Nota de procedencia: VRoid Hub exige iniciar sesión para descargar, así que el
archivo se tomó de un espejo público en GitHub. Los metadatos embebidos
coinciden con el modelo oficial, pero **no se comparó byte a byte** contra la
descarga de VRoid Hub.

## `seed-san.vrm` — Seed-san (alternativa)

| | |
|---|---|
| Autor | VirtualCast, Inc. |
| Formato | VRM 1.0, 10 917 800 bytes |
| SHA-256 | `624d0d554bc205bbdc33e22a68a2c3c20edebb3e573011ead8878a65e5329b23` |
| Fuente oficial | https://github.com/vrm-c/vrm-specification/tree/master/samples/Seed-san (repositorio del VRM Consortium), sin modificar |
| Licencia | VRM Public License 1.0 — https://vrm.dev/licenses/1.0/ |

Permisos declarados en los metadatos del propio archivo (`VRMC_vrm.meta`):

| Campo | Valor |
|---|---|
| `allowRedistribution` | `true` |
| `modification` | `allowModificationRedistribution` |
| `commercialUsage` | `corporation` |
| `avatarPermission` | `everyone` |
| `creditNotation` | **`required`** |
| `copyrightInformation` | `VirtualCast, Inc.` |

**Crédito obligatorio.** Si este modelo se muestra, debe aparecer la
atribución: *"Seed-san model by VirtualCast, Inc."*

## Código

`three` (MIT) y `@pixiv/three-vrm` (MIT) se instalan por npm; sus licencias
están en `node_modules/`.
