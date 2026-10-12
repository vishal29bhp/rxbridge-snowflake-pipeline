"""Secrets come from Azure Key Vault; .env only says which vault (RX_KEY_VAULT_URL).

Each secret has an environment-variable name (what the code and dbt use) and a Key Vault name
(Key Vault allows only letters, digits and dashes). Lookup order:

  1. RX_KEY_VAULT_URL set  -> the secret from Key Vault, signed in as you (`az login`)
  2. not in the vault, or no vault configured -> the environment variable / .env line (local fallback)

Nothing is fetched until a secret is first used, so offline commands never touch Azure.
"""

from __future__ import annotations

import functools
import os

# environment variable -> Key Vault secret name
SECRETS = {
    "AZURE_STORAGE_CONNECTION_STRING": "azure-storage-connection-string",
    "AZURE_DI_KEY": "azure-di-key",
    "SNOWFLAKE_PASSWORD": "snowflake-password",
}


def vault_url() -> str | None:
    return os.getenv("RX_KEY_VAULT_URL") or None


@functools.lru_cache(maxsize=None)
def _client(url: str):
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    return SecretClient(vault_url=url, credential=DefaultAzureCredential())


def _from_vault(env_name: str) -> str | None:
    url = vault_url()
    if not url:
        return None
    from azure.core.exceptions import ResourceNotFoundError

    try:
        return _client(url).get_secret(SECRETS[env_name]).value or None
    except ResourceNotFoundError:
        return None


@functools.lru_cache(maxsize=None)
def get_secret(env_name: str) -> str | None:
    """The secret's value, or None if neither the vault nor the environment has it."""
    return _from_vault(env_name) or os.getenv(env_name) or None


def source(env_name: str) -> str:
    """Where a secret would come from: 'key vault', 'env' or 'missing'. Never returns the value."""
    if _from_vault(env_name):
        return "key vault"
    return "env" if os.getenv(env_name) else "missing"


def set_secret(env_name: str, value: str) -> None:
    url = vault_url()
    if not url:
        raise SystemExit("Set RX_KEY_VAULT_URL in .env first (terraform output -raw key_vault_url).")
    _client(url).set_secret(SECRETS[env_name], value)
    get_secret.cache_clear()
