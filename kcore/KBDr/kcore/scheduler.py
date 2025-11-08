from abc import abstractmethod

from .rpc import *
from .models import *

from aio_pika.abc import AbstractRobustConnection

class SchedulerClient:
    get_system_config: RpcClient[SystemConfigRequest, SystemConfig] = None
    focus_job: RpcClient[JobFocusRequest, JobFocusReceipt] = None
    update_job: RpcClient[JobUpdateRequest, None] = None

    def __init__(self, mq_conn: AbstractRobustConnection):
        self._mq_conn = mq_conn
        self.get_system_config = RpcClient[SystemConfigRequest, SystemConfig](self._mq_conn, 'scheduler.get_system_config', SystemConfigRequest, SystemConfig)
        self.focus_job = RpcClient[JobFocusRequest, JobFocusReceipt](self._mq_conn, 'scheduler.focus_job', JobFocusRequest, JobFocusReceipt)
        self.update_job = RpcClient[JobUpdateRequest, None](self._mq_conn, 'scheduler.update_job', JobUpdateRequest, None)

    async def start(self):
        await self.get_system_config.start()
        await self.focus_job.start()
        await self.update_job.start()

class SchedulerServerBase:
    _get_system_config: RpcServer[SystemConfigRequest, SystemConfig] = None
    _focus_job: RpcServer[JobFocusRequest, JobFocusReceipt] = None
    _update_job: RpcServer[JobUpdateRequest, None] = None

    def __init__(self, mq_conn: AbstractRobustConnection):
        self._mq_conn = mq_conn
        self._get_system_config = RpcServer[SystemConfigRequest, SystemConfig](self._mq_conn, 'scheduler.get_system_config', self.get_system_config, SystemConfigRequest, SystemConfig)
        self._focus_job = RpcServer[JobFocusRequest, JobFocusReceipt](self._mq_conn, 'scheduler.focus_job', self.focus_job, JobFocusRequest, JobFocusReceipt)
        self._update_job = RpcServer[JobUpdateRequest, None](self._mq_conn, 'scheduler.update_job', self.update_job, JobUpdateRequest, None)

    @abstractmethod
    async def get_system_config(self, request: SystemConfigRequest) -> SystemConfig:
        raise NotImplementedError()

    @abstractmethod
    async def focus_job(self, request: JobFocusRequest) -> JobFocusReceipt:
        raise NotImplementedError()

    @abstractmethod
    async def update_job(self, request: JobUpdateRequest) -> None:
        raise NotImplementedError()

    async def start(self):
        await self._get_system_config.start()
        await self._focus_job.start()
        await self._update_job.start()
