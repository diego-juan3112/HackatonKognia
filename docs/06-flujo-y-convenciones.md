# Flujo de trabajo y convenciones

## Flujo

1. **Explore → Plan → Code → Commit.** Toda tarea no trivial empieza en Plan
   Mode (`Shift+Tab` x2). No se escribe código sin plan aprobado.
2. Para exploración o depuración con criterio ya definido, usar
   `/superpowers:brainstorm`, `/superpowers:write-plan` y
   `/superpowers:execute-plan` en vez de reconstruir el proceso a mano.
3. Los cambios de arquitectura (nueva integración, nuevo servicio) requieren
   aprobación explícita del plan antes de tocar código; no se infieren sobre la
   marcha.

## Convenciones de código

- Type hints obligatorios en toda función pública.
- Documentación y docstrings en inglés.
- Archivos en `snake_case`, clases en `PascalCase`.
- Cada nodo de LangGraph vive en su propio archivo bajo `services/graph/nodes/`.
- Al citar una regla o decisión desde código, comentario, commit o PR, usar su
  código (`R-04`, `D-03`), no la sección de un documento.
- **R-20.** Todo cambio a nivel de feature queda registrado en `CHANGELOG.md`
  con fecha, versión y funcionalidad.

## Reto 01: SDD, ramas y worktrees

- **Contrato primero (R-30).** Un cambio de eventos, esquemas, puertos o API se escribe antes
  en `docs/` y en `src/models/` (o `web/src/voice/types.ts`); el PR enlaza la sección. Es la
  única puerta formal; el resto va ligero.
- **`main` es la rama de integración y de producción** (D-19). Cada persona trabaja en una
  rama de carril (`feat/reto-01-front`, `feat/reto-01-api`) dentro de su worktree y empuja a
  `main` en las puertas, con pruebas en verde y sin `--force`. Desde las 14:30, solo
  correcciones P0 acordadas.
- **Dos personas, dos sesiones de Claude, dos carriles** con propiedad de archivos distinta;
  las sesiones no comparten memoria. Detalle, comandos y prompts de arranque:
  [12](12-guia-de-trabajo-2-personas.md).
- Al fusionar en una puerta, quien fusiona escribe la entrada de `CHANGELOG.md` (R-20),
  distinguiendo lo planeado de lo implementado y de lo verificado.

## Commits (Conventional Commits)

Un commit, un cambio lógico.

```
feat: agrega nodo de confirmación de cita al grafo
fix: corrige reconexión de websocket en el cliente de voz
docs: actualiza README con instrucciones de despliegue
refactor: extrae lógica de reintento a utilidad compartida
test: cubre transición de estado de escalamiento
chore: actualiza dependencias de requirements.txt
```

## CI/CD (propuesta — confirmar antes de tratarla como fija)

Pipeline en GitHub Actions, en cada PR contra `main`:

1. Lint + type-check (`ruff`, `mypy`)
2. `pytest`
3. `terraform plan` (solo plan)
4. Build de la imagen de contenedor

**R-21.** `terraform apply` es siempre manual, ejecutado por una persona,
nunca por el pipeline.

Para Reto 01 basta, en cada *push* a `main` o rama de carril, `pytest` (offline) y
`npm run build` en `web/`; Vercel genera el *preview* de cada rama.

## Herramientas y MCP registrados

**R-11.** No se instalan ni usan plugins, skills o MCP de terceros que no estén
en esta tabla. Agregar uno es una decisión que se registra aquí.

| Tipo | Nombre | Uso |
|---|---|---|
| MCP | Azure MCP | Consultar recursos de Azure |
| MCP | Terraform MCP | Requiere Docker corriendo |
| MCP | Context7 | Documentación de librerías al día |
| Plugin | `superpowers` | Flujo brainstorm / plan / execute |
| Plugin | `frontend-design` | Panel Astro y avatar |
| Plugin | `security-guidance` | Hooks en segundo plano |
| Plugin | `playwright` | Pruebas de navegador |
| Skill | `archify` (tt-a1i, MIT, v3.0.1) | Diagramas HTML validados contra el código. Instalada a nivel de usuario (`~/.claude/skills/archify`), no en el repo. Revisada: sin dependencias npm; su única llamada de red es un chequeo de versión, que se apaga con `ARCHIFY_UPDATE_CHECK_DISABLED=1`. Los diagramas viven en este repo, en `docs/diagrams/` |
