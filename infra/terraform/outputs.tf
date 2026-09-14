output "agent_url" {
  description = "URL pública del agente desplegado"
  value       = "https://${azurerm_container_app.agent.ingress[0].fqdn}"
}

output "acr_login_server" {
  description = "Registro de contenedores: aquí pusheas tu imagen (docker build + push)"
  value       = azurerm_container_registry.this.login_server
}

output "azure_openai_endpoint" {
  value = azurerm_cognitive_account.openai.endpoint
}

output "azure_openai_deployment" {
  value = azurerm_cognitive_deployment.agent_model.name
}
