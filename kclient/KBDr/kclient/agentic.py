import os
import asyncio
import asyncio.subprocess as asp
from pathlib import Path

from KBDr.kcore import (
    create_storage_backend, StorageProviderConfig, JobStatus, run_async
)

from .kgym_client import kGymAsyncClient
from .kgym_dataset import kBench, kBenchEvaluationResult
from .models import kJobContext, kBuilderResult, kVMManagerResult

def try_rm(path: str):
    if os.path.exists(path):
        os.remove(path)

def filter_binary_files_from_patch(patch_content: str) -> str:
    from unidiff import PatchSet
    if not patch_content or not patch_content.strip():
        return patch_content
    try:
        # Parse the patch
        patchset = PatchSet(patch_content)

        # Filter out binary files
        filtered_files = [f for f in patchset if not f.is_binary_file]

        # If no binary files were found, return original
        if len(filtered_files) == len(patchset):
            return patch_content

        # Recompose the patch from non-binary files
        filtered_patch_lines = []
        for patch_file in filtered_files:
            filtered_patch_lines.append(str(patch_file))

        filtered_patch = ''.join(filtered_patch_lines)

        num_binary = len(patchset) - len(filtered_files)
        return filtered_patch
    except Exception as e:
        return patch_content

class kGymAgentClient(kGymAsyncClient):

    def __init__(
        self,
        base_url: str,
        root: str,
        bug_id: str,
        kbench_path: str,
        eval_result_path: str,
        storage_cfg_path: str,
        **kwargs
    ):
        # Environment variables -> config;
        super().__init__(base_url, **kwargs)
        if len(root) > 1 and root[-1] == '/':
            root = root[:-1]
        self.root = root
        self.bug_id = bug_id
        self.kbench_path = kbench_path
        self.storage_cfg_path = storage_cfg_path
        self.home = os.path.expanduser('~')
        self.tool_observation = ''

    def print(self, s: str):
        self.tool_observation += s + '\n'

    async def connect(self):
        self.storage_backend = await create_storage_backend(StorageProviderConfig.model_validate_json(
            await run_async(Path(self.storage_cfg_path).read_text)
        ))
        self.kb = kBench.model_validate_json(
            await run_async(Path(self.kbench_path).read_text)
        )
        self.bug = self.kb.dataset.get(self.bug_id)

    async def close(self):
        await super().close()

    async def resolve_job_context(self, ctx: kJobContext):
        # error;
        if ctx.status == JobStatus.Aborted:
            problemWorker = ctx.jobWorkers[ctx.currentWorker]
            if problemWorker.workerResult.workerException:
                self.print('kGym error: ' + problemWorker.workerType + ', ' + problemWorker.workerResult.workerException.code + '.')
                return
            elif problemWorker.workerResult.jobException:
                if problemWorker.workerType == 'kbuilder' and problemWorker.workerResult.kBuilderStderr:
                    await self.storage_backend.download_resource(
                        problemWorker.workerResult.kBuilderStderr.key,
                        os.path.join(self.home, 'LinuxBuildStderr.txt')
                    )
                    self.print(f'Compilation error, builder\'s log at: `{os.path.abspath(os.path.join(self.home, "LinuxBuildStderr.txt"))}`')
                    return
                self.print('kGym error:' + problemWorker.workerType + ', ' + problemWorker.workerResult.jobException.code + ', ' + str(problemWorker.workerResult.jobException.content))
                return
            else:
                self.print('kGym error: unknown error; You may try the tool once more to see if things change.')
                return
        # not reproduced -> delete existing resources;
        crashes = []
        for i in range(1, len(ctx.jobWorkers)):
            vmmanagerResult: kVMManagerResult = ctx.jobWorkers[i].workerResult
            if vmmanagerResult.crashes is not None:
                for crash in vmmanagerResult.crashes:
                    if crash.crashType is not None and crash.crashType == 'crash':
                        crashes.append(crash)

        async with asyncio.TaskGroup() as tg:
            for crash in crashes:
                if len(crash.incidents) > 0:
                    incident = crash.incidents[0]
                    if incident.report:
                        tg.create_task(self.storage_backend.download_resource(
                            incident.report.key,
                            os.path.join(self.home, 'report.txt')
                        ))
                        self.print(f'Crash reproduced: "{crashes[0].title}"')
                        self.print(f'Check crash report at `' + os.path.join(self.home, 'report.txt') + '`.')
                        return
        
        self.print('No crash reproduced.')
        # clean stuff up;
        try_rm(os.path.join(self.home, 'LinuxBuildStderr.txt'))
        try_rm(os.path.join(self.home, 'report.txt'))
        return

    async def run(self, patch: str, **kwargs):
        er = (await self.kb.evaluate_kgym(
            self,
            patches={self.bug_id: patch},
            only_bug_ids=[self.bug_id],
            timeout=45 * 60,
            pbar=False,
            **kwargs
        )).root
        await self.resolve_job_context(er[self.bug_id].jobContext)
        return er

    async def get_patch(self):
        proc = await asp.create_subprocess_exec(
            'git', 'add', '-A',
            cwd=self.root,
            stdout=asp.DEVNULL,
            stderr=asp.DEVNULL,
            stdin=asp.DEVNULL
        )
        assert (await proc.wait()) == 0
        proc = await asp.create_subprocess_exec(
            'git', 'diff', '--cached',
            cwd=self.root,
            stdout=asp.PIPE,
            stderr=asp.DEVNULL,
            stdin=asp.DEVNULL
        )
        assert (await proc.wait()) == 0
        patch = (await proc.stdout.read()).decode('utf-8')
        patch = filter_binary_files_from_patch(patch)
        return patch

