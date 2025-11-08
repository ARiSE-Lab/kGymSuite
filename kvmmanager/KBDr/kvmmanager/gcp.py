# gcp.py
from KBDr.kcore import run_async, JobExceptionError, JobContext
from KBDr.kcore.storage_backends.storage_gcs import GCSStorageProviderConfig
from KBDr.kclient_models.kvmmanager import kVMManagerWorker
from .vm_task import VMTask

from google.cloud.compute import ImagesClient, Image

async def image_cleanup(vm_task: VMTask):
    from google.api_core.exceptions import NotFound
    from google.auth import default

    _, project_id = default()
    image_client = ImagesClient()
    image_name = vm_task.syz_crush_cfg['vm']['gce_image']
    try:
        existing_image = await run_async(image_client.get, image=image_name, project=project_id)
    except NotFound:
        return
    operation = await run_async(image_client.delete, project=project_id, image=image_name)
    deletion_result = await run_async(operation.result, timeout=600)
    if operation.error_code:
        raise JobExceptionError('kvmmanager.GCE.ImageDeletionError', f'GCP Error Code: {operation.error_code}, {operation.error_message}')

async def prepare_gce_image(vm_task: VMTask, vm_image_uri: str):
    from google.api_core.exceptions import NotFound
    from google.auth import default

    _, project_id = default()
    storage_config: GCSStorageProviderConfig = vm_task._worker.system_config.storage

    image_url = vm_image_uri
    image_name = f'{vm_task._worker.system_config.deploymentName}-job-{vm_task.job_id}'

    image_client = ImagesClient()
    try:
        existing_image = await run_async(image_client.get, image=image_name, project=project_id)
    except NotFound:
        existing_image = None
    
    vm_task.image_cleanup_handler = image_cleanup

    if existing_image is not None:
        operation = await run_async(image_client.delete, project=project_id, image=image_name)
        deletion_result = await run_async(operation.result, timeout=600)
        if operation.error_code:
            raise JobExceptionError('kvmmanager.GCE.ImageDeletionError', f'GCP Error Code: {operation.error_code}, {operation.error_message}')

    image = Image()
    image.raw_disk.source = image_url
    image.name = image_name
    operation = image_client.insert(project=project_id, image_resource=image)
    creation_result = await run_async(operation.result, timeout=600)
    if operation.error_code:
        raise JobExceptionError('kvmmanager.GCE.ImageCreationError', f'GCP Error Code: {operation.error_code}, {operation.error_message}')

    vm_task.syz_crush_cfg['vm']['gce_image'] = image_name
