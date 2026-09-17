# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

## [0.2.0] - 2026-09-17

### Changed
- **Refactor de capas** a la estructura que declara AGENTS.md §2:
  `src/{api,services,integrations,models}`. Se elimina `src/agent_core/`.
- **El grafo se reescribe a mano** (`StateGraph`) en lugar de
  `create_react_agent`. Motivo: en un agente ReAct el LLM controla el bucle vía
  tool-calls, lo que incumple AGENTS.md §8 ("el LLM nunca decide transiciones").
  Ahora las aristas son funciones puras de estado en `services/graph/edges.py`.
- `api/main.py` ya no construye el agente en tiempo de import: se usa
  `lifespan` + un composition root en `api/dependencies.py`. Antes, importar la
  app exigía credenciales reales y rompía tests y CI.
- `AGENTS.md`: voz y avatar 3D pasan a PENDIENTE DE DECISIÓN con candidatos
  documentados; se añaden el principio de núcleo genérico (§3), los puertos
  intercambiables (§5) y el diseño del RAG (§6).

### Added
- Seis nodos genéricos, uno por archivo, en `services/graph/nodes/`: intake,
  classify_intent, collect_data, route, retrieve_context, respond.
- Puertos `VoicePort`, `AvatarPort` y `RetrievalPort` en `src/models/ports.py`.
  Voz y avatar quedan **declarados sin implementación** hasta decidir proveedor.
- Dominio declarativo en YAML (`config/domains/faq_demo.yaml`) con catálogo de
  intenciones y esquema de campos. Los nodos no conocen su contenido.
- RAG sobre Chroma: `integrations/retrieval/` con cargadores (`.md`, `.txt`,
  `.csv`, `.pdf`), embeddings intercambiables y `scripts/ingest.py`.
- `MODEL_PROVIDER=fake` y `EMBEDDING_PROVIDER=fake`: el pipeline completo corre
  sin credenciales ni red.
- `pyproject.toml` con `pythonpath = ["src"]`. Sin esto la suite nunca había
  podido importar el paquete.
- Suite de 22 tests por capas (`tests/{services,integrations,api}/`).

### Fixed
- `classify_intent` no pasaba los `examples` del catálogo al prompt, perdiendo
  la señal más fuerte de clasificación.
- El embedder de desarrollo no filtraba palabras vacías: la consulta "cual es
  el horario de atencion" devolvía `solicitudes.md` antes que `horarios.md`.
  Añadidos stopwords y frecuencia sublineal, con test de regresión sobre el
  corpus real.

### Por hacer
- [ ] Decidir proveedor de voz (AGENTS.md §1.1) e implementar `VoicePort`.
- [ ] Decidir stack de avatar 3D (§1.2) e implementar `AvatarPort`.
- [ ] Frontend Astro.
- [ ] Sustituir el dominio de juguete por el del reto real.

## [0.1.0-base] - 2026-09-14

### Added
- Estructura hexagonal inicial del agente (`domain` / `application` / `infrastructure`).
- Agente general tipo ReAct sobre LangGraph (`create_react_agent`) con memoria en `MemorySaver`.
- Adaptador de LLM intercambiable: `openai` (dev local) <-> `azure` (Azure OpenAI / AI Foundry).
- Herramienta `calculator` (offline, para tests) y hook opcional de búsqueda web (Tavily).
- API FastAPI con `/health` y `/chat`.
- Test de humo (`tests/test_agent_smoke.py`) que corre sin credenciales reales.
- Esqueleto de Terraform para desplegar en Azure Container Apps + Azure OpenAI.

### Por hacer durante el reto
- [ ] Conectar `MODEL_PROVIDER=azure` con el recurso real de Azure OpenAI/Foundry.
- [ ] Definir y agregar las herramientas específicas del caso de uso elegido.
- [ ] Ajustar el prompt de sistema al dominio del reto.
- [ ] Aplicar Terraform contra la suscripción del hackathon y desplegar la imagen.
- [ ] (Opcional) Cambiar `MemorySaver` por un checkpointer persistente si el demo lo requiere.

## [0.1.0] - 2026-09-14
### Added
- Primera versión del agente base para el Kognia Challenge 2026.
