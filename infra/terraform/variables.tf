variable "project_name" {
  description = "Prefijo corto para nombrar los recursos, ej: kognia-agent"
  type        = string
  default     = "kognia-agent"
}

variable "location" {
  description = "Región de Azure. Desde Colombia, eastus2 suele dar buena latencia y precio."
  type        = string
  default     = "eastus2"
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
