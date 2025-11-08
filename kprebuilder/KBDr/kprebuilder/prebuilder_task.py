# build_task.py
import os, aiofiles, json, asyncio
import asyncio.subprocess as asp
from unidiff import PatchSet

from KBDr.kcore import TaskBase, run_async, JobExceptionError
from KBDr.kclient_models.kprebuilder import *

from .checkout_manager import CheckoutManager
from .utils import *
from .analyze_binary import compare_binaries_subutil

class PrebuildTask(TaskBase):

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
            raise JobExceptionError('kprebuilder.FailedUntarError', f'Failed to untar the {KCACHE_FILENAME}')

        # delete the kcache.ztd;
        await run_async(os.remove, kcache_local_path)
        return checkout_path

    async def on_task(self):
        self.argument = kPreBuilderArgument.model_validate(self.argument.model_dump())
        checkout_path = await self.pull_from_kcache(self.argument.cacheKey)
        async with aiofiles.open(os.path.join(checkout_path, 'kcache.json')) as fp:
            kcache_cfg = json.loads(await fp.read())

        make_args = [
            'ARCH=' + {'amd64': 'x86_64', '386': 'i386'}[kcache_cfg["kernel-arch"]],
            f'CC={kcache_cfg["compiler"]}', f'LD={kcache_cfg["linker"]}'
        ]

        checkout_mgr = CheckoutManager(checkout_path)
        ret: List[PatchResult] = []

        for i, patch in enumerate(self.argument['patches']):
            patch_set = PatchSet(patch)

            if not (await checkout_mgr.apply_patch(patch)):
                await self.report_job_log(f'Unsuccessful patch application: {i}')
                ret.append(PatchResult(
                    status=PatchResultStatus.patchUnapplicable,
                    modifiedFiles=[]
                ))
                # reverse back;
                if not (await checkout_mgr.apply_reverse_patch(patch)):
                    raise JobExceptionError('kprebuilder.PatchReverseFailed', 'Reverse patch unapplicable')
                continue
            else:
                await self.report_job_log(f'Successful patch application: {i}')
            await checkout_mgr.ensure_reproducible()

            # pull compile command;
            target_objects = []
            for patched_file in patch_set:
                fname = patched_file.path
                if fname[-2:] == '.c':
                    target_objects.append(fname[:-2] + '.o')
                else:
                    await self.report_job_log(f'Neglecting file {fname} in patch {i}')
            
            proc = await asp.create_subprocess_exec(
                'make', *make_args,
                '-j4', 'KCFLAGS="-fno-inline"',
                *target_objects,
                cwd=checkout_path,
                stdin=asp.DEVNULL,
                stdout=asp.DEVNULL,
                stderr=asp.DEVNULL
            )
            code = await proc.wait()

            if code != 0:
                ret.append({ 'patch-status': 'compilation-error', 'modified-files': [] })
                if not (await checkout_mgr.apply_reverse_patch(patch)):
                    raise JobExceptionError('Reverse patch unapplicable')
                continue

            patch_ret = { 'patch-status': 'success' }

            async def _mv_target_object(target_object: str):
                proc = await asp.create_subprocess_exec('mv', target_object, target_object[:-2] + '_new.o', cwd=checkout_path)
                await proc.wait()
            await asyncio.gather(*list(map(_mv_target_object, target_objects)))

            if not (await checkout_mgr.apply_reverse_patch(patch)):
                raise JobExceptionError('Reverse patch unapplicable')

            proc = await asp.create_subprocess_exec(
                'make', *make_args, '-j4',
                'KCFLAGS="-fno-inline"',
                *target_objects,
                cwd=checkout_path,
                stdin=asp.DEVNULL,
                stdout=asp.DEVNULL,
                stderr=asp.DEVNULL
            )
            await proc.wait()

            async def _compare_binary(target_object: str) -> dict:
                modified_functions = await compare_binaries_subutil(
                    os.path.join(checkout_path, target_object), 
                    os.path.join(checkout_path, target_object[:-2] + '_new.o'), 
                    target_object[:-2] + '.c'
                )
                proc = await asp.create_subprocess_exec('rm', target_object[:-2] + '_new.o', cwd=checkout_path)
                await proc.wait()
                return {
                    'filename': target_object[:-2] + '.c',
                    'modified-functions': modified_functions
                }

            patch_ret['modified-files'] = await asyncio.gather(*list(map(_compare_binary, target_objects)))

            ret.append(patch_ret)

        return ret
