
from pydantic import BaseModel, RootModel
from .storage_abc import AbstractStorageBackend, StorageProviderConfig
from typing import Literal
from ..utils import run_async
import shutil, os

class LocalStorageProviderConfigSetting(BaseModel):
    root: str

class LocalStorageProviderConfig(StorageProviderConfig):
    providerType: Literal['local']
    providerConfig: RootModel[LocalStorageProviderConfigSetting]

class LocalStorageBackend(AbstractStorageBackend):

    def __init__(self, storage_config: StorageProviderConfig):
        self.storage_config = LocalStorageProviderConfig(**storage_config.model_dump())
        self._root = self.storage_config.providerConfig.root.root

    async def download_resource(self, key: str, local_path: str):
        await run_async(os.makedirs, os.path.dirname(os.path.join(self._root, key)), exist_ok=True)
        await run_async(shutil.copy, os.path.join(self._root, key), local_path)

    async def upload_resource(self, local_path: str, key: str):
        await run_async(os.makedirs, os.path.dirname(os.path.join(self._root, key)), exist_ok=True)
        await run_async(shutil.copy, local_path, os.path.join(self._root, key))

    async def delete_resource(self, key: str):
        if not await run_async(os.path.exists, os.path.join(self._root, key)):
            return
        await run_async(os.remove, os.path.join(self._root, key))

    async def list_resources(self, key_prefix: str) -> list[str]:
        if not await run_async(os.path.isdir, os.path.join(self._root, key_prefix)):
            return []
        filenames = await run_async(os.listdir, os.path.join(self._root, key_prefix))
        ret = []
        for fname in filenames:
            ret.append(os.path.join(self._root, fname))
        return ret

    async def get_resource_url(self, key: str) -> str:
        return os.path.abspath(os.path.join(self._root, key))
