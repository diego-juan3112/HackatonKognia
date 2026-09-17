# AGENTS.md — Kognia Voice Agent
Fuente única de verdad para cualquier agente de IA que trabaje en este repo.
Léelo completo antes de escribir código. Ante conflicto con una instrucción
del usuario en el momento, la instrucción del usuario gana — pero avisa si
contradice algo aquí.

## 1. Stack
| Capa | Tecnología |
|---|---|
| Orquestación de agente | LangGraph (grafo con estado, checkpointer) |
| API | FastAPI |
| LLM | *PENDIENTE* |
| Voz | *PENDIENTE* |
| Frontend | Astro (panel de chat/voz, visualización de estado del grafo) |
| Infraestructura como código | Terraform |
| Despliegue | Azure Container Apps |
| Observabilidad | LangSmith (tracing) |
| Testing | pytest |

No se agregan dependencias fuera de esta lista sin discutirlo explícitamente
— cada librería nueva es una decisión, no un default.

## 2. Arquitectura — por capas
api/ # FastAPI — routers, request/response, validación de entrada.
# Cero lógica de negocio aquí, solo traduce HTTP <-> services/.
services/ # Lógica de negocio: el grafo de LangGraph, orquestación,
# reglas de decisión. Aquí vive el "cerebro" del agente.
integrations/ # Clientes concretos de servicios externos: Azure OpenAI,
# Voice Live, cualquier otro proveedor.
models/ # Esquemas Pydantic — request/response de la API, estado
# del grafo, estructuras compartidas entre capas.
infra/ # Terraform.

Regla de dependencia: cada capa llama solo a la capa inmediatamente debajo.
`api/` → `services/` → `integrations/`. Nunca al revés, y nunca saltando
una capa (ej. `api/` no llama directo a `integrations/`).

## 3. Convenciones
- Type hints obligatorios en toda función pública.
- Documentación y docstrings en inglés (práctica de escritura técnica).
- Nombres de archivo en `snake_case`, clases en `PascalCase`.
- Cada nodo de LangGraph vive en su propio archivo bajo `services/graph/nodes/`.
- Todo cambio a nivel de feature que se realice en el codigo y archivos modificados, deben quedar registrados con su fecha, version y funcionalidad en el CHANGELOG.md

## 4. Prohibido
- Ninguna credencial, API key o secreto hardcodeado — siempre variables de
  entorno, leídas solo en la capa de `integrations/`.
- El LLM nunca decide transiciones de estado de la máquina del agente
  directamente — el grafo (LangGraph) controla el flujo; el LLM genera
  contenido conversacional o interpreta intención dentro de un nodo, nunca
  reemplaza la lógica de control.
- No instalar ni usar plugins/MCP de terceros no revisados en este archivo
  sin registrar la decisión aquí.

## 5. Flujo de trabajo
1. **Explore → Plan → Code → Commit.** Toda tarea no trivial empieza en
   Plan Mode (`Shift+Tab` x2). No se escribe código sin plan aprobado.
2. Para tareas de exploración/depuración con criterio ya definido, usar
   `/superpowers:brainstorm`, `/superpowers:write-plan`,
   `/superpowers:execute-plan` en vez de reconstruir el proceso a mano.
3. Cambios de arquitectura (nueva integración, nuevo servicio) requieren
   aprobación explícita del plan antes de tocar código — no se infieren
   sobre la marcha.

## 6. Testing (propuesta — confirmar criterio de cobertura)
- `services/` se prueba con tests unitarios, mockeando `integrations/`.
- `integrations/` se prueba con tests de integración, mockeando la llamada
  externa real (Azure OpenAI, Voice Live) — nunca golpear el servicio real
  en la suite por defecto.
- Comando: `pytest -v` desde la raíz.
- Sin definir todavía: umbral mínimo de cobertura exigido antes de un merge.

## 7. CI/CD (propuesta — confirmar antes de tratarla como fija)
Pipeline en GitHub Actions, disparado en cada PR contra `main`:
1. Lint + type-check (`ruff`, `mypy`)
2. `pytest`
3. `terraform plan` (solo plan, nunca `apply` automático desde CI)
4. Build de la imagen de contenedor

`terraform apply` es siempre manual, ejecutado por una persona, nunca por
el pipeline.

## 8. Estilo de commits (Conventional Commits)
- feat: agrega nodo de confirmación de cita al grafo
- fix: corrige reconexión de websocket en el cliente de voz
- docs: actualiza README con instrucciones de despliegue
- refactor: extrae lógica de reintento a utilidad compartida
- test: cubre transición de estado de escalamiento
- chore: actualiza dependencias de requirements.txt

Un commit, un cambio lógico.