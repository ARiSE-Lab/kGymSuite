"""KBDr-Runner HTTP Client Library.

This module provides synchronous and asynchronous HTTP clients for interacting with
the KBDr-Runner scheduler API. The clients support all core operations including job
management, log retrieval, tagging, search, and system information access.

Classes:
    kGymAsyncClient: Async HTTP client with full API support
    kGymClient: Synchronous HTTP client with full API support

Example:
    Async client usage:

    >>> async with kGymAsyncClient("http://localhost:8000") as client:
    ...     job_id = await client.create_job(job_request)
    ...     job = await client.get_job(job_id)
    ...     logs = await client.get_job_log(job_id)

    Sync client usage:

    >>> client = kGymClient("http://localhost:8000")
    >>> job_id = client.create_job(job_request)
    >>> job = client.get_job(job_id)
    >>> client.close()
"""

import httpx
import asyncio
from typing import Dict, List, Tuple, Optional
from KBDr.kcore import (
    JobId, JobContext, JobDigest, JobRequest, JobLog, SystemLog,
    PaginatedResult
)
from .models import kJobContext, kJobWorker

class kGymAsyncClient:
    """Asynchronous HTTP client for KBDr-Runner scheduler API.

    This client provides async methods for all KBDr-Runner API operations including
    job creation and management, log streaming, tagging, search, and system monitoring.
    All methods are coroutines that must be awaited.

    Attributes:
        _client: Underlying httpx AsyncClient instance

    Example:
        >>> client = kGymAsyncClient("http://localhost:8000")
        >>> try:
        ...     job_id = await client.create_job(job_request)
        ...     status = await client.get_job(job_id)
        ...     logs = await client.get_job_log(job_id, page_size=50)
        ... finally:
        ...     await client.close()

        Or use as context manager:

        >>> async with kGymAsyncClient("http://localhost:8000") as client:
        ...     job_id = await client.create_job(job_request)
        ...     await client.abort_job(job_id)
    """

    def __init__(self, base_url: str, timeout: float = 30.0, max_connections=5):
        """Initialize the async client.

        Args:
            base_url: Base URL of the KBDr-Runner scheduler (e.g., 'http://localhost:8000')
            timeout: Request timeout in seconds (default: 30.0)
            max_connections: Maximum concurrent connections (default: 5)
        """
        self._client = httpx.AsyncClient(base_url=base_url.rstrip('/'), timeout=timeout, limits=httpx.Limits(
            max_connections=max_connections
        ))

    async def close(self):
        """Close the HTTP client and clean up resources.

        Should be called when done using the client to properly release connections.
        """
        await self._client.aclose()

    # Job Management

    async def get_jobs(
        self,
        sort_by: str = 'modifiedTime',
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[JobDigest]:
        """Get paginated list of jobs.

        Args:
            sort_by: Sort field ('modifiedTime', 'createdTime')
            skip: Number of records to skip for pagination
            page_size: Number of records per page (max: 100)

        Returns:
            PaginatedResult containing list of JobDigest objects with total count

        Example:
            >>> result = await client.get_jobs(sort_by='createdTime', page_size=50)
            >>> for job in result.items:
            ...     print(f"{job.jobId}: {job.status}")
        """
        response = await self._client.get(
            "/jobs",
            params={
                'sortBy': sort_by,
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[JobDigest].model_validate_json(response.text)

    async def get_job(self, job_id: JobId) -> Optional[kJobContext]:
        """Get detailed job information including results and worker states.

        Args:
            job_id: The job ID to query

        Returns:
            kJobContext with full job details, or None if job not found

        Example:
            >>> ctx = await client.get_job("abc12345")
            >>> print(f"Status: {ctx.status}")
            >>> if ctx.status == JobStatus.Finished:
            ...     result = ctx.jobWorkers[-1].workerResult
        """
        response = await self._client.get(f"/jobs/{job_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return kJobContext.model_validate_json(response.text)

    async def create_job(self, job_request: JobRequest) -> JobId:
        """Submit a new job to the scheduler.

        Args:
            job_request: JobRequest containing worker pipeline and optional tags

        Returns:
            JobId: 8-character hex job identifier

        Example:
            >>> from KBDr.kclient import kJobRequest
            >>> from KBDr.kclient_models import kBuilderArgument, KernelGitCommit
            >>>
            >>> req = kJobRequest(
            ...     jobWorkers=[
            ...         kBuilderArgument(
            ...             kernelSource=KernelGitCommit(...),
            ...             userspaceImage="buildroot.raw"
            ...         )
            ...     ],
            ...     tags={"bugId": "12345"}
            ... )
            >>> job_id = await client.create_job(req)
        """
        response = await self._client.post(
            "/newJob",
            json=job_request.model_dump()
        )
        response.raise_for_status()
        return JobId(response.json())

    async def abort_job(self, job_id: JobId) -> None:
        """Abort a running or pending job.

        Args:
            job_id: The job ID to abort

        Example:
            >>> await client.abort_job("abc12345")
        """
        response = await self._client.post(f"/jobs/{job_id}/abort")
        response.raise_for_status()

    async def restart_job(self, job_id: JobId, restart_from: int = -1) -> None:
        """Restart a job from a specific worker stage.

        Args:
            job_id: The job ID to restart
            restart_from: Worker index to restart from (-1 for full restart)

        Example:
            >>> # Restart from beginning
            >>> await client.restart_job("abc12345")
            >>> # Restart from second worker
            >>> await client.restart_job("abc12345", restart_from=1)
        """
        response = await self._client.post(
            f"/jobs/{job_id}/restart",
            params={'restartFrom': restart_from}
        )
        response.raise_for_status()

    # Job Logs

    async def get_job_log(
        self,
        job_id: JobId,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[JobLog]:
        """Get paginated job logs for a specific job.

        Args:
            job_id: The job ID to query
            skip: Number of log entries to skip
            page_size: Number of log entries per page

        Returns:
            PaginatedResult containing JobLog entries with timestamps and messages
        """
        response = await self._client.get(
            f"/jobs/{job_id}/log",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[JobLog].model_validate_json(response.text)

    # Job Tags

    async def get_job_tags(self, job_id: JobId) -> Dict[str, str]:
        """Get all tags associated with a job.

        Args:
            job_id: The job ID to query

        Returns:
            Dictionary mapping tag keys to values
        """
        response = await self._client.get(f"/jobs/{job_id}/tags")
        response.raise_for_status()
        return response.json()

    async def get_job_tag(self, job_id: JobId, tag_key: str) -> Optional[str]:
        """Get a specific tag value for a job.

        Args:
            job_id: The job ID to query
            tag_key: The tag key to retrieve

        Returns:
            Tag value string, or None if tag doesn't exist
        """
        response = await self._client.get(f"/jobs/{job_id}/tags/{tag_key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def update_job_tag(self, job_id: JobId, tag_key: str, tag_value: str) -> None:
        """Set or update a tag on a job.

        Args:
            job_id: The job ID to tag
            tag_key: The tag key
            tag_value: The tag value

        Example:
            >>> await client.update_job_tag("abc12345", "bugId", "syzbot-12345")
        """
        response = await self._client.post(
            f"/jobs/{job_id}/tags/{tag_key}",
            params={'tagValue': tag_value}
        )
        response.raise_for_status()

    # Search and Discovery

    async def get_tags(
        self,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[str]:
        """Get list of all tag keys used across jobs.

        Args:
            skip: Number of tags to skip
            page_size: Number of tags per page

        Returns:
            PaginatedResult containing tag key strings
        """
        response = await self._client.get(
            "/tags",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[str].model_validate_json(response.text)

    async def search_jobs(
        self,
        tag_key: str = '',
        tag_value: Optional[str] = None,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[Tuple[JobId, str, str]]:
        """Search for jobs by tag key and optional value.

        Args:
            tag_key: Tag key to search for (empty string matches all)
            tag_value: Optional tag value to filter by
            skip: Number of results to skip
            page_size: Number of results per page

        Returns:
            PaginatedResult of tuples (JobId, tag_key, tag_value)

        Example:
            >>> # Find all jobs with bugId tag
            >>> result = await client.search_jobs(tag_key="bugId")
            >>> # Find jobs with specific bugId value
            >>> result = await client.search_jobs(tag_key="bugId", tag_value="12345")
        """
        params = {
            'tagKey': tag_key,
            'skip': skip,
            'pageSize': page_size
        }
        if tag_value is not None:
            params['tagValue'] = tag_value

        response = await self._client.get(
            "/search",
            params=params
        )
        response.raise_for_status()
        return PaginatedResult[Tuple[JobId, str, str]].model_validate_json(response.text)

    # System Information

    async def get_system_info(self) -> Dict[str, str]:
        """Get system configuration information.

        Returns:
            Dictionary containing system info (version, storage backend, etc.)
        """
        response = await self._client.get("/system/info")
        response.raise_for_status()
        return response.json()

    async def get_system_logs(
        self,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[SystemLog]:
        """Get paginated system-wide logs.

        Args:
            skip: Number of log entries to skip
            page_size: Number of log entries per page

        Returns:
            PaginatedResult containing SystemLog entries
        """
        response = await self._client.get(
            "/system/displays/systemLog",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[SystemLog].model_validate_json(response.text)

    async def get_all_job_logs(
        self,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[JobLog]:
        """Get paginated logs from all jobs system-wide.

        Args:
            skip: Number of log entries to skip
            page_size: Number of log entries per page

        Returns:
            PaginatedResult containing JobLog entries from all jobs
        """
        response = await self._client.get(
            "/system/displays/jobLog",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[JobLog].model_validate_json(response.text)

class kGymClient:
    """Synchronous HTTP client for KBDr-Runner scheduler API.

    This client provides synchronous methods for all KBDr-Runner API operations.
    It's a blocking version of kGymAsyncClient suitable for use in non-async contexts.

    Attributes:
        _client: Underlying httpx Client instance

    Example:
        >>> client = kGymClient("http://localhost:8000")
        >>> try:
        ...     job_id = client.create_job(job_request)
        ...     status = client.get_job(job_id)
        ...     logs = client.get_job_log(job_id, page_size=50)
        ... finally:
        ...     client.close()
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        """Initialize the synchronous client.

        Args:
            base_url: Base URL of the KBDr-Runner scheduler (e.g., 'http://localhost:8000')
            timeout: Request timeout in seconds (default: 30.0)
        """
        self._client = httpx.Client(base_url=base_url.rstrip('/'), timeout=timeout, limits=httpx.Limits(
            max_connections=5
        ))

    def close(self):
        """Close the HTTP client and clean up resources.

        Should be called when done using the client to properly release connections.
        """
        self._client.close()

    # Job Management

    def get_jobs(
        self,
        sort_by: str = 'modifiedTime',
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[JobDigest]:
        response = self._client.get(
            "/jobs",
            params={
                'sortBy': sort_by,
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[JobDigest].model_validate_json(response.text)

    def get_job(self, job_id: JobId) -> Optional[kJobContext]:
        response = self._client.get(f"/jobs/{job_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return kJobContext.model_validate_json(response.text)

    def create_job(self, job_request: JobRequest) -> JobId:
        response = self._client.post(
            "/newJob",
            json=job_request.model_dump()
        )
        response.raise_for_status()
        return JobId(response.json())

    def abort_job(self, job_id: JobId) -> None:
        response =  self._client.post(f"/jobs/{job_id}/abort")
        response.raise_for_status()

    def restart_job(self, job_id: JobId, restart_from: int = -1) -> None:
        response =  self._client.post(
            f"/jobs/{job_id}/restart",
            params={'restartFrom': restart_from}
        )
        response.raise_for_status()

    # Job Logs

    def get_job_log(
        self,
        job_id: JobId,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[JobLog]:
        response =  self._client.get(
            f"/jobs/{job_id}/log",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[JobLog].model_validate_json(response.text)

    # Job Tags

    def get_job_tags(self, job_id: JobId) -> Dict[str, str]:
        response =  self._client.get(f"/jobs/{job_id}/tags")
        response.raise_for_status()
        return response.json()

    def get_job_tag(self, job_id: JobId, tag_key: str) -> Optional[str]:
        response =  self._client.get(f"/jobs/{job_id}/tags/{tag_key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def update_job_tag(self, job_id: JobId, tag_key: str, tag_value: str) -> None:
        response =  self._client.post(
            f"/jobs/{job_id}/tags/{tag_key}",
            params={'tagValue': tag_value}
        )
        response.raise_for_status()

    # Search and Discovery

    def get_tags(
        self,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[str]:
        response =  self._client.get(
            "/tags",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[str].model_validate_json(response.text)

    def search_jobs(
        self,
        tag_key: str = '',
        tag_value: Optional[str] = None,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[Tuple[JobId, str, str]]:
        params = {
            'tagKey': tag_key,
            'skip': skip,
            'pageSize': page_size
        }
        if tag_value is not None:
            params['tagValue'] = tag_value

        response =  self._client.get(
            "/search",
            params=params
        )
        response.raise_for_status()
        return PaginatedResult[Tuple[JobId, str, str]].model_validate_json(response.text)

    # System Information

    def get_system_info(self) -> Dict[str, str]:
        response =  self._client.get("/system/info")
        response.raise_for_status()
        return response.json()

    def get_system_logs(
        self,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[SystemLog]:
        response =  self._client.get(
            "/system/displays/systemLog",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[SystemLog].model_validate_json(response.text)

    def get_all_job_logs(
        self,
        skip: int = 0,
        page_size: int = 20
    ) -> PaginatedResult[JobLog]:
        response =  self._client.get(
            "/system/displays/jobLog",
            params={
                'skip': skip,
                'pageSize': page_size
            }
        )
        response.raise_for_status()
        return PaginatedResult[JobLog].model_validate_json(response.text)
