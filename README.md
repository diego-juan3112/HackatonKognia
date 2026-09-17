# Kognia Voice Agent — base genérica adaptable

Esqueleto de agente conversacional sobre **LangGraph**, diseñado para que el
día del reto solo haya que conectar dos cosas:

1. La lógica específica del negocio (un YAML de dominio y, si acaso, un nodo).
2. Los proveedores de voz y avatar, cuando estén decididos.

**No sabemos el reto todavía.** Puede ser PQR o atención financiera, por voz o
por video. Por eso el núcleo modela capacidades genéricas y nada de un dominio
concreto. Ver `AGENTS.md` §0 y §3.

## Arranque rápido (sin credenciales, sin red)

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate en Linux/Mac
pip install -r requirements.txt

pytest                             # 22 tests, todos offline
python -m scripts.ingest --path docs/faq_demo --reset
uvicorn api.main:app --app-dir src --port 8000
```

`MODEL_PROVIDER` viene en `fake` por defecto: el grafo completo corre con un
modelo determinista, sin gastar un token. Para usar un modelo real, copia
`.env.example` a `.env` y cambia el proveedor.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "cual es el horario de atencion", "thread_id": "demo"}'
```

## Arquitectura

```
src/
├── models/          # Transversal: estructuras de datos + contratos de puerto
│   ├── ports.py     #   LLMPort, VoicePort, AvatarPort, RetrievalPort
│   ├── conversation.py
│   ├── retrieval.py
│   └── domain_config.py
├── services/        # El cerebro. No sabe de HTTP ni de SDKs.
│   ├── graph/
│   │   ├── builder.py    # arma y compila el StateGraph
│   │   ├── state.py
│   │   ├── edges.py      # transiciones: funciones puras de estado
│   │   └── nodes/        # un archivo por capacidad genérica
│   └── domain_loader.py
├── integrations/    # Todo lo que toca el mundo exterior
│   ├── llm/         #   openai | azure | fake
│   ├── retrieval/   #   Chroma + cargadores + embeddings
│   ├── voice/       #   VACÍO a propósito (§8)
│   └── avatar/      #   VACÍO a propósito (§8)
└── api/             # FastAPI. Única capa que sabe que existe HTTP.
config/domains/      # Dominios declarativos (YAML)
docs/faq_demo/       # Corpus de juguete para el RAG
scripts/ingest.py    # Reindexado
```

Regla de dependencia: `api/` → `services/` → `integrations/`. `models/` es
transversal. Ver `AGENTS.md` §2.

## El grafo

```
intake → classify_intent → collect_data → route ─┬→ retrieve_context → respond → END
                                                 └→ respond → END
```

Las cinco capacidades son genéricas: recepción, clasificación de intención,
recolección de datos, enrutamiento y respuesta. **Ningún nodo menciona PQR ni
finanzas.**

La regla que sostiene el diseño (`AGENTS.md` §8): **el LLM nunca decide una
transición.** Rellena `intent` y redacta texto; la arista condicional en
`edges.py` es una función pura que lee `state["route"]`. Por eso el grafo está
construido a mano en vez de con `create_react_agent`, donde el modelo controla
el bucle vía tool-calls.

## Adaptar al reto real

1. **Dominio:** escribir `config/domains/<reto>.yaml` con el catálogo de
   intenciones y el esquema de campos. Apuntar `DOMAIN_CONFIG_PATH` ahí.
2. **Conocimiento:** `python -m scripts.ingest --path <carpeta que nos den> --reset`.
   Soporta `.md`, `.txt`, `.csv`, `.pdf`.
3. **Modelo:** `MODEL_PROVIDER=azure` (o `openai`) más sus variables.
4. **Voz/avatar:** implementar el adaptador en `integrations/voice/` o
   `integrations/avatar/` — y **solo** ahí. Ver el README de cada carpeta.

Borrar `config/domains/faq_demo.yaml` y `docs/faq_demo/` cuando el dominio real
esté listo: son desechables por diseño (`AGENTS.md` §4).

## Limitaciones conocidas

- Con `EMBEDDING_PROVIDER=fake` la recuperación es léxica (bolsa de palabras con
  hashing), no semántica. Sirve para validar el cableado; para calidad real usar
  `EMBEDDING_PROVIDER=openai`.
- `MODEL_PROVIDER=fake` no razona: clasifica por solapamiento de palabras y, al
  responder, cita el contexto recuperado. Es una herramienta de diagnóstico.
- El checkpointer es `MemorySaver`: la memoria se pierde al reiniciar.

## Despliegue

Ver `infra/terraform/README.md`. `terraform apply` es siempre manual
(`AGENTS.md` §12).
