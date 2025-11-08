# __main__.py
import os
from .prebuilder_task import PrebuildTask
from KBDr.kcore import Worker

if __name__ == '__main__':
    ctx = Worker(
        os.environ['KGYM_MQ_CONN_URL'],
        'kprebuilder',
        PrebuildTask
    )
    ctx.run()
