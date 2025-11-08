import os
from .vm_task import VMTask
from KBDr.kcore import Worker

if __name__ == '__main__':
    worker = Worker(
        os.environ['KGYM_MQ_CONN_URL'],
        'kvmmanager',
        VMTask
    )
    worker.run()
