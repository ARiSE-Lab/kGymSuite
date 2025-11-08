from .storage_abc import AbstractStorageBackend, StorageProviderConfig
from .storage_gcs import GCSStorageBackend
from .storage_local import LocalStorageBackend

async def create_storage_backend(config: StorageProviderConfig) -> AbstractStorageBackend:
    if config.providerType == 'gcs':
        return GCSStorageBackend(config)
    if config.providerType == 'local':
        return LocalStorageBackend(config)
