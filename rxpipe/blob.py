"""Azure Blob Storage: the only place the original files live. The pipeline never edits them.

Container layout (one container, three folders):
  inbox/     the documents (PDFs, photos, scans, TIFFs)      -> Snowflake stage RAW.DOCS_STAGE
  _meta/     manifest.csv, patients.csv                      -> Snowflake stage RAW.META_STAGE
  results/   AI output, one JSONL file per batch             -> Snowflake stage RAW.RESULTS_STAGE
"""

from __future__ import annotations

from pathlib import Path


class BlobStore:
    def __init__(self, connection_string: str, container: str):
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(connection_string)
        self.container = service.get_container_client(container)
        if not self.container.exists():
            self.container.create_container()

    def upload_file(self, local: Path, blob_name: str, overwrite: bool = False) -> bool:
        """Returns False if the blob already exists and overwrite is False (originals are immutable)."""
        client = self.container.get_blob_client(blob_name)
        if client.exists() and not overwrite:
            return False
        with open(local, "rb") as f:
            client.upload_blob(f, overwrite=overwrite)
        return True

    def upload_bytes(self, data: bytes, blob_name: str) -> None:
        self.container.get_blob_client(blob_name).upload_blob(data, overwrite=True)

    def download(self, blob_name: str) -> bytes:
        return self.container.download_blob(blob_name).readall()

    def delete_prefix(self, prefix: str) -> int:
        names = self.list(prefix)
        for n in names:
            self.container.delete_blob(n)
        return len(names)

    def list(self, prefix: str = "") -> list[str]:
        return [b.name for b in self.container.list_blobs(name_starts_with=prefix)]


def get_blob_store(settings) -> BlobStore:
    if not settings.azure_storage_conn:
        raise SystemExit("No storage connection string: set RX_KEY_VAULT_URL in .env (python -m rxpipe secret check), or AZURE_STORAGE_CONNECTION_STRING for a local run.")
    return BlobStore(settings.azure_storage_conn, settings.azure_container)
