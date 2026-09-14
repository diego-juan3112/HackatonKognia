# Agente General — Base para Kognia Challenge 2026

Base de un agente de IA general construida sobre **LangGraph**, pensada
para arrancar rápido el día del hackathon y solo tener que:

1. Conectar el modelo real (Azure OpenAI / Azure AI Foundry).
2. Agregar las herramientas específicas del reto que les toque.
3. Desplegarlo con el Terraform incluido.

## Arquitectura (hexagonal / por capas)

```
src/
├── agent_core/
│   ├── domain/            # Puertos (contratos). Sin dependencias externas.
│   │   └── ports.py       # LLMPort, ToolPort
│   ├── application/       # Casos de uso: arma el grafo del agente.
│   │   └── agent_graph.py # create_react_agent (LangGraph) + memoria
│   ├── infrastructure/    # Adaptadores concretos.
│   │   ├── llm_factory.py # OpenAI <-> Azure OpenAI (según .env)
│   │   └── tools/         # calculator (offline), web_search (Tavily)
│   └── config.py          # Settings vía variables de entorno
└── api/
    └── main.py            # FastAPI: única capa que sabe que existe HTTP
tests/
└── test_agent_smoke.py    # Corre el grafo con un LLM falso (sin API keys)
infra/terraform/           # Azure OpenAI + Container Apps
```

La idea de separar en capas: la lógica del agente (`application`) no
sabe si el modelo es de Azure o de OpenAI, ni si se expone por FastAPI,
un CLI o un worker. Eso vive en `infrastructure` y `api`. Así, cambiar
de proveedor de modelo el día del reto es **cambiar variables de
entorno**, no reescribir código.

## Cómo correrlo hoy (sin Azure todavía)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edita .env: MODEL_PROVIDER=openai y OPENAI_API_KEY=sk-...

PYTHONPATH=src pytest -q                 # valida el agente sin gastar API
uvicorn api.main:app --reload --app-dir src --port 8000
```

Probar el endpoint:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "cuanto es 23 * 4 + 10", "thread_id": "demo"}'
```

## Cómo pasar a Azure el día del hackathon

Solo cambian las variables de entorno (ver `.env.example`):

```bash
MODEL_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://<tu-recurso>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini      # o el deployment que hayan creado
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2024-10-21
```

No se toca ni una línea de `agent_graph.py` ni de `api/main.py`.

## Agregar una herramienta nueva

1. Crear el archivo en `src/agent_core/infrastructure/tools/mi_tool.py` con
   una función decorada `@tool` (ver `calculator_tool.py` como ejemplo).
2. Agregarla a la lista en `infrastructure/tools/__init__.py`
   (`default_toolset`).

El agente la detecta y decide solo cuándo usarla (así funciona ReAct).

## Despliegue en Azure (Terraform)

Ver `infra/terraform/README.md`. En resumen:

```bash
cd infra/terraform
terraform init
terraform apply
```

Esto crea: Azure OpenAI (con un deployment de modelo), Container Apps
Environment + Container App, Log Analytics y Container Registry.

## Si necesitan algo más complejo que un solo agente ReAct

- **Varios sub-agentes especializados coordinados por uno principal:**
  librería [`langgraph-supervisor`](https://github.com/langchain-ai/langgraph-supervisor-py).
- **Varios agentes que se pasan el control entre sí (peer-to-peer):**
  librería [`langgraph-swarm`](https://github.com/langchain-ai/langgraph-swarm-py).
- **Flujo totalmente custom (pasos fijos, ramas propias):** construir un
  `StateGraph` a mano en vez de `create_react_agent` (ver la guía .md
  adjunta para la sintaxis básica de nodos/edges).

## Referencia

Ver `GUIA-LANGGRAPH-HACKATHON.md` para la explicación conceptual de
LangGraph, la comparación de modelos disponibles en Azure y el plan de
trabajo sugerido para hoy y para el día del reto.
