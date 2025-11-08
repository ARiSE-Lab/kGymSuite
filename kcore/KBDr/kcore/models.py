from datetime import datetime

from typing import Any, Union, List, Tuple, Dict
from enum import Enum
from pydantic import GetCoreSchemaHandler, BaseModel, RootModel, ConfigDict, Field, SerializeAsAny
from pydantic_core import core_schema

class JobId(int):
    def __new__(cls, value):
        if isinstance(value, int):
            return int.__new__(cls, value)
        elif isinstance(value, str):
            return int.__new__(cls, int('0x' + value, 16))
        else:
            raise ValueError('Type not supported', type(value))

    def __add__(self, other):
        res = super(JobId, self).__add__(other)
        return self.__class__(res)

    def __sub__(self, other):
        res = super(JobId, self).__sub__(other)
        if res <= 0:
            raise ValueError()
        return self.__class__(res)

    def __mul__(self, other):
        raise NotImplementedError()

    def __div__(self, other):
        raise NotImplementedError()

    def __str__(self):
        s = hex(self)[2:]
        return '0' * (8 - len(s)) + s

    def __repr__(self):
        return self.__str__()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: type[Any], handler: GetCoreSchemaHandler):
        return core_schema.no_info_after_validator_function(
            cls,
            handler(Union[int, str]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls.__str__
            )
        )

class SystemLog(BaseModel):
    timeStamp: datetime
    workerType: str
    workerHostname: str
    content: Any

class JobLog(BaseModel):
    timeStamp: datetime
    jobId: JobId
    workerType: str
    workerHostname: str
    content: Any

class JobArgument(BaseModel):
    model_config = ConfigDict(extra='allow')

    workerType: str

# Inherit this exception for custom exception;
# or just fill in the code and content;
class JobExceptionError(Exception):
    def __init__(self, code: str, content=None):
        self.code = code
        self.content = content

class JobException(BaseModel):
    code: str
    traceback: str
    content: Any

WorkerAbortedExceptionCode = 'kworker.AbortedException'
WorkerYieldedExceptionCode = 'kworker.YieldedException'
WorkerGeneralExceptionCode = 'kworker.GeneralException'

class WorkerException(BaseModel):
    code: str
    exceptionType: str
    traceback: str

class JobResource(BaseModel):
    key: str
    storageUri: str

class JobResult(BaseModel):
    # auto-parsing for unknown workers;
    __pydantic_extra__: Dict[str, Union[JobResource, Any]]=Field(init=False)
    model_config = ConfigDict(extra='allow')

    workerType: str
    jobException: SerializeAsAny[JobException] | None=None
    workerException: WorkerException | None=None

from .storage_backends import StorageProviderConfig

class SystemConfig(BaseModel):
    storage: SerializeAsAny[StorageProviderConfig]
    workerConfig: Dict[str, Any] | None=None
    deploymentName: str

class JobStatus(str, Enum):
    Pending = 'pending'
    InProgress = 'inProgress'
    Waiting = 'waiting'
    Aborted = 'aborted'
    Finished = 'finished'

class JobWorker(BaseModel):
    workerType: str
    workerArgument: SerializeAsAny[JobArgument]
    workerResult: SerializeAsAny[JobResult] | None=None

class JobDigest(BaseModel):
    jobId: JobId
    createdTime: datetime
    modifiedTime: datetime
    status: JobStatus
    currentWorkerHostname: str
    currentWorker: int

class JobContext(BaseModel):
    jobId: JobId
    createdTime: datetime
    modifiedTime: datetime
    status: JobStatus
    currentWorkerHostname: str
    currentWorker: int
    jobWorkers: List[SerializeAsAny[JobWorker]]
    tags: dict[str, str]

# RESTful;

class JobRequest(BaseModel):
    jobWorkers: List[SerializeAsAny[JobArgument]]
    tags: dict[str, str]

# RPC;

class SystemConfigRequest(BaseModel):
    workerType: str

class JobUpdateRequest(BaseModel):
    workerHostname: str
    workerType: str
    workerIndex: int
    jobId: JobId
    deliverable: SerializeAsAny[JobResult]

class JobFocusRequest(BaseModel):
    jobId: JobId
    workerHostname: str

class JobFocusStatus(str, Enum):
    focused = 'focused'
    rejected = 'rejected'

class JobFocusReceipt(BaseModel):
    status: JobFocusStatus
    jobContext: JobContext

class JobAbortRequest(BaseModel):
    jobId: JobId

class JobYieldRequest(BaseModel):
    jobId: JobId
