"""KBDr-Runner Patch Prebuilder Worker Models.

This module defines data models for the kprebuilder worker, which tests
patch applicability on cached kernel builds without running full reproductions.
Useful for testing if patches can be backported to specific kernel versions.

Classes:
    kPreBuilderArgument: Input arguments for kprebuilder worker
    kPreBuilderResult: Output results from kprebuilder worker
    kPreBuilderWorker: Complete worker state with argument and result
    PatchResultStatus: Enum of patch application outcomes
    PatchResult: Result for a single patch test
    ModifiedFunction: Function-level patch analysis
    ModifiedFile: File-level patch analysis

Example:
    Testing patch applicability:

    >>> from KBDr.kclient import kJobRequest, kGymClient
    >>> from KBDr.kclient_models import kPreBuilderArgument
    >>>
    >>> job = kJobRequest(jobWorkers=[
    ...     kPreBuilderArgument(
    ...         kCache=cached_kernel_resource,
    ...         patches=[
    ...             "diff --git a/file.c b/file.c\\n...",
    ...             "diff --git a/other.c b/other.c\\n..."
    ...         ]
    ...     )
    ... ])
    >>> client = kGymClient("http://localhost:8000")
    >>> job_id = client.create_job(job)
    >>> ctx = client.get_job(job_id)
    >>> result = ctx.jobWorkers[0].workerResult
    >>> for i, patch_result in enumerate(result.patchResults):
    ...     print(f"Patch {i}: {patch_result.status}")
"""

from typing import Literal, List
from enum import Enum
from KBDr import kcore
from pydantic import BaseModel, RootModel, ConfigDict, Field

class kPreBuilderArgument(kcore.JobArgument):
    """Input arguments for kprebuilder worker.

    Specifies kernel cache and patches to test for applicability.

    Attributes:
        workerType: Always 'kprebuilder'
        kCache: Reference to cached kernel build from kbuilder
        patches: List of patch strings (unified diff format) to test

    Example:
        >>> arg = kPreBuilderArgument(
        ...     kCache=kernel_cache_resource,
        ...     patches=[
        ...         "diff --git a/fs/ext4/inode.c b/fs/ext4/inode.c\\n...",
        ...         "diff --git a/mm/page_alloc.c b/mm/page_alloc.c\\n..."
        ...     ]
        ... )
    """
    # required for parser;
    workerType: Literal['kprebuilder']=Field(default='kprebuilder')

    kCache: kcore.JobResource
    patches: List[str]

class PatchResultStatus(str, Enum):
    """Status of patch application attempt.

    Attributes:
        patchUnapplicable: Patch failed to apply (conflict or missing context)
        compilationError: Patch applied but kernel failed to compile
        patchApplicable: Patch applied successfully and kernel compiled
    """
    patchUnapplicable = 'patchUnapplicable'
    compilationError = 'compilationError'
    patchApplicable = 'patchApplicable'

class ModifiedFunction(BaseModel):
    """Function-level analysis of patch changes.

    Attributes:
        functionName: Name of the modified function
        instrCountBefore: Instruction count before patch
        instrCountAfter: Instruction count after patch

    Example:
        >>> func = ModifiedFunction(
        ...     functionName="ext4_write_begin",
        ...     instrCountBefore=150,
        ...     instrCountAfter=165
        ... )
    """
    functionName: str
    instrCountBefore: int
    instrCountAfter: int

class ModifiedFile(BaseModel):
    """File-level analysis of patch changes.

    Attributes:
        filename: Path to modified file
        modifiedFunctions: List of functions changed in this file

    Example:
        >>> file = ModifiedFile(
        ...     filename="fs/ext4/inode.c",
        ...     modifiedFunctions=[func1, func2]
        ... )
    """
    filename: str
    modifiedFunctions: List[ModifiedFunction]

class PatchResult(BaseModel):
    """Result of testing a single patch.

    Attributes:
        status: Outcome of patch application and compilation
        modifiedFiles: List of files modified by the patch

    Example:
        >>> result = PatchResult(
        ...     status=PatchResultStatus.patchApplicable,
        ...     modifiedFiles=["fs/ext4/inode.c", "fs/ext4/super.c"]
        ... )
    """
    status: PatchResultStatus
    modifiedFiles: List[str]

class kPreBuilderResult(kcore.JobResult):
    """Output results from kprebuilder worker.

    Contains test results for each patch, indicating whether it applies
    cleanly and compiles successfully.

    Attributes:
        workerType: Always 'kprebuilder'
        patchResults: List of results, one per input patch (same order)

    Example:
        >>> ctx = client.get_job(job_id)
        >>> result: kPreBuilderResult = ctx.jobWorkers[0].workerResult
        >>> for i, patch_result in enumerate(result.patchResults):
        ...     if patch_result.status == PatchResultStatus.patchApplicable:
        ...         print(f"Patch {i} applies cleanly")
        ...     elif patch_result.status == PatchResultStatus.patchUnapplicable:
        ...         print(f"Patch {i} has conflicts")
        ...     elif patch_result.status == PatchResultStatus.compilationError:
        ...         print(f"Patch {i} applies but breaks build")
    """
    # required for parser;
    workerType: Literal['kprebuilder']=Field(default='kprebuilder')

    patchResults: List[PatchResult] | None=None

class kPreBuilderWorker(kcore.JobWorker):
    """Complete kprebuilder worker state with argument and result.

    Represents a kprebuilder worker stage in a job pipeline, containing
    both the input arguments and output result (if completed).

    Attributes:
        workerType: Always 'kprebuilder'
        workerArgument: Input arguments
        workerResult: Output result (None if not completed)
    """
    workerType: Literal['kprebuilder']=Field(default='kprebuilder')

    workerArgument: kPreBuilderArgument
    workerResult: kPreBuilderResult | None
