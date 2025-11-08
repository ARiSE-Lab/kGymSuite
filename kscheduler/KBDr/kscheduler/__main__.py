# __main__.py
import sys, os
from .main import SchedulerApplication, SchedulerConfig

if __name__ == '__main__':
    if len(sys.argv) == 2:
        config_path = sys.argv[1]
    else:
        config_path = os.environ['KBDR_SCHEDULER_CONFIG']
    with open(config_path) as fp:
        app = SchedulerApplication(SchedulerConfig.model_validate_json(
            fp.read()
        ))
    app.main()
