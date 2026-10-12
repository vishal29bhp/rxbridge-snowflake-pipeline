# Everything RxBridge needs in Azure, created inside the existing resource group:
#   1. a private storage account + the rx-archive container        (the documents)
#   2. Azure AI Document Intelligence                             (reads the documents)
#   3. optional: Storage Queue + Event Grid for automatic loading (90_automation.sql)
#   4. phase 2: role assignments that let Snowflake read the container (replaces the portal clicks)

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

locals {
  location             = coalesce(var.location, data.azurerm_resource_group.rg.location)
  storage_account_name = coalesce(var.storage_account_name, "rxbridgedocs${random_string.suffix.result}")
  docintel_name        = "rx-docintel-${random_string.suffix.result}"

  tags = merge({
    project    = "rxbridge"
    component  = "document-pipeline"
    managed_by = "terraform"
  }, var.tags)
}

# ---------------------------------------------------------------- 1. storage
# No anonymous access to patient documents, ever. Shared keys stay on because the
# laptop step uses the connection string; versioning means an overwritten original
# can always be recovered.
resource "azurerm_storage_account" "docs" {
  name                            = local.storage_account_name
  resource_group_name             = data.azurerm_resource_group.rg.name
  location                        = local.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = true

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  tags = local.tags
}

resource "azurerm_storage_container" "archive" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.docs.id
  container_access_type = "private"
}

# ---------------------------------------------------------------- 2. Document Intelligence
# kind "FormRecognizer" is Azure's resource type name for Document Intelligence.
resource "azurerm_cognitive_account" "docintel" {
  name                  = local.docintel_name
  resource_group_name   = data.azurerm_resource_group.rg.name
  location              = coalesce(var.docintel_location, local.location)
  kind                  = "FormRecognizer"
  sku_name              = var.docintel_sku
  custom_subdomain_name = local.docintel_name
  tags                  = local.tags
}

# ---------------------------------------------------------------- 3. automation (optional)
resource "azurerm_storage_queue" "events" {
  count                = var.enable_automation ? 1 : 0
  name                 = var.queue_name
  storage_account_name = azurerm_storage_account.docs.name
}

resource "azurerm_eventgrid_system_topic" "storage" {
  count               = var.enable_automation ? 1 : 0
  name                = "rx-storage-events"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = local.location
  source_resource_id  = azurerm_storage_account.docs.id
  topic_type          = "Microsoft.Storage.StorageAccounts"
  tags                = local.tags
}

resource "azurerm_eventgrid_system_topic_event_subscription" "blob_created" {
  count                = var.enable_automation ? 1 : 0
  name                 = "rx-blob-created"
  system_topic         = azurerm_eventgrid_system_topic.storage[0].name
  resource_group_name  = data.azurerm_resource_group.rg.name
  included_event_types = ["Microsoft.Storage.BlobCreated"]

  subject_filter {
    subject_begins_with = "/blobServices/default/containers/${var.container_name}/"
  }

  storage_queue_endpoint {
    storage_account_id = azurerm_storage_account.docs.id
    queue_name         = azurerm_storage_queue.events[0].name
  }
}

# ---------------------------------------------------------------- 4. access
# You (whoever runs Terraform) can browse and upload files in the portal.
resource "azurerm_role_assignment" "current_user_blob" {
  count                = var.grant_current_user_blob_access ? 1 : 0
  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# PHASE 2: Snowflake's storage-integration app may READ the container (never write).
data "azuread_service_principal" "snowflake_storage" {
  count     = var.snowflake_storage_app_client_id == "" ? 0 : 1
  client_id = var.snowflake_storage_app_client_id
}

resource "azurerm_role_assignment" "snowflake_blob_reader" {
  count                = var.snowflake_storage_app_client_id == "" ? 0 : 1
  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = data.azuread_service_principal.snowflake_storage[0].object_id
}

# PHASE 2 (automation): Snowflake's notification app may read and delete queue messages.
data "azuread_service_principal" "snowflake_queue" {
  count     = var.enable_automation && var.snowflake_queue_app_client_id != "" ? 1 : 0
  client_id = var.snowflake_queue_app_client_id
}

resource "azurerm_role_assignment" "snowflake_queue_contributor" {
  count                = var.enable_automation && var.snowflake_queue_app_client_id != "" ? 1 : 0
  scope                = azurerm_storage_account.docs.id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = data.azuread_service_principal.snowflake_queue[0].object_id
}
