variable "project_name" {
  description = "Prefijo corto para nombrar los recursos, ej: kognia-agent"
  type        = string
  default     = "kognia-agent"
}

variable "location" {
  description = "Región de Azure. Revisa que tenga cupo/soporte para el modelo elegido."
  type        = string
  default     = "swedencentral"
}

variable "openai_model_name" {
  description = "Modelo a desplegar en Azure OpenAI (gpt-4o-mini recomendado para el hackathon: barato y rápido)"
  type        = string
  default     = "gpt-4o-mini"
}

variable "openai_model_version" {
  type    = string
  default = "2024-07-18"
}

variable "openai_sku_name" {
  type    = string
  default = "S0"
}

variable "container_image" {
  description = <<-EOT
    Imagen del agente a desplegar en Container Apps.
    En el primer `apply` (antes de tener imagen propia en el ACR)
    deja el valor por defecto; luego de construir y pushear tu imagen
    al ACR (ver README de esta carpeta), vuelve a aplicar apuntando a
    "<acr_login_server>/agent:latest".
  EOT
  type    = string
  default = "mcr.microsoft.com/k8se/quickstart:latest"
}
