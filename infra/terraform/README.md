# Infra: Container Apps en Azure

> **Estado: incompleto a propósito.** En la versión 0.4.0 solo se retiró Azure
> OpenAI, porque el LLM ahora es Gemini (una API externa, sin recurso de
> Azure). Este Terraform todavía **no** despliega el sistema actual: le faltan
> PostgreSQL con pgvector, los secretos de Gemini y de la base, y el tamaño que
> necesita el modelo E5. Esa reescritura es la siguiente fase. El detalle de lo
> pendiente está en el encabezado de `main.tf`.

Hoy crea: grupo de recursos, Log Analytics, Azure Container Registry, y una
Container App que corre la imagen del agente.

Validado con `terraform validate` (Terraform 1.16.4) usando la imagen oficial
de Docker, sin instalar nada:

```bash
docker run --rm -v "$(pwd):/w" -w /w -e TF_DATA_DIR=/tmp/tfdata \
  --entrypoint sh hashicorp/terraform:latest \
  -c "terraform init -backend=false -input=false && terraform validate"
```

## Requisitos

- Azure CLI autenticado (`az login`) con permisos para crear recursos.
- Terraform >= 1.6 (o la imagen de Docker de arriba).
- Los proveedores de recursos registrados en la suscripción:
  `Microsoft.App`, `Microsoft.OperationalInsights`,
  `Microsoft.ContainerRegistry` y, para la siguiente fase,
  `Microsoft.DBforPostgreSQL`.

## Flujo (2 pasos, por el problema del huevo y la gallina: la Container App necesita una imagen, y la imagen se sube al ACR que este mismo Terraform crea)

```bash
cd infra/terraform
terraform init

# 1) Primer apply: crea todo con una imagen pública de placeholder
terraform apply

# 2) Construye la imagen EN Azure (no sube varios GB desde tu PC)
ACR=$(terraform output -raw acr_login_server)
az acr build --registry "${ACR%%.*}" --image agent:latest ../..

# 3) Segundo apply, apuntando la Container App a tu imagen real
terraform apply -var="container_image=$ACR/agent:latest"
```

`terraform apply` lo ejecuta siempre una persona, nunca un agente ni un pipeline
(R-21).

## Variables

| Variable | Default | Notas |
|---|---|---|
| `project_name` | `kognia-agent` | prefijo de nombres |
| `location` | `eastus2` | buena latencia y precio desde Colombia |
| `container_image` | imagen pública de prueba | cámbiala al ACR una vez construida tu imagen |

## Limpiar todo

Con créditos limitados, destruye la infraestructura cuando no la estés usando:

```bash
terraform destroy
```
