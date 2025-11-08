import os, shutil, asyncio, aiofiles
import asyncio.subprocess as asp
from .utils import KERNEL_SEED, KERNEL_MODULE_SIGNING_KEY
from KBDr.kcore import TaskBase, JobExceptionError
from KBDr.kcore.utils import run_async

class CheckoutManager:
    
    def __init__(self, task: TaskBase, checkout_path: str, backport_commit_list: list):
        self.task = task
        self.checkout_path = checkout_path
        self.backport_commit_list = backport_commit_list

    async def clone_and_checkout(self, local_repo_path: str, remote_repo_url: str, commit_id: str):
        # clean up the potential unfinished checkout;
        if await run_async(os.path.exists, self.checkout_path):
            await run_async(shutil.rmtree, self.checkout_path)
        # clone repo;
        await self.task.report_job_log('Cloning from cached repository')
        code = await ((await asp.create_subprocess_exec(
            'git',
            'clone',
            local_repo_path,
            self.checkout_path,
            stdin=asp.DEVNULL,
            stderr=asp.DEVNULL)).wait())
        if code != 0:
            raise JobExceptionError('kbuilder.GitError', f'Failed to clone from the local repo: \"{local_repo_path}\"')
        # set the remote url;
        code = await ((await asp.create_subprocess_exec(
            'git',
            'remote',
            'set-url',
            'origin',
            remote_repo_url,
            cwd=self.checkout_path,
            stdin=asp.DEVNULL,
            stderr=asp.DEVNULL)).wait())
        if code != 0:
            raise JobExceptionError('kbuilder.GitError', f'Failed to set the remote URL of the local repo \"{local_repo_path}\" to \"{remote_repo_url}\"')
        # checkout;
        async def __checkout():
            return await ((await asp.create_subprocess_exec(
            'git',
            'checkout',
            commit_id,
            cwd=self.checkout_path,
            stdin=asp.DEVNULL,
            stdout=asp.DEVNULL,
            stderr=asp.DEVNULL)).wait())
        code = await __checkout()
        if code != 0:
            # try fetch the orphan;
            # git fetch origin <commit-id>:refs/remotes/origin/orphaned-commit
            code = await ((await asp.create_subprocess_exec(
                'git',
                'fetch',
                'origin',
                f'{commit_id}:refs/remotes/origin/orphaned-commit',
                cwd=self.checkout_path,
                stdin=asp.DEVNULL,
                stdout=asp.DEVNULL,
                stderr=asp.DEVNULL)).wait())
            if code != 0:
                raise JobExceptionError('kbuilder.GitError', f'Failed to fetch the commit \"{commit_id}\" from \"{remote_repo_url}\", even as if it\'s dangling commit')
            code = await __checkout()
            if code != 0:
                raise JobExceptionError('kbuilder.GitError', f'Fetched the dangling commit successfully, but failed to checkout \"{commit_id}\"')
        await self.task.report_job_log('Checkout obtained')

    COMMIT_PREFIXES = [
        'UPSTREAM:',
        'CHROMIUM:',
        'FROMLIST:',
        'BACKPORT:',
        'FROMGIT:',
        'net-backports:'
    ]
    
    @staticmethod
    def canonicalize_commit_title(title: str):
        for prefix in CheckoutManager.COMMIT_PREFIXES:
            if title.find(prefix) == 0:
                return (title[len(prefix):]).strip()
        return title.strip()

    async def get_commit_id_by_message(self, message: str):
        proc = await asp.create_subprocess_exec(
            'git',
            'log',
            '-F',
            '--grep',
            message,
            stdout=asp.PIPE,
            stdin=asp.DEVNULL,
            stderr=asp.PIPE,
            cwd=self.checkout_path)
        out = (await proc.communicate())[0]
        out = out.decode(encoding='utf-8')
        if len(out) != 0:
            return out.split('\n', maxsplit=1)[0].split(' ')[1]
        else:
            return None

    async def check_ancestor_by_commit_id(self, ancestor_commit_id: str):
        code = await ((await asp.create_subprocess_exec(
            'git',
            'merge-base',
            '--is-ancestor',
            ancestor_commit_id,
            'HEAD',
            stdout=asp.DEVNULL,
            stdin=asp.DEVNULL,
            stderr=asp.DEVNULL,
            cwd=self.checkout_path)).wait())
        return code == 0

    async def apply_backport(self):
        await self.task.report_job_log('Finding necessary backport commits')

        ancestor_check_lk = asyncio.Lock()

        async def get_cherry_pick_cmdlet(checkout_mgr: CheckoutManager, commit: dict) -> None | list:
            if ('guilty_hash' in commit):
                await ancestor_check_lk.acquire()
                is_ancestor = await checkout_mgr.check_ancestor_by_commit_id(commit['guilty_hash'])
                ancestor_check_lk.release()
                # not problematic;
                if not is_ancestor:
                    return

            fix_commit = await checkout_mgr.get_commit_id_by_message(CheckoutManager.canonicalize_commit_title(commit['fix_title']))
            if isinstance(fix_commit, str):
                # fixed in the previous commits;
                return
            # need backport;
            cherry_pick_cmdlet = ['cherry-pick', '--no-commit', '--strategy-option']
            if commit.get('force_merge', False):
                cherry_pick_cmdlet.append('theirs')
            else:
                cherry_pick_cmdlet.append('ours')
            cherry_pick_cmdlet.append(commit['fix_hash'])
            return cherry_pick_cmdlet

        cmdlets = await asyncio.gather(*[get_cherry_pick_cmdlet(self, cmt) for cmt in self.backport_commit_list])
        
        await self.task.report_job_log('Applying necessary backport commits')
        for cmdlet in cmdlets:
            if not isinstance(cmdlet, list):
                continue
            # in order;
            proc = await asp.create_subprocess_exec(
                'git', *cmdlet, cwd=self.checkout_path,
                stdin=asp.DEVNULL, stdout=asp.DEVNULL, stderr=asp.DEVNULL
            )
            await proc.wait()
        await self.task.report_job_log('Backport commits applied')

    async def apply_patch(self, patch: str):
        if patch == '':
            return True
        proc = await asp.create_subprocess_exec(
            "git",
            "apply",
            stdin=asp.PIPE,
            cwd=self.checkout_path
        )
        await proc.communicate(patch.encode('utf-8'))
        return (await proc.wait()) == 0

    async def ensure_reproducible(self):
        gcc_plugin_path = os.path.join(self.checkout_path, 'scripts', 'gcc-plugins')
        if await run_async(os.path.exists, gcc_plugin_path):
            async with aiofiles.open(os.path.join(gcc_plugin_path, 'randomize_layout_seed.h'), 'w') as fp:
                await fp.write(KERNEL_SEED)

        certs_path = os.path.join(self.checkout_path, 'certs')
        if await run_async(os.path.exists, certs_path):
            async with aiofiles.open(os.path.join(certs_path, 'signing_key.pem'), 'w') as fp:
                await fp.write(KERNEL_MODULE_SIGNING_KEY)
