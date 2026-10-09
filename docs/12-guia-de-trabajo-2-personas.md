# Guía de trabajo para dos personas

Contrato vigente · versión `2026-10-09.1` · dueña de la integración: **Persona B**.
Cada persona trabaja en su equipo, con **su sesión de Claude y sus worktrees**. Qué se construye:
[07](07-reto-01-especificacion.md); contratos: [08](08-contrato-voz-en-vivo.md) (voz),
[09](09-datos-en-vivo-datos-gov-co.md) (datos), [10](10-modelos-afecto-y-recuperacion.md) (modelos, afecto, recuperación).

**Plazo: 2026-10-09 16:00.** Congelar **14:30**, candidato **15:00**, registrar la URL **15:30**, colchón **15:45**.

## 1. Cómo se reparte

| | **Persona A · Front y voz** | **Persona B · API, datos, análisis e integración** |
|---|---|---|
| Construye | `web/` (Astro + TypeScript sin framework): `VoiceEngine` con los motores OpenAI Realtime y Gemini Live, audio (`MicTap`, reproductor), puente de herramientas, transcripción, panel «API en vivo», HUD, panel de afecto y estilo, controles de corrección, aviso de IA y consentimiento | `src/api/app_voice.py` y rutas, `services/ips` (5 herramientas), `integrations/datasets` (SODA3), `integrations/realtime` (credenciales), analista LangGraph, política de estilo, léxico, sesión firmada, despliegue de la API |
| Lee primero | 07, 08, 12 | 07, 09, 10, 12 |
| Contrato que firma | [08](08-contrato-voz-en-vivo.md) | [09](09-datos-en-vivo-datos-gov-co.md) y [10](10-modelos-afecto-y-recuperacion.md) |
| Spikes | G2 (voz) + G1 web | G3 (datos y análisis) + G1 api |

**Las dos sesiones de Claude no comparten memoria.** Lo que las sincroniza son los contratos
versionados (`docs/08`, `docs/09`, `src/models/`, `web/src/voice/types.ts`), no el chat. Cada
quien edita solo lo suyo, se trabaja contra *mocks* hasta la Puerta 1 y se hace *push* en cada
commit. Si falta tiempo, se deja el trabajo opcional primero y se protege la última hora y media.

## 2. Propiedad de archivos

| Carril | Dueño de | No tocar |
|---|---|---|
| **A** | `web/**`, `docs/08`, `docs/11` (parte web) | `src/**`, `tests/**`, `config/**`, `data/**`, `scripts/**`, `docs/09–10` |
| **B** | `src/**`, `tests/**`, `config/**`, `data/**`, `scripts/**`, `docs/09`, `docs/10` | `web/**`, `docs/08` |
| **Compartidos (un solo escritor)** | `AGENTS.md`, `docs/00`, `docs/02`, `docs/03` → **B** · `README.md` → **A** · `CHANGELOG.md` → quien fusiona en la puerta | Commit pequeño, *push* inmediato y aviso |

## 3. Preparación (una vez por persona)

**Software:** Git, Python 3.12+, Node 20+, VS Code con la extensión de Claude Code.
**Claves** (en el `.env` de cada worktree; **nunca** en git, R-05) — se comparten por un canal privado:

| Variable | Para qué |
|---|---|
| `GEMINI_API_KEY`, `OPENAI_API_KEY` | Motores de voz y analista |
| `DATOS_GOV_APP_TOKEN` | Token de aplicación de datos.gov.co (Portal del desarrollador → opcional pero recomendado) |
| `SESSION_SIGNING_KEY` | Firma de la sesión anónima (32 bytes aleatorios) |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING` | Trazas y feedback (opcional) |

**Si aún no tienes clon**, hazlo fuera de OneDrive. En PowerShell:

```powershell
New-Item -ItemType Directory -Force C:\dev\kognia | Out-Null
git clone https://github.com/diego-juan3112/HackatonKognia.git C:\dev\kognia\HackatonKognia
```

## 4. Ramas y worktrees

`main` es la rama de **integración y de producción de Vercel** (D-19). Cada persona crea sus
worktrees desde su clon; van **fuera de OneDrive** porque `node_modules` y `.venv` allí causan
tormentas de sincronización. Tras la Puerta 0 (docs ya en `main`), en PowerShell, **dentro de tu
clon** (en el equipo de Persona A: `C:\Users\danna\OneDrive\Documentos\Kognia\agent-starter`;
en el otro: `C:\dev\kognia\HackatonKognia`):

```powershell
git fetch origin
New-Item -ItemType Directory -Force C:\dev\kognia | Out-Null

# Persona A
git worktree add -b feat/reto-01-front C:\dev\kognia\A-front origin/main
git worktree add --detach C:\dev\kognia\A-main origin/main       # solo para probar todo junto

# Persona B
git worktree add -b feat/reto-01-api C:\dev\kognia\B-api origin/main
git worktree add --detach C:\dev\kognia\B-main origin/main
```

Cada worktree necesita su propio `.env`: `Copy-Item .env.example C:\dev\kognia\A-front\.env`
(o `B-api`) y se rellenan las claves. Para refrescar el worktree de pruebas:
`git -C C:\dev\kognia\A-main fetch origin; git -C C:\dev\kognia\A-main checkout --detach origin/main`.

## 5. Una sesión de Claude por worktree

1. En VS Code: *Archivo → Abrir carpeta* → `C:\dev\kognia\A-front` (Persona A) o `C:\dev\kognia\B-api` (Persona B).
2. Abre ahí el panel de Claude Code. `AGENTS.md`, `CLAUDE.md` y `docs/` viajan con la rama.
3. Pega el prompt de arranque de tu carril.

**Prompt de arranque — Persona A**

```
Eres el carril A (Front + Voz) del Reto 01. Antes de actuar lee AGENTS.md y docs/07, 08 y 12; docs/sdd_ips es insumo, mandan docs/07-13.
Eres dueño de web/**, docs/08 y la parte web de docs/11. No edites src/**, tests/**, config/** ni docs/09-10 (carril B): si necesitas algo ahí, descríbelo y pídemelo.
Si hay que cambiar un contrato (eventos de VoiceEngine, forma de /tools o /realtime/session), primero cambia el doc y avísame: se acuerda con B antes de codificar (R-30).
Trabaja contra web/mocks/ hasta que B publique el backend. Plan Mode en lo no trivial, commits convencionales pequeños, push tras cada commit. Nunca push a main sin que yo lo diga.
Primera tarea: andamiaje de web/ (Astro + TypeScript, sin framework) y un motor de voz hablando contra un stub de herramientas.
```

**Prompt de arranque — Persona B**

```
Eres el carril B (API + Datos + Análisis e integración) del Reto 01. Antes de actuar lee AGENTS.md y docs/07, 09, 10 y 12; docs/sdd_ips es insumo, mandan docs/07-13.
Eres dueño de src/**, tests/**, config/**, data/**, scripts/**, docs/09 y docs/10, y escribes AGENTS.md y docs/00, 02 y 03. No edites web/** ni docs/08 (carril A).
Si hay que cambiar un contrato (/tools, /realtime/session, /analysis/utterance, sobre de evidencia), primero cambia el doc y el esquema en src/models/ y avísame (R-30).
Reglas duras: R-05 (entorno solo en src/config.py), R-22 (toda cifra sale de una consulta en vivo), R-23 (el modelo nunca escribe SoQL), pruebas offline con dobles. Plan Mode en lo no trivial, commits pequeños, push tras cada commit. Nunca push a main sin que yo lo diga.
Primera tarea: cliente SODA3 en vivo + aggregate_ips con pruebas offline; luego /realtime/session y /tools/*.
```

## 6. Flujo diario

Dentro del worktree de tu carril, en PowerShell:

```powershell
git pull --rebase origin main                       # cada ~45 min: trae lo del otro
git add -A; git commit -m "feat(voz): ..."; git push -u origin HEAD
# en cada puerta, con tus pruebas en verde (pytest / npm run build):
git fetch origin; git rebase origin/main; git push origin HEAD:main
```

Convenciones: Conventional Commits ([06](06-flujo-y-convenciones.md)), un commit por cambio lógico.
**`main` despliega a producción**: no empujes nada que rompa la demo, **nunca `--force`**, y desde las
14:30 solo correcciones P0 acordadas entre ambas. Si el `push` a `main` es rechazado, el otro llegó
primero: repite `pull --rebase`. Los worktrees de carril se despliegan como *preview* de Vercel para
probar el micrófono sobre HTTPS.

**Aviso (Vercel Hobby, [11](11-despliegue.md) §6):** hasta que G1 confirme que Vercel no bloquea los
commits del otro autor, si el despliegue de `main` sale bloqueado tras un *push* de A, A abre un PR
de su rama y **B lo fusiona en GitHub** (el commit de fusión queda a nombre de B). Si aun así bloquea,
`vercel deploy --prod` desde el equipo de B.

## 7. Cambio de contrato (R-30)

1. Doc y esquema en un commit pequeño (`docs/08` y `web/src/voice/types.ts`, o `docs/09–10` y `src/models/`).
2. *Push* a tu rama y a `main`.
3. Avisar al otro con la sección exacta.
4. El otro hace `pull --rebase` **antes** de seguir.

La versión del contrato viaja en `GET /health`. **Superficie mínima para trabajar en paralelo:**
B publica `GET /health`, `POST /sessions`, `POST /realtime/session`, `POST /tools/{nombre}`,
`GET /dataset/brief`, `POST /analysis/utterance`, `POST /feedback`; A define los eventos del
`VoiceEngine`. A empieza con `web/mocks/*.json`; B con eventos grabados en `tests/fixtures/`.

## 8. Spikes (10:10–10:50, en carpetas temporales fuera del repo; lo útil se porta)

| Spike | Qué hace | Qué se reporta (5 líneas en el chat) |
|---|---|---|
| **G1** Vercel (A web, B api) | Esqueleto desplegado, CORS, `GET /health`, mintear una credencial efímera | ¿Empaqueta la API? ¿Tiempo de arranque en frío? ¿Un proyecto o dos? → cierra D-15 |
| **G2** Voz (A) | OpenAI Realtime y Gemini Live desde el navegador: **verificar los IDs de modelo llamándolos**, WebSocket con credencial efímera (y WebRTC si falla), voz es-CO, primer audio, una llamada de herramienta con un stub, interrupción y tiempos | Motor ganador y por qué, IDs, primer audio, ¿interrumpe bien?, ¿qué falló? → cierra D-11 |
| **G3** Datos y análisis (B) | SODA3 con y sin token, prototipo de `aggregate_ips` y `search_ips`, `build_lexicon.py`, una llamada Gemini multimodal con un recorte de 5 s frente a OpenAI para el analista | Latencias, ¿el token funciona?, esquema válido del analista, IDs → fija D-10 |

## 9. Puertas y cronograma

| Hora | Persona A | Persona B |
|---|---|---|
| 10:10–10:50 | G2 + G1 web · lee 07–08 y 12 | G3 + G1 api · lee 07–10 y 12 |
| 10:50–11:10 | **Puerta 0 (juntos)** | |
| 11:10–12:15 | `web/`, motor 1 hablando, puente de herramientas contra mocks | `/realtime/session`, `/tools/*`, `/dataset/brief`, despliegue de la API |
| 12:15 | **Puerta 1** | |
| 12:15–13:45 | Motor 2 + selector, transcripción, panel «API en vivo», HUD, controles de corrección | `get_ips_details`, `correct_context`, léxico y normalización, analista + estilo, recuperación, pruebas |
| 13:45–14:30 | Panel de afecto y estilo, recortes de audio, pulido, accesibilidad | Caché y plazos, benchmark de 10 enunciados, `smoke_public.py`, Should |
| **14:30** | **Congelamiento (R-30)** | |
| 14:30–15:00 | Ensayo 1 y solo correcciones P0 → **candidato a las 15:00** | |
| 15:00–15:45 | 2 ensayos del guion de 10 min · README · acceso al repo · **registrar la URL (15:30)** | |
| 15:45–16:00 | Colchón (RETO-M07: un único reintento de 2 min) | |

**Lista de la Puerta 0 (≈ 11:10):**
☐ ambos leyeron 07–10 y 12 · ☐ G1–G3 reportados y IDs fijados (D-10, D-11, D-15 cerrados en `docs/00`) ·
☐ docs fusionados a `main` · ☐ `git pull` y worktrees creados · ☐ `.env` en cada worktree · ☐ cada sesión de Claude arrancada con su prompt.

**Lista de la Puerta 1 (12:15):**
☐ URL de producción responde `/health` · ☐ el navegador conecta un motor con credencial efímera · ☐ una consulta real por voz se ve en «API en vivo» · ☐ transcripción básica · ☐ *push* a `main` con pruebas en verde.

**Lista del candidato (15:00):**
☐ A-01…A-14, A-16…A-18 y A-21…A-25 ejecutados ([07](07-reto-01-especificacion.md) §7) · ☐ benchmark de humo publicado · ☐ README de 1 página con declaración de IA · ☐ `smoke_public.py` en verde · ☐ escaneo de secretos del historial.

**15:30:** ☐ URL registrada en el formulario · ☐ repo público o con acceso a jueces · ☐ calentar y `/health`.

## 10. Orden de caída

Si va tarde, se corta **en este orden** y se protege la última hora y media:
1. Refinamiento multi-hablante · 2. Descargar transcripción · 3. Entidades visibles en la transcripción · 4. `compare_ips` · 5. Paridad total del segundo motor (basta que funcione con el selector) · 6. Caché de respaldo del brief.

**Se protege siempre:** voz, datos en vivo con el panel, recuperación básica, afecto (si el análisis por voz no llega, se entrega el de texto, rotulado), README y URL estable.

## 11. Si algo se rompe

| Situación | Qué hacer |
|---|---|
| Conflicto al hacer `pull --rebase` | No resolver archivos del otro carril: avisar y pedir que los resuelva su dueño; en los compartidos, decide el escritor único |
| La API no empaqueta o el arranque en frío es lento en Vercel | Plan B: mismo backend en contenedor (Dockerfile) y cambiar la URL base del frontend; tope de 20 min para decidirlo |
| Una clave se filtró | Revocarla de inmediato en el proveedor, rotarla en Vercel y en cada `.env`, y revisar el historial (R-05) |
| Un motor falla en pleno ensayo | Cambiar al otro con el selector; anotarlo en el benchmark (los fallos se reportan) |
| Un push a `main` rompió la demo | `git revert <commit>` y push; nunca `--force` |

## 12. Comunicación

Un chat compartido. Cada ~45 min, tres líneas: **Hecho · Haciendo · Bloqueado**. Antes de cambiar un
contrato o de empujar a `main` en una puerta, avisar. Las decisiones nuevas se anotan en
[00](00-contexto-y-decisiones.md) §5 con su código `D-xx`.

## 13. Arranque de cada persona (primeros 40 minutos)

**Estado al 2026-10-09 ≈ 10:45.** `main` ya trae `docs/00–06`; los docs `07–13` y `sdd_ips` llegan
con el PR de `docs/reto-01-sdd`. Antes de crear los worktrees comprueba que ya está fusionado: en
PowerShell, dentro de tu clon, `git fetch origin; git ls-tree --name-only origin/main docs/12-guia-de-trabajo-2-personas.md`
debe imprimir el archivo. El repo es **público**: nada de claves en ningún commit (R-05).

### Los dos, primero (≈ 5 min)

1. Worktrees y `.env` según §4 (cada quien el suyo).
2. VS Code → *Archivo → Abrir carpeta* → `C:\dev\kognia\A-front` (A) o `C:\dev\kognia\B-api` (B) → panel de Claude Code → prompt de §5.
3. Avisa en el chat: «worktree listo, empiezo G…».

### Persona A — G2 (voz) y G1 web (≈ 35 min)

1. **Carpeta temporal fuera del repo** (`C:\dev\kognia\spike-g2`): el código del spike es desechable; lo útil se porta a `web/` después.
2. **Verificar los IDs llamando**, no por catálogo: OpenAI → `GET https://api.openai.com/v1/models` y buscar los de tiempo real; Gemini → `GET https://generativelanguage.googleapis.com/v1beta/models` y quedarse con los que admiten `bidiGenerateContent` (Live). Con cada candidato, abrir una sesión corta de verdad.
3. **Credencial efímera:** un script desechable **del lado del servidor** (nunca en el navegador) la emite con la clave del `.env`: OpenAI por su endpoint de *client secrets*, Gemini por sus tokens efímeros (confirmar en la documentación vigente). Es el germen de `integrations/realtime/` del carril B.
4. **Página mínima** con `getUserMedia`, `AudioWorklet` a 16 kHz PCM16 y reproducción a 24 kHz; conexión por WebSocket (WebRTC solo si falla en OpenAI). Probar: es-CO, primer audio, una llamada de herramienta con un stub, interrupción.
5. **G1 web:** `npm create astro@latest` (plantilla mínima, TypeScript estricto) en una carpeta temporal, desplegado como estático en Vercel con un `PUBLIC_API_URL` de prueba. Verifica además lo de [11](11-despliegue.md) §6 (autores de commits en Hobby).
6. **Reporta 5 líneas:** motor ganador y por qué · IDs verificados · primer audio medido · ¿interrumpe bien? · qué falló.

### Persona B — G3 (datos y análisis) y G1 api (≈ 35 min)

1. **Token SODA3** (datos.gov.co → Portal del desarrollador): `curl` con `X-App-Token` y comprobar 200; guardarlo en el `.env` (`DATOS_GOV_APP_TOKEN`). Si falla, seguir anónimo.
2. **Prototipo desechable** (Python 3.12, `httpx`) de `aggregate_ips` y `search_ips` contra la API real, con los números dorados de [09](09-datos-en-vivo-datos-gov-co.md) §9 como control: 9.320 IPS y 97.036 camas.
3. **`build_lexicon.py` en borrador:** consultas agrupadas y paginadas (`pageSize` 5000) para departamentos, municipios y nombres de prestador; medir tiempo y tamaño del JSON.
4. **Analista:** una llamada Gemini multimodal con un recorte WAV de 5 s (audio + transcripción, esquema JSON de [10](10-modelos-afecto-y-recuperacion.md) §6) y su equivalente en OpenAI; medir latencia y validez del esquema.
5. **G1 api:** FastAPI mínimo con `GET /health` desplegado en Vercel. **Primer obstáculo:** `pyproject.toml` lee sus dependencias de `requirements.txt`, que incluye `sentence-transformers` (torch), `psycopg` y `langgraph-checkpoint-postgres`; hay que sacarlas del camino de Vercel ([11](11-despliegue.md) §3). Tope de 20 min; si no sale, plan B (contenedor).
6. **Reporta 5 líneas:** ¿funciona el token? · latencias de herramienta y de analista · ¿empaqueta la API en Vercel? · arranque en frío · IDs de modelo del analista.

### Puerta 0 (≈ 11:10, juntos)

B anota en `docs/00` los IDs y deja cerrados D-11 y D-15, y lo empuja; A confirma. Si a las 11:10 un
spike no cerró, se decide con lo que haya: motor 1 = el que mejor midió; despliegue = lo que ya corre.

### Primeras tareas de código (tras la Puerta 0)

| | Persona A | Persona B |
|---|---|---|
| 1 | `web/` con Astro + TypeScript estricto; `.gitignore` de `web/node_modules`, `web/dist`, `.astro` y `.vercel`; `web/src/voice/types.ts` con los eventos de [08](08-contrato-voz-en-vivo.md) §2; `FakeEngine` y `web/mocks/` | `src/models/ips.py` (herramientas y sobre de evidencia); `src/config.py` y `.env.example` con las variables nuevas ([11](11-despliegue.md) §2); `socrata_client.py` y `aggregate_ips` con pruebas offline |
| 2 | Consola con transcripción, panel «API en vivo» y HUD sobre `FakeEngine`; despliegue *preview* | `api/app_voice.py` con `/health`, `/sessions`, `/tools/{n}` y `/dataset/brief`; despliegue de la API |
| 3 | Adaptador del motor ganador de G2 hablando con una herramienta stub | `/realtime/session` (credenciales efímeras de ambos motores) |

**Puerta 1 (12:15):** voz y una consulta real en la URL pública.
