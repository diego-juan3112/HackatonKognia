# Crear el avatar propio en VRoid Studio (objetivo: 30 min)

Meta: hombre joven estilo anime, pelo negro corto muy rizado (suelto arriba,
corto a los lados), cejas marcadas, barba corta y bigote, piel morena clara,
chaqueta blanca con detalles azules y negros (alternativa: sudadera gris).

Contrastado el 09/10/2026 con la ayuda oficial de VRoid Studio
(`vroid.pixiv.help`, artículos enlazados al final). Marcas:

- **[OK]** lo dice la documentación oficial vigente.
- **[SIN VERIFICAR]** lo escribo de memoria de la aplicación; el nombre exacto
  del control o el valor pueden variar según la versión. No se pudo abrir VRoid
  Studio para comprobarlo.

VRoid Studio es gratis: https://vroid.com/en/studio (también en Steam). Usar la
versión estable actual (2.x); la herramienta de pegatinas exige 2.11 o superior
**[OK]**.

## Antes de empezar (decisión de 1 minuto)

| Camino | Cuándo | Licencia del resultado |
|---|---|---|
| **A. Modelo nuevo, base masculina** (recomendado) | Siempre que se quiera publicar el `.vrm` en el repo sin condiciones | Tuya; tú eliges los permisos al exportar |
| B. Partir de un modelo de muestra (AvatarSample_C / VRoidPreset) | Si falta tiempo: ya trae chaqueta y pelo corto oscuro | Sigue bajo las condiciones de pixiv: se puede editar y redistribuir, pero **no declararlo CC0 ni cobrar por él** **[OK]** |

Los modelos de muestra se descargan desde "Sample Models" en la pantalla de
selección de modelo **[OK]**.

## Cronograma

### 0:00–0:02 — Crear el modelo
1. Abrir VRoid Studio → crear modelo nuevo → elegir la base **masculina**
   **[SIN VERIFICAR: texto exacto del botón]**.
2. Guardar ya (`Ctrl+S`) como `kognia-avatar.vroid`. Guardar tras cada bloque.

### 0:02–0:08 — Rostro y piel (pestaña **Face**)
La pestaña Face tiene estas categorías **[OK]**: Face Sets, Eyes Sets, Irises,
Eye Highlights, Scleras, Eyebrows, Eyelid, Eyeliner, Eyelashes, Nose, Mouth,
Mouth Inside, Lips, Cheeks, Skin, Face Paint, Expression Editor. Cada elemento
tiene **Color** y **Parameters** en el panel derecho **[OK]**.

1. **Face Sets**: elegir el conjunto masculino más adulto (mandíbula marcada,
   ojos estrechos). Ahorra casi todos los deslizadores.
2. **Skin** → Color: tono moreno claro. Punto de partida `#D9A77E`, sombra
   (Dark Color) `#B27A55` **[valores orientativos]**. El color de piel se
   propaga solo a nariz, párpado y cuerpo **[OK]**.
3. **Eyebrows**: elegir un preajuste grueso y recto; Color negro `#1A1614`.
   En Parameters, subir grosor/tamaño y bajarlas un poco hacia el ojo
   **[SIN VERIFICAR: nombres de los deslizadores]**.
4. **Irises**: marrón oscuro `#3A2418`.
5. Deslizadores de forma de cara **[SIN VERIFICAR: nombres]**: bajar el tamaño
   de los ojos y subir su separación mínima para que no parezca niño; ensanchar
   mandíbula y barbilla; bajar "cheek" (mejillas redondas); nariz algo más
   larga y marcada. Regla práctica: ojos más pequeños + mandíbula más ancha =
   adulto.
6. **Cheeks** y **Lips**: quitar el rubor (opacidad a 0 o elemento vacío).

### 0:08–0:16 — Pelo corto rizado (pestaña **Hairstyle**)
No encontré en la documentación ningún preajuste llamado "curly" (la búsqueda
en la ayuda oficial devuelve 0 resultados); los rizos hay que aproximarlos.

**Paso 1 — base rápida (2 min).** Categorías **[OK]**: Hairstyle Sets, Overall
Hair, Front, Back, Extensions, Sides, Ahoge, Extra. Elegir un **Hairstyle Set
corto masculino** de lados cortos; si hay uno despeinado u ondulado, ese.
Color: Main `#141210`, Highlight `#3A3230` **[OK: Main Color / Highlight Color]**.
En "Sides", elegir lo más corto o ninguno para marcar el degradado lateral.

**Paso 2 — rizos procedurales arriba (5 min).** **[OK]** el flujo; los valores
son orientativos:
1. Categoría **Extra** (o Front) → pestaña **Custom** → **+** → seleccionar el
   elemento nuevo → **Edit Hairstyle**.
2. **Add Procedural Hair Guides**. Aparece un grupo en la lista de la izquierda;
   al seleccionarlo, sus parámetros salen a la derecha: cantidad de mechones,
   sección (cross-section), **twist** y más **[OK]**.
3. Ajustar: cantidad 25–35; longitud corta; **Twist alto** (es lo que enrosca
   el mechón); grosor medio; sección triangular o rombo; y en la curva del
   mechón dibujar una "S" para que se doble sobre sí mismo
   **[SIN VERIFICAR: nombres y rangos exactos]**.
4. Con los puntos verdes de la guía, encoger la malla guía para que cubra solo
   la coronilla y la parte superior, no los lados **[OK: la guía se deforma con
   los puntos verdes]**.
5. Clic derecho sobre el grupo → **Clone**; en el clon cambiar un poco
   longitud, twist y desplazamiento para romper la regularidad. Dos o tres
   grupos bastan **[OK: Clone existe en el menú contextual]**.
6. Bajar **Smoothness** de los grupos rizados a 6–8: muchos mechones finos
   disparan los polígonos; la documentación mide 5496 → 1304 polígonos al pasar
   de smoothness 15 a 7 **[OK]**.

**Si los rizos no salen en 5 min (plan B, 1 min):** dejar el Hairstyle Set
corto y añadir 2–3 elementos de **Extra** y **Ahoge** con puntas hacia arriba
y hacia fuera. Lectura "pelo revuelto con volumen", que a tamaño de busto se
entiende como rizado.

**Plan C, solo para uso local:** preajustes de pelo rizado de BOOTH (ver
informe de candidatos); sus licencias prohíben redistribuirlos.

### 0:16–0:21 — Barba y bigote (textura de la cara)
1. Face → **Face Paint** → Custom → **+** → **Edit Texture** **[OK: Face Paint
   existe y se edita con Edit Texture]**. Así la barba queda en su propia capa
   y no ensucia la piel.
2. En el editor de texturas **[OK]**: herramienta **Brush**, activar **Mirror**
   (simetría), color `#1A1614`, **Brush Opacity** 50–60 %, ancho pequeño.
   Se puede pintar directamente sobre el modelo 3D o sobre la textura 2D.
3. Pintar, de dentro hacia fuera: bigote fino sobre el labio, perilla bajo el
   labio, y una banda por la línea de la mandíbula que suba hasta la patilla.
   Dos pasadas donde deba ser más densa (mentón y bigote).
4. Pasar **Blur** por el borde superior de la barba para que no parezca
   pegatina **[OK: Blur existe]**. Corregir con **Eraser**.
5. Atajo si no hay pulso: pintar la barba en cualquier editor sobre la textura
   exportada (clic derecho sobre la capa → Export, PNG) y volver a importarla
   (Import) **[OK]**; o colocarla con la herramienta **Sticker** (2.11+) **[OK]**.
   Hay un paquete gratuito con dos barbas ya dibujadas, CC BY 4.0, "Winter Male
   Skin Base" de aemeth (https://booth.pm/en/items/2534286): exige citar al
   autor si se redistribuye.

Nota: la barba pintada sigue la boca al hablar porque va en la malla de la
cara; no hace falta nada más para el lip-sync.

### 0:21–0:27 — Ropa blanca con detalles azules (pestaña **Outfit**)
1. Tops: elegir una chaqueta o abrigo de cuello alto; para la alternativa, la
   sudadera con capucha **[SIN VERIFICAR: nombres de las prendas]**.
2. En el panel derecho, **Color** → blanco `#F2F4F7`. Si la prenda base es
   oscura y el color no llega a blanco, entrar en **Edit Texture** y trabajar
   con "Apply color when editing" y "Use Color Calibration" **[OK]**, o rellenar
   con **Bucket**. La vía oficial para pasar de negro a blanco sin perder
   sombras es un mapa de degradado en un editor externo **[OK]**, pero no cabe
   en 30 min.
3. Detalles: capa nueva en Edit Texture → Brush azul `#1E6BFF` con Mirror
   activo sobre la textura 2D: franja en mangas, borde del cuello y cremallera.
   Remates en negro `#111318`. Líneas rectas: pintar en la vista 2D, no en el 3D.
4. Pantalón y calzado oscuros (`#111318`) para que la chaqueta destaque.
5. Al cerrar el editor, guardar la prenda como elemento personalizado (los
   editados salen marcados con `*`) **[OK]**.

Solo se ve el busto en la consola: no invertir tiempo de cintura para abajo.

### 0:27–0:30 — Exportar a VRM
1. Icono de exportación arriba a la derecha → **Export VRM** **[OK]**.
2. En la pantalla de exportación se pueden reducir **polígonos, materiales y
   huesos** **[OK]**. Valores recomendados **[SIN VERIFICAR: nombres exactos]**:
   - Reduce polygons: activar "Delete transparent meshes"; bajar los polígonos
     del pelo hasta quedar por debajo de ~40 000 triángulos en total.
   - Reduce materials: fusionar a **8 o menos** (atlas de texturas) y
     resolución de atlas **2048**. Es lo que más baja el peso del archivo.
   - Reduce bones: dejar los huesos del pelo; reducirlos solo si el pelo rizado
     tiembla demasiado.
3. **Export** → elegir formato **[OK: VRM0.0 o VRM1.0]**. El cargador de este
   proyecto acepta los dos. Recomendado **VRM0.0**: es el formato de los dos
   modelos VRoid ya probados aquí (`avatar-sample-a`, `avatar-sample-c`). VRM1.0
   también funciona (probado con `seed-san`), pero no con una exportación de
   VRoid Studio.
4. Campos obligatorios **[OK]**: título y creador (VRM0.0) o nombre del avatar
   y creador (VRM1.0). En permisos, permitir redistribución si se va a subir al
   repo público.
5. Las expresiones se exportan solas: no hace falta tocar el Expression Editor.
   Un VRM de VRoid trae las cinco vocales y el parpadeo que usa el lip-sync
   (`aa ih ou ee oh`, `blink`); comprobado en los dos modelos VRoid de esta
   carpeta.

## Conectarlo a la consola

**Dónde se ejecuta:** en PowerShell.

```powershell
Copy-Item "$HOME\Documents\kognia-avatar.vrm" "C:\dev\kognia\A-front\web\public\avatars\kognia-avatar.vrm"
```

Después, en `C:\dev\kognia\A-front\web\.env`, añadir la línea:

```
PUBLIC_AVATAR_URL=/avatars/kognia-avatar.vrm
```

y arrancar:

```powershell
cd C:\dev\kognia\A-front\web
npm run dev
```

Abrir http://localhost:4321/consola?avatarDemo y comprobar que la boca se mueve.
Si el archivo pesa más de ~16 MB, volver a exportar con atlas a 2048 o 1024.
Si se sube al repo, añadir su entrada en [`LICENSE.md`](./LICENSE.md).

## Fuentes oficiales consultadas

- Exportar VRM: https://vroid.pixiv.help/hc/en-us/articles/15760756822297
- Editar la cara: https://vroid.pixiv.help/hc/en-us/articles/4406164546969
- Editor de texturas: https://vroid.pixiv.help/hc/en-us/articles/4405430561817
- Importar/exportar texturas: https://vroid.pixiv.help/hc/en-us/articles/360015449634
- Pegatinas (v2.11): https://vroid.pixiv.help/hc/en-us/articles/55426007561113
- Calibración de color: https://vroid.pixiv.help/hc/en-us/articles/4405438979225
- Pelo por combinación de piezas: https://vroid.pixiv.help/hc/en-us/articles/4405086656153
- Personalizar peinados (pelo procedural): https://vroid.pixiv.help/hc/en-us/articles/900005678786
- Reducir polígonos del pelo: https://vroid.pixiv.help/hc/en-us/articles/360013210674
- Elementos personalizados: https://vroid.pixiv.help/hc/en-us/articles/900005583186
- Negro a blanco con mapa de degradado: https://vroid.pixiv.help/hc/en-us/articles/360015474813
- Modelos de muestra y sus condiciones: https://vroid.pixiv.help/hc/en-us/articles/31627266179865 y https://vroid.pixiv.help/hc/en-us/articles/4402394424089
