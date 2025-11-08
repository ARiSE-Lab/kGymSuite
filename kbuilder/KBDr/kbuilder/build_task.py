# build_task.py
import os, shutil, aiofiles, json, time, asyncio
import asyncio.subprocess as asp

from KBDr.kcore import TaskBase, JobExceptionError
from KBDr.kcore.utils import run_async
from KBDr.kclient_models.kbuilder import *

from .checkout_manager import CheckoutManager
from .repository_manager import RepositoryManager
from .linux_builder import LinuxBuilder
from .utils import *

class kBuilderTask(TaskBase):

    argument: kBuilderArgument
    result_lock: asyncio.Lock
    pending_result: kBuilderResult | None=None

    async def pull_from_scratch(self, commit: KernelGitCommit):
        await self.report_job_log('Pulling source from scratch')

        local_git_path = await self.repo_mgr.get_repository(commit.gitUrl)
        checkout_path = os.path.join(self.cwd, 'linux')
        checkout_mgr = CheckoutManager(
            self,
            checkout_path,
            self.backport_commit_list
        )

        await checkout_mgr.clone_and_checkout(local_git_path, commit.gitUrl, commit.commitId)
        await checkout_mgr.apply_backport()

        async with aiofiles.open(os.path.join(checkout_path, '.config'), 'w') as fp:
            await fp.write(commit.kConfig)

        return checkout_path

    async def pull_from_kcache(self, kcache_key: str):
        await self.report_job_log('Pulling source from kcache')

        kcache_local_path = os.path.join(self.cwd, KCACHE_FILENAME)
        await self.storage_backend.download_resource(kcache_key, kcache_local_path)

        checkout_path = os.path.join(self.cwd, 'linux')
        await run_async(os.makedirs, checkout_path)

        # untar;
        proc = await asp.create_subprocess_exec(
            'tar', '-x', '--use-compress-program=zstdmt',
            '-f', kcache_local_path, '-C', checkout_path,
            stdin=asp.DEVNULL, stdout=asp.DEVNULL, stderr=asp.DEVNULL
        )
        code = await proc.wait()
        if code != 0:
            raise JobExceptionError('kbuilder.KcacheUntarError', f'Failed to untar the {KCACHE_FILENAME}')

        # delete the kcache;
        await run_async(os.remove, kcache_local_path)
        return checkout_path

    async def pull(self):
        checkout_path = ''
        kcache_cfg = dict()
        if isinstance(self.argument.kernelSource, kcore.JobResource):
            checkout_path = await self.pull_from_kcache(self.argument.kernelSource.key)
            async with aiofiles.open(os.path.join(checkout_path, 'kcache.json')) as fp:
                kcache_cfg = json.loads(await fp.read())
        elif isinstance(self.argument.kernelSource, KernelGitCommit):
            checkout_path = await self.pull_from_scratch(self.argument.kernelSource)
            kcache_cfg = {
                'kernel-arch': self.argument.kernelSource.arch,
                'compiler': self.argument.kernelSource.compiler,
                'linker': self.argument.kernelSource.linker
            }
        async with aiofiles.open(os.path.join(checkout_path, 'kcache.json'), 'w') as fp:
            await fp.write(json.dumps(kcache_cfg))
        checkout_mgr = CheckoutManager(self, checkout_path, self.backport_commit_list)
        if self.argument.patch != '':
            if not (await checkout_mgr.apply_patch(self.argument.patch)):
                raise JobExceptionError('kbuilder.PatchApplicationError', 'Patch is not applicable')
            else:
                await self.report_job_log('Successful patch application')
        await checkout_mgr.ensure_reproducible()
        return checkout_path, kcache_cfg
    
    async def build(self, checkout_path: str, kcache_cfg: dict):
        userspace_image_blob_key = f'userspace-images/{self.argument.userspaceImage}'
        userspace_image_path = os.path.join(self.cwd, 'disk.raw')
        await self.report_job_log('Downloading userspace image')
        await self.storage_backend.download_resource(userspace_image_blob_key, userspace_image_path)
        await self.report_job_log('Userspace image downloaded')

        await self.report_job_log('Invoking LinuxBuilder')
        _build_time_l = time.time()
        linux_builder = LinuxBuilder(
            self,
            checkout_path,
            os.cpu_count(),
            kcache_cfg['kernel-arch'],
            kcache_cfg['compiler'],
            kcache_cfg['linker'],
            userspace_image_path
        )
        await linux_builder.make()
        self.pending_result.compilationTime = time.time() - _build_time_l
        await self.report_job_log('LinuxBuilder finished')

    async def build_kcache(self, checkout_path: str, kcache_path: str):
        # tar;
        # remove the .git;
        git_folder_path = os.path.join(checkout_path, '.git')
        if os.path.exists(git_folder_path) and os.path.isdir(git_folder_path):
            await run_async(shutil.rmtree, git_folder_path)
        await self.report_job_log('Building kcache')
        proc = await asp.create_subprocess_exec(
            'tar', '-c', '--use-compress-program=zstdmt',
            '-f', kcache_path, './',
            cwd=checkout_path, stdin=asp.DEVNULL,
            stdout=asp.DEVNULL, stderr=asp.DEVNULL
        )
        code = await proc.wait()
        if code != 0:
            raise JobExceptionError('kbuilder.KcacheBuildError', 'Failed to create kcache')
        await self.report_job_log('kcache was built successfully')
        self.pending_result.kCache = await self.submit_resource(
            'kcache.tar.zstd', kcache_path
        )

    async def on_task(self) -> kBuilderResult:
        self.result_lock = asyncio.Lock()
        self.pending_result = kBuilderResult()
        self.argument = kBuilderArgument.model_validate(self.argument.model_dump())
        self.pending_result.compilationTime = 0

        self.repositories_path = os.environ['KBUILDER_KERNEL_REPO_PATH']
        self.backport_commit_list = self.system_config.workerConfig['backportCommits']

        self.repo_mgr = RepositoryManager(self, self.repositories_path)

        checkout_path, kcache_cfg = await self.pull()
        self.pending_result.kernelArch = kcache_cfg['kernel-arch']

        await self.build(checkout_path, kcache_cfg)
        kcache_path = os.path.join(self.cwd, KCACHE_FILENAME)
        await self.build_kcache(checkout_path, kcache_path)

        return self.pending_result
