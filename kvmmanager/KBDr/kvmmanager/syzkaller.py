# syzkaller.py
import asyncio.subprocess as asp
from KBDr.kcore import JobExceptionError

async def prepare_syzkaller(syzkaller_path: str, checkout_name: str, rollback: bool, latest_tag: str='ca620dd8f97f5b3a9134b687b5584203019518fb') -> str:
    # not necessary to rollback if it's already preparing ca620dd8f97f5b3a9134b687b5584203019518fb;
    rollback = rollback and (checkout_name != latest_tag)

    # make clean;
    proc = await asp.create_subprocess_exec(
        'git', 'clean', '-fxd', stdin=asp.DEVNULL, stderr=asp.DEVNULL,
        stdout=asp.DEVNULL, cwd=syzkaller_path
    )
    code = await proc.wait()
    if code != 0:
        raise JobExceptionError('kvmmanager.SyzkallerBuildError', 'Failed to make clean the syzkaller folder')
    # git fetch --all;
    proc = await asp.create_subprocess_exec(
        'git', 'fetch', '--all', stdin=asp.DEVNULL, stderr=asp.DEVNULL,
        stdout=asp.DEVNULL, cwd=syzkaller_path
    )
    code = await proc.wait()
    if code != 0:
        raise JobExceptionError('kvmmanager.SyzkallerBuildError', f'Failed to fetch the latest syzkaller')
    # git pull;
    org = 'origin'
    if latest_tag == 'master':
        org = 'upstream'
    proc = await asp.create_subprocess_exec(
        'git', 'pull', org, latest_tag, stdin=asp.DEVNULL, stderr=asp.DEVNULL,
        stdout=asp.DEVNULL, cwd=syzkaller_path
    )
    code = await proc.wait()
    if code != 0:
        raise JobExceptionError('kvmmanager.SyzkallerBuildError', f'Failed to pull the latest syzkaller at {latest_tag}')
    # git checkout {checkout_name};
    proc = await asp.create_subprocess_exec(
        'git', 'checkout', checkout_name, stdin=asp.DEVNULL, stderr=asp.DEVNULL,
        stdout=asp.DEVNULL, cwd=syzkaller_path
    )
    code = await proc.wait()
    if code != 0:
        raise JobExceptionError('kvmmanager.SyzkallerBuildError', f'Failed to checkout syzkaller:{checkout_name}')
    # make target;
    proc = await asp.create_subprocess_exec(
        'make', 'target', '-j8', stdin=asp.DEVNULL, stderr=asp.DEVNULL,
        stdout=asp.DEVNULL, cwd=syzkaller_path
    )
    code = await proc.wait()
    if code == 0:
        proc = await asp.create_subprocess_exec(
            'git', 'rev-parse', 'HEAD', stdin=asp.DEVNULL, stderr=asp.DEVNULL,
            stdout=asp.PIPE, cwd=syzkaller_path
        )
        commit_id, _ = await proc.communicate()
        return commit_id.decode('utf-8').strip()
    if not rollback:
        raise JobExceptionError('kvmmanager.SyzkallerBuildError', f'Failed to build syzkaller:{checkout_name}')
    # rollback;
    return await prepare_syzkaller(syzkaller_path, latest_tag, False, latest_tag)
