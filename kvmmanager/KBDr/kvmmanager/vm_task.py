# vm_task.py
import os, aiofiles, json, signal
import asyncio.subprocess as asp
from .utils import *
from functools import reduce

from KBDr.kcore import TaskBase, run_async, JobExceptionError
from KBDr.kclient_models.kvmmanager import *
from KBDr.kclient_models.kbuilder import kBuilderResult

class VMTask(TaskBase):

    pending_result: kVMManagerResult | None=None
    argument: kVMManagerArgument | None=None

    async def prepare_resources(self):
        self.vm_provider, self.vm_type = self.argument.machineType.split(':', maxsplit=1)

        if isinstance(self.argument.image, int):
            wid: int = self.argument.image

            if wid < 0 or wid >= len(self.job_ctx.jobWorkers):
                raise JobExceptionError(
                    'kvmmanager.InvalidArgumentError',
                    'imageAtBuilder: out of bound'
                )
            if self.job_ctx.jobWorkers[wid].workerType != 'kbuilder':
                raise JobExceptionError(
                    'kvmmanager.InvalidArgumentError',
                    'imageAtBuilder: not kbuilder'
                )
            kbuilder_result: kBuilderResult = kBuilderResult.model_validate(
                self.job_ctx.jobWorkers[wid].workerResult.model_dump()
            )
            vmlinux_key = kbuilder_result.vmlinux.key
            self.vm_image = kbuilder_result.vmImage
            arch = kbuilder_result.kernelArch
        elif isinstance(self.argument.image, Image):
            vmlinux_key = self.argument.image.vmlinux.key
            self.vm_image = self.argument.image.vmImage
            arch = self.argument.image.arch
        else:
            raise JobExceptionError('kvmmanager.InvalidImageError', 'No image provided')
        # get vmlinux;
        self.vmlinux_path = os.path.join(self.cwd, 'vmlinux')
        await self.storage_backend.download_resource(vmlinux_key, self.vmlinux_path)
        await self.report_job_log('Pulled vmlinux')
        self.arch = arch

    async def prepare_syzkaller(self, syzkaller_checkout: str, rollback: bool, latest_tag: str):
        from .syzkaller import prepare_syzkaller
        self.pending_result.finalSyzkallerCheckout = await prepare_syzkaller(
            self.syzkaller_path, syzkaller_checkout, rollback, latest_tag
        )
        self.syz_crush_cfg['syzkaller'] = self.syzkaller_path

    async def prepare_reproducer(self):
        self.restart_time = self.argument.reproducer.restartTime
        self.ninstance = self.argument.reproducer.nInstance
        repro_fname = {
            'log': 'execution.log',
            'c': 'creprog.c'
        }[self.argument.reproducer.reproducerType]
        self.reproducer_path = os.path.join(self.cwd, repro_fname)
        async with aiofiles.open(self.reproducer_path, 'w') as fp:
            await fp.write(self.argument.reproducer.reproducerText)
        await self.prepare_syzkaller(
            self.argument.reproducer.syzkallerCheckout,
            self.argument.reproducer.syzkallerCheckoutRollback,
            self.argument.reproducer.syzkallerLatestTag
        )

    async def prepare_gce(self):
        if self._worker.system_config.storage.providerType != 'gcs':
            raise JobExceptionError('kvmmanager.IncompatibleConfigError', 'GCE machine needs to work with image on GCP bucket')
        from .gcp import prepare_gce_image
        self.syz_crush_cfg['vm'] = {
            'count': self.ninstance,
            'machine_type': self.vm_type
        }
        await prepare_gce_image(self, self.vm_image.storageUri)
        await self.report_job_log('GCE image prepared')

    async def prepare_qemu(self):
        self.vm_image_path = os.path.join(self.cwd, 'image.tar.gz')
        await self.storage_backend.download_resource(self.vm_image.key, self.vm_image_path)
        # decompress and set image;
        proc = await asp.create_subprocess_exec(
            'tar', 'xvf', 'image.tar.gz',
            cwd=self.cwd, stdout=asp.DEVNULL,
            stderr=asp.DEVNULL, stdin=asp.DEVNULL
        )
        code = await proc.wait()
        if code != 0:
            raise JobExceptionError('kvmmanager.ImageDecompressionError', 'Failed to decompress')
        cpu, mem = self.vm_type.split('-')
        cpu, mem = int(cpu), int(mem)
        self.syz_crush_cfg['vm'] = {
            'count': self.ninstance,
            'cpu': cpu,
            'mem': mem
        }
        self.syz_crush_cfg['image'] = './disk.raw'
        await self.report_job_log('QEMU image prepared')

    async def on_clean(self):
        # shutdown syz-crush;
        if self.crush_proc:
            self.crush_proc.send_signal(signal.SIGINT)
            await self.report_job_log('Sent SIGINT to syz-crush for job cancellation')
            await self.crush_proc.wait()
        # clean up image;
        if self.image_cleanup_handler:
            await self.image_cleanup_handler(self)

    async def collect_crashes(self):
        crash_dir = os.path.join(self.cwd, 'crashes')
        crashes: list[Crash] = []

        if not await run_async(os.path.exists, crash_dir):
            return crashes
        crash_hashes = await run_async(os.listdir, crash_dir)

        for crash_idx, crash_hash in enumerate(crash_hashes):
            crash_incidents = list[CrashIncident]()
            hash_dir = os.path.join(crash_dir, crash_hash)
            async with aiofiles.open(os.path.join(hash_dir, 'description'), 'r', encoding='utf-8') as fp:
                crash_description = await fp.read()
            crash_description = crash_description.strip()
            crash_files = await run_async(os.listdir, hash_dir)
            max_id = 0
            while max_id <= self.argument.reproducer.nInstance:
                log_max_id = f'log{max_id}'
                if log_max_id in crash_files:
                    max_id += 1
                else:
                    break
            # [0, max_id);
            for nid in range(0, max_id):
                incident = CrashIncident()
                log_file = os.path.join(hash_dir, f'log{nid}')
                report_file = os.path.join(hash_dir, f'report{nid}')

                if f'log{nid}' in crash_files:
                    incident.log = await self.submit_resource(f'{crash_idx}/log{nid}', log_file)
                if f'report{nid}' in crash_files:
                    incident.report = await self.submit_resource(f'{crash_idx}/report{nid}', report_file)

                crash_incidents.append(incident)

            crashes.append(Crash(
                crashId=crash_idx,
                title=crash_description,
                crashType='special' if crash_description in SPECIAL_CRASHES else 'crash',
                incidents=crash_incidents
            ))
        return crashes

    async def collect_image_ability(self):
        failed_to_setup_cnt = 0
        async with aiofiles.open(self.syz_crush_log_path, 'r') as fp:
            while ln := await fp.readline():
                if 'failed to set up instance' in ln:
                    failed_to_setup_cnt += 1
        self.pending_result.imageAbility = 'normal'
        if len(self.crashes) == 0:
            # no crash;
            self.pending_result.imageAbility = 'normal'
        elif failed_to_setup_cnt == self.ninstance:
            # all died;
            self.pending_result.imageAbility = 'error'
        elif len(self.crashes) == self.ninstance - failed_to_setup_cnt:
            # living machines all crashed;
            if reduce(lambda a, b: a and b, map(lambda x: x.crashType == 'special', self.crashes)):
                self.pending_result.imageAbility = 'warning'
            else:
                # at least a normal crash;
                self.pending_result.imageAbility = 'normal'
        else:
            # there's a dp didn't crash;
            self.pending_result.imageAbility = 'normal'

    async def collect_result(self) -> List[Crash]:
        self.crashes = await self.collect_crashes()
        await self.collect_image_ability()
        return self.crashes

    async def on_task(self) -> kVMManagerResult:
        self.argument = kVMManagerArgument.model_validate(self.argument.model_dump())
        self.pending_result = kVMManagerResult()
        self.crush_proc = None
        self.syzkaller_path = os.environ['KVMMANAGER_SYZKALLER_PATH']
        self.image_cleanup_handler = None

        await self.prepare_resources()

        self.syz_crush_cfg = {
            'name': f'linux-gce-{self._worker.worker_hostname}',
            'target': f'linux/{self.arch}',
            'workdir': self.cwd,
            'syzkaller': '',
            'http': ':10000',
            'ssh_user': 'root',
            'type': self.vm_provider,
            'kernel_obj': self.cwd
        }

        await self.prepare_reproducer()

        async def _no_matching_vm_provider():
            raise JobExceptionError('kvmmanager.InvalidVMProviderError', f'Unsupported VM provider \'{self.vm_provider}\'')

        await ({
            'gce': self.prepare_gce,
            'qemu': self.prepare_qemu
        }.get(self.vm_provider, _no_matching_vm_provider))()

        self.syz_crush_cfg_path = os.path.join(self.cwd, 'crush.cfg')
        async with aiofiles.open(self.syz_crush_cfg_path, 'w') as fp:
            await fp.write(json.dumps(self.syz_crush_cfg))
        self.syz_crush_log_path = os.path.join(self.cwd, 'syz-crush.log')

        await self.report_job_log('Invoking syz-crush')

        # run syz_crush;
        self.crush_proc = await asp.create_subprocess_exec(
            '/usr/local/bin/syz-crush',
            '-config', self.syz_crush_cfg_path,
            '-restart_time', self.restart_time,
            '-infinite=false',
            self.reproducer_path, cwd=self.cwd,
            stdout=await run_async(open, self.syz_crush_log_path, 'w', encoding='utf-8'),
            stderr=asp.STDOUT,
            stdin=asp.DEVNULL
        )
        await self.crush_proc.wait()
        self.crush_proc = None

        await self.report_job_log('syz-crush finished execution')
        self.pending_result.crushLog = await self.submit_resource('syz-crush.log', self.syz_crush_log_path)
        self.pending_result.crashes = await self.collect_result()

        return self.pending_result
