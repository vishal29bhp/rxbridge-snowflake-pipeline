# ---------------------------------------------------------------- 5. Key Vault
# The pipeline's secrets live here instead of in .env. .env keeps only RX_KEY_VAULT_URL and
# non-secret settings; rxpipe reads each secret with your `az login` identity (DefaultAzureCredential).
#
#   azure-storage-connection-string   written by Terraform
#   azure-di-key                      written by Terraform
#   snowflake-password                you add it: python -m rxpipe secret set SNOWFLAKE_PASSWORD
#
# RBAC authorization (no access policies): access is an ordinary Azure role assignment.
resource "azurerm_key_vault" "rx" {
  name                       = local.key_vault_name
  resource_group_name        = data.azurerm_resource_group.rg.name
  location                   = local.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

# You (whoever runs Terraform) can read and write secrets: Terraform writes them, rxpipe reads them.
resource "azurerm_role_assignment" "current_user_kv_secrets" {
  scope                = azurerm_key_vault.rx.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# A new role assignment can take a minute to reach Key Vault; writing secrets before then fails with 403.
resource "time_sleep" "kv_rbac_propagation" {
  depends_on      = [azurerm_role_assignment.current_user_kv_secrets]
  create_duration = "60s"
}

resource "azurerm_key_vault_secret" "storage_connection_string" {
  name         = "azure-storage-connection-string"
  value        = azurerm_storage_account.docs.primary_connection_string
  key_vault_id = azurerm_key_vault.rx.id
  content_type = "Azure Storage connection string"
  depends_on   = [time_sleep.kv_rbac_propagation]
}

resource "azurerm_key_vault_secret" "docintel_key" {
  name         = "azure-di-key"
  value        = azurerm_cognitive_account.docintel.primary_access_key
  key_vault_id = azurerm_key_vault.rx.id
  content_type = "Document Intelligence key"
  depends_on   = [time_sleep.kv_rbac_propagation]
}
