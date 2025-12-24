'''
initializes azure blob service client and container client. lazy/global way so once per worker
utility functions to check_blob,upload_raw, delete_raw,read_blob

'''
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.core.exceptions import ResourceNotFoundError
from typing import Optional
from datetime import datetime, timezone
from ..utils.sanitize_file_path import sanitize_file_path
from ..config import AZURE_STORAGE_CONNECTION_STRING,AZURE_CONTAINER_RAW_FOLDER_PREFIX, AZURE_CONTAINER_NAME

_blob_service_client: Optional[BlobServiceClient] = None
_container_client: Optional[ContainerClient] = None

def _initialize_clients() -> None:
    global _blob_service_client , _container_client
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise ValueError(
            "AZURE_STORAGE_CONNECTION_STRING is not configured. "
            "Please set it in environment."
        )
    _blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    _container_client = _blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
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
        blob_client =  get_blob_client(blob_path)
        blob_client.get_blob_properties()
        return True
    except ResourceNotFoundError as e:
        return False
    except e:
        return False

def upload_raw(session_id: str,filename : str,file_bytes: bytes) -> str:
    filename = sanitize_file_path(filename)
    blob_path = f"{AZURE_CONTAINER_RAW_FOLDER_PREFIX}/{session_id}/{filename}"
    metadata = {
        "session_id": session_id, "upload_type":"raw", "uploaded_at": datetime.now().isoformat()    }

    blob_client = get_blob_client(blob_path)
    blob_client.upload_blob(
        file_bytes, overwrite=False, metadata=metadata
    )
    return blob_path

def delete_raw(session_id:str) -> int:
    container_client = _get_container_client()
    prefix = f"{AZURE_CONTAINER_RAW_FOLDER_PREFIX}/{session_id}/"

    blob_to_delete = list(container_client.list_blobs(name_starts_with=prefix))
    delete_count = 0
    for blob in blob_to_delete:
        blob_client = container_client.get_blob_client(blob.name)
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            pass
        delete_count += 1
    return delete_count
import json
def upload_extracted(
    *,
    session_id: str,
    data: dict,
) -> str:
    blob_path = f"extracted/{session_id}/extracted.json"
    blob_client = get_blob_client(blob_path=blob_path)
    try:
        payload = json.dumps(data,ensure_ascii=True).encode("utf-8")
        blob_client.upload_blob(payload, overwrite=True)
    except Exception as e:
        pass
    return blob_path

def read_blob(blob_path: str)-> bytes:
    blob_client = get_blob_client(blob_path)
    return blob_client.download_blob().readall()

def initialize_blob_storage() -> None:
    # explicit initialization, jsut call once at fastapi
    _initialize_clients()