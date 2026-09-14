# Infra: Azure OpenAI + Container Apps

Despliega: grupo de recursos, Azure OpenAI (con un deployment de
modelo), Azure Container Registry, Log Analytics y un Container App
que corre la imagen del agente (`Dockerfile` en la raíz del proyecto).

> Nota: este HCL no se pudo validar con `terraform validate` en esta
> sesión (no hay Terraform CLI ni credenciales de Azure disponibles
> aquí). Está escrito contra el esquema estable del provider
> `azurerm ~> 3.116`; antes de confiar en él para la demo, corre
> `terraform validate` / `terraform plan` con tu propia suscripción.

## Requisitos

- Azure CLI autenticado (`az login`) con permisos para crear recursos.
- Cupo/acceso habilitado para Azure OpenAI en la región elegida
  (`swedencentral` por defecto — cambia `location` si tu suscripción no
  tiene acceso ahí).
- Terraform >= 1.6.

## Flujo recomendado (2 pasos, por el problema del huevo y la gallina: la Container App necesita una imagen, y la imagen se sube al ACR que este mismo Terraform crea)

```bash
cd infra/terraform
terraform init

# 1) Primer apply: crea todo con una imagen pública de placeholder
terraform apply

# 2) Construye y pushea tu imagen real al ACR que se acaba de crear
ACR=$(terraform output -raw acr_login_server)
az acr login --name "${ACR%%.*}"
docker build -t "$ACR/agent:latest" ../..
docker push "$ACR/agent:latest"

# 3) Segundo apply, apuntando la Container App a tu imagen real
terraform apply -var="container_image=$ACR/agent:latest"
```

## Variables útiles

| Variable | Default | Notas |
|---|---|---|
| `project_name` | `kognia-agent` | prefijo de nombres |
| `location` | `swedencentral` | debe soportar el modelo elegido |
| `openai_model_name` | `gpt-4o-mini` | ver guía .md para alternativas (gpt-4o, gpt-5-mini, etc.) |
| `container_image` | imagen pública de prueba | cámbiala al ACR una vez pusheada tu imagen |

## Autenticación del agente contra Azure OpenAI

Para ir rápido en el hackathon, este Terraform pasa la API key de
Azure OpenAI como *secret* de Container Apps (variable
`AZURE_OPENAI_API_KEY`). Para producción real se recomienda cambiar a
**Managed Identity** (sin keys) — el patrón está documentado en la
guía .md, sección "Autenticación en producción".

## Limpiar todo

```bash
terraform destroy
```
