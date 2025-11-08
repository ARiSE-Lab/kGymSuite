from abc import ABC, abstractmethod
from pydantic import BaseModel, RootModel

class StorageProviderConfig(BaseModel):
    providerType: str
    providerConfig: RootModel | None

class AbstractStorageBackend(ABC):

    @abstractmethod
    def __init__(self, storage_config: StorageProviderConfig):
        pass

    @abstractmethod
    async def download_resource(self, key: str, local_path: str):
        pass

    @abstractmethod
    async def upload_resource(self, local_path: str, key: str):
        pass

    @abstractmethod
    async def delete_resource(self, key: str):
        pass

    @abstractmethod
    async def list_resources(self, key_prefix: str) -> list[str]:
        pass

    @abstractmethod
    async def get_resource_url(self, key: str) -> str:
        pass
