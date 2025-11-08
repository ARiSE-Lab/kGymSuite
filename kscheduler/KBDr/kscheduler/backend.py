import aiosqlite
from KBDr.kcore import *
from typing import Annotated, Dict
from fastapi import FastAPI, Query, Path, HTTPException
from fastapi.responses import RedirectResponse
from .utils import JobIDRegex, SortingModes, PaginatedResult
from .config import SchedulerConfig
from pydantic_core import from_json, to_json
from datetime import UTC, datetime

DigestTupleToModel = lambda digestTuple: JobDigest(
    jobId=digestTuple[0],
    createdTime=digestTuple[1],
    modifiedTime=digestTuple[2],
    status=digestTuple[3],
    currentWorkerHostname=digestTuple[4],
    currentWorker=digestTuple[5]
)

WorkerTupleToModel = lambda workerTuple: JobWorker(
    workerType=workerTuple[2],
    workerArgument=from_json(workerTuple[3]),
    workerResult=from_json(workerTuple[4])
)

JobLogTupleToModel = lambda jobLogTuple: JobLog(
    timeStamp=jobLogTuple[0],
    jobId=jobLogTuple[1],
    workerType=jobLogTuple[2],
    workerHostname=jobLogTuple[3],
    content=from_json(jobLogTuple[4])
)

SystemLogTupleToModel = lambda systemLogTuple: SystemLog(
    timeStamp=systemLogTuple[0],
    workerType=systemLogTuple[1],
    workerHostname=systemLogTuple[2],
    content=from_json(systemLogTuple[3])
)

KEY_EXTRACTOR = {
    'modifiedTime': lambda x: x.modifiedTime,
    'createdTime': lambda x: x.createdTime
}

class SchedulerBackend:

    def __init__(self, config: SchedulerConfig):
        self.config = config
        self._backend_conn_str = config.dbPath
        self._storage_backend: AbstractStorageBackend = None

    async def _create_db(self):
        async with self._db_conn.cursor() as cur:
            await cur.executescript('\n'.join((
                "CREATE TABLE jobDigest (",
                "jobId INTEGER PRIMARY KEY AUTOINCREMENT,",
                "createdTime TEXT,",
                "modifiedTime TEXT,",
                "`status` TEXT,",
                "currentWorkerHostname TEXT,",
                "currentWorker INT",
                ");"
            )))
            await cur.executescript('\n'.join((
                "CREATE TABLE jobWorker (",
                "jobId INTEGER,",
                "workerIndex INTEGER,",
                "workerType TEXT,",
                "workerArgument TEXT,",
                "workerResult TEXT,",
                "CONSTRAINT mkey PRIMARY KEY(jobId, workerIndex)",
                ");"
            )))
            await cur.executescript('\n'.join((
                "CREATE TABLE jobTag (",
                "jobId INTEGER,",
                "tagKey TEXT,",
                "tagValue TEXT,",
                "CONSTRAINT mkey PRIMARY KEY(jobId, tagKey)",
                ");"
            )))
            await cur.executescript('\n'.join((
                "CREATE TABLE jobLog (",
                "timeStamp TEXT,",
                "jobId INTEGER,",
                "workerType TEXT,",
                "workerHostname TEXT,",
                "content TEXT",
                ");"
            )))
            await cur.executescript('\n'.join((
                "CREATE TABLE systemLog (",
                "timeStamp TEXT,",
                "workerType TEXT,",
                "workerHostname TEXT,",
                "content TEXT",
                ");"
            )))
            await cur.executescript('\n'.join((
                "CREATE TABLE authenticationToken (",
                "token TEXT PRIMARY KEY,",
                "expirationDate TEXT",
                ");"
            )))
            await cur.executescript("CREATE INDEX jobDigestModifiedTimeIndex ON jobDigest (modifiedTime);")
            await cur.executescript("CREATE INDEX jobDigestCreatedTimeIndex ON jobDigest (createdTime);")
            await cur.executescript("CREATE INDEX jobWorkerIndex ON jobWorker (jobId);")
            await cur.executescript("CREATE INDEX jobTagIndex ON jobTag (jobId);")
            await cur.executescript("CREATE INDEX jobTagKeyIndex ON jobTag (tagKey);")
            await cur.executescript("CREATE INDEX jobLogTSIndex ON jobLog (timeStamp);")
            await cur.executescript("CREATE INDEX jobLogIdIndex ON jobLog (jobId);")
            await cur.executescript("CREATE INDEX systemLogTSIndex ON systemLog (timeStamp);")
        await self._db_conn.commit()

    async def _shutdown_left_over_jobs(self):
        async with self._db_conn.cursor() as cur:
            ts = datetime.now(UTC).isoformat()
            await cur.execute(
                "UPDATE jobDigest SET `status`=?, currentWorkerHostname=?, modifiedTime=? \
                WHERE `status`=? OR `status`=? OR `status`=?;",
                (JobStatus.Aborted, '', ts, JobStatus.InProgress, JobStatus.Pending, JobStatus.Waiting)
            )
        await self._db_conn.commit()

    async def get_job(
        self,
        jobId: str
    ) -> JobContext | None:
        jobId = JobId(jobId)
        async with self._db_conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM jobDigest WHERE jobId=?",
                (jobId, )
            )
            digest = await cur.fetchall()
            if len(digest) == 0:
                return None
            digest = DigestTupleToModel(digest[0])

            await cur.execute(
                "SELECT * FROM jobWorker WHERE jobId=? ORDER BY workerIndex ASC",
                (jobId, )
            )
            workers: List[JobWorker] = list(map(WorkerTupleToModel, await cur.fetchall()))

            await cur.execute(
                "SELECT * FROM jobTag WHERE jobId=?",
                (jobId, )
            )
            tagKVpairs = await cur.fetchall()
            tags = dict[str, str]()
            for kv_pair in tagKVpairs:
                tags[kv_pair[1]] = kv_pair[2]

            return JobContext(
                **digest.model_dump(),
                jobWorkers=workers,
                tags=tags
            )

    async def insert_system_log(self, log: SystemLog):
        async with self._db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO systemLog( \
                    timeStamp, workerType, \
                    workerHostname, content \
                ) VALUES(?, ?, ?, ?) \
                ;",
                (log.timeStamp.astimezone(UTC).isoformat(), log.workerType, log.workerHostname, to_json(log.content))
            )
        await self._db_conn.commit()

    async def insert_job_log(self, log: JobLog):
        async with self._db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO jobLog( \
                    timeStamp, jobId, \
                    workerType, workerHostname, \
                    content \
                ) VALUES(?, ?, ?, ?, ?) \
                ;",
                (
                    log.timeStamp.astimezone(UTC).isoformat(), log.jobId,
                    log.workerType, log.workerHostname,
                    to_json(log.content)
                )
            )
        await self._db_conn.commit()

    async def focus_job(self, request: JobFocusRequest) -> JobFocusReceipt:
        async with self._db_conn.cursor() as cur:
            ts = datetime.now(UTC).isoformat()
            await cur.execute(
                "UPDATE jobDigest SET `status`=?, currentWorkerHostname=?, modifiedTime=? \
                WHERE jobId = ? AND currentWorkerHostname = ? AND \
                (`status` = ? OR `status` = ?) AND modifiedTime < ?;",
                (JobStatus.InProgress, request.workerHostname, ts,
                request.jobId, '', JobStatus.Waiting, JobStatus.Pending, ts)
            )
            if cur.rowcount == 1:
                status = JobFocusStatus.focused
            else:
                status = JobFocusStatus.rejected
        await self._db_conn.commit()
        return JobFocusReceipt(
            status=status,
            jobContext=await self.get_job(str(request.jobId))
        )

    async def restart_job(self, job_id: JobId, restart_from: int):
        async with self._db_conn.cursor() as cur:
            ts = datetime.now(UTC).isoformat()
            await cur.execute(
                "UPDATE jobDigest SET \
                    `status`=?, \
                    modifiedTime=?, \
                    currentWorker=? \
                WHERE \
                    jobId=? AND \
                    currentWorkerHostname=? AND \
                    (`status`=? OR `status`=?) AND \
                    modifiedTime<? \
                ;",
                (
                    JobStatus.Pending, ts, restart_from, job_id,
                    '', JobStatus.Aborted, JobStatus.Finished, ts
                )
            )
            ret = (cur.rowcount == 1)
        await self._db_conn.commit()
        if not ret:
            raise HTTPException(400, 'Failed to restart job')

    async def new_job(self, request: JobRequest) -> JobId:
        async with self._db_conn.cursor() as cur:
            ts = datetime.now(UTC).isoformat()
            await cur.execute(
                'INSERT INTO jobDigest( \
                    jobId, \
                    createdTime, \
                    modifiedTime, \
                    `status`, \
                    currentWorkerHostname, \
                    currentWorker \
                ) VALUES(NULL, ?, ?, ?, ?, ?) \
                RETURNING jobId;',
                (ts, ts, JobStatus.Pending, '', 0)
            )
            job_id = JobId((await cur.fetchall())[0][0])

            worker_tuples = []
            for i, worker_arg in enumerate(request.jobWorkers):
                worker_tuples.append((
                    job_id,
                    i,
                    worker_arg.workerType,
                    worker_arg.model_dump_json(),
                    to_json(None)
                ))
            await cur.executemany(
                'INSERT INTO jobWorker( \
                    jobId, \
                    workerIndex, \
                    workerType, \
                    workerArgument, \
                    workerResult \
                ) VALUES(?, ?, ?, ?, ?);',
                worker_tuples
            )

            tag_tuples = []
            for tagKey in request.tags:
                tag_tuples.append((
                    job_id,
                    tagKey,
                    request.tags[tagKey]
                ))
            await cur.executemany(
                'INSERT INTO jobTag( \
                    jobId, \
                    tagKey, \
                    tagValue \
                ) VALUES(?, ?, ?);',
                tag_tuples
            )

            return job_id

    _update_sql_script = """
    UPDATE jobWorker SET
        workerResult=?
    WHERE
        jobId=? AND workerIndex=?;
    """

    async def update_job(self, request: JobUpdateRequest) -> Tuple[JobId, str] | None:
        deliverable = request.deliverable
        yielded = False
        status = JobStatus.Aborted
        nextAvailable = False
        nextWorkerIndex = request.workerIndex
        if deliverable.workerException:
            exType = deliverable.workerException.exceptionType
            if exType == WorkerYieldedExceptionCode:
                yielded = True
                status = JobStatus.Waiting
        elif deliverable.jobException is None:
            status = JobStatus.Waiting
            nextWorkerIndex += 1
            nextAvailable = True

        ret = None
        async with self._db_conn.cursor() as cur:
            if not yielded:
                ts = datetime.now(UTC).isoformat()
                params = (
                    deliverable.model_dump_json(),
                    request.jobId,
                    request.workerIndex
                )
                await cur.execute(
                    self._update_sql_script,
                    params
                )

            await cur.execute(
                "UPDATE jobDigest SET \
                    `status`=?, \
                    currentWorkerHostname=?, \
                    currentWorker=?, \
                    modifiedTime=? \
                WHERE \
                    jobId=? AND \
                    `status`=? AND \
                    currentWorkerHostname=? AND \
                    currentWorker=? AND \
                    modifiedTime<? \
                ;",
                (
                    status, '', nextWorkerIndex, ts,
                    request.jobId, JobStatus.InProgress,
                    request.workerHostname,
                    request.workerIndex, ts
                )
            )
            if nextAvailable:
                await cur.execute(
                    "SELECT workerType FROM jobWorker \
                    WHERE \
                        jobId=? AND \
                        workerIndex=? \
                    ;",
                    (request.jobId, nextWorkerIndex)
                )
                nextType = await cur.fetchall()
                if len(nextType) != 0:
                    ret = [request.jobId, nextType[0][0]]
                else:
                    await cur.execute(
                        "UPDATE jobDigest SET \
                            `status`=? \
                        WHERE \
                            jobId=? \
                        ;",
                        (JobStatus.Finished, request.jobId)
                    )

        await self._db_conn.commit()
        return ret

    async def abort_job(self, jobId: JobId):
        async with self._db_conn.cursor() as cur:
            await cur.execute(
                'UPDATE jobDigest SET \
                    `status`=? \
                WHERE \
                    jobId=? AND `currentWorkerHostname`=? AND \
                    (`status`=? OR `status`=?) \
                ;',
                (JobStatus.Aborted, jobId, '', JobStatus.Pending, JobStatus.Waiting)
            )
            return (cur.rowcount == 1)

    async def mount_apis(self, app: FastAPI):
        @app.get('/jobs')
        async def get_jobs(
            sortBy: Annotated[SortingModes, Query()]='modifiedTime',
            skip: Annotated[int, Query(ge=0)]=0,
            pageSize: Annotated[int, Query(ge=0, le=500)]=20
        ) -> PaginatedResult[JobDigest]:
            async with self._db_conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM jobDigest"
                )
                total = (await cur.fetchall())[0][0]

                await cur.execute(
                    f"SELECT * FROM jobDigest ORDER BY {sortBy} DESC LIMIT ? OFFSET ?",
                    (pageSize, skip)
                )
                digestTuples = await cur.fetchall()
                digests = map(DigestTupleToModel, digestTuples)
                digests = list[JobDigest](digests)
                digests.sort(key=KEY_EXTRACTOR[sortBy], reverse=True)

                return PaginatedResult[JobDigest](
                    page=digests,
                    pageSize=len(digests),
                    total=total,
                    offsetNextPage=skip + len(digests)
                )
        
        @app.get('/jobs/{jobId}')
        async def get_job(
            jobId: Annotated[str, Path(pattern=JobIDRegex)]
        ) -> JobContext | None:
            return await self.get_job(jobId)

        @app.get('/jobs/{jobId}/log')
        async def get_job_log(
            jobId: Annotated[str, Path(pattern=JobIDRegex)],
            skip: Annotated[int, Query(ge=0)]=0,
            pageSize: Annotated[int, Query(ge=0, le=500)]=20
        ) -> PaginatedResult[JobLog]:
            jobId = JobId(jobId)
            async with self._db_conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM jobLog WHERE jobId=?",
                    (jobId, )
                )
                total = (await cur.fetchall())[0][0]
                await cur.execute(
                    "SELECT * FROM jobLog WHERE jobId=? ORDER BY timeStamp DESC LIMIT ? OFFSET ?",
                    (jobId, pageSize, skip)
                )
                logs = list[JobLog](map(JobLogTupleToModel, await cur.fetchall()))
                return PaginatedResult[JobLog](
                    page=logs,
                    pageSize=len(logs),
                    offsetNextPage=skip + len(logs),
                    total=total
                )

        @app.get('/jobs/{jobId}/tags')
        async def get_job_tags(
            jobId: Annotated[str, Path(pattern=JobIDRegex)]
        ) -> Dict[str, str]:
            jobId = JobId(jobId)
            async with self._db_conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM jobTag WHERE jobId=?",
                    (jobId, )
                )
                tagKVpairs = await cur.fetchall()
                tags = dict[str, str]()
                for kv_pair in tagKVpairs:
                    tags[kv_pair[1]] = kv_pair[2]
                return tags
 
        @app.get('/jobs/{jobId}/tags/{tagKey}')
        async def get_job_tag_value_by_key(
            jobId: Annotated[str, Path(pattern=JobIDRegex)],
            tagKey: Annotated[str, Path()]
        ) -> str:
            jobId = JobId(jobId)
            async with self._db_conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM jobTag WHERE jobId=? AND tagKey=?",
                    (jobId, tagKey)
                )
                tagKVpairs = await cur.fetchall()
                if len(tagKVpairs) == 0:
                    return None
                else:
                    return tagKVpairs[0][2]

        @app.post('/jobs/{jobId}/tags/{tagKey}')
        async def update_job_tag_value_by_key(
            jobId: Annotated[str, Path(pattern=JobIDRegex)],
            tagKey: Annotated[str, Path()],
            tagValue: Annotated[str, Query()]
        ) -> None:
            async with self._db_conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM jobTag WHERE \
                        jobId=? AND tagKey=? \
                    ;",
                    (jobId, tagKey)
                )
                await cur.execute(
                    "INSERT INTO jobTag(jobId, tagKey, tagValue) \
                    VALUES(?, ?, ?) \
                    ;",
                    (jobId, tagKey, tagValue)
                )
            await self._db_conn.commit()

        @app.get('/tags')
        async def get_tags(
            skip: Annotated[int, Query(ge=0)]=0,
            pageSize: Annotated[int, Query(ge=0, le=500)]=20
        ) -> PaginatedResult[str]:
            async with self._db_conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(DISTINCT tagKey) FROM jobTag;"
                )
                total = (await cur.fetchall())[0][0]
                await cur.execute(
                    "SELECT DISTINCT tagKey FROM jobTag ORDER BY tagKey ASC LIMIT ? OFFSET ?;",
                    (pageSize, skip)
                )
                tags = list(map(lambda x: x[0], await cur.fetchall()))
                return PaginatedResult[str](
                    page=tags,
                    pageSize=pageSize,
                    offsetNextPage=skip + len(tags),
                    total=total
                )

        @app.get('/search')
        async def search(
            tagKey: Annotated[str, Query()]='',
            tagValue: Annotated[str | None, Query()]=None,
            skip: Annotated[int, Query(ge=0)]=0,
            pageSize: Annotated[int, Query(ge=0, le=500)]=20
        ) -> PaginatedResult[Tuple[JobId, str, str]]:
            async with self._db_conn.cursor() as cur:
                if tagValue is None:
                    await cur.execute(
                        "SELECT COUNT(*) FROM jobTag WHERE tagKey=? ORDER BY jobId DESC LIMIT ? OFFSET ?;",
                        (tagKey, pageSize, skip)
                    )
                    total = (await cur.fetchall())[0][0]
                    await cur.execute(
                        "SELECT * FROM jobTag WHERE tagKey=? ORDER BY jobId DESC LIMIT ? OFFSET ?;",
                        (tagKey, pageSize, skip)
                    )
                else:
                    await cur.execute(
                        "SELECT COUNT(*) FROM jobTag WHERE tagKey=? AND tagValue=? ORDER BY jobId DESC LIMIT ? OFFSET ?;",
                        (tagKey, tagValue, pageSize, skip)
                    )
                    total = (await cur.fetchall())[0][0]
                    await cur.execute(
                        "SELECT * FROM jobTag WHERE tagKey=? AND tagValue=? ORDER BY jobId DESC LIMIT ? OFFSET ?;",
                        (tagKey, tagValue, pageSize, skip)
                    )
                tagKVpairs = await cur.fetchall()
                page = list(map(lambda row: (JobId(row[0]), row[1], row[2]), tagKVpairs))
                return PaginatedResult[Tuple[JobId, str, str]](
                    page=page,
                    pageSize=len(page),
                    offsetNextPage=skip + len(page),
                    total=total
                )

        @app.get('/system/displays/systemLog')
        async def display_system_log(
            skip: Annotated[int, Query(ge=0)]=0,
            pageSize: Annotated[int, Query(ge=0, le=500)]=20
        ) -> PaginatedResult[SystemLog]:
            async with self._db_conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM systemLog")
                total = (await cur.fetchall())[0][0]
                await cur.execute(
                    "SELECT * FROM systemLog ORDER BY timeStamp DESC LIMIT ? OFFSET ?;",
                    (pageSize, skip)
                )
                logs = list[SystemLog](map(SystemLogTupleToModel, await cur.fetchall()))
                return PaginatedResult[SystemLog](
                    page=logs,
                    pageSize=len(logs),
                    offsetNextPage=skip + len(logs),
                    total=total
                )

        @app.get('/system/displays/jobLog')
        async def display_job_log(
            skip: Annotated[int, Query(ge=0)]=0,
            pageSize: Annotated[int, Query(ge=0, le=500)]=20
        ) -> PaginatedResult[JobLog]:
            async with self._db_conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM jobLog")
                total = (await cur.fetchall())[0][0]
                await cur.execute(
                    "SELECT * FROM jobLog ORDER BY timeStamp DESC LIMIT ? OFFSET ?;",
                    (pageSize, skip)
                )
                logs = list[JobLog](map(JobLogTupleToModel, await cur.fetchall()))
                return PaginatedResult[JobLog](
                    page=logs,
                    pageSize=len(logs),
                    offsetNextPage=skip + len(logs),
                    total=total
                )

    async def start(self):
        self._db_conn = await aiosqlite.connect(self._backend_conn_str)
        self._storage_backend = await create_storage_backend(self.config.storage)
        async with self._db_conn.cursor() as cur:
            await cur.execute(
                'SELECT name FROM sqlite_master WHERE type=? AND name=?;',
                ('table', 'jobDigest')
            )
            result = await cur.fetchall()
        # if it's necessary to build the table structures;
        if len(result) == 0:
            await self._create_db()
        await self._shutdown_left_over_jobs()

    async def stop(self):
        await self._db_conn.commit()
        await self._db_conn.close()
