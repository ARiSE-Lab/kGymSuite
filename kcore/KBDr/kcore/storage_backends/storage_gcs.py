
from pydantic import BaseModel, RootModel
from .storage_abc import AbstractStorageBackend, StorageProviderConfig
from typing import Literal
from ..utils import run_async
import os

class GCSStorageProviderConfigSetting(BaseModel):
    bucketName: str

class GCSStorageProviderConfig(StorageProviderConfig):
    providerType: Literal['gcs']
    providerConfig: RootModel[GCSStorageProviderConfigSetting] | None

class GCSStorageBackend(AbstractStorageBackend):

    def __init__(self, storage_config: StorageProviderConfig):
        self.storage_config = GCSStorageProviderConfig(**storage_config.model_dump())

        from google.cloud.storage import Client
        self._client = Client()
        self._bucket = self._client.bucket(self.storage_config.providerConfig.root.bucketName)

    async def download_resource(self, key: str, local_path: str):
        from google.cloud.storage.transfer_manager import download_chunks_concurrently
        await run_async(download_chunks_concurrently, self._bucket.get_blob(key), local_path)

    async def upload_resource(self, local_path: str, key: str):
        from google.cloud.storage.transfer_manager import upload_chunks_concurrently
        await run_async(upload_chunks_concurrently, local_path, self._bucket.blob(key))

    async def delete_resource(self, key: str):
        await run_async(self._bucket.get_blob(key).delete)

    async def list_resources(self, key_prefix: str) -> list[str]:
        return [e.path for e in await run_async(self._bucket.list_blobs, prefix=key_prefix)]

    async def get_resource_url(self, key: str) -> str:
        return f'https://storage.cloud.google.com/{self.storage_config.providerConfig.root.bucketName}/{key}'
