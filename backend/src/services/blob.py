'''
initializes azure blob service client and container client. lazy/global way so once per worker
utility functions to check_blob,upload_raw, delete_raw,read_blob

'''
import json
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, ContentSettings
from azure.core.exceptions import ResourceNotFoundError
from typing import Optional
from datetime import datetime, timezone
from ..utils.sanitize_file_path import sanitize_file_path
from ..config import AZURE_STORAGE_CONNECTION_STRING, AZURE_CONTAINER_RAW_FOLDER_PREFIX, AZURE_CONTAINER_NAME

_blob_service_client: Optional[BlobServiceClient] = None
_container_client: Optional[ContainerClient] = None


def _initialize_clients() -> None:
    global _blob_service_client, _container_client
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise ValueError(
            "AZURE_STORAGE_CONNECTION_STRING is not configured. "
            "Please set it in environment."
        )
    _blob_service_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING)
    _container_client = _blob_service_client.get_container_client(
        AZURE_CONTAINER_NAME)
    try:
        _container_client.get_container_properties()
    except ResourceNotFoundError:
        _container_client.create_container()
        print(f"Created container: {AZURE_CONTAINER_NAME}")


def _get_container_client() -> ContainerClient:
    if _container_client is None:
        _initialize_clients()
    return _container_client


def get_blob_client(blob_path: str) -> BlobClient:
    container_client = _get_container_client()
    return container_client.get_blob_client(blob_path)


def blob_exists(blob_path: str) -> bool:
    try:
        blob_client = get_blob_client(blob_path)
        blob_client.get_blob_properties()
        return True
    except ResourceNotFoundError:
        return False
    except Exception:
        return False


def upload_raw(session_id: str, filename: str, file_bytes: bytes) -> str:
    filename = sanitize_file_path(filename)
    blob_path = f"{AZURE_CONTAINER_RAW_FOLDER_PREFIX}/{session_id}/{filename}"
    metadata = {
        "session_id": session_id, "upload_type": "raw", "uploaded_at": datetime.now().isoformat()}

    blob_client = get_blob_client(blob_path)
    blob_client.upload_blob(
        file_bytes, overwrite=False, metadata=metadata
    )
    return blob_path


def _delete_prefix(container_client: ContainerClient, prefix: str) -> int:
    blobs_to_delete = list(container_client.list_blobs(name_starts_with=prefix))
    delete_count = 0
    for blob in blobs_to_delete:
        blob_client = container_client.get_blob_client(blob.name)
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            pass
        delete_count += 1
    return delete_count


def delete_raw(session_id: str) -> int:
    container_client = _get_container_client()
    prefix = f"{AZURE_CONTAINER_RAW_FOLDER_PREFIX}/{session_id}/"
    return _delete_prefix(container_client, prefix)


# Every blob prefix a session can ever have data under (see the blob path
# convention -- extraction through render). Not including AZURE_CONTAINER_RAW_
# FOLDER_PREFIX by name here since delete_raw() already covers that one and
# callers of delete_all_session_blobs() may have already run it separately.
_ALL_SESSION_BLOB_PREFIXES = (
    "extracted",
    "normalized",
    "anonymized",
    "scored",
    "prompt",
    "roast",
    "render",
)


def delete_all_session_blobs(session_id: str) -> int:
    """Deletes every blob for a session across all pipeline stages, including raw."""
    container_client = _get_container_client()
    delete_count = delete_raw(session_id)
    for prefix_name in _ALL_SESSION_BLOB_PREFIXES:
        prefix = f"{prefix_name}/{session_id}/"
        delete_count += _delete_prefix(container_client, prefix)
    return delete_count


def upload_extracted(
    *,
    session_id: str,
    data: dict,
) -> str:
    blob_path = f"extracted/{session_id}/extracted.json"
    blob_client = get_blob_client(blob_path=blob_path)
    payload = json.dumps(data, ensure_ascii=True).encode("utf-8")
    blob_client.upload_blob(payload, overwrite=True)
    return blob_path


def read_blob(blob_path: str) -> bytes:
    blob_client = get_blob_client(blob_path)
    return blob_client.download_blob().readall()


def upload_normalized(session_id, data):
    blob_path = f"normalized/{session_id}/normalized.json"
    blob_client = get_blob_client(blob_path=blob_path)
    payload = json.dumps(data, ensure_ascii=True).encode("utf-8")
    blob_client.upload_blob(payload, overwrite=True)
    return blob_path


def upload_anonymized(session_id, data):
    blob_path = f"anonymized/{session_id}/anonymized.json"
    blob_client = get_blob_client(blob_path=blob_path)
    payload = json.dumps(data, ensure_ascii=True).encode("utf-8")
    blob_client.upload_blob(payload, overwrite=True)
    return blob_path


def upload_scored(session_id, data):
    blob_path = f"scored/{session_id}/scored.json"
    blob_client = get_blob_client(blob_path=blob_path)
    payload = json.dumps(data, ensure_ascii=True).encode("utf-8")
    blob_client.upload_blob(payload, overwrite=True)
    return blob_path

def upload_prompt(session_id: str, prompt: str) -> str:
    blob_path = f"prompt/{session_id}/prompt.txt"
    blob_client = get_blob_client(blob_path=blob_path)
    blob_client.upload_blob(prompt.encode("utf-8"), overwrite=True)
    return blob_path


def read_prompt(session_id: str) -> str:
    blob_path = f"prompt/{session_id}/prompt.txt"
    return read_blob(blob_path).decode("utf-8")


def upload_roast(session_id: str, data: dict) -> str:
    blob_path = f"roast/{session_id}/roast.json"
    blob_client = get_blob_client(blob_path=blob_path)
    payload = json.dumps(data, ensure_ascii=True).encode("utf-8")
    blob_client.upload_blob(payload, overwrite=True)
    return blob_path


def upload_render(session_id: str, png_bytes: bytes) -> str:
    blob_path = f"render/{session_id}/render.png"
    blob_client = get_blob_client(blob_path=blob_path)
    blob_client.upload_blob(png_bytes, overwrite=True, content_settings=ContentSettings(content_type="image/png"))
    return blob_path


def initialize_blob_storage() -> None:
    # explicit initialization, jsut call once at fastapi
    _initialize_clients()
