# repository_manager.py
import os, shutil, aiofiles, json, hashlib
import asyncio.subprocess as asp
from KBDr.kcore import TaskBase, run_async, JobExceptionError
from datetime import datetime

last_updated = dict()

class RepositoryManager:

    @staticmethod
    def canonicalize_git_url(git_url: str):
        if git_url[-1] == '/':
            git_url = git_url[:-1]
        return git_url

    def __init__(self, task: TaskBase, repo_dir: str):
        self.task = task
        self.repo_dir = repo_dir
        self.repo_metadata_fname = os.path.join(self.repo_dir, 'repo.json')
        self.repos = None

    async def save_local_repository_list(self):
        async with aiofiles.open(self.repo_metadata_fname, 'w', encoding='utf-8') as fp:
            await fp.write(json.dumps(self.repos))

    async def load_local_repository_list(self):
        if not await run_async(os.path.exists, self.repo_metadata_fname):
            # create when non-existing;
            self.repos = dict()
            await self.save_local_repository_list()
        else:
            # read info;
            async with aiofiles.open(self.repo_metadata_fname, 'r', encoding='utf-8') as fp:
                self.repos = json.loads(await fp.read())

    async def update_local_repository_list(self, git_url: str, local_name: str):
        if not isinstance(self.repos, dict):
            await self.load_local_repository_list()
        self.repos[git_url] = local_name
        await self.save_local_repository_list()

    async def get_from_local_repository_list(self, git_url: str):
        if not isinstance(self.repos, dict):
            await self.load_local_repository_list()
        return self.repos.get(git_url, None)

    async def clone_bare_repository(self, git_url: str):
        local_name = hashlib.md5(git_url.encode('utf-8')).hexdigest()
        local_path = os.path.join(self.repo_dir, local_name)
        await self.task.report_job_log(f'Cloning bare repository \"{git_url}\" to \"{local_name}\"')

        # clean up the potential unfinished clone;
        if await run_async(os.path.exists, local_path):
            await run_async(shutil.rmtree, local_path)

        code = await ((await asp.create_subprocess_exec(
            'git',
            'clone',
            '--bare',
            git_url,
            local_name,
            cwd=self.repo_dir,
            stdin=asp.DEVNULL,
            stdout=asp.DEVNULL,
            stderr=asp.DEVNULL)).wait())

        if code != 0:
            raise JobExceptionError('kbuilder.GitError', f'Failed to clone base repository \"{git_url}\"')

        await self.update_local_repository_list(git_url, local_name)
        return local_name

    async def update_local_repository(self, local_name: str):
        code = await ((await asp.create_subprocess_exec(
            'git', 'fetch', 'origin',
            cwd=os.path.join(self.repo_dir, local_name),
            stdin=asp.DEVNULL,
            stdout=asp.DEVNULL,
            stderr=asp.DEVNULL
        )).wait())
        if code != 0:
            raise JobExceptionError('kbuilder.RepositoryManagerError', f'Failed to update cached repository \"{local_name}\"')


    async def get_repository(self, git_url: str):
        git_url = RepositoryManager.canonicalize_git_url(git_url)
        local_name = await self.get_from_local_repository_list(git_url)
        if not isinstance(local_name, str):
            local_name = await self.clone_bare_repository(git_url)
        else:
            updated_ts: datetime = last_updated.get(local_name, datetime.fromtimestamp(0))
            interval = datetime.now() - updated_ts
            if interval.days >= 1:
                await self.task.report_job_log(f'Updating cached repository \"{local_name}\"')
                await self.update_local_repository(local_name)
                last_updated[local_name] = datetime.now()
        await self.task.report_job_log(f'Use cached bare repository \"{local_name}\"')
        return os.path.join(self.repo_dir, local_name)
