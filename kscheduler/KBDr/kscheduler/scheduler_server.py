from KBDr.kcore import *
from typing import Annotated
from fastapi import FastAPI, Path, Query, HTTPException
from .utils import JobIDRegex
from .backend import SchedulerBackend

class SchedulerServer(SchedulerServerBase):

    def __init__(self, mq_conn: str, backend: SchedulerBackend):
        super(SchedulerServer, self).__init__(mq_conn)
        self._backend = backend
        self._worker_control: WorkerControl = None

    async def enqueue_job(self, job_id: JobId, worker_type: str):
        await self._message_chan.default_exchange.publish(
            Message(body=str(job_id).encode('utf-8')),
            routing_key=worker_type
        )

    async def get_system_config(self, request: SystemConfigRequest) -> SystemConfig:
        return SystemConfig(
            storage=self._backend.config.storage,
            workerConfig=self._backend.config.workerConfigs.get(request.workerType, None),
            deploymentName=self._backend.config.deploymentName
        )

    async def focus_job(self, request: JobFocusRequest) -> JobFocusReceipt:
        return await self._backend.focus_job(request)

    async def update_job(self, request: JobUpdateRequest) -> None:
        ret = await self._backend.update_job(request)
        if ret:
            jobId, nextAvailableWorker = ret
            await self.enqueue_job(jobId, nextAvailableWorker)

    async def mount_apis(self, app: FastAPI):
        @app.post('/jobs/{jobId}/abort')
        async def abort_job(jobId: Annotated[str, Path(pattern=JobIDRegex)]) -> None:
            job_context = await self._backend.get_job(jobId)
            jobId = JobId(jobId)
            if job_context is None:
                raise HTTPException(404, 'Job not found')
            if job_context.status == JobStatus.Aborted:
                return
            if not await self._backend.abort_job(jobId):
                await self._worker_control.abort_job(
                    job_context.currentWorkerHostname,
                    JobAbortRequest(jobId=jobId)
                )

        @app.post('/jobs/{jobId}/restart')
        async def restart_job(
            jobId: Annotated[str, Path(pattern=JobIDRegex)],
            restartFrom: Annotated[int, Query(ge=-1)]=-1
        ) -> None:
            job_context = await self._backend.get_job(jobId)
            jobId = JobId(jobId)
            if job_context is None:
                raise HTTPException(404, 'Job not found')
            if job_context.status not in (JobStatus.Aborted, JobStatus.Finished):
                raise HTTPException(400, 'Job needs to be inactive')
            if restartFrom == -1:
                restartFrom = len(job_context.jobWorkers) - 1
            if restartFrom >= len(job_context.jobWorkers):
                raise HTTPException(400, 'Worker index out of bound')
            await self._backend.restart_job(jobId, restartFrom)
            await self.enqueue_job(jobId, job_context.jobWorkers[restartFrom].workerType)

        @app.post('/newJob')
        async def new_job(request: JobRequest) -> JobId:
            job_id = await self._backend.new_job(request)
            await self.enqueue_job(job_id, request.jobWorkers[0].workerType)
            return job_id

    async def _insert_system_log(self, message: AbstractIncomingMessage):
        async with message.process():
            await self._backend.insert_system_log(SystemLog.model_validate_json(message.body))
    
    async def _insert_job_log(self, message: AbstractIncomingMessage):
        async with message.process():
            await self._backend.insert_job_log(JobLog.model_validate_json(message.body))

    async def start(self):
        self._worker_control_chan = await self._mq_conn.channel()
        self._message_chan = await self._mq_conn.channel()

        self._log_chan = await self._mq_conn.channel()
        self._system_log_queue = await self._log_chan.get_queue('scheduler.insert_system_log')
        self._job_log_queue = await self._log_chan.get_queue('scheduler.insert_job_log')
        await self._system_log_queue.consume(self._insert_system_log)
        await self._job_log_queue.consume(self._insert_job_log)

        self._worker_control = WorkerControl(self._worker_control_chan)
        await self._worker_control.start()

        await super(SchedulerServer, self).start()
