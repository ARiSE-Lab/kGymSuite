"""KBDr-Runner Client Library.

This module provides the client library for interacting with the KBDr-Runner distributed
kernel build, test, and crash reproduction framework. It includes HTTP clients for API
communication, dataset utilities for working with Syzbot data, and data models for
job submission and control.

Main Components:
    kGymClient: Synchronous HTTP client for KBDr-Runner API
    kGymAsyncClient: Asynchronous HTTP client for KBDr-Runner API
    SyzbotDataset: Dataset models for Syzbot crash data
    kBench: Benchmark evaluation utilities
    kJobRequest: Job submission model
    kJobContext: Job status and results model

Example:
    Basic job submission:

    >>> from KBDr.kclient import kGymClient, kJobRequest
    >>> from KBDr.kclient_models import kBuilderArgument, KernelGitCommit
    >>>
    >>> client = kGymClient("http://localhost:8000")
    >>> job = kJobRequest(
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
    ...         )
    ...     ]
    ... )
    >>> job_id = client.create_job(job)
    >>> status = client.get_job(job_id)
"""

from .kgym_client import kGymAsyncClient, kGymClient
from .kgym_dataset import *
from .models import *
