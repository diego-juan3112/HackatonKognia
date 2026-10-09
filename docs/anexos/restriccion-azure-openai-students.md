# Restricción: Azure for Students no despliega modelos de Azure OpenAI

> Hallazgo del equipo, **20/09/2026**. Afecta la fila **LLM** del stack de
> `AGENTS.md` §1 y el Terraform de `infra/`.
> Registrado aparte de US1/US2 porque no es una decisión de voz ni de avatar.

## 1. Qué se encontró

La suscripción **Azure for Students** no permite crear despliegues de modelos de
Azure OpenAI. **Es una restricción de política de la suscripción, no de región**:
cambiar de `eastus` a otra región no la esquiva, y no se resuelve esperando
cuota.

> Observación reportada por el equipo al intentarlo. **No verificada de forma
> independiente en esta sesión** — no hay CLI de Azure ni sesión iniciada en esta
> máquina. Si alguien la reproduce, vale la pena pegar aquí el mensaje de error
> exacto y la fecha, porque las políticas de Azure cambian.

## 2. Qué rompe

| Pieza | Impacto |
|---|---|
| `AGENTS.md` §1, fila **LLM** | Dice "Azure OpenAI / OpenAI (intercambiable por `MODEL_PROVIDER`)" y la marca **Fijo**. La abstracción sigue en pie; lo que cae es el supuesto de que la rama `azure` se puede usar desde la suscripción que tenemos hoy |
| `infra/terraform/main.tf` | Declara `azurerm_cognitive_account.openai` (kind `OpenAI`) y `azurerm_cognitive_deployment.agent_model`. **Un `terraform apply` contra la suscripción de estudiante falla en esos dos recursos** |
| `infra/terraform/outputs.tf` | `azure_openai_endpoint` y `azure_openai_deployment` dependen de ellos |
| `AGENTS.md` §12, paso 3 de CI | `terraform plan` pasa (el plan no crea nada); el `apply` manual es el que revienta |
| `src/` | **Nada.** `LLMPort` y `MODEL_PROVIDER` ya aíslan esto: es exactamente el caso que §5 anticipó |

**Lo importante: esto no es un problema de arquitectura, es un problema de
suscripción.** El puerto hizo su trabajo. Lo que hay que cambiar es de dónde
sale el modelo, no cómo lo llama el grafo.

## 3. Opciones

| # | Opción | Costo | Cambio de código | Riesgo |
|---|---|---|---|---|
| **A** | **OpenAI directo** (`MODEL_PROVIDER=openai`) | Saldo prepago, ~$5 alcanza de sobra | **Ninguno** — la rama ya existe en `integrations/llm/factory.py` | Rompe el "todo en Azure" del despliegue; nada más |
| **B** | **GitHub Models** (endpoint compatible con OpenAI) | **Gratis** con cuenta de GitHub | Añadir `base_url` a la rama `openai` de `factory.py` — contenido en `integrations/`, permitido por §5 | Límites de tasa agresivos: sirve para desarrollar, **es un riesgo en una demo en vivo** |
| **C** | **Otra suscripción de Azure** (pay-as-you-go propia, o la que dé el reto) | Según créditos | Ninguno | Depende de terceros; lo más probable es que el día del evento den créditos |
| **D** | **Subir la suscripción Students a Pay-As-You-Go** | Requiere tarjeta; conserva el crédito restante | Ninguno | Quita la restricción de política, pero expone a cobros reales |

## 4. Propuesta

**Corto plazo (desarrollo, de aquí al reto): B, con A como respaldo inmediato.**
GitHub Models cuesta $0 y deja el pipeline corriendo de punta a punta contra un
modelo real. Si los límites de tasa estorban, se pasa a A gastando unos dólares.
Para tests y CI **no se cambia nada**: `MODEL_PROVIDER=fake` ya cubre §11.

**Día del reto: C.** Si Kognia entrega créditos o una suscripción, se vuelve a
`MODEL_PROVIDER=azure` sin tocar una línea. Ese es justamente el escenario para
el que se construyó el puerto.

### Cambios que esto implica (cada uno con su propio plan, no en esta tarea)

1. **`AGENTS.md` §1, fila LLM** — mantenerla Fija, pero anotar la restricción:

   > LLM · Azure OpenAI / OpenAI / GitHub Models (intercambiable por
   > `MODEL_PROVIDER`) · Fijo — **Azure OpenAI no disponible desde la
   > suscripción Students, ver `docs/restriccion-azure-openai-students.md`**

2. **`integrations/llm/factory.py`** — la rama `openai` construye `ChatOpenAI`
   sin `base_url`, así que hoy no puede apuntar a GitHub Models. Hace falta
   leer un `OPENAI_BASE_URL` opcional desde `Settings` y pasarlo. Es un cambio
   de ~4 líneas, confinado a `integrations/` como exige §5.

3. **`infra/terraform`** — poner `azurerm_cognitive_account.openai` y su
   `azurerm_cognitive_deployment` detrás de una variable
   (`var.create_azure_openai`, con `count`), para que el despliegue no asuma un
   recurso que la suscripción actual no deja crear.

4. **`.env.example`** — documentar `OPENAI_BASE_URL` y el bloque de GitHub
   Models junto a los que ya están.

## Fuentes

- Observación directa del equipo al intentar el despliegue (20/09/2026).
- `infra/terraform/main.tf` líneas 30-46 — los recursos afectados.
- `src/integrations/llm/factory.py` — el único archivo que conoce al proveedor.
