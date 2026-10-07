# AGENTS.md — Kognia Voice Agent

Reglas para cualquier asistente de IA que trabaje en este repo. Ante conflicto
con una instrucción del usuario en el momento, la instrucción del usuario gana,
pero avisa qué regla contradice (por su código).

Agente conversacional genérico: LangGraph + FastAPI + Gemini + PostgreSQL/pgvector,
en Python. **Todavía no conocemos el reto** (PQR o atención financiera, por voz
o video): construimos una base adaptable, no el agente final.

## Antes de tocar, lee

| Si vas a… | Lee primero |
|---|---|
| Hacer cualquier cosa por primera vez | [docs/00-contexto-y-decisiones.md](docs/00-contexto-y-decisiones.md) |
| Crear o mover archivos, tocar el grafo o un nodo | [docs/01-arquitectura.md](docs/01-arquitectura.md) |
| Agregar o cambiar un proveedor (LLM, voz, avatar, BD) | [docs/02-puertos.md](docs/02-puertos.md) |
| Tocar rutas HTTP, respuestas o errores | [docs/03-api.md](docs/03-api.md) |
| Tocar ingesta, embeddings o recuperación | [docs/04-rag.md](docs/04-rag.md) |
| Escribir o correr pruebas | [docs/05-pruebas.md](docs/05-pruebas.md) |
| Hacer commit, PR o agregar herramientas | [docs/06-flujo-y-convenciones.md](docs/06-flujo-y-convenciones.md) |

## Reglas (resumen; el detalle está en el documento enlazado)

| Código | Regla | Detalle |
|---|---|---|
| R-01 | Capas solo hacia abajo: `api/` → `services/` → `integrations/`. Nunca al revés ni saltando. `models/` es transversal. | [01](docs/01-arquitectura.md) §3 |
| R-02 | El núcleo (`services/graph/nodes/`) modela capacidades genéricas. Lo específico del reto entra como configuración o como nodo nuevo, nunca editando un nodo genérico. | [01](docs/01-arquitectura.md) §3 |
| R-03 | Cambiar el proveedor de un puerto = editar solo `integrations/`. Ningún tipo de SDK cruza esa frontera. | [02](docs/02-puertos.md) |
| R-04 | El LLM nunca decide transiciones del grafo. Genera contenido o interpreta intención dentro de un nodo; el flujo lo controla LangGraph. | [01](docs/01-arquitectura.md) §3 |
| R-05 | Ninguna credencial, API key o secreto en el código: siempre variables de entorno, leídas solo en `src/config.py`. | [01](docs/01-arquitectura.md) §4.5 |
| R-06 | No escribir lógica de negocio de PQR, finanzas ni ningún dominio concreto mientras no conozcamos el reto. | [00](docs/00-contexto-y-decisiones.md) §1 |
| R-07 | El dominio de juguete (`faq_demo`) es desechable: no se extiende, se reemplaza. | [00](docs/00-contexto-y-decisiones.md) §1 |
| R-08 | No implementar un adaptador concreto de voz ni de avatar mientras su proveedor siga abierto. | [02](docs/02-puertos.md) |
| R-09 | Cada puerto tiene un doble en memoria, y los dobles viven solo en `tests/doubles/`. | [02](docs/02-puertos.md) |
| R-10 | No agregar dependencias fuera del stack sin discutirlo. | [00](docs/00-contexto-y-decisiones.md) §2 |
| R-11 | No usar plugins, skills o MCP no registrados. | [06](docs/06-flujo-y-convenciones.md) |
| R-12 a R-15 | Ingesta en un comando, cargadores intercambiables, recuperación solo vía `RetrievalPort`, dimensión 768 fija. | [04](docs/04-rag.md) |
| R-16 a R-19 | `pytest` sin red ni credenciales; integración solo en bases `*_test`; la cédula completa nunca llega al LLM. | [05](docs/05-pruebas.md) |
| R-20 | Todo cambio de feature se registra en `CHANGELOG.md` con fecha y versión. | [06](docs/06-flujo-y-convenciones.md) |
| R-21 | `terraform apply` siempre manual, nunca desde CI. | [06](docs/06-flujo-y-convenciones.md) |

Las decisiones tomadas (Gemini, pgvector, E5, auth por cédula…) son `D-01` a
`D-08`, en [docs/00-contexto-y-decisiones.md](docs/00-contexto-y-decisiones.md) §5.
**Al cambiar de modelo, el catálogo del proveedor no prueba nada:** llama al
modelo antes de elegirlo.

## Cómo trabajar

- Toda tarea no trivial: **Explore → Plan → Code → Commit**, con plan aprobado
  antes de escribir código.
- Al citar una regla o decisión (código, commits, PR), usa su código: `R-04`, `D-03`.
- Antes de terminar: `pytest` en verde y entrada en `CHANGELOG.md`.
- Si una regla de aquí contradice el código o a otro documento, **avisa**; no
  lo resuelvas en silencio.
