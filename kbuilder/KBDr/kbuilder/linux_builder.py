# linux_builder.py
import os, shutil, fcntl, struct, ctypes, asyncio
import asyncio.subprocess as asp
from KBDr.kcore import run_async, JobExceptionError, TaskBase
from KBDr.kclient_models.kbuilder import *

def create_loop_info64(
    lo_device: int,
    lo_inode: int,
    lo_rdevice: int,
    lo_offset: int,
    lo_sizelimit: int,
    lo_number: int,
    lo_encrypt_type: int,
    lo_encrypt_key_size: int,
    lo_flags: int,
    lo_file_name: str,
    lo_crypt_name: str,
    lo_encrypt_key: str,
    lo_init: list[int]
):
    """
    struct loop_info64 {
        uint64_t lo_device;           /* ioctl r/o */
        uint64_t lo_inode;            /* ioctl r/o */
        uint64_t lo_rdevice;          /* ioctl r/o */
        uint64_t lo_offset;
        uint64_t lo_sizelimit;  /* bytes, 0 == max available */
        uint32_t lo_number;           /* ioctl r/o */
        uint32_t lo_encrypt_type;
        uint32_t lo_encrypt_key_size; /* ioctl w/o */
        uint32_t lo_flags; i          /* ioctl r/w (r/o before
                                        Linux 2.6.25) */
        uint8_t  lo_file_name[LO_NAME_SIZE];
        uint8_t  lo_crypt_name[LO_NAME_SIZE];
        uint8_t  lo_encrypt_key[LO_KEY_SIZE]; /* ioctl w/o */
        uint64_t lo_init[2];
    };
    """
    LOOP_INFO64_FMT = 'QQQQQIIII64s64s32sQQ'
    return struct.pack(
        LOOP_INFO64_FMT,
        lo_device,
        lo_inode,
        lo_rdevice,
        lo_offset,
        lo_sizelimit,
        lo_number,
        lo_encrypt_type,
        lo_encrypt_key_size,
        lo_flags,
        lo_file_name.encode('utf-8') + b'\0',
        lo_crypt_name.encode('utf-8') + b'\0',
        lo_encrypt_key.encode('utf-8') + b'\0',
        lo_init[0],
        lo_init[1]
    )

libc = ctypes.CDLL(None, use_errno=True)
libc.mount.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p)
libc.umount.argtypes = (ctypes.c_char_p, )

def mount(source: str, target: str, fs: str, options: str=''):
    return libc.mount(source.encode(), target.encode(), fs.encode(), 0, options.encode())

def umount(target: str):
    return libc.umount(target.encode())

class LinuxBuilder:
    
    def __init__(
        self,
        build_task: TaskBase,
        checkout_path: str,
        max_workers: int,
        arch: str,
        compiler: str,
        linker: str,
        userspace_image_path: str
    ):
        self.build_task = build_task
        self.checkout_path = checkout_path
        self.make_arguments = [
            '-j' + str(max_workers),
            'ARCH=' + {'amd64': 'x86_64', '386': 'i386'}[arch],
            'CC=' + compiler,
            'LD=' + linker
        ]
        if (compiler, linker) == ('clang', 'ld.lld'):
            self.make_arguments.append('LLVM=1')
        self.arch = arch
        self.userspace_image_path = userspace_image_path
        self.mount_point = ''
        self.compressed_image_path = ''

    async def make_kernel_config(self):
        proc = await asp.create_subprocess_exec(
            *(['make', 'oldconfig'] + self.make_arguments),
            cwd=self.checkout_path,
            stdin=asp.DEVNULL, stdout=asp.DEVNULL, stderr=asp.DEVNULL
        )
        if (await proc.wait()) != 0:
            raise JobExceptionError(
                'kbuilder.KernelConfigError',
                'Unable to `make oldconfig`'
            )
        final_config_path = os.path.join(self.checkout_path, '.config')
        self.build_task.pending_result.kernelConfig = await self.build_task.submit_resource(
            'kconfig', final_config_path
        )

    async def make_kernel(self):
        linux_builder_stdout_path = os.path.join(self.checkout_path, 'LinuxBuilder.log')
        linux_builder_stderr_path = os.path.join(self.checkout_path, 'LinuxBuilder.err.log')

        stdout_fp = await run_async(open, linux_builder_stdout_path, 'w')
        stderr_fp = await run_async(open, linux_builder_stderr_path, 'w')

        proc = await asp.create_subprocess_exec(
            *(['make'] + self.make_arguments),
            cwd=self.checkout_path,
            stdin=asp.DEVNULL,
            stdout=stdout_fp,
            stderr=stderr_fp
        )
        
        # sanity check #1;
        code = await proc.wait()

        if not stdout_fp.closed:
            await run_async(stdout_fp.close)
        if not stderr_fp.closed:
            await run_async(stderr_fp.close)

        # submit logs;
        self.build_task.pending_result.kBuilderStdout = await self.build_task.submit_resource(
            'LinuxBuilder.log', linux_builder_stdout_path
        )
        self.build_task.pending_result.kBuilderStderr = await self.build_task.submit_resource(
            'LinuxBuilder.err.log', linux_builder_stderr_path
        )

        if code != 0:
            raise JobExceptionError(
                'kbuilder.KernelBuildError',
                'Unable to build the kernel'
            )

        # sanity check #2;
        compressed_image_path = {
            'amd64': 'arch/x86/boot/bzImage',
            '386': 'arch/x86/boot/bzImage'
        }.get(self.arch, '')
        if compressed_image_path == '':
            raise JobExceptionError(
                'kbuilder.KernelBuildError',
                f'Unable to find the compressed image for arch \"{self.arch}\"'
            )

        # submit deliverables;
        compressed_image_path = os.path.join(self.checkout_path, compressed_image_path)
        self.build_task.pending_result.kernelImage = await self.build_task.submit_resource(
            'bzImage', compressed_image_path
        )
        vmlinux_image_path = os.path.join(self.checkout_path, 'vmlinux')
        self.build_task.pending_result.vmlinux = await self.build_task.submit_resource(
            'vmlinux', vmlinux_image_path
        )

        self.compressed_image_path = compressed_image_path

    LOOP_CTL_GET_FREE = 0x4c82
    LOOP_SET_FD = 0x4c00
    LO_FLAGS_PARTSCAN = 0x8
    LOOP_CLR_FD = 0x4c01
    LOOP_SET_STATUS64 = 0x4c04
    
    def setup_userspace_image_loop_device(self) -> str:
        # https://www.man7.org/linux/man-pages/man4/loop.4.html
        # open image;
        self.userspace_image_fd = os.open(self.userspace_image_path, os.O_RDWR, 0)
        if self.userspace_image_fd == -1:
            raise JobExceptionError(
                'kbuilder.ImageBuildError',
                'Failed to open userspace image'
            )
        # ask for a free loopback device;
        loopctl_fd = os.open('/dev/loop-control', os.O_RDWR, 0)
        if loopctl_fd == -1:
            os.close(self.userspace_image_fd)
            raise JobExceptionError(
                'kbuilder.ImageBuildError',
                'Failed to open loop-control device'
            )
        loop_index = fcntl.ioctl(loopctl_fd, LinuxBuilder.LOOP_CTL_GET_FREE)
        os.close(loopctl_fd)
        # open loopback device;
        self.loopdev_path = f'/dev/loop{loop_index}'
        self.loopdev_fd = os.open(self.loopdev_path, os.O_RDWR, 0)
        if self.loopdev_fd == -1:
            os.close(self.userspace_image_fd)
            raise JobExceptionError(
                'kbuilder.ImageBuildError',
                'Failed to open the loopback device'
            )
        # link the image;
        fcntl.ioctl(self.loopdev_fd, LinuxBuilder.LOOP_SET_FD, self.userspace_image_fd)
        # enable partscan;
        loop_info64 = create_loop_info64(
            0, 0, 0, 0, 0, 0, 0, 0,
            LinuxBuilder.LO_FLAGS_PARTSCAN, self.userspace_image_path,
            '', '', [0, 0]
        )
        fcntl.ioctl(self.loopdev_fd, LinuxBuilder.LOOP_SET_STATUS64, loop_info64)

    def try_mount_userspace_image(self, fs_type: str) -> str | None:
        mount_point = '/tmp/kbuilder-userspace-mount-point'
        os.makedirs(mount_point, exist_ok=True)
        ret = mount(
            self.loopdev_path + 'p1',
            mount_point,
            fs_type
        )
        if ret == 0:
            self.mount_point = mount_point
            return mount_point
        else:
            return None
    
    def close_userspace_image(self):
        if self.loopdev_fd >= 0:
            fcntl.ioctl(self.loopdev_fd, LinuxBuilder.LOOP_CLR_FD)
            os.close(self.loopdev_fd)
        if self.userspace_image_fd >= 0:
            os.close(self.userspace_image_fd)
        if self.mount_point != '':
            umount(self.mount_point)
    
    async def make_disk_image(self, kernel_image_path: str):
        await run_async(self.setup_userspace_image_loop_device)
        valid = False
        for fs_type in ['ext4', 'vfat']:
            if isinstance(await run_async(self.try_mount_userspace_image, fs_type), str):
                valid = True
                break
        
        if not valid:
            await run_async(self.close_userspace_image)
            raise JobExceptionError(
                'kbuilder.ImageBuildError',
                'Failed to mount userspace image'
            )

        # kernel;
        kernel_embedded = False
        for image_name in ["boot/vmlinuz", "boot/bzImage", "vmlinuz", "bzImage", "Image.gz"]:
            target_place = os.path.join(self.mount_point, image_name)
            if await run_async(os.path.exists, target_place):
                await run_async(shutil.copy, kernel_image_path, target_place)
                kernel_embedded = True
                break
        if not kernel_embedded:
            await run_async(self.close_userspace_image)
            raise JobExceptionError(
                'kbuilder.ImageBuildError',
                'Failed to embed kernel image into userspace image'
            )

        await run_async(self.close_userspace_image)

        # compression;
        userspace_image_dir = os.path.dirname(self.userspace_image_path)
        renamed_image_tar_gz = os.path.join(userspace_image_dir, 'image.tar.gz')

        ret = await ((await asp.create_subprocess_exec(
            'tar', '-c', '--use-compress-program=pigz',
            '-f', 'image.tar.gz', 'disk.raw',
            cwd=userspace_image_dir,
            stdout=asp.DEVNULL,
            stderr=asp.DEVNULL)).wait())
        if ret != 0:
            raise JobExceptionError(
                'kbuilder.ImageBuildError',
                'Failed to compress disk.raw'
            )
        
        # submit VM image;
        self.build_task.pending_result.vmImage = await self.build_task.submit_resource('image.tar.gz', renamed_image_tar_gz)

    async def make_compile_commands(self):
        script_path = [
            os.path.join(self.checkout_path, 'scripts/clang-tools/gen_compile_commands.py'),
            os.path.join(self.checkout_path, 'scripts/gen_compile_commands.py')
        ]
        for p in script_path:
            full_path = os.path.join(self.checkout_path, p)
            if not await run_async(os.path.exists, full_path):
                continue
            proc = await asp.create_subprocess_exec(
                'python3', p, cwd=self.checkout_path,
                stdin=asp.DEVNULL, stdout=asp.DEVNULL, stderr=asp.DEVNULL
            )
            code = await proc.wait()
            if code == 0:
                compile_commands_path = os.path.join(self.checkout_path, 'compile_commands.json')
                self.build_task.pending_result.kernelCompileCommands = await self.build_task.submit_resource('compile_commands.json', compile_commands_path)
            else:
                return

    async def make_cscope(self) :
        """ Creates the cscope database. We only need to do this, so that 
        we can store the cscope.files list of filenames. """
        if self.arch not in ["amd64", "386"] :
            raise JobExceptionError('kbuilder.CscopeBuildError', f'Unable to build cscope for arch \"{self.arch}\"')

        proc = await asp.create_subprocess_exec(*(["make", "ARCH=x86", "COMPILED_SOURCE=1", "cscope"]),
            cwd=self.checkout_path,
            stdin=asp.DEVNULL, 
            stdout=await run_async(open, os.path.join(self.build_task.cwd, 'LinuxCscope.log'), 'w'), 
            stderr=asp.STDOUT
        )

        if (await proc.wait()) != 0:
            raise JobExceptionError('kbuilder.CscopeBuildError', 'Unable to build cscope')

        cscope_files = os.path.join(self.checkout_path, "cscope.files")
        self.build_task.pending_result.cscopeFiles = await self.build_task.submit_resource("cscope.files", cscope_files)
        cscope_out = os.path.join(self.checkout_path, "cscope.out")
        self.build_task.pending_result.cscopeOut = await self.build_task.submit_resource("cscope.out", cscope_out)
        cscope_out_in = os.path.join(self.checkout_path, "cscope.out.in")
        self.build_task.pending_result.cscopeOutIn = await self.build_task.submit_resource("cscope.out.in", cscope_out_in)
        cscope_out_po = os.path.join(self.checkout_path, "cscope.out.po")
        self.build_task.pending_result.cscopeOutPo = await self.build_task.submit_resource("cscope.out.po", cscope_out_po)

    async def make(self):
        await self.make_kernel_config()
        await self.make_kernel()
        image_creation_task = asyncio.create_task(self.make_disk_image(self.compressed_image_path))
        compile_commands_creation_task = asyncio.create_task(self.make_compile_commands())
        await image_creation_task
        await compile_commands_creation_task
        await self.make_cscope()
