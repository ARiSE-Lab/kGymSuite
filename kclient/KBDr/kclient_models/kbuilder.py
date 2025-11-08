"""KBDr-Runner Kernel Builder Worker Models.

This module defines the data models for the kbuilder worker, which compiles
Linux kernels from git commits or cached builds and creates bootable VM images.

Classes:
    KernelGitCommit: Specification for building kernel from git
    kBuilderArgument: Input arguments for kbuilder worker
    kBuilderResult: Output results from kbuilder worker
    kBuilderWorker: Complete worker state with argument and result

Example:
    Building a kernel from git:

    >>> from KBDr.kclient import kJobRequest, kGymClient
    >>> from KBDr.kclient_models import kBuilderArgument, KernelGitCommit
    >>>
    >>> job = kJobRequest(jobWorkers=[
    ...     kBuilderArgument(
    ...         kernelSource=KernelGitCommit(
    ...             gitUrl="https://github.com/torvalds/linux",
    ...             commitId="v6.1",
    ...             kConfig="CONFIG_X86=y\\nCONFIG_64BIT=y\\n...",
    ...             arch="amd64",
    ...             compiler="gcc",
    ...             linker="ld"
    ...         ),
    ...         userspaceImage="buildroot.raw"
    ...     )
    ... ])
    >>> client = kGymClient("http://localhost:8000")
    >>> job_id = client.create_job(job)
"""

from typing import Literal
from KBDr import kcore
from pydantic import BaseModel, Field

class KernelGitCommit(BaseModel):
    """Specification for building a kernel from a git repository.

    Attributes:
        gitUrl: Git repository URL (e.g., https://github.com/torvalds/linux)
        commitId: Git commit SHA or tag to checkout
        kConfig: Kernel configuration file content (newline-separated CONFIG_* lines)
        arch: Target architecture (amd64, 386, arm64, arm)
        compiler: Compiler to use (gcc, clang)
        linker: Linker to use (ld, ld.lld)

    Example:
        >>> source = KernelGitCommit(
        ...     gitUrl="https://github.com/torvalds/linux",
        ...     commitId="v6.1",
        ...     kConfig="CONFIG_X86=y\\nCONFIG_64BIT=y\\n",
        ...     arch="amd64",
        ...     compiler="gcc",
        ...     linker="ld"
        ... )
    """
    gitUrl: str
    commitId: str
    kConfig: str
    arch: str
    compiler: str
    linker: str

class kBuilderArgument(kcore.JobArgument):
    """Input arguments for kbuilder worker.

    Specifies what kernel to build and what userspace image to combine it with.
    The kernel source can be either a git commit specification or a reference
    to a cached kernel build.

    Attributes:
        workerType: Always 'kbuilder'
        kernelSource: Either KernelGitCommit for fresh build or JobResource for cache
        userspaceImage: Filename of userspace image in storage
        patch: Optional patch to apply before building (unified diff format)

    Example:
        Fresh build from git:

        >>> arg = kBuilderArgument(
        ...     kernelSource=KernelGitCommit(...),
        ...     userspaceImage="buildroot.raw",
        ...     patch="diff --git a/file.c b/file.c\\n..."
        ... )

        Build from cache:

        >>> arg = kBuilderArgument(
        ...     kernelSource=cached_kernel_resource,
        ...     userspaceImage="buildroot.raw"
        ... )
    """
    # required for parser;
    workerType: Literal['kbuilder']=Field(default='kbuilder')

    kernelSource: kcore.JobResource | KernelGitCommit
    userspaceImage: str
    patch: str=''

    @classmethod
    def parse_url(
        cls,
        git_url: str
    ):
        if '/commit/?id=' in git_url:
            git_url = git_url.split('/commit/?id=')[0]
        elif 'https://github.com/' in git_url:
            git_url = git_url.split('/commits/')[0]
        elif 'https://git.kernel.org/pub/scm/linux/kernel/git/' in git_url:
            git_url = git_url.split('/log/?id=')[0]
        elif not git_url:
            # Default kernel git URL
            git_url = 'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git'
        else:
            raise ValueError(f'Unsupported git URL: {git_url}')
        return git_url

    @classmethod
    def model_from_syzbot_data(
        cls,
        syzbot_data: 'SyzbotData',
        userspace_image_name: str | None = None,
        compiler: str = '',
        linker: str = '',
        crash_index: int = 0,
        commit_from: Literal['parent', 'crash'] = 'parent'
    ) -> 'kBuilderArgument':
        """
        Create kBuilderArgument from SyzbotData.

        Args:
            syzbot_data: The syzbot bug data
            userspace_image_name: The userspace image filename in the bucket
            compiler: gcc, clang (auto-detected if empty)
            linker: ld, ld.lld (auto-detected if empty)
            crash_index: Which crash to use from the crashes list (default: 0)

        Returns:
            kBuilderArgument: The pydantic model for kbuilder

        Raises:
            ValueError: If required fields are missing or invalid
            IndexError: If crash_index is out of bounds
        """
        from ..kclient.kgym_dataset import SyzbotData

        ARCH_MAP = {
            'amd64': 'amd64',
            'i386': '386',
            'arm64': 'arm64',
            'arm': 'arm'
        }

        if not syzbot_data.crashes:
            raise ValueError(f'No crashes found in bug {syzbot_data.bugId}')

        if crash_index >= len(syzbot_data.crashes):
            raise IndexError(f'Crash index {crash_index} out of bounds for {len(syzbot_data.crashes)} crashes')

        crash = syzbot_data.crashes[crash_index]

        # Validate required fields
        if not crash.kernelConfig:
            raise ValueError(f'Missing kernel-config in crash {crash_index}')
        if not crash.kernelSourceCommit:
            raise ValueError(f'Missing kernel-source-commit in crash {crash_index}')
        if crash.architecture not in ARCH_MAP:
            raise ValueError(f'Unsupported architecture: {crash.architecture}')

        # Process git URL
        git_url = cls.parse_url(crash.kernelSourceGit)

        # Auto-detect compiler if not specified
        if compiler == '':
            if 'clang' in crash.compilerDescription.lower():
                compiler = 'clang'
            else:
                compiler = 'gcc'

        # Auto-detect linker if not specified
        if linker == '':
            if compiler == 'clang':
                linker = 'ld.lld'
            else:
                linker = 'ld'

        # Create KernelGitCommit
        kernel_source = KernelGitCommit(
            gitUrl=git_url,
            commitId=syzbot_data.parentOfFixCommit if commit_from == 'parent' else crash.kernelSourceCommit,
            kConfig=crash.kernelConfig,
            arch=ARCH_MAP[crash.architecture],
            compiler=compiler,
            linker=linker
        )

        # Create kBuilderArgument
        return cls(
            kernelSource=kernel_source,
            userspaceImage=syzbot_data.userspaceImage if not userspace_image_name else userspace_image_name
        )

    @classmethod
    def model_from_syzbot_data_with_kcache(
        cls,
        syzbot_data: 'SyzbotData',
        kcache_resource: kcore.JobResource,
        userspace_image_name: str | None = None
    ) -> 'kBuilderArgument':
        """
        Create kBuilderArgument from SyzbotData using a pre-built kernel cache.

        Args:
            syzbot_data: The syzbot bug data
            kcache_resource: JobResource pointing to the kernel cache
            userspace_image_name: The userspace image filename

        Returns:
            kBuilderArgument: The pydantic model for kbuilder
        """
        return cls(
            kernelSource=kcache_resource,
            userspaceImage=syzbot_data.userspaceImage if not userspace_image_name else userspace_image_name
        )

class kBuilderResult(kcore.JobResult):
    """Output results from kbuilder worker.

    Contains all artifacts produced by kernel build including compiled kernel,
    VM image, build cache, and compilation metadata.

    Attributes:
        workerType: Always 'kbuilder'
        compilationTime: Time taken to compile in seconds (if successful)
        kernelArch: Target architecture that was built
        kCache: Kernel cache for reuse in future builds
        kernelConfig: Final kernel configuration used
        kBuilderStdout: Build stdout logs
        kBuilderStderr: Build stderr logs
        kernelImage: Compressed kernel image (bzImage/Image)
        vmlinux: Uncompressed kernel with debug symbols
        vmImage: Complete bootable VM disk image
        kernelCompileCommands: compile_commands.json for IDE integration

    Example:
        >>> ctx = client.get_job(job_id)
        >>> result: kBuilderResult = ctx.jobWorkers[0].workerResult
        >>> if result.vmImage:
        ...     print(f"Built in {result.compilationTime}s")
        ...     image = result.get_image()
    """
    # required for parser;
    workerType: Literal['kbuilder']=Field(default='kbuilder')

    # optional field in case of any exceptions;
    compilationTime: float | None=None
    kernelArch: str | None=None

    kCache: kcore.JobResource | None=None
    kernelConfig: kcore.JobResource | None=None
    kBuilderStdout: kcore.JobResource | None=None
    kBuilderStderr: kcore.JobResource | None=None
    kernelImage: kcore.JobResource | None=None
    vmlinux: kcore.JobResource | None=None
    vmImage: kcore.JobResource | None=None
    kernelCompileCommands: kcore.JobResource | None=None

    def get_image(self) -> 'Image':
        """Extract Image specification for use with kvmmanager.

        Returns:
            Image object containing vmImage, vmlinux, and arch

        Example:
            >>> result: kBuilderResult = ...
            >>> image = result.get_image()
            >>> # Use image in kvmmanager
            >>> vm_arg = kVMManagerArgument(image=image, ...)
        """
        from .kvmmanager import Image
        return Image(
            vmImage=self.vmImage,
            vmlinux=self.vmlinux,
            arch=self.kernelArch
        )

class kBuilderWorker(kcore.JobWorker):
    """Complete kbuilder worker state with argument and result.

    Represents a kbuilder worker stage in a job pipeline, containing both
    the input arguments and output result (if completed).

    Attributes:
        workerType: Always 'kbuilder'
        workerArgument: Input arguments
        workerResult: Output result (None if not completed)
    """
    workerType: Literal['kbuilder']=Field(default='kbuilder')

    workerArgument: kBuilderArgument
    workerResult: kBuilderResult | None
