"""Azure Blob Storage backend for job artifacts.

Mirrors the local-disk interface used by StorageManager but reads/writes
to Azure Blob Storage instead of the local filesystem.

Usage
-----
Set these env vars:

    PDVE_STORAGE_BACKEND=azure
    PDVE_AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
    PDVE_AZURE_STORAGE_CONTAINER=pdve-jobs   # created automatically on first use

The container uses a flat namespace mirroring the local directory layout:

    {job_id}/raw/{filename}
    {job_id}/prep/{filename}
    {job_id}/signals/{name}.json
    {job_id}/plans/{name}.json
    {job_id}/dsl/timeline.json
    {job_id}/outputs/final.mp4
    {job_id}/outputs/thumbnail.png

Large binary files (raw uploads, final.mp4, thumbnail.png) are stored as
blobs. JSON signals/plans/dsl are stored as blobs too (small, cheap).

Download URLs
-------------
Use generate_sas_url() to create time-limited SAS URLs for video download
and thumbnail serving — replaces the FileResponse approach used locally.
"""

from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO

from app.core.logger import get_logger

log = get_logger(__name__)

# Lazy import so the rest of the app starts even if azure-storage-blob
# isn't installed (local-only deployments don't need it).
_BlobServiceClient = None
_generate_sas_token = None


def _get_sdk():
    global _BlobServiceClient, _generate_sas_token
    if _BlobServiceClient is None:
        try:
            from azure.storage.blob import (  # type: ignore
                BlobServiceClient,
                generate_blob_sas,
                BlobSasPermissions,
            )
            _BlobServiceClient = BlobServiceClient
            _generate_sas_token = (generate_blob_sas, BlobSasPermissions)
        except ImportError as e:
            raise RuntimeError(
                "azure-storage-blob is not installed. "
                "Run: pip install azure-storage-blob"
            ) from e
    return _BlobServiceClient, _generate_sas_token


class AzureBlobStore:
    """Thin wrapper around Azure Blob Storage for job artifact I/O."""

    def __init__(self, connection_string: str, container_name: str):
        BlobServiceClient, _ = _get_sdk()
        self._client = BlobServiceClient.from_connection_string(connection_string)
        self._container = container_name
        self._ensure_container()

    def _ensure_container(self) -> None:
        """Create the container if it doesn't exist."""
        try:
            self._client.create_container(self._container)
            log.info("Created Azure Blob container: %s", self._container)
        except Exception:
            pass  # Already exists

    def _blob_name(self, job_id: str, stage: str, filename: str) -> str:
        return f"{job_id}/{stage}/{filename}"

    # --- Upload ---

    def upload_file(self, job_id: str, stage: str, local_path: Path) -> str:
        """Upload a local file to blob storage. Returns the blob name."""
        blob_name = self._blob_name(job_id, stage, local_path.name)
        blob_client = self._client.get_blob_client(
            container=self._container, blob=blob_name
        )
        with open(local_path, "rb") as f:
            blob_client.upload_blob(f, overwrite=True)
        log.debug("Uploaded %s → %s", local_path.name, blob_name)
        return blob_name

    def upload_bytes(self, job_id: str, stage: str, filename: str, data: bytes) -> str:
        """Upload raw bytes (e.g. JSON) to blob storage."""
        blob_name = self._blob_name(job_id, stage, filename)
        blob_client = self._client.get_blob_client(
            container=self._container, blob=blob_name
        )
        blob_client.upload_blob(data, overwrite=True)
        return blob_name

    # --- Download ---

    def download_to_file(self, job_id: str, stage: str, filename: str, dest: Path) -> None:
        """Download a blob to a local path."""
        blob_name = self._blob_name(job_id, stage, filename)
        blob_client = self._client.get_blob_client(
            container=self._container, blob=blob_name
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            download = blob_client.download_blob()
            download.readinto(f)
        log.debug("Downloaded %s → %s", blob_name, dest)

    def download_bytes(self, job_id: str, stage: str, filename: str) -> bytes:
        """Download a blob as bytes."""
        blob_name = self._blob_name(job_id, stage, filename)
        blob_client = self._client.get_blob_client(
            container=self._container, blob=blob_name
        )
        return blob_client.download_blob().readall()

    def download_json(self, job_id: str, stage: str, name: str) -> dict | list:
        """Download and parse a JSON blob."""
        raw = self.download_bytes(job_id, stage, f"{name}.json")
        return json.loads(raw.decode("utf-8"))

    def upload_json(self, job_id: str, stage: str, name: str, data: dict | list) -> str:
        """Serialize and upload a JSON blob."""
        payload = json.dumps(data, indent=2, default=str).encode("utf-8")
        return self.upload_bytes(job_id, stage, f"{name}.json", payload)

    def blob_exists(self, job_id: str, stage: str, filename: str) -> bool:
        blob_name = self._blob_name(job_id, stage, filename)
        blob_client = self._client.get_blob_client(
            container=self._container, blob=blob_name
        )
        try:
            blob_client.get_blob_properties()
            return True
        except Exception:
            return False

    # --- SAS URLs (replaces FileResponse for download/thumbnail) ---

    def generate_sas_url(
        self,
        job_id: str,
        stage: str,
        filename: str,
        expiry_hours: int = 1,
    ) -> str:
        """Generate a time-limited SAS URL for direct browser download/stream.

        Use this instead of FileResponse when PDVE_STORAGE_BACKEND=azure.
        """
        _, (generate_blob_sas, BlobSasPermissions) = _get_sdk()

        blob_name = self._blob_name(job_id, stage, filename)
        account_name = self._client.account_name
        account_key = self._client.credential.account_key

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self._container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        )
        return (
            f"https://{account_name}.blob.core.windows.net"
            f"/{self._container}/{blob_name}?{sas_token}"
        )

    # --- List ---

    def list_blobs(self, job_id: str, stage: str) -> list[str]:
        """List blob names in a job stage prefix."""
        prefix = f"{job_id}/{stage}/"
        container_client = self._client.get_container_client(self._container)
        return [
            b.name[len(prefix):]
            for b in container_client.list_blobs(name_starts_with=prefix)
        ]

    # --- Delete ---

    def delete_stage(self, job_id: str, stage: str) -> int:
        """Delete all blobs in a job stage. Returns count deleted."""
        prefix = f"{job_id}/{stage}/"
        container_client = self._client.get_container_client(self._container)
        blobs = list(container_client.list_blobs(name_starts_with=prefix))
        for blob in blobs:
            container_client.delete_blob(blob.name)
        return len(blobs)


# --- Singleton accessor ---

_store: AzureBlobStore | None = None


def get_blob_store() -> AzureBlobStore:
    """Return the singleton AzureBlobStore, creating it on first call."""
    global _store
    if _store is None:
        from app.core.config import settings
        conn_str = settings.azure_storage_connection_string
        container = settings.azure_storage_container
        if not conn_str:
            raise RuntimeError(
                "PDVE_AZURE_STORAGE_CONNECTION_STRING is not set. "
                "Set it or use PDVE_STORAGE_BACKEND=local."
            )
        _store = AzureBlobStore(conn_str, container)
    return _store
