variable "subscription_id" {
  description = "Azure subscription that contains the resource group (az account show --query id -o tsv)."
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group. Terraform creates resources in it but does not manage the group itself."
  type        = string
  default     = "rxbridge-snowflake"
}

variable "location" {
  description = "Azure region. Defaults to the resource group's region. Use the same region as your Snowflake account."
  type        = string
  default     = null
}

variable "storage_account_name" {
  description = "Globally unique, 3-24 lowercase letters/digits. Leave null to generate rxbridgedocs<random>."
  type        = string
  default     = null
}

variable "container_name" {
  description = "Blob container holding inbox/, _meta/ and results/."
  type        = string
  default     = "rx-archive"
}

variable "docintel_sku" {
  description = "Document Intelligence pricing tier: F0 (free, 500 pages/month) or S0 (pay as you go)."
  type        = string
  default     = "F0"
}

variable "docintel_location" {
  description = "Region for Document Intelligence if it is not offered in var.location. Null = same region."
  type        = string
  default     = null
}

variable "enable_automation" {
  description = "Create the Storage Queue + Event Grid subscription used by snowflake/90_automation.sql."
  type        = bool
  default     = false
}

variable "queue_name" {
  description = "Storage Queue that receives BlobCreated events (only when enable_automation = true)."
  type        = string
  default     = "rx-blob-events"
}

variable "snowflake_storage_app_client_id" {
  description = <<-EOT
    PHASE 2. The client_id of Snowflake's app for the storage integration. After running
    00_admin_setup.sql, open AZURE_CONSENT_URL, accept it, and copy the client_id=... value
    from that URL. Leave empty on the first apply.
  EOT
  type        = string
  default     = ""
}

variable "snowflake_queue_app_client_id" {
  description = "PHASE 2 (automation only). client_id from the notification integration's AZURE_CONSENT_URL."
  type        = string
  default     = ""
}

variable "grant_current_user_blob_access" {
  description = "Give the identity running Terraform 'Storage Blob Data Contributor', so you can browse files in the portal."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags for every resource."
  type        = map(string)
  default     = {}
}
