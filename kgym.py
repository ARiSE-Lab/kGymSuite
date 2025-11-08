
import os, json, asyncio, functools
import asyncio.subprocess as asp
from concurrent.futures import ThreadPoolExecutor

async def run(prog, *args):
    if prog in ('ssh', 'scp'):
        args = ('-o', 'StrictHostKeyChecking=no', *args)
    proc = await asp.create_subprocess_exec(
        prog, *args, stdin=asp.DEVNULL
    )
    return await proc.wait()

class RemoteDeployment:

    def __init__(self, deployment_name: str):
        self.deployment_name = deployment_name

        self.config_path = os.path.join('./deployment', self.deployment_name, 'config.json')
        self.env_path = os.path.join('./deployment', self.deployment_name, 'kgym-runner.env')
        self.compose_path = os.path.join('./deployment', self.deployment_name, 'compose.yml')
        with open(self.config_path, 'r') as fp:
            self.config = json.load(fp)

        self.deploy_script_path = './deployment/deploy-new.sh'

    async def deploy(self, username: str, hostname: str):
        # deploy-new.sh
        # scp {self.deploy_script_path} {username}@{hostname}:/tmp/deploy-new.sh
        # ssh {username}@{hostname} "chmod +x /tmp/deploy-new.sh && /tmp/deploy-new.sh"
        assert (await run('scp', './deployment/deploy-new.sh', f'{username}@{hostname}:/tmp/deploy-new.sh')) == 0
        assert (await run('ssh', f'{username}@{hostname}', 'chmod +x /tmp/deploy-new.sh && /tmp/deploy-new.sh')) == 0
        await self.update_config(username, hostname)
        print(hostname, 'deployed')

    async def bring_up(self, username: str, hostname: str, services: list[str]):
        # ssh {username}@{hostname} "docker compose pull && docker compose up -d {services}"
        _services = ' '.join(services)
        assert (await run('ssh', f'{username}@{hostname}', f'echo "DEPLOYMENT={self.deployment_name}" > .env && sudo docker compose pull && sudo docker compose up -d {_services}')) == 0
        print(hostname, 'brought up')

    async def update_config(self, username: str, hostname: str):
        # scp ./deployment/{self.deployment_name}/{config.json,kgym-runner.env,compose.yml} {username}@{hostname}:
        assert (await run('scp', f'./deployment/{self.deployment_name}/' + 'config.json', f'{username}@{hostname}:')) == 0
        assert (await run('scp', f'./deployment/{self.deployment_name}/' + 'kgym-runner.env', f'{username}@{hostname}:')) == 0
        assert (await run('scp', f'./deployment/{self.deployment_name}/' + 'compose.yml', f'{username}@{hostname}:')) == 0
        print(hostname, 'config updated')

    async def bring_down(self, username: str, hostname: str):
        # ssh {username}@{hostname} "sudo docker compose down"
        assert (await run('ssh', f'{username}@{hostname}', f'echo "DEPLOYMENT={self.deployment_name}" > .env && sudo docker compose down')) == 0
        print(hostname, 'brought down')

    async def config_ar(self, username: str, hostname: str, server: str):
        assert (await run('ssh', f'{username}@{hostname}', f'yes | sudo gcloud auth configure-docker {server}')) == 0

    async def config_artifact_reg(self, args):
        tasks = []
        for name in self.config['servers']:
            tasks.append(asyncio.create_task(self.config_ar(self.config['servers'][name]['user'], self.config['servers'][name]['hostname'], args.server)))
        await asyncio.wait(tasks)

    async def new_deploy(self, args):
        tasks = []
        for name in self.config['servers']:
            tasks.append(asyncio.create_task(self.deploy(self.config['servers'][name]['user'], self.config['servers'][name]['hostname'])))
        await asyncio.wait(tasks)

    async def down(self, args):
        service_map = {}
        for name in self.config['servers']:
            service_map[name] = list()
        for service in self.config['services']:
            for server in self.config['services'][service]:
                service_map[server].append(service)
        mainServer = self.config['mainServer']

        tasks = []
        for server in service_map:
            if server == mainServer:
                continue
            tasks.append(
                asyncio.create_task(self.bring_down(
                    self.config['servers'][server]['user'],
                    self.config['servers'][server]['hostname']
                ))
            )
        await asyncio.wait(tasks)
        await self.bring_down(
            self.config['servers'][mainServer]['user'],
            self.config['servers'][mainServer]['hostname']
        )

        tasks = []
        for server in service_map:
            tasks.append(
                asyncio.create_task(self.update_config(
                    self.config['servers'][server]['user'],
                    self.config['servers'][server]['hostname']
                ))
            )
        await asyncio.wait(tasks)

    async def upgrade(self, args):
        service_map = {}
        for name in self.config['servers']:
            service_map[name] = list()
        for service in self.config['services']:
            for server in self.config['services'][service]:
                service_map[server].append(service)
        mainServer = self.config['mainServer']

        tasks = []
        for server in service_map:
            if server == mainServer:
                continue
            tasks.append(
                asyncio.create_task(self.bring_down(
                    self.config['servers'][server]['user'],
                    self.config['servers'][server]['hostname']
                ))
            )
        await asyncio.wait(tasks)
        await self.bring_down(
            self.config['servers'][mainServer]['user'],
            self.config['servers'][mainServer]['hostname']
        )

        tasks = []
        for server in service_map:
            tasks.append(
                asyncio.create_task(self.update_config(
                    self.config['servers'][server]['user'],
                    self.config['servers'][server]['hostname']
                ))
            )
        await asyncio.wait(tasks)

        tasks = []
        await self.bring_up(
            self.config['servers'][mainServer]['user'],
            self.config['servers'][mainServer]['hostname'],
            service_map[mainServer]
        )
        for server in service_map:
            if server == mainServer:
                continue
            tasks.append(
                asyncio.create_task(self.bring_up(
                    self.config['servers'][server]['user'],
                    self.config['servers'][server]['hostname'],
                    service_map[server]
                ))
            )
        await asyncio.wait(tasks)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(
        'kgym.py'
    )
    ap.add_argument('deploymentName')
    sp = ap.add_subparsers()

    nd = sp.add_parser('new-deploy')
    nd.set_defaults(func=RemoteDeployment.new_deploy)

    ug = sp.add_parser('upgrade')
    ug.set_defaults(func=RemoteDeployment.upgrade)

    dn = sp.add_parser('down')
    dn.set_defaults(func=RemoteDeployment.down)

    car = sp.add_parser('config-artifact-reg')
    car.add_argument('server')
    car.set_defaults(func=RemoteDeployment.config_artifact_reg)

    args = ap.parse_args()
    rd = RemoteDeployment(args.deploymentName)

    async def main(p):
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=8)
        loop.set_default_executor(executor)
        await p()

    asyncio.run(main(functools.partial(args.func, rd, args)))
