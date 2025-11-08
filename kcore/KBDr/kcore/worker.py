import platform, traceback, shutil, tempfile, os
from datetime import datetime, timezone
from signal import SIGTERM
from abc import abstractmethod

from .rpc import *
from .models import *
from .scheduler import SchedulerClient
from .utils import get_type_fullname, run_async
from .storage_backends import create_storage_backend, AbstractStorageBackend

from aio_pika.abc import AbstractChannel
from aio_pika import Message, connect_robust

class WorkerControl:

    def __init__(self, mq_chan: AbstractChannel):
        self._rpc_client = GeneralRpcClient(mq_chan)

    async def start(self):
        await self._rpc_client.start()

    async def _control_worker(self, command: str, worker_hostname: str, request: BaseModel):
        return await (self._rpc_client(
            f'workers.{worker_hostname}.{command}',
            request.model_dump_json().encode('utf-8')
        ))

    async def abort_job(self, worker_hostname: str, request: JobAbortRequest) -> None:
        await self._control_worker('abort_job', worker_hostname, request)

    async def yield_job(self, worker_hostname: str, request: JobYieldRequest) -> None:
        await self._control_worker('yield_job', worker_hostname, request)

class TaskBase:

    pending_result: JobResult | None=None
    argument: JobArgument | None=None

    def __init__(self, worker: 'Worker', job_ctx: JobContext):
        self._worker = worker
        self.system_config = self._worker.system_config
        self.storage_backend = self._worker.storage_backend
        self.job_ctx = job_ctx
        self.job_id = job_ctx.jobId
        self.argument = job_ctx.jobWorkers[job_ctx.currentWorker].workerArgument
        self.task: asyncio.Task = None
        self.cwd = tempfile.mkdtemp(prefix='kgym-')

    def _get_storage_prefix(self):
        return f'jobs/{self.job_ctx.jobId}/{self.job_ctx.currentWorker}_{self._worker.worker_type}/'

    async def submit_resource(self, in_folder_key: str, local_path: str) -> JobResource | None:
        fsize = (await run_async(os.stat, local_path)).st_size
        if fsize == 0:
            return None
        key = self._get_storage_prefix() + in_folder_key
        await self.storage_backend.upload_resource(local_path, self._get_storage_prefix() + in_folder_key)
        return JobResource(
            key=key,
            storageUri=await self.storage_backend.get_resource_url(key)
        )

    async def report_job_log(self, message):
        await self._worker.report_job_log(self.job_ctx.jobId, message)

    @abstractmethod
    async def on_clean(self):
        pass

    @abstractmethod
    async def on_task(self) -> JobResult:
        pass

    async def _clean(self):
        try:
            await self.on_clean()
        except:
            pass
        await run_async(shutil.rmtree, self.cwd, ignore_errors=True)

    async def run(self) -> JobResult:
        # prepare one just in case;
        # task can get their own if they want a new one;
        self.pending_result = JobResult(workerType=self._worker.worker_type)
        try:
            self.task = asyncio.create_task(self.on_task())
            result: JobResult = await self.task
            self.task = None
            assert self.pending_result is result
            await self._clean()
            return self.pending_result
        except JobExceptionError as e:
            self.task = None
            await self._clean()
            self.pending_result.jobException = JobException(
                code=e.code,
                traceback=traceback.format_exc(),
                content=e.content
            )
            self.pending_result.workerException = None
            return self.pending_result
        except asyncio.exceptions.CancelledError as e:
            self.task = None
            await self._clean()
            self.pending_result.workerException = WorkerException(
                code=e.args[0],
                exceptionType=get_type_fullname(type(e)),
                traceback=traceback.format_exc()
            )
            self.pending_result.jobException = None
            return self.pending_result
        except Exception as e:
            self.task = None
            await self._clean()
            self.pending_result.workerException = WorkerException(
                code=WorkerGeneralExceptionCode,
                exceptionType=get_type_fullname(type(e)),
                traceback=traceback.format_exc()
            )
            self.pending_result.jobException = None
            return self.pending_result

class Worker:

    def __init__(
        self,
        conn_url: str,
        worker_type: str,
        task_type: type[TaskBase]
    ):
        self._conn_url = conn_url

        self.mq_conn: AbstractRobustConnection = None
        self._abort_job: RpcServer[JobAbortRequest, None] = None
        self._yield_job: RpcServer[JobYieldRequest, None] = None
        self.scheduler: SchedulerClient = None

        self.worker_type = worker_type
        self.worker_hostname = platform.node()

        self._blocker_lock = asyncio.Semaphore(0)
        self._closed = False
        self._task_type = task_type
        self._yield_blocker = None

        self.current_task = None
        self.system_config: SystemConfig = None
        self.storage_backend: AbstractStorageBackend = None

    async def _send_message(self, queue_name: str, message: RootModel):
        await self.job_chan.default_exchange.publish(
            Message(body=message.model_dump_json().encode('utf-8')),
            routing_key=queue_name,
        )

    async def report_system_log(self, message):
        await self._send_message(
            'scheduler.insert_system_log',
            SystemLog(
                timeStamp=datetime.now(timezone.utc),
                workerType=self.worker_type,
                workerHostname=self.worker_hostname,
                content=message
            )
        )

    async def report_job_log(self, job_id: JobId, message):
        await self._send_message(
            'scheduler.insert_job_log',
            JobLog(
                jobId=job_id,
                timeStamp=datetime.now(timezone.utc),
                workerType=self.worker_type,
                workerHostname=self.worker_hostname,
                content=message
            )
        )

    def _cancel_job(self, job_id: JobId, code: str) -> None:
        if self.current_task is None:
            return
        if job_id != self.current_task.job_ctx.jobId:
            return
        if self.current_task.task is None:
            return
        self.current_task.task.cancel(code)

    async def abort_job(self, request: JobAbortRequest) -> None:
        self._cancel_job(request.jobId, WorkerAbortedExceptionCode)

    async def yield_job(self, request: JobYieldRequest) -> None:
        self._cancel_job(request.jobId, WorkerYieldedExceptionCode)

    async def _on_dispatch(self, message: AbstractIncomingMessage):
        if self._closed:
            await message.reject(True)
            return

        async with message.process(requeue=True):
            job_id = JobId(message.body.decode('utf-8'))

            self.system_config = await self.scheduler.get_system_config(SystemConfigRequest(workerType=self.worker_type))
            ret: JobFocusReceipt = await self.scheduler.focus_job(JobFocusRequest(jobId=job_id, workerHostname=self.worker_hostname))
            if ret is None or ret.status == JobFocusStatus.rejected:
                return
            self.storage_backend: AbstractStorageBackend = await create_storage_backend(self.system_config.storage)

            self.current_task = self._task_type(self, ret.jobContext)
            result: JobResult = await self.current_task.run()
            self.current_task = None
            await self.scheduler.update_job(JobUpdateRequest(
                workerHostname=self.worker_hostname,
                workerType=self.worker_type,
                workerIndex=ret.jobContext.currentWorker,
                jobId=job_id,
                deliverable=result
            ))

            if result.workerException is None:
                return
            if result.workerException.code != WorkerYieldedExceptionCode:
                return
            if self._yield_blocker:
                await self._yield_blocker.release()

    async def _signal_handler(self):
        self._closed = True

        if self.mq_conn is None or self.mq_conn.is_closed:
            quit()

        if self.current_task:
            if self.current_task.task:
                # job yielding logic;
                self._yield_blocker = asyncio.Semaphore(0)
                # cancel the job and tell it to yield;
                self.current_task.task.cancel(WorkerYieldedExceptionCode)
                await self.current_task.report_job_log(f'Worker going offline, yielded')
            # wait for completion;
            if self._yield_blocker:
                await self._yield_blocker.acquire()

        await self.report_system_log(f'Worker {self.worker_type} at {self.worker_hostname} exiting')
        await self.mq_conn.close()
        # give signal here to exit the whole thing;
        self._blocker_lock.release()

    async def _start(self):
        self.mq_conn = await connect_robust(self._conn_url)

        self.scheduler = SchedulerClient(self.mq_conn)
        self._abort_job = RpcServer[JobAbortRequest, None](
            self.mq_conn,
            f'workers.{self.worker_hostname}.abort_job',
            self.abort_job,
            JobAbortRequest,
            None
        )
        self._yield_job = RpcServer[JobYieldRequest, None](
            self.mq_conn,
            f'workers.{self.worker_hostname}.yield_job',
            self.yield_job,
            JobYieldRequest,
            None
        )

        asyncio.get_event_loop().add_signal_handler(
            SIGTERM,
            lambda: asyncio.create_task(self._signal_handler())
        )

        await self.scheduler.start()
        await self._abort_job.start()
        await self._yield_job.start()

        self.job_chan = await self.mq_conn.channel()
        await self.job_chan.set_qos(prefetch_count=1)
        self.job_queue = await self.job_chan.get_queue(self.worker_type)
        await self.job_queue.consume(self._on_dispatch)

        await self.report_system_log(f'Worker {self.worker_type} at {self.worker_hostname} joined')

        await self._blocker_lock.acquire()

    def run(self):
        asyncio.run(self._start())
