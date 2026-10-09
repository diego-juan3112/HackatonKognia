# web/dev — SOLO DESARROLLO

`dev-backend.mjs` es un **sustituto temporal** del backend real (FastAPI, carril B,
`src/api/app_voice.py`) para poder probar la consola con los motores de voz reales mientras
ese backend no está disponible. **No es un segundo backend:** imita la forma del contrato
([docs/08](../../docs/08-contrato-voz-en-vivo.md) §3 y [docs/09](../../docs/09-datos-en-vivo-datos-gov-co.md) §4–§5, §8)
y se borra cuando el real esté en pie.

- **No se despliega y no entra en el build.** Vive fuera de `src/` y `public/`; `astro build` no lo toca.
- Node ≥ 20, sin dependencias. Escucha solo en `127.0.0.1:8787`.
- Lee `OPENAI_API_KEY` y `GEMINI_API_KEY` del `.env` de la raíz del repo. **Nunca** las imprime,
  ni las credenciales efímeras que emite, ni los cuerpos de las peticiones.

## Qué implementa

| Ruta | Qué hace |
|---|---|
| `GET /health` | `contract`, `voice_modes: ["engine"]`, qué claves hay |
| `POST /sessions` | Token de sesión firmado en memoria (2 h) |
| `POST /realtime/session` | Credencial efímera **real** de OpenAI (`gpt-realtime-2.1`) o Gemini (`gemini-3.8-live`), con el prompt de docs/10 §7 y las herramientas declaradas |
| `GET /dataset/brief` | Tres consultas SODA3 en vivo a datos.gov.co |
| `POST /tools/aggregate_ips` | Consulta SODA3 en vivo + sobre de evidencia con `trace{soql, ms, rows}` |
| `POST /tools/search_ips` | Igual, versión básica (sin cursor) |
| `POST /analysis/utterance` | Responde 503 `ANALYSIS_UNAVAILABLE` (no hay analista aquí) |

## Qué NO tiene (lo pone el backend real)

`get_ips_details`, `compare_ips`, `correct_context`, el analista de afecto, la voz clonada
(`/speech/session`), límites de tasa, léxico persistente y pruebas. El léxico es ingenuo: se arma
al arrancar con dos consultas agrupadas. El `context` de las herramientas se acepta y se ignora.

## Cómo arrancar (PowerShell)

Terminal 1, el backend de desarrollo:

```powershell
node C:\dev\kognia\A-front\web\dev\dev-backend.mjs
```

Terminal 2, la consola apuntando a él:

```powershell
cd C:\dev\kognia\A-front\web
$env:PUBLIC_API_URL = "http://localhost:8787"
npm run dev
```

Abrir `http://localhost:4321/consola/` en Chrome o Edge y pulsar **Iniciar**. Sin
`PUBLIC_API_URL` la consola usa el motor simulado; con `?engine=fake` en la URL se fuerza el
simulado aunque haya backend.

Variables opcionales del backend: `DEV_BACKEND_PORT` (por omisión 8787) y `DEV_BACKEND_ORIGINS`
(orígenes CORS extra, separados por comas, si la consola no corre en el puerto 4321).
