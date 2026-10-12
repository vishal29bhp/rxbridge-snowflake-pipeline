# Azure infrastructure (Terraform)

Creates everything RxBridge needs **inside the existing resource group `rxbridge-snowflake`**:

| Resource | Why |
|---|---|
| Storage account (private, TLS 1.2, versioning + 7-day soft delete) | Holds the original documents. Versioning means an overwritten original can always be recovered. |
| Container `rx-archive` | `inbox/`, `_meta/`, `results/` |
| Document Intelligence (F0 free tier) | Reads the documents (`prebuilt-read` + `prebuilt-layout`) |
| Key Vault (RBAC) + secrets `azure-storage-connection-string`, `azure-di-key` | Keeps keys out of `.env`. rxpipe reads them as you (`az login`). |
| "Key Vault Secrets Officer" for you | Terraform writes the secrets, rxpipe reads them, you add `snowflake-password` |
| Role assignment for you | Browse and upload files in the portal |
| **Phase 2:** "Storage Blob Data Reader" for Snowflake's app | Lets Snowflake's stage read the container. Replaces the manual IAM click. |
| Optional (`enable_automation = true`): Storage Queue + Event Grid | Feeds `snowflake/90_automation.sql` (auto-refresh + Snowpipe) |

The resource group itself is read with a `data` source, so `terraform destroy` removes what Terraform
created and **leaves the group alone**.

## Phase 1 — create the resources

```bash
cd infra/terraform
az login
az account set --subscription "<your subscription>"
cp terraform.tfvars.example terraform.tfvars      # set subscription_id
terraform init
terraform plan
terraform apply

terraform output -raw env_file >> ../../.env      # vault URL + non-secret values (no keys)
```
Then add your non-secret Snowflake values to `.env`, store the password in the vault
(`python -m rxpipe secret set SNOWFLAKE_PASSWORD`, from the project root) and continue with
**README Step 3** (Snowflake admin setup).

## Phase 2 — let Snowflake read the container

`00_admin_setup.sql` ends with `DESC STORAGE INTEGRATION RX_AZURE_INT`. Open **AZURE_CONSENT_URL** and click
**Accept**. The URL contains `client_id=<guid>`: put that guid in `terraform.tfvars`:

```hcl
snowflake_storage_app_client_id = "<guid from the consent URL>"
```

```bash
terraform apply      # adds only the "Storage Blob Data Reader" role assignment
```
Wait a few minutes, then in Snowsight: `LIST @RX_DB.RAW.DOCS_STAGE;` should run without an access error.

Why two phases? Snowflake's app only exists in your tenant after you accept the consent URL, and that
needs the storage integration, which needs the storage account. So the dependency order is:
storage → integration → consent → role assignment.

## Notes

- **State:** this uses local state (`terraform.tfstate`, git-ignored). It still contains the storage and
  Document Intelligence keys (Terraform has to know them to write them to the vault), so keep it safe. For a team, move it to an Azure Storage backend.
- **Region:** Document Intelligence uses `docintel_location` (default `centralindia`), separate from `location`, because it isn't offered in every region (for example westindia).
- **Key Vault:** soft delete is 7 days and purge protection is off, so `terraform destroy` followed by a
  new apply works. Rotate a key in Azure, then `terraform apply` to copy the new value into the vault.
- **Cost:** storage costs pennies; Key Vault standard is a few cents per 10,000 reads; Document Intelligence F0 is free (500 pages/month); the Event Grid +
  queue option costs fractions of a penny at this volume.
- CI runs `terraform fmt -check` and `terraform validate` on every push.
