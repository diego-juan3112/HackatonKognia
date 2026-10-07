# =============================================================================
# ESTADO: INCOMPLETO A PROPOSITO -- reescritura pendiente (fase de despliegue).
#
# El LLM es Gemini, que se consume como API externa: no necesita un recurso
# de Azure. Lo que todavia falta para que este Terraform despliegue
# el sistema actual:
#   - Azure Database for PostgreSQL Flexible Server, con `azure.extensions`
#     = VECTOR (sin eso, CREATE EXTENSION vector falla) y sslmode=require.
#   - Secretos GEMINI_API_KEY y DATABASE_URL en la Container App.
#   - 2 vCPU / 4 GiB: el modelo E5 no cabe en 1 GiB.
#   - Dockerfile con torch sin CUDA, config/ y migrations/ incluidos.
#   - Provider azurerm actualizado (este pide ~> 3.116; el actual es 5.x).
# =============================================================================

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  name = "${var.project_name}-${random_id.suffix.hex}"
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name}"
  location = var.location
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_registry" "this" {
  name                = replace("acr${local.name}", "-", "")
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"
  admin_enabled       = true
}

# --- Azure Container Apps (donde corre el FastAPI + LangGraph) ---
resource "azurerm_container_app_environment" "this" {
  name                       = "cae-${local.name}"
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
}

resource "azurerm_container_app" "agent" {
  name                         = "ca-${local.name}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.this.admin_password
  }

  registry {
    server               = azurerm_container_registry.this.login_server
    username             = azurerm_container_registry.this.admin_username
    password_secret_name = "acr-password"
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "agent"
      image  = var.container_image
      cpu    = 0.5
      memory = "1Gi"
      # Pendiente (ver encabezado): GEMINI_API_KEY y DATABASE_URL como
      # secretos, y el tamano que necesita E5.
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}
