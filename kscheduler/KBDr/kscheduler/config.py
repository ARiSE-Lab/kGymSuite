from typing import List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from KBDr.kcore import StorageProviderConfig

class SchedulerConfig(BaseModel):
    model_config = ConfigDict(extra='allow')

    deploymentName: str
    allowedOrigins: List[str]
    storage: StorageProviderConfig
    workerConfigs: Dict[str, Dict[Any, Any]]
    dbPath: str
    listen: str=Field('0.0.0.0')
    listenPort: int=Field(8000)
