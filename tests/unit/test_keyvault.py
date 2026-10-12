"""Secrets: Key Vault first, environment as fallback, and nothing fetched until first use."""

import pytest
from azure.core.exceptions import ResourceNotFoundError

from rxpipe import keyvault
from rxpipe.config import Settings


class FakeVault:
    def __init__(self, secrets):
        self.secrets = dict(secrets)
        self.calls = 0

    def get_secret(self, name):
        self.calls += 1
        if name not in self.secrets:
            raise ResourceNotFoundError(f"{name} not found")
        return type("Secret", (), {"value": self.secrets[name]})()

    def set_secret(self, name, value):
        self.secrets[name] = value


@pytest.fixture
def vault(monkeypatch):
    fake = FakeVault({"azure-di-key": "di-from-vault", "azure-storage-connection-string": "conn-from-vault"})
    monkeypatch.setenv("RX_KEY_VAULT_URL", "https://rx-kv-test.vault.azure.net/")
    monkeypatch.setattr(keyvault, "_client", lambda url: fake)
    keyvault.get_secret.cache_clear()
    yield fake
    keyvault.get_secret.cache_clear()


@pytest.fixture
def no_vault(monkeypatch):
    monkeypatch.delenv("RX_KEY_VAULT_URL", raising=False)
    keyvault.get_secret.cache_clear()
    yield
    keyvault.get_secret.cache_clear()


def test_vault_wins_over_env(vault, monkeypatch):
    monkeypatch.setenv("AZURE_DI_KEY", "stale-key-in-dotenv")
    assert Settings().azure_di_key == "di-from-vault"
    assert Settings().azure_storage_conn == "conn-from-vault"


def test_falls_back_to_env_when_secret_not_in_vault(vault, monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "pw-from-env")
    assert Settings().sf_password == "pw-from-env"


def test_env_only_without_vault(no_vault, monkeypatch):
    monkeypatch.setenv("AZURE_DI_KEY", "di-from-env")
    monkeypatch.delenv("SNOWFLAKE_PASSWORD", raising=False)
    s = Settings()
    assert s.azure_di_key == "di-from-env"
    assert s.sf_password is None


def test_building_settings_does_not_touch_the_vault(vault):
    Settings()
    assert vault.calls == 0


def test_each_secret_fetched_once(vault):
    for _ in range(3):
        Settings().azure_di_key
    assert vault.calls == 1


def test_set_secret_stores_under_vault_name(vault):
    keyvault.set_secret("SNOWFLAKE_PASSWORD", "new-pw")
    assert vault.secrets["snowflake-password"] == "new-pw"
    assert Settings().sf_password == "new-pw"


def test_source_never_reveals_value(vault, monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "pw")
    monkeypatch.delenv("AZURE_DI_KEY", raising=False)
    assert keyvault.source("AZURE_DI_KEY") == "key vault"
    assert keyvault.source("SNOWFLAKE_PASSWORD") == "env"


def test_set_secret_needs_a_vault(no_vault):
    with pytest.raises(SystemExit, match="RX_KEY_VAULT_URL"):
        keyvault.set_secret("SNOWFLAKE_PASSWORD", "x")
