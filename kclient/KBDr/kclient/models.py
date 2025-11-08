"""KBDr-Runner Job Request and Context Models.

This module provides typed models for job submission and job context retrieval.
It extends the core kcore models with specific worker types to enable proper
type checking and serialization for kbuilder, kvmmanager, and kprebuilder workers.

Type Aliases:
    kJobWorker: Union type for all worker types with results
    kJobArgument: Union type for all worker argument types

Classes:
    kJobContext: Extended JobContext with typed worker results
    kJobRequest: Extended JobRequest with typed worker arguments

Example:
    Creating a multi-stage job request:

    >>> from KBDr.kclient import kJobRequest
    >>> from KBDr.kclient_models import (
    ...     kBuilderArgument, KernelGitCommit,
    ...     kVMManagerArgument, Reproducer, Image
    ... )
    >>>
    >>> req = kJobRequest(
    ...     jobWorkers=[
    ...         kBuilderArgument(
    ...             kernelSource=KernelGitCommit(
    ...                 gitUrl="https://github.com/torvalds/linux",
    ...                 commitId="abc123",
    ...                 kConfig="CONFIG_X86=y\\n...",
    ...                 arch="amd64",
    ...                 compiler="gcc",
    ...                 linker="ld"
    ...             ),
    ...             userspaceImage="buildroot.raw"
    ...         ),
    ...         kVMManagerArgument(
    ...             reproducer=Reproducer(
    ...                 reproducerType="c",
    ...                 reproducerText="int main() { ... }"
    ...             ),
    ...             image=0,  # Use output from worker 0
    ...             machineType="qemu:2-4096"
    ...         )
    ...     ],
    ...     tags={"bugId": "12345", "experiment": "repro-test"}
    ... )
"""

from typing import Union

from ..kclient_models.kbuilder import *
from ..kclient_models.kvmmanager import *
from ..kclient_models.kprebuilder import *

from KBDr.kcore.models import JobRequest, JobContext, JobWorker, JobArgument

from pydantic import SerializeAsAny

kJobWorker = Union[kBuilderWorker, kPreBuilderWorker, kVMManagerWorker, SerializeAsAny[JobWorker]]
kJobArgument = Union[kBuilderArgument, kPreBuilderArgument, kVMManagerArgument, SerializeAsAny[JobArgument]]

class kJobContext(JobContext):
    """Extended job context with typed worker results.

    Extends the base JobContext with specific typing for KBDr worker types,
    enabling proper deserialization and type checking of worker results.

    Attributes:
        jobWorkers: List of worker states with typed arguments and results
        All other attributes inherited from JobContext (jobId, status, etc.)

    Example:
        >>> client = kGymClient("http://localhost:8000")
        >>> ctx = client.get_job("abc12345")
        >>> if ctx.status == JobStatus.Finished:
        ...     builder_result = ctx.jobWorkers[0].workerResult
        ...     vm_result = ctx.jobWorkers[1].workerResult
    """
    jobWorkers: List[kJobWorker]

class kJobRequest(JobRequest):
    """Extended job request with typed worker arguments.

    Extends the base JobRequest with specific typing for KBDr worker arguments,
    enabling proper validation and serialization of worker configurations.

    Attributes:
        jobWorkers: List of worker arguments defining the job pipeline
        tags: Optional dictionary of metadata tags

    Example:
        >>> req = kJobRequest(
        ...     jobWorkers=[kBuilderArgument(...)],
        ...     tags={"bugId": "12345"}
        ... )
        >>> job_id = client.create_job(req)
    """
    jobWorkers: List[kJobArgument]
