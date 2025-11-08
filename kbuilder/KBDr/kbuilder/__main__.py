# __main__.py
import os
from .build_task import kBuilderTask
from KBDr.kcore import Worker

if __name__ == '__main__':
    worker = Worker(
        os.environ['KGYM_MQ_CONN_URL'],
        'kbuilder',
        kBuilderTask
    )
    worker.run()
