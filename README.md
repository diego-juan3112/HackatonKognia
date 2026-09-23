# Kognia Voice Agent — base genérica adaptable

Esqueleto de agente conversacional sobre **LangGraph**, expuesto por **FastAPI**,
con RAG sobre **PostgreSQL + pgvector** y usuarios identificados por cédula.

**No sabemos el reto todavía.** Puede ser PQR o atención financiera, por voz o
por video. Por eso el núcleo modela capacidades genéricas y nada de un dominio
concreto. Ver `AGENTS.md` §0 y `ARCHITECTURE.md`.

> Para entender el proyecto a fondo — qué hace cada archivo, el flujo completo,
> las advertencias — lee **`ARCHITECTURE.md`**.

## Arranque

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate en Linux/Mac
pip install -r requirements.txt

cp .env.example .env              # y ajusta lo que necesites

docker compose up -d              # PostgreSQL 17 + pgvector en :5433
python -m scripts.migrate         # crea las tablas
python -m scripts.ingest --path docs/faq_demo --reset

pytest                            # 55 tests, sin red ni Docker
pytest -m integration             # 16 tests contra la base real

python -m scripts.serve           # NO uses uvicorn directamente, ver abajo
```

> **Windows: arranca el servidor con `python -m scripts.serve`.**
> psycopg no funciona sobre el event loop por defecto de Windows, y uvicorn
> 0.36+ construye el suyo ignorando la política de asyncio. `scripts/serve.py`
> le pasa la factory correcta. Si invocas `uvicorn api.main:app` a mano, la app
> falla al arrancar con un mensaje que te trae de vuelta aquí.
> Detalle completo en `ARCHITECTURE.md` §4.4.

Por defecto `MODEL_PROVIDER=fake` y `EMBEDDING_PROVIDER=fake`: todo corre sin
gastar un token ni descargar un modelo.

## Probarlo

```bash
# 1. Identificarse (devuelve un session_id)
curl -X POST http://localhost:8000/auth/identify \
  -H "Content-Type: application/json" \
  -d '{"cedula": "1053812345"}'

# 2. Conversar
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: <el session_id del paso 1>" \
  -d '{"message": "cual es el horario de atencion"}'

# 3. Ver el historial
curl http://localhost:8000/conversations -H "X-Session-Id: <...>"
```

Documentación interactiva en `http://localhost:8000/docs`.

## Arquitectura en una pantalla

```
api/  ->  services/  ->  integrations/        models/ es transversal
```

```
intake → classify_intent → collect_data → route ─┬→ retrieve_context → respond
                                                 └→ respond
```

La regla que sostiene el diseño (`AGENTS.md` §8): **el LLM nunca decide una
transición.** Clasifica y redacta; la arista condicional es una función pura que
lee `state["route"]`.

## Pasar a producción

| Variable | De | A |
|---|---|---|
| `MODEL_PROVIDER` | `fake` | `nvidia` (+ `NVIDIA_API_KEY`) |
| `EMBEDDING_PROVIDER` | `fake` | `local` (descarga ~1.1 GB la 1ª vez) |
| `DOMAIN_CONFIG_PATH` | `faq_demo.yaml` | el YAML del reto real |

## Advertencias

- **La identificación por cédula no es autenticación.** No hay contraseña:
  cualquiera que conozca una cédula obtiene una sesión. Ver `ARCHITECTURE.md` §8.
- **`EMBEDDING_PROVIDER=fake` no es semántico** — es bolsa de palabras. Sirve
  para validar el cableado, no para calidad de recuperación.
- **`MODEL_PROVIDER=fake` no razona.** Es una herramienta de diagnóstico: si la
  respuesta repite el corpus, la recuperación funcionó.
- **La dimensión del embedding está clavada** en `vector(768)`. Cambiar de
  modelo exige una migración nueva y reindexar.

## Despliegue

Ver `infra/terraform/README.md`. `terraform apply` es siempre manual
(`AGENTS.md` §12).
