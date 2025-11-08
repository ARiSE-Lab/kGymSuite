"""KBDr-Runner VM Manager Worker Models.

This module defines data models for the kvmmanager worker, which executes
crash reproducers in VMs using syzkaller/syz-crush and collects crash artifacts.

Classes:
    Reproducer: Crash reproducer configuration (C or syzkaller log)
    Image: VM image specification from kbuilder
    kVMManagerArgument: Input arguments for kvmmanager worker
    kVMManagerResult: Output results from kvmmanager worker
    kVMManagerWorker: Complete worker state with argument and result
    Crash: Detected crash with incidents
    CrashIncident: Single crash occurrence with artifacts

Example:
    Running a reproducer on a built kernel:

    >>> from KBDr.kclient import kJobRequest, kGymClient
    >>> from KBDr.kclient_models import kVMManagerArgument, Reproducer
    >>>
    >>> job = kJobRequest(jobWorkers=[
    ...     kBuilderArgument(...),  # Build kernel first
    ...     kVMManagerArgument(
    ...         reproducer=Reproducer(
    ...             reproducerType="c",
    ...             reproducerText="int main() { ... }"
    ...         ),
    ...         image=0,  # Use output from worker 0
    ...         machineType="qemu:2-4096"
    ...     )
    ... ])
    >>> client = kGymClient("http://localhost:8000")
    >>> job_id = client.create_job(job)
"""

from typing import Literal, List, Optional
from KBDr import kcore
from pydantic import BaseModel

class Reproducer(BaseModel):
    """Crash reproducer configuration.

    Specifies the reproducer type, content, and syzkaller version to use
    for crash reproduction.

    Attributes:
        reproducerType: Type of reproducer ('c' for C program, 'log' for syz log)
        reproducerText: Content of the reproducer
        syzkallerCheckout: Syzkaller git commit to use
        syzkallerCheckoutRollback: Whether to rollback on failure
        syzkallerLatestTag: Tag to use if checkout fails
        restartTime: VM restart interval (e.g., '10m')
        nInstance: Number of VM instances to run
        threaded: Whether to enable threading in C reproducers

    Example:
        C reproducer:

        >>> repro = Reproducer(
        ...     reproducerType="c",
        ...     reproducerText="int main() { /* crash code */ }",
        ...     syzkallerCheckout="abc123",
        ...     restartTime="10m"
        ... )

        Syzkaller log reproducer:

        >>> repro = Reproducer(
        ...     reproducerType="log",
        ...     reproducerText="r0 = openat(...)",
        ...     nInstance=4
        ... )
    """
    reproducerType: Literal['c', 'log']
    reproducerText: str
    syzkallerCheckout: str='ca620dd8f97f5b3a9134b687b5584203019518fb'
    syzkallerCheckoutRollback: bool=True
    syzkallerLatestTag: str='ca620dd8f97f5b3a9134b687b5584203019518fb'
    restartTime: str='10m'
    nInstance: int=1
    threaded: bool=True

class Image(BaseModel):
    """VM image specification for crash reproduction.

    Contains references to kernel image artifacts produced by kbuilder.

    Attributes:
        vmImage: Bootable VM disk image
        vmlinux: Uncompressed kernel with symbols
        arch: CPU architecture

    Example:
        >>> image = Image(
        ...     vmImage=vm_image_resource,
        ...     vmlinux=vmlinux_resource,
        ...     arch="amd64"
        ... )
    """
    vmImage: kcore.JobResource
    vmlinux: kcore.JobResource
    arch: str

    @classmethod
    def model_from_kbuilder_result(cls, result: 'kBuilderResult'):
        """Create Image from kbuilder result.

        Args:
            result: kBuilderResult from completed kbuilder worker

        Returns:
            Image specification extracted from result

        Example:
            >>> ctx = client.get_job(job_id)
            >>> builder_result = ctx.jobWorkers[0].workerResult
            >>> image = Image.model_from_kbuilder_result(builder_result)
        """
        from .kbuilder import kBuilderResult
        return cls(
            vmImage=result.vmImage,
            vmlinux=result.vmlinux,
            arch=result.kernelArch
        )

class kVMManagerArgument(kcore.JobArgument):
    """Input arguments for kvmmanager worker.

    Specifies reproducer, VM image, machine type.

    Attributes:
        workerType: Always 'kvmmanager'
        reproducer: Reproducer configuration
        image: Image specification or worker index (int) to get image from
        machineType: Machine type ('qemu:cpu-memory' or 'gce:machine-type')

    Example:
        Using image from previous worker:

        >>> arg = kVMManagerArgument(
        ...     reproducer=Reproducer(...),
        ...     image=0,  # Use output from worker 0
        ...     machineType="qemu:2-4096"
        ... )
    """
    workerType: Literal['kvmmanager']='kvmmanager'

    reproducer: Reproducer
    image: Image | int
    machineType: str='gce:e2-standard-2'

    @classmethod
    def model_from_syzbot_data(
        cls,
        syzbot_data: 'SyzbotData',
        machine_type: str = 'gce:e2-standard-2',
        image: Image | int = -1,
        reproducer_preference: str = 'log',
        ninstance: int = 1,
        restart_time: str = '10m',
        syzkaller_latest_tag: str = 'ca620dd8f97f5b3a9134b687b5584203019518fb',
        rollback: bool = True,
        crash_index: int = 0
    ) -> 'kVMManagerArgument':
        """
        Create kVMManagerArgument from SyzbotData.

        Args:
            syzbot_data: The syzbot bug data
            machine_type: Machine type (e.g., 'gce:e2-standard-2')
            image_from_worker: Worker index to get image from (-1 means use provided image)
            image: Image specification (if not using image_from_worker)
            reproducer_preference: 'log' or 'c' reproducer preference
            ninstance: Number of VM instances
            restart_time: VM restart time (e.g., '10m')
            syzkaller_checkout: Syzkaller checkout to use
            syzkaller_latest_tag: Syzkaller latest tag to use
            rollback: Whether to rollback syzkaller on failure
            crash_index: Which crash to use from the crashes list (default: 0)

        Returns:
            kVMManagerArgument: The pydantic model for kvmmanager

        Raises:
            ValueError: If required fields are missing or invalid
            IndexError: If crash_index is out of bounds
        """
        from ..kclient.kgym_dataset import SyzbotData
        from typing import Optional

        if not syzbot_data.crashes:
            raise ValueError(f'No crashes found in bug {syzbot_data.bugId}')

        if crash_index >= len(syzbot_data.crashes):
            raise IndexError(f'Crash index {crash_index} out of bounds for {len(syzbot_data.crashes)} crashes')

        crash = syzbot_data.crashes[crash_index]

        # Check for reproducers
        if not crash.syzReproducer and not crash.cReproducer:
            raise ValueError(f'No reproducer found in crash {crash_index}')

        # Create reproducer based on preference
        if reproducer_preference == 'log':
            if crash.syzReproducer:
                reproducer_type = 'log'
                reproducer_text = crash.syzReproducer
            elif crash.cReproducer:
                reproducer_type = 'c'
                reproducer_text = crash.cReproducer
            else:
                raise ValueError(f'No suitable reproducer found in crash {crash_index}')
        elif reproducer_preference == 'c':
            if crash.cReproducer:
                reproducer_type = 'c'
                reproducer_text = crash.cReproducer
            elif crash.syzReproducer:
                reproducer_type = 'log'
                reproducer_text = crash.syzReproducer
            else:
                raise ValueError(f'No suitable reproducer found in crash {crash_index}')
        else:
            raise ValueError(f'Invalid reproducer preference: {reproducer_preference}')

        # Create Reproducer
        reproducer = Reproducer(
            reproducerType=reproducer_type,
            reproducerText=reproducer_text,
            syzkallerCheckout=crash.syzkallerCommit,
            syzkallerCheckoutRollback=rollback,
            syzkallerLatestTag=syzkaller_latest_tag,
            restartTime=restart_time,
            nInstance=ninstance
        )

        # Create kVMManagerArgument
        return cls(
            reproducer=reproducer,
            image=image,
            machineType=machine_type
        )

class CrashIncident(BaseModel):
    """Single crash occurrence with collected artifacts.

    Represents one instance of a crash with all collected artifacts including
    logs, reports.

    Attributes:
        log: Kernel console log
        report: Crash report (stack trace, etc.)

    Example:
        >>> incident = result.crashes[0].incidents[0]
        >>> if incident.log:
        ...     print("Has console log")
    """
    log: kcore.JobResource | None=None
    report: kcore.JobResource | None=None

class Crash(BaseModel):
    """Detected crash with metadata and incidents.

    Groups multiple crash incidents of the same type together with
    identifying information.

    Attributes:
        crashId: Unique crash identifier within this job
        title: Crash title/summary (e.g., "KASAN: use-after-free")
        crashType: 'crash' for real crashes, 'special' for test/boot events
        incidents: List of crash occurrences with artifacts

    Example:
        >>> for crash in result.crashes:
        ...     if crash.crashType == 'crash':
        ...         print(f"Crash: {crash.title}")
        ...         print(f"Occurred {len(crash.incidents)} times")
    """
    crashId: int
    title: str
    crashType: Literal['crash', 'special']
    incidents: List[CrashIncident]

class kVMManagerResult(kcore.JobResult):
    """Output results from kvmmanager worker.

    Contains crash reproduction results including detected crashes,
    logs, and metadata about image quality and features.

    Attributes:
        workerType: Always 'kvmmanager'
        crushLog: Complete syz-crush execution log
        crashes: List of detected crashes with artifacts
        finalSyzkallerCheckout: Syzkaller version actually used
        imageAbility: Image quality ('normal', 'warning', 'error')

    Example:
        >>> ctx = client.get_job(job_id)
        >>> result: kVMManagerResult = ctx.jobWorkers[1].workerResult
        >>> if result.crashes:
        ...     for crash in result.crashes:
        ...         if crash.crashType == 'crash':
        ...             print(f"Reproduced: {crash.title}")
        ... else:
        ...     print("No crashes reproduced")
        >>> print(f"Image quality: {result.imageAbility}")
    """
    workerType: Literal['kvmmanager']='kvmmanager'

    crushLog: kcore.JobResource | None=None
    crashes: List[Crash] | None=None
    finalSyzkallerCheckout: str | None=None
    imageAbility: Literal['normal', 'warning', 'error'] | None=None

class kVMManagerWorker(kcore.JobWorker):
    """Complete kvmmanager worker state with argument and result.

    Represents a kvmmanager worker stage in a job pipeline, containing
    both the input arguments and output result (if completed).

    Attributes:
        workerType: Always 'kvmmanager'
        workerArgument: Input arguments
        workerResult: Output result (None if not completed)
    """
    workerType: Literal['kvmmanager']='kvmmanager'

    workerArgument: kVMManagerArgument
    workerResult: kVMManagerResult | None
