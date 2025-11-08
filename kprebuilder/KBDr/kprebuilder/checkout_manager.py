import os, aiofiles
import asyncio.subprocess as asp
from .utils import KERNEL_SEED, KERNEL_MODULE_SIGNING_KEY
from KBDr.kcore import run_async

class CheckoutManager:
    
    def __init__(self,  checkout_path: str):
        self.checkout_path = checkout_path

    async def apply_patch(self, patch: str):
        proc = await asp.create_subprocess_exec(
            "patch",
            "-p1",
            "--forward",
            "-r",
            "-",
            stdin=asp.PIPE,
            cwd=self.checkout_path
        )
        await proc.communicate(patch.encode('utf-8'))
        return (await proc.wait()) == 0

    async def apply_reverse_patch(self, patch: str):
        proc = await asp.create_subprocess_exec(
            "patch",
            "-p1",
            "--forward",
            "-r",
            "-",
            "-R",
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
