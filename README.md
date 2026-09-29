# Kognia Voice Agent — base genérica adaptable

Agente conversacional sobre **LangGraph**, expuesto por **FastAPI**, que responde
con **Gemini** usando documentos embebidos con **E5** en **PostgreSQL + pgvector**,
y que sabe con quién está hablando.

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

cp .env.example .env              # y pon tu GEMINI_API_KEY

docker compose up -d              # PostgreSQL 17 + pgvector en :5433
python -m scripts.migrate         # crea las tablas en la base de desarrollo
python -m scripts.seed            # 2 usuarios demo + documentos embebidos con E5

python -m scripts.serve           # NO uses uvicorn directamente, ver abajo
```

La primera vez, `scripts.seed` descarga el modelo E5 (~1.1 GB). Después carga
desde la caché sin tocar la red.

> **Windows: arranca el servidor con `python -m scripts.serve`.**
> psycopg no funciona sobre el event loop por defecto de Windows, y uvicorn
> construye el suyo ignorando la política de asyncio. `scripts/serve.py` le pasa
> la factory correcta. Detalle en `ARCHITECTURE.md` §4.4.

## Probarlo

Documentación interactiva en **http://localhost:8000/docs**. Qué significa cada
campo y qué hacer con cada error está en [API.md](API.md). O con curl:

```bash
# 1. Crear un usuario
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" \
  -d '{"cedula": "3333333333", "display_name": "Carla"}'

# 2. Iniciar sesión (solo funciona para usuarios registrados; el seed trae
#    a Ana Demo 1000000001 y Beto Demo 1000000002)
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"cedula": "3333333333"}'

# 3. Conversar con el session_id del paso 2
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -H "X-Session-Id: <session_id>" \
  -d '{"message": "a que hora puedo ir el fin de semana?"}'

# 4. Historial
curl http://localhost:8000/conversations -H "X-Session-Id: <session_id>"
```

## Pruebas

```bash
pytest                   # con dobles en memoria: sin red, sin Docker, sin key
pytest -m integration    # contra PostgreSQL real, en la base kognia_test
```

Los tests de integración **nunca tocan la base de desarrollo**: corren en
`kognia_test`, que se crea sola, y se niegan a ejecutarse contra cualquier base
cuyo nombre no termine en `_test`. Tus datos del seed quedan intactos.

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

## Advertencias

- **La identificación por cédula no es autenticación.** No hay contraseña:
  cualquiera que conozca una cédula registrada obtiene una sesión.
- **Al LLM solo le llegan el nombre y los últimos 4 dígitos de la cédula**, nunca
  la cédula completa. Hay un test que lo garantiza.
- **Cuota gratuita de Gemini**: si se agota, la API responde 503 con un mensaje
  claro. Un turno con RAG cuesta dos llamadas al modelo.
- **La dimensión del embedding está clavada** en `vector(768)`. Cambiar de
  modelo exige una migración nueva y reindexar.

## Despliegue

Pendiente: el Terraform de `infra/terraform/` todavía no incluye PostgreSQL ni
el modelo E5. Es la siguiente fase. `terraform apply` es siempre manual
(`AGENTS.md` §12).
