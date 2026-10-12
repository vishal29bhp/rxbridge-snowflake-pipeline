output "storage_account_name" {
  value = azurerm_storage_account.docs.name
}

output "container_name" {
  value = azurerm_storage_container.archive.name
}

output "snowflake_allowed_location" {
  description = "Goes into STORAGE_ALLOWED_LOCATIONS (00_admin_setup.sql fills it in from .env)."
  value       = "azure://${azurerm_storage_account.docs.name}.blob.core.windows.net/${var.container_name}/"
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "docintel_endpoint" {
  value = azurerm_cognitive_account.docintel.endpoint
}

output "queue_uri" {
  value = var.enable_automation ? "https://${azurerm_storage_account.docs.name}.queue.core.windows.net/${var.queue_name}" : null
}

output "key_vault_name" {
  value = azurerm_key_vault.rx.name
}

output "key_vault_url" {
  value = azurerm_key_vault.rx.vault_uri
}

# Everything the pipeline needs, in .env format. No secrets: those are in Key Vault.
#   terraform output -raw env_file >> ../../.env
output "env_file" {
  description = "Append to the project's .env. Secrets are not in it; rxpipe reads them from Key Vault."
  value       = <<-EOT

    # ---- written by infra/terraform ----
    RX_KEY_VAULT_URL=${azurerm_key_vault.rx.vault_uri}
    AZURE_STORAGE_ACCOUNT=${azurerm_storage_account.docs.name}
    AZURE_CONTAINER=${var.container_name}
    AZURE_TENANT_ID=${data.azurerm_client_config.current.tenant_id}
    AZURE_QUEUE=${var.queue_name}
    AZURE_DI_ENDPOINT=${azurerm_cognitive_account.docintel.endpoint}
  EOT
}
