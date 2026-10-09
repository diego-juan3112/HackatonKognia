# Especificación del Reto 01 — Agente Vocal Cognitivo

Contrato vigente · versión 1 · 2026-10-09 · entrega **2026-10-09 16:00** (America/Bogota).

Qué se construye, cómo se sabrá que está hecho y qué queda fuera. Es la spec de la
que cuelgan [08](08-contrato-voz-en-vivo.md) (voz), [09](09-datos-en-vivo-datos-gov-co.md)
(datos), [10](10-modelos-afecto-y-recuperacion.md) (modelos, afecto y recuperación) y
[12](12-guia-de-trabajo-2-personas.md) (cómo trabajamos de a dos). Las decisiones
`D-xx` están en [00](00-contexto-y-decisiones.md) §5 y las reglas `R-xx` en
[AGENTS.md](../AGENTS.md).

## 1. El reto en una frase

Un agente conversacional **por voz**, desplegado en una **URL pública**, que habla en
vivo con la «Relación de IPS públicas y privadas según el nivel de atención y capacidad
instalada» de datos.gov.co **consumida por API**, muestra la **transcripción diarizada**
y el análisis de **sentimiento y emociones** mientras ocurre la conversación, y responde
con baja latencia. El jurado lo ejecuta desde la URL en 10 minutos (guion P1–P6, §10).

## 2. Fuentes y supuestos

Fuentes: las cinco capturas del reto, las tres transcripciones del arranque, el libro
`V2.xlsx` (leído por el paquete sdd_ips) y ese mismo paquete (retirado del repo con D-23;
queda en el historial de git).

**Supuestos confirmados por el equipo el 2026-10-09:**

| # | Supuesto |
|---|---|
| 1 | El reto es lo que muestran las capturas. La hoja habla de «ocho requisitos» pero solo R08 está poblada y remite a una hoja `02 CRITERIOS` que no existe: **no se inventan requisitos**. |
| 2 | El contexto del agente es **solo la API** de datos.gov.co. No hay documento sorpresa ni subida de archivos. **Riesgo aceptado (RETO-M05):** si el jurado entregara un archivo, el MVP no lo carga (issue B-11). |
| 3 | «Acciones» = consultar IPS y corregir la conversación. Sin agendar citas ni crear solicitudes. |
| 4 | Equipo de dos personas; plazo 16:00; se congela a las 14:30. |
| 5 | Voz con las APIs pagas de OpenAI y Gemini (prioridad); Cartesia, contratada el 2026-10-09, aporta una **voz clonada opcional** sobre el mismo motor ([08](08-contrato-voz-en-vivo.md) §15; D-20 propuesta); la voz del motor sigue siendo la base y el respaldo. |
| 6 | Psicología adaptativa y emoción acústica son **Must**. |
| 7 | Sin base de datos, sin RAG, sin embeddings, sin cédula. |
| 8 | Vercel con Dockerfile de respaldo; `main` es la rama de integración y de producción. |

**Códigos.** Los del reto se citan con prefijo `RETO-` (RETO-R08, RETO-P4, RETO-M07) para
no chocar con las reglas `R-xx` del repo. Esta spec usa `F-xx` (funcional), `NF-xx`
(no funcional) y `A-xx` (aceptación, los mismos IDs del paquete sdd_ips).

## 3. Reconciliación con el paquete sdd_ips (histórico)

El paquete sdd_ips (generado por GPT el 2026-10-09) fue **insumo** de estos documentos. **El
paquete sdd_ips se retiró del repo (D-23); queda en el historial** (último commit con él:
`0a5a625`). Los contratos vigentes son `docs/00–13`. La tabla registra qué se tomó de él.

| Pieza de sdd_ips | Tratamiento | Vive en |
|---|---|---|
| C-IPS (5 herramientas y sus límites), C-EVIDENCE, mapeo de campos, grano de datos | **Adoptado** (+ `top_n`, orden y `trace`) | [09](09-datos-en-vivo-datos-gov-co.md) |
| C-STATE, C-RECOVERY | **Adoptados y adaptados**: estado en el navegador; «intento de modelo» = intento de **motor**; se suma la conmutación de motor | [10](10-modelos-afecto-y-recuperacion.md), [08](08-contrato-voz-en-vivo.md) |
| C-AFFECT (salvaguardas) | **Adoptado** como salvaguardas; el alcance (voz + estilo adaptativo) es decisión del equipo (D-16) | [10](10-modelos-afecto-y-recuperacion.md) |
| Aceptación A-01…A-20, métricas y protocolo de benchmark | **Adoptados**; se añaden A-21…A-26 | §7–§8 |
| Reglas IPS-R01…R12 | **Fusionadas** en R-22…R-31 | [AGENTS.md](../AGENTS.md) |
| Sobre de contexto neutral, prompt v1, taxonomía de feedback, guion de demo, backlog B-01…B-11, hitos 14:30/15:00/15:45 | **Adoptados** (backlog adaptado) | [10](10-modelos-afecto-y-recuperacion.md), [12](12-guia-de-trabajo-2-personas.md) |
| Estado, caché y eventos en PostgreSQL; pgvector + E5 (D-14 de sdd_ips); `002_ips.sql` | **Descartado** (sin BD): caché en memoria; feedback y trazas a LangSmith; B-01 queda en backlog | — |
| Voz base = STT del navegador + Azure TTS (D-11 de sdd_ips) y API `/v1/turns` con audio base64 | **Movido a motor 3 / plan B** (cascada) | backlog |
| «No desplegar un modelo de psicología» (D-16 de sdd_ips) | **Reemplazado** por la decisión del equipo (D-16), conservando sus salvaguardas | [10](10-modelos-afecto-y-recuperacion.md) |

## 4. Alcance (MoSCoW)

| | Contenido |
|---|---|
| **Must** | **Voz (20%):** motor en tiempo real es-CO con OpenAI y Gemini + selector, interrupciones, reconocimiento previo a consultas, HUD de latencia, modo texto · **Datos en vivo:** brief + 5 herramientas, sobre de evidencia, normalización de entidades, panel «API en vivo» (SoQL, ms, filas, fuente y corte, «Reconsultar») · **Recuperación:** ambigüedad, correcciones («Corregir lo que dije»), reintentos acotados, **conmutación de motor**, «Repetir» · **Transcripción (15%):** roles + marcas de tiempo + texto realmente escuchado · **Afecto/psicología:** analista texto ∥ voz, panel de emociones, estilo adaptativo visible, «Más directo» · **UX/demo (25%):** consola Astro cuidada, aviso de IA y consentimiento · **Entrega (10%):** URL estable, repo accesible, README de 1 página |
| **Should** (si falta tiempo cae primero lo último) | **Voz clonada con Cartesia** (seleccionable; degrada a la voz del motor) · descargar transcripción · entidades visibles en la transcripción («original → corregido») · caché de respaldo del brief · `compare_ips` · paridad total del segundo motor · refinamiento multi-hablante con Gemini |
| **Won't (hoy)** | Subir documentos · BD, RAG, embeddings · cédula · avatar 3D · Twilio · Azure Container Apps · motor en cascada · *hedged requests* · turno semántico propio · text-to-SQL libre · agendar citas |

## 5. Requisitos funcionales

| ID | Requisito | Prioridad | Origen |
|---|---|---|---|
| F-01 | Abrir la URL HTTPS, iniciar el micrófono tras un gesto del usuario, escuchar aviso de IA (visible y hablado), saludo y **brief en vivo** | Must | RETO-P1, P3 |
| F-02 | Buscar IPS por departamento, municipio, nombre, naturaleza y nivel registrado; ver el detalle de una sede | Must | RETO-P4 (detalle fino) |
| F-03 | Contar prestadores y sedes, sumar y comparar capacidad con unidad explícita | Must | RETO-P4 (resumen) |
| F-04 | Mostrar fuente, corte y límites de la fuente; decir qué no se sabe | Must | RETO-P4 (fuera del contexto) |
| F-05 | Mantener contexto entre turnos; reparar entidades mal oídas o corregidas por el usuario | Must | RETO-P4 |
| F-06 | Interrumpir, reintentar de forma acotada, **conmutar de motor** y ofrecer una siguiente acción útil | Must | RETO-P4, rúbrica de voz |
| F-07 | Transcripción con rol, marcas de tiempo, parcial/final y texto realmente escuchado | Must | RETO-P5 |
| F-08 | Análisis de sentimiento y emociones en vivo, por texto y por voz, con panel | Must | RETO-P5 |
| F-09 | Estilo adaptativo («psicología»): preferencia explícita y estado inferido, con motivo visible | Must | decisión del equipo |
| F-10 | Selector de motor (OpenAI Realtime / Gemini Live) y HUD de latencia con motor y modelo activos | Must | RETO-P6, rúbrica de voz |
| F-11 | Panel «API en vivo»: SoQL, ms, filas, fuente y corte, «Reconsultar» | Must | objetivo del reto |
| F-12 | Modo texto de respaldo y controles: Corregir lo que dije, Más directo, Repetir, Reiniciar | Must | RETO-P4, accesibilidad |

## 6. Requisitos no funcionales

| ID | Requisito |
|---|---|
| NF-01 | **Latencia** según §8: primer audio útil, reconocimiento previo, parada por interrupción, parcial visible, plazo de primer plano. |
| NF-02 | **Disponibilidad en la demo** (RETO-M07: sin demo local y un único reintento de 2 min): arranque en caliente, `GET /health` antes del jurado, calentamiento al conectar. |
| NF-03 | **Privacidad:** aviso de IA, consentimiento para el análisis de voz, sin audio guardado, estado efímero y botón de reinicio (R-26). |
| NF-04 | **Seguridad:** secretos solo en el backend; el navegador recibe credenciales efímeras; sesión anónima firmada; límites de tasa (R-28). |
| NF-05 | **Navegadores:** Chrome y Edge actuales con micrófono sobre HTTPS; mensaje claro en cualquier otro. |
| NF-06 | **UX y accesibilidad:** contraste, subtítulos con `aria-live`, uso por teclado, español es-CO. |
| NF-07 | **Entrega** (RETO-E01–E03, R08, M04): URL estable de producción (no *preview*), repo público o con acceso a jueces, README de 1 página con declaración de uso de IA (R-31), sin secretos en el historial. |
| NF-08 | **Atribución:** «Ministerio de Salud y Protección Social — REPS, CC BY-SA 4.0, corte 2022-11-05» visible en la interfaz y dicha en voz cuando se da una cifra. |
| NF-09 | **Observabilidad:** trazas y feedback en LangSmith (opcional); ni audio ni datos personales innecesarios en logs. |

## 7. Escenarios de aceptación

Prioridad **P0** = debe pasar en la URL pública, con proveedores reales y un navegador ajeno
a la sesión de desarrollo. Una capacidad que falla se registra tal cual; el modo texto **no**
cuenta como voz aprobada.

| ID | P | Dado / cuando | Resultado observable | Req. |
|---|---|---|---|---|
| A-01 | P0 | Un visitante abre la URL HTTPS | Carga sin errores ni instalación; el permiso del micrófono se pide solo tras pulsar Iniciar; error útil si lo rechaza | F-01 |
| A-02 | P0 | Inicia la voz | Aviso de IA visible y hablado; brief hablado ≤ 20 s con conteos **reales y en vivo** y la fecha de corte; 3–5 preguntas sugeridas visibles | F-01, F-04 |
| A-03 | P0 | Pide IPS públicas de un municipio o departamento | Filtros exactos por herramienta; ≤ 3 resultados hablados y el resto en pantalla; fuente visible | F-02 |
| A-04 | P0 | Pide «San José» sin ubicación | Pregunta ubicación o sede; nunca elige la primera coincidencia | F-02, F-05 |
| A-05 | P0 | Pregunta cuántos prestadores hay | Agregado de prestadores **distintos**, no 41.427 filas; 9.320 solo para esta versión de la fuente | F-03 |
| A-06 | P0 | Compara las camas «Adultos» de dos sedes resueltas | Mismo tipo y corte; cantidades y unidades de la fuente; nulos o ambiguos quedan desconocidos | F-03 |
| A-07 | P0 | Pide un nivel o teléfono ausente | Dice que no está registrado; no inventa | F-04 |
| A-08 | P0 | Pregunta «¿hay cama disponible hoy?» o «la más cercana» | Explica que la fuente no tiene disponibilidad ni geolocalización; ofrece lo que sí puede consultar | F-04 |
| A-09 | P0 | Corrige «Medellín» por «Melgar» | Original preservado, corrección visible, evidencia anterior invalidada, nueva consulta con la localidad confirmada | F-05 |
| A-10 | P0 | Dice «la segunda» tras unos resultados y luego se reconecta o cambia de motor | La entidad sigue ligada a esos resultados | F-05, F-06 |
| A-11 | P0 | Interrumpe mientras el agente habla | La reproducción se detiene (p95 ≤ 200 ms), se descarta el audio tardío y el nuevo turno atiende la tarea corregida; la transcripción conserva solo lo escuchado | F-06, F-07 |
| A-12 | P0 | Se simula un timeout de la fuente o un 429 del proveedor con un doble | Reintento o respaldo acotado, fuente/caché visible, sin bucles ni respuestas duplicadas | F-06 |
| A-13 | P0 | Usuario y agente intercambian tres turnos | Transcripción con rol, marcas de tiempo, parcial/final e historial de correcciones | F-07 |
| A-14 | P0 | Dice «me estás confundiendo, sé más directo» | La siguiente respuesta es más breve; el sentimiento se muestra como estimación; los hechos no cambian | F-08, F-09 |
| A-15 | P0 | Se ejecuta el protocolo de benchmark (§8) | p50/p95 reales con tamaño de muestra, motor y modelo, despliegue y fallos publicados | NF-01 |
| A-16 | P0 | El motor principal falla tras una consulta válida | Un único cambio de motor reutiliza contexto y evidencia; sin resultados inventados ni consulta duplicada | F-06 |
| A-17 | P0 | Solicitud duplicada, evento tardío o sesión ajena | Se reutiliza el mismo turno, se descarta el evento tardío y los datos ajenos son inaccesibles | NF-04 |
| A-18 | P0 | La fuente no responde y solo hay caché parcial | Estado «no disponible/parcial» explícito; ningún agregado nacional a partir de datos incompletos | F-04, F-06 |
| A-19 | P1 | Nombre coloquial o error de reconocimiento | El léxico mejora la resolución; una sustitución incierta se confirma | F-05 |
| A-20 | P1 | Dos observadores (analistas) discrepan | Una sola respuesta en primer plano; las observaciones no sobrescriben hechos ni repiten herramientas | F-08 |
| A-21 | P0 | La misma frase dicha con tono tenso y con tono calmado | El panel muestra una estimación **por voz** distinta de la del texto, con bandera de discrepancia; siempre rotulada como estimación | F-08 |
| A-22 | P0 | Frustración detectada o preferencia explícita | El estilo cambia (directo, cálido o didáctico) desde el turno siguiente, con motivo visible; la preferencia explícita persiste y gana | F-09 |
| A-23 | P0 | Se corta un motor a mitad de sesión (simulado) | El otro motor retoma con el sobre de contexto; el HUD indica «sesión renovada»; sin consulta duplicada | F-06, F-10 |
| A-24 | P0 | Cada consulta termina | El panel «API en vivo» muestra SoQL, ms, filas, fuente y corte; «Reconsultar» repite la llamada y el resultado coincide | F-11 |
| A-25 | P0 | Al iniciar la sesión | Aviso de IA visible y hablado; consentimiento explícito para el análisis de voz; sin audio retenido; Reiniciar borra el estado | NF-03 |
| A-26 | P1 | Menciona «Valle del Cauca» (Cali y Buenaventura figuran como «departamentos» aparte) | El agente aclara el alcance del filtro y lo advierte en `warnings` | F-05 |

Las pruebas de semántica de datos deben cubrir filas repetidas de un prestador, varias
sedes, naturaleza Mixta, nivel vacío, cantidad nula y cambio de corte, con fixtures
sintéticos y dobles (R-16); nunca datos reales de pacientes ni claves de proveedor.

## 8. Métricas de latencia y protocolo de benchmark

Objetivos de ingeniería **a validar** (no son promesas de los proveedores). Tiempos con el
reloj monótono del navegador; los spans del servidor, con el suyo; **no se restan relojes
de distintas máquinas**. Se correlacionan por `turn_id`.

| Métrica | Definición | Objetivo |
|---|---|---|
| Primer audio útil (sin consulta) | Fin de la voz del usuario → primer audio audible relevante | p50 ≤ 1,2 s · p95 ≤ 2,5 s |
| Primer audio útil (con consulta en vivo) | Igual, con una llamada a la API de datos | p95 ≤ 4,0 s |
| Reconocimiento previo | «Déjame verificarlo en datos.gov.co…»; **se mide aparte y no cuenta como respuesta** | ≤ 1,0 s |
| Parada por interrupción | Voz detectada → reproducción detenida | p95 ≤ 200 ms |
| Parcial de transcripción visible | Voz capturada → parcial renderizado | p95 ≤ 500 ms |
| Plazo de primer plano | Transcripción final → turno completado, fallido o aclarado | ≤ 6 s |

**Protocolo.** *Humo para elegir modelo:* 10 enunciados por candidato (esquema válido, filtros
correctos, resultado anclado, primer audio útil, tasa de *timeouts*, costo); no es evidencia
de percentiles. *Liberación:* ≥ 30 turnos en caliente (consultas directas, caché, nombres
ambiguos, correcciones y vacíos) + 5 en frío + 5 interrupciones, y una prueba de 3 sesiones
concurrentes. Registrar motor y modelo, versiones del prompt y de los esquemas, región,
transporte, navegador, concurrencia, estado de caché, tokens o costo, frío/caliente y
resultado. **Los fallos y peores casos se reportan, no se descartan.** La corrección se juzga
contra respuestas esperadas revisadas, sacadas de consultas reales a la fuente; un LLM puede
sugerir una discrepancia, no define lo correcto. Ningún proveedor se declara «más rápido» o
«mejor razonando» por reputación.

## 9. Trazabilidad

| Rúbrica, paso o entregable | Requisitos | Aceptación | Documento |
|---|---|---|---|
| Voz y latencia en tiempo real (20%) | F-01, F-06, F-10, F-12, NF-01 | A-01, A-02, A-11, A-12, A-15, A-16, A-23 | [08](08-contrato-voz-en-vivo.md), [10](10-modelos-afecto-y-recuperacion.md) |
| Transcripción diarizada (15%) | F-07, F-08 | A-13, A-14, A-20, A-21 | [08](08-contrato-voz-en-vivo.md), [10](10-modelos-afecto-y-recuperacion.md) |
| Despliegue y entregable (10%) | F-12, NF-02, NF-07 | A-01, A-17, A-25 | [11](11-despliegue.md) *(Tier 1)*, README |
| UX, diseño y demo (25%) | F-01, F-04, F-09, F-11, F-12 | A-02, A-22, A-24, guion §10 | [08](08-contrato-voz-en-vivo.md), esta spec |
| RETO-P1 (URL carga sin errores) | F-01, NF-05 | A-01 | [08](08-contrato-voz-en-vivo.md) |
| RETO-P2 («documento» = conexión a la API) | F-11, F-01 | A-02, A-24 | [09](09-datos-en-vivo-datos-gov-co.md) |
| RETO-P3 (brief y 3–5 preguntas) | F-01, F-04 | A-02 | [09](09-datos-en-vivo-datos-gov-co.md) |
| RETO-P4 (resumen, detalle fino, fuera del contexto) | F-02…F-06 | A-03…A-12, A-16, A-18 | [09](09-datos-en-vivo-datos-gov-co.md), [10](10-modelos-afecto-y-recuperacion.md) |
| RETO-P5 (transcripción y panel) | F-07, F-08, F-09 | A-13, A-14, A-21, A-22 | [10](10-modelos-afecto-y-recuperacion.md) |
| RETO-P6 (arquitectura y decisiones) | F-10, NF-09 | README, [10](10-modelos-afecto-y-recuperacion.md) §9 | README |
| RETO-E01 / E02 / E03, R08 | NF-07 | A-01, A-17 | README, [11](11-despliegue.md) |
| RETO-M04 (uso de IA declarado) | NF-07 | revisión del README | README (R-31) |
| RETO-M05 (documento sorpresa) | — | riesgo aceptado | §2 |
| RETO-M06 (costos por cuenta del participante) | NF-01 | tope de gasto en proveedores | [11](11-despliegue.md) |
| RETO-M07 (sin demo local, un reintento de 2 min) | NF-02 | smoke público y calentamiento | [11](11-despliegue.md) |

## 10. Guion de 10 minutos y ensayo

| Minuto | Qué ocurre | Qué se muestra |
|---|---|---|
| 0:00–1:00 | Abrir la URL, Iniciar, aviso de IA y brief con la fecha de corte (P1–P3) | Panel «API en vivo» con los tres conteos |
| 1:00–3:00 | Pregunta de directorio y un conteo filtrado exacto | SoQL, ms y filas de cada consulta |
| 3:00–5:00 | Interrumpir; corregir el municipio; «¿y las privadas?» | Corrección visible y evidencia anterior invalidada |
| 5:00–6:30 | Pregunta no soportada («¿hay cama disponible hoy?») | Límite honesto de la fuente |
| 6:30–8:00 | Revisar la transcripción y el panel de afecto; pedir un tono más directo | Estilo adaptativo con motivo (P5) |
| 8:00–9:00 | Cambiar de motor (OpenAI ↔ Gemini) y repetir una pregunta | HUD con latencias de ambos |
| 9:00–10:00 | Arquitectura y decisiones (P6): respuestas ensayadas de [10](10-modelos-afecto-y-recuperacion.md) §9 | README y diagrama |

Se ensaya **dos veces** de punta a punta, con cronómetro y en un equipo ajeno, antes de las 15:45.

## 11. Definición de hecho y puertas

Una tarea está hecha con: código + enlace al contrato + pruebas relevantes en verde +
comportamiento ante fallos + evidencia del despliegue real cuando aplique + entrada fechada
en `CHANGELOG.md` (R-20). Lo planeado no se marca como verificado.

| Hora | Puerta |
|---|---|
| 10:50–11:10 | **Puerta 0:** docs 07–10 y 12 aprobados por ambos, fusionados a `main`, `pull` y worktrees |
| 12:15 | **Puerta 1:** URL pública con voz y una consulta real |
| **14:30** | **Congelamiento** de funciones (R-30) |
| 15:00 | Candidato a liberación elegido |
| 15:30 | URL registrada en el formulario y repo accesible |
| 15:45–16:00 | Colchón (no se migra arquitectura) |

## 12. Preguntas abiertas (no bloquean)

- ¿Los organizadores entregarán un archivo el día de la evaluación? (riesgo aceptado, B-11)
- ¿Cómo verificará el jurado la conexión en vivo a la API? El panel «API en vivo» y «Reconsultar» están pensados para eso.
- ¿La hoja `02 CRITERIOS` existe con más pesos que los 70 puntos visibles?
