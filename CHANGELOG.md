# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

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
