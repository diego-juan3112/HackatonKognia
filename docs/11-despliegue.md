# Despliegue (Vercel) y operación de la demo

Contrato vigente · versión `2026-10-09.1` · dueños: **A** (web) y **B** (API) — [12](12-guia-de-trabajo-2-personas.md).
Decisiones: D-15 (Vercel + Dockerfile de respaldo), D-19 (`main` = producción). Reglas: R-05, R-28, R-30.
Requisitos del reto: RETO-R08, E01–E03, M06, M07 ([07](07-reto-01-especificacion.md) §9).

## 1. Topología

```
Navegador ──HTTPS──► Vercel · proyecto web  (Astro estático)            https://<dominio>/
Navegador ──HTTPS──► Vercel · proyecto api  (FastAPI, solo HTTP)         https://<api>/   (CORS: solo el origen del web)
Navegador ──WSS───► OpenAI Realtime / Gemini Live                        (credencial efímera emitida por la api)
Navegador ──WSS───► Cartesia (solo con la voz clonada, opcional)         (token de acceso emitido por la api)
api ──HTTPS──► datos.gov.co (SODA3)   ·   api ──HTTPS──► Gemini / OpenAI / Cartesia (analista, credenciales)
```

Dos proyectos de Vercel (carril A despliega `web`, carril B despliega `api`). Alternativa si
se verifica en G1: **un solo proyecto con servicios** (Astro + Python bajo un mismo dominio,
sin CORS). **No hay WebSocket propio, base de datos ni E5**: el audio va navegador ↔ proveedor.

| Proyecto | Raíz | Rama de producción | Previews |
|---|---|---|---|
| `web` | `web/` | `main` | cada rama de carril |
| `api` | `.` con entrypoint `src/api/app_voice.py` (`tool.vercel.entrypoint`) | `main` | cada rama de carril |

## 2. Variables de entorno (se definen en Vercel; nunca en git, R-05)

| Variable | Proyecto | Para qué |
|---|---|---|
| `GEMINI_API_KEY`, `OPENAI_API_KEY` | api | Credenciales efímeras de los motores y analista |
| `CARTESIA_API_KEY` | api | Emite el token de acceso de la voz clonada (`POST /speech/session`, [08](08-contrato-voz-en-vivo.md) §15.3). **Opcional:** sin ella, `GET /health` no anuncia `cloned` y solo se ofrece la voz del motor. Nunca llega al navegador (R-28) |
| `CARTESIA_VOICE_ID` | api | Identificador de la voz clonada del equipo; el backend lo entrega al navegador junto al token. No es un secreto, pero se configura aquí para no fijarlo en el código. Requerida si hay `CARTESIA_API_KEY` |
| `DATOS_GOV_APP_TOKEN` | api | Token SODA3 (opcional; si es inválido se descarta, [09](09-datos-en-vivo-datos-gov-co.md) §2) |
| `SESSION_SIGNING_KEY` | api | Firma de la sesión anónima (32 bytes aleatorios) |
| `ALLOWED_ORIGINS` | api | Origen(es) del web para CORS |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING` | api | Trazas y feedback (opcional) |
| `PUBLIC_API_URL` | web | URL base de la api (se fija en la compilación) |

Lectura de variables **solo** en `src/config.py` (R-05); `LANGSMITH_*` las lee la librería
(excepción documentada). Los worktrees locales usan su propio `.env` (ignorado por git).

## 3. Backend en Vercel

- **Dependencias mínimas** (sin `torch`, `sentence-transformers` ni `psycopg`): `fastapi`, `httpx`, `pydantic-settings`, `pyyaml`, `langgraph`, `langchain-core`, `langchain-google-genai`, `langchain-openai`. Paquete Python ≤ 500 MB; `vercel.json` excluye `tests/`, `docs/`, `spikes/`.
- **Límites a recordar:** cuerpo de petición y respuesta **4,5 MB** (los recortes WAV de ≤ 30 s caben, [08](08-contrato-voz-en-vivo.md) §4); duración máxima 300 s en Hobby (las llamadas del reto duran segundos); memoria 2 GB / 1 vCPU.
- **Región:** la predeterminada es `iad1`; medir una alternativa más cercana a Colombia en G1.
- **Calentamiento:** el brief ([09](09-datos-en-vivo-datos-gov-co.md) §8) abre la conexión a la fuente; el primer arranque en frío se mide en G1.
- **Dependencias — primer obstáculo de G1:** hoy `pyproject.toml` declara `dynamic = ["dependencies"]` leyendo `requirements.txt`, que incluye `sentence-transformers` (torch), `psycopg` y `langgraph-checkpoint-postgres`. Vercel instalaría todo eso. El carril B lo resuelve en G1 con una de estas salidas: (1) `requirements.txt` pasa a ser el conjunto mínimo de Reto 01 y lo pesado se mueve a `requirements-base.txt` (se actualizan `pyproject.toml` y los comandos de [01](01-arquitectura.md) §9); (2) un proyecto de Vercel con raíz en un subdirectorio y su propio `requirements.txt` (verificar que el paquete incluya `src/`); (3) plan B (contenedor).
- **Tope de 20 min (D-15):** si no empaqueta o el arranque en frío es inaceptable, se pasa al plan B.

## 4. Frontend en Vercel

Astro con salida **estática** (sin adaptador SSR salvo que algo lo exija). `PUBLIC_API_URL` apunta a la api.
HTTPS es obligatorio para el micrófono; los previews de rama sirven para probarlo.

## 5. Plan B: contenedor

El mismo backend corre en un contenedor sin cambiar código; solo cambia `PUBLIC_API_URL`.
El `Dockerfile` actual está **desactualizado** para Reto 01: debe copiar `src/`, `config/` y `data/`,
instalar solo las dependencias mínimas (sin E5) y arrancar `uvicorn api.app_voice:app`. Hosts
posibles: Azure Container Apps (regiones permitidas por Azure for Students: `spaincentral`,
`westus`, `canadacentral`, `belgiumcentral`, `chilecentral`), Render o Railway. **`terraform apply` es
siempre manual (R-21).** Mantener una instancia caliente durante el jurado.

## 6. Producción, previews y la URL que se entrega

`main` despliega a **producción**; las ramas despliegan como *preview*. **En el formulario va la
URL de producción estable, nunca un preview** (RETO-E01). Se anota el ID del último despliegue
bueno para poder volver con *Instant Rollback* de Vercel.

### Autores de commits y el plan Hobby

En el plan **Hobby**, Vercel bloquea el despliegue cuando el autor del commit no es la cuenta
dueña del proyecto: según reportes de su comunidad, «Hobby no admite colaboración en repos
privados», y igualar los correos no lo arregla. Aquí hay dos autores. El repo es **público**
(verificado el 2026-10-09 con la API de GitHub), lo que en teoría evita el bloqueo: **se verifica
en G1 con un commit del otro autor (10 min)**, no se da por hecho. Si se bloquea, en este orden:
1. La dueña del proyecto de Vercel (Persona B, integradora) integra en `main` con commits de fusión propios (`git merge --no-ff`); no está confirmado que baste, se prueba.
2. Desplegar con `vercel deploy --prod` desde su equipo (la CLI aún no está instalada: `npm i -g vercel`).
3. Prueba de Pro, o transferir el proyecto a la cuenta de quien empuja.

Como el repo es público, **ningún commit puede llevar claves** (R-05): el `.env` está en `.gitignore`
y los secretos viven solo en las variables de Vercel.

## 7. `scripts/smoke_public.py` (carril B)

Contra la URL pública, sale con error si algo falla y imprime latencias:

1. `GET /health` → `status`, `contract`, motores configurados y estado de la fuente.
2. `POST /sessions` → token firmado.
3. `GET /dataset/brief` → coincide con los números esperados del corte ([09](09-datos-en-vivo-datos-gov-co.md) §9).
4. `POST /tools/aggregate_ips` (`provider_count`) → `status = ok` y `cache_status = live`.
5. `POST /realtime/session` para **cada motor** → credencial emitida (no se conecta).
6. Preflight CORS desde el origen del web.
7. `GET /` del web → 200 y el aviso de IA presente.

## 8. Runbook RETO-M07 (sin demo local; un único reintento de 2 min)

| Hora | Acción |
|---|---|
| 14:30 | Congelamiento; solo correcciones P0 acordadas |
| 15:00 | Candidato elegido; `smoke_public.py` en verde; escaneo de secretos |
| 15:25 | Calentar: abrir la URL, pedir el brief, probar ambos motores; `GET /health` |
| 15:30 | URL de producción y repo registrados en el formulario |
| Durante el jurado | Pestaña de respaldo abierta; si algo falla: `GET /health`, cambiar de motor (o de voz, a la del motor), *Instant Rollback* |

## 9. Secretos antes de abrir el repo (RETO-E02)

El repo debe ser público o con acceso a los jueces. Antes: revisar el **historial** (no solo el
árbol) con `git log -p` y búsquedas de patrones (`AIza`, `sk-`, `sk_car_`, `xai-`, `DATOS_GOV`, `.env`);
la extensión `security-guidance` ya corre en segundo plano. Si algo apareció, **revocar y rotar**
la clave (no basta con borrarla del último commit). Rotar las claves de la demo al terminar.

## 10. Costos y abuso (RETO-M06)

Los costos de API son del equipo. Configurar **topes de gasto y alertas** en las consolas de OpenAI
y Google; una demo de 10 minutos cuesta centavos, los ensayos también. La sesión anónima firmada
y los límites de tasa por token e IP evitan que un tercero use las claves (R-28).

**Cartesia (voz clonada, [08](08-contrato-voz-en-vivo.md) §15):** cobra 1 crédito por carácter sintetizado
(≈ 750–800 créditos por minuto de audio) y el plan Pro trae 100.000 créditos al mes y **3 síntesis
concurrentes** (precios publicados, leídos el 2026-10-09). Al agotarse los créditos o superar la
concurrencia, la interfaz degrada sola a la voz del motor. El navegador solo recibe un token de
10 min con alcance de síntesis; `/speech/session` tiene los mismos límites de tasa. Revisar el
consumo en la consola de Cartesia tras los ensayos y rotar la clave al terminar (§9).

## 11. Fase 2

Azure Container Apps con Terraform y Twilio Media Streams (μ-law 8 kHz, un track por hablante) quedan
en el backlog ([13](13-diferenciadores-y-backlog.md), B-08 y B-09).
