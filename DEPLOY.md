# kGymSuite Deployment Guide

This guide covers deploying kGymSuite in both Google Cloud Platform (GCP) and local environments.

## Table of Contents

- [GCP Deployment](#gcp-deployment)
- [Local Deployment](#local-deployment)
- [Configuration Reference](#configuration-reference)
- [Common Operations](#common-operations)
- [Troubleshooting](#troubleshooting)

## GCP Deployment

### Prerequisites

- Google Cloud Platform project with:
  - Compute Engine VMs provisioned (Debian recommended)
  - Google Artifact Registry repository created
  - Google Cloud Storage bucket created
- VMs configured with appropriate IAM roles for Artifact Registry and GCS access
- `gcloud` CLI configured and authenticated

### Step 1: Create Deployment Configuration

#### 1.1 Create Deployment Directory

Create a new deployment configuration based on the GCP template:

```bash
cd deployment
cp -r gcp example
cd example
```

#### 1.2 Configure config.json

Edit `deployment/example/config.json`:

```json
{
  "deploymentName": "example",
  "allowedOrigins": [
    "https://your-domain.com",
    "http://localhost:3000"
  ],
  "storage": {
    "providerType": "gcs",
    "providerConfig": {
      "bucketName": "your-bucket-name"
    }
  },
  "workerConfigs": {
    "kbuilder": {
      "backportCommits": [
        ...
      ]
    }
  },
  "dbPath": "/root/scheduler-db/scheduler.db",
  "kGymAPIEndpoint": "https://your-api-domain.com",
  "servers": {
    "main": {
      "user": "your-username",
      "hostname": "main.us-central1-c.c.your-project-id.internal"
    },
    "builder": {
      "user": "your-username",
      "hostname": "builder.us-central1-c.c.your-project-id.internal"
    },
    "vmmanager": {
      "user": "your-username",
      "hostname": "vmmanager.us-central1-c.c.your-project-id.internal"
    }
  },
  "mainServer": "main",
  "services": {
    "kmq": ["main"],
    "kscheduler": ["main"],
    "kdashboard": ["main"],
    "kbuilder": ["builder"],
    "kvmmanager": ["vmmanager"]
  }
}
```

**Configuration Notes:**
- `servers`: Maps server names to their configuration
  - `user`: SSH username for the VM
  - `hostname`: GCP internal DNS hostname (format: `<vm-name>.<zone>.c.<project-id>.internal`)
- `mainServer`: The server running core services (kmq, kscheduler, kdashboard)
- `services`: Maps each service to an array of servers where it should run
- `allowedOrigins`: CORS origins allowed to access the API
- `kGymAPIEndpoint`: Public-facing API endpoint URL (optional)

#### 1.3 Configure kgym-runner.env

Edit `deployment/example/kgym-runner.env`:

```bash
KGYM_CONN_URL=amqp://kbdr:ey4lai1the7peeGh@main.us-central1-c.c.your-project-id.internal:5672/?heartbeat=60
```

Replace the hostname with your main server's internal DNS name or IP address.

#### 1.4 Update compose.yml Image Tags

Edit `deployment/example/compose.yml` and update all image tags to use your Artifact Registry:

```yaml
services:
  kmq:
    image: us-docker.pkg.dev/your-project-id/your-repo/kgym-mq:${DEPLOYMENT}
    # ...

  kscheduler:
    image: us-docker.pkg.dev/your-project-id/your-repo/kgym-scheduler:${DEPLOYMENT}
    # ...

  kdashboard:
    image: us-docker.pkg.dev/your-project-id/your-repo/kgym-dashboard:${DEPLOYMENT}
    # ...

  kbuilder:
    image: us-docker.pkg.dev/your-project-id/your-repo/kgym-builder:${DEPLOYMENT}
    # ...

  kvmmanager:
    image: us-docker.pkg.dev/your-project-id/your-repo/kgym-vmmanager:${DEPLOYMENT}
    # ...

  kprebuilder:
    image: us-docker.pkg.dev/your-project-id/your-repo/kgym-prebuilder:${DEPLOYMENT}
    # ...
```

Replace `your-project-id` and `your-repo` with your GCP project ID and Artifact Registry repository name.

### Step 2: Build and Push Images

#### 2.1 Build All Images

From the repository root:

```bash
DEPLOYMENT=example docker compose -f ./deployment/example/compose.yml \
  --project-directory . \
  build
```

#### 2.2 Configure Docker for Artifact Registry

For the machine where you build Docker images:

```bash
gcloud auth configure-docker <GCP Artifact Registry Server, e.g. us-docker.pkg.dev>
```

#### 2.3 Push Images to Artifact Registry

```bash
DEPLOYMENT=example docker compose -f ./deployment/example/compose.yml push
```

### Step 3: Deploy to GCP VMs

#### 3.1 Initial Deployment

Use `kgym.py` to deploy all services to configured servers:

```bash
python kgym.py new-deploy example
python kgym.py config-artifact-reg example <GCP Artifact Registry Server, e.g. us-docker.pkg.dev>
```

This script will:
1. Install Docker on all remote VMs (if not already installed)
2. Copy configuration files to each VM
3. Pull Docker images from Artifact Registry
4. Start services on appropriate servers according to `config.json`

#### 3.2 Verify Deployment

SSH to main server and check services:

```bash
gcloud compute ssh <your-main-vm-name>

# Check running containers
docker ps

# Check logs
docker logs kgym-scheduler
docker logs kgym-dashboard

# Check scheduler API
curl http://localhost:8000/docs
```

Access the dashboard at `http://<main-server-ip>:3000` or configure a load balancer/SSH tunnel.

### Step 4: Upload Base Images to GCS

Download required userspace VM images from HuggingFace: [https://huggingface.co/datasets/chenxi-kalorona-huang/kGym-images](https://huggingface.co/datasets/chenxi-kalorona-huang/kGym-images)

Upload to your GCS bucket:

```bash
gsutil cp buildroot.raw gs://your-bucket-name/userspace-images/
gsutil cp bullseye.raw gs://your-bucket-name/userspace-images/
```

Verify the upload:

```bash
gsutil ls gs://your-bucket-name/userspace-images/
```

## Local Deployment

Local deployment is ideal for development and testing. It uses local filesystem storage and runs all services on a single machine.

### Step 1: Prepare Local Storage

Create local storage structure:

```bash
mkdir -p ./deployment/example/bucket/userspace-images
mkdir -p ./deployment/example/bucket/jobs
```

### Step 2: Upload Base Images to Local Storage

Download required userspace VM images from HuggingFace: [https://huggingface.co/datasets/chenxi-kalorona-huang/kGym-images](https://huggingface.co/datasets/chenxi-kalorona-huang/kGym-images)

Copy to local storage directory:

```bash
cp buildroot.raw ./deployment/example/bucket/userspace-images/
cp bullseye.raw ./deployment/example/bucket/userspace-images/
```

Verify the images are in place:

```bash
ls -lh ./deployment/example/bucket/userspace-images/
```

### Step 3: Configure Environment

Review and customize `deployment/local/config.json` if needed. The default configuration uses:
- Local filesystem storage at `/mnt/bucket`
- Single machine deployment (no remote servers)
- Services accessible on localhost

### Step 4: Build Images

From the repository root, build all services:

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml --project-directory . build
```

### Step 5: Start Services

```bash
# Core services
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml up -d kmq kscheduler kdashboard

# Add workers
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml up -d kbuilder kvmmanager kprebuilder
```

### Step 6: Verify Deployment

Check running services:

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml ps
```

View logs:

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml logs -f kscheduler
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml logs -f kbuilder
```

Access services:
- Dashboard: http://localhost:3000
- API: http://localhost:8000/docs

### Alternative: Using kgym.py for Local Deployment with Multiple Servers

You can also use `kgym.py` for local deployment with remote server configuration:

1. Configure `deployment/local/config.json` with your local server details:

```json
{
  "servers": {
    "localhost": {
      "user": "your-username",
      "hostname": "localhost"
    },
    ...
  },
  "mainServer": "localhost",
  "services": {
    "kmq": ["localhost"],
    "kscheduler": ["localhost"],
    "kdashboard": ["localhost"],
    "kbuilder": ["localhost"],
    "kvmmanager": ["localhost"]
  }
}
```

2. Deploy using kgym.py:

```bash
python kgym.py new-deploy local
```

### Alternative: Using DockerHub or Other Registries

To use a container registry for local deployment:

#### 1. Update compose.yml

Edit `deployment/local/compose.yml` and change image tags:

```yaml
services:
  kscheduler:
    image: yourusername/kgym-scheduler:latest
    # Update all other services similarly
```

#### 2. Build and Push

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml --project-directory . build
docker login
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml push
```

#### 3. Pull and Run on Target Machine

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml pull
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml up -d <services>
```

**Note:** Pre-built images will be available in future releases.

## Configuration Reference

### config.json Structure

```json
{
  "deploymentName": "string",
  "allowedOrigins": ["http://localhost:3000"],
  "storage": {
    "providerType": "local|gcs",
    "providerConfig": {}
  },
  "workerConfigs": {
    "kbuilder": {
      "backportCommits": []
    }
  },
  "dbPath": "/root/scheduler-db/scheduler.db",
  "kGymAPIEndpoint": "https://api-endpoint.com",
  "servers": {},
  "mainServer": "string",
  "services": {}
}
```

### Storage Providers

#### Local Filesystem

```json
{
  "providerType": "local",
  "providerConfig": {
    "root": "/mnt/bucket"
  }
}
```

The local storage directory structure:
```
/mnt/bucket/
├── userspace-images/
│   ├── buildroot.raw
└── jobs/
    └── <job-id>/
        ├── 0_kbuilder/
        │   └── ...
        └── 1_kvmmanager/
            └── ...
```

#### Google Cloud Storage

```json
{
  "providerType": "gcs",
  "providerConfig": {
    "bucketName": "your-bucket-name"
  }
}
```

Requires VM to have appropriate IAM roles or `GOOGLE_APPLICATION_CREDENTIALS` environment variable set.

### Server and Service Configuration

#### servers

Maps logical server names to their connection details:

```json
{
  "servers": {
    "main": {
      "user": "ubuntu",
      "hostname": "main.us-central1-c.c.project-id.internal"
    },
    "builder": {
      "user": "ubuntu",
      "hostname": "builder.us-central1-c.c.project-id.internal"
    }
  }
}
```

- `user`: SSH username for accessing the server
- `hostname`: Internal DNS hostname or IP address

#### services

Maps each service to the servers where it should run:

```json
{
  "services": {
    "kmq": ["main"],
    "kscheduler": ["main"],
    "kdashboard": ["main"],
    "kbuilder": ["builder"],
    "kvmmanager": ["vmmanager"]
  }
}
```

Each service maps to an array of server names. Multiple servers can run the same service for scaling.

### Worker Configurations

#### kbuilder Backport Commits

The `backportCommits` array contains kernel patches to automatically apply for build compatibility:

```json
{
  "workerConfigs": {
    "kbuilder": {
      "backportCommits": [
        {
          "fix_hash": "commit-sha",
          "guilty_hash": "commit-sha-that-broke-it",
          "fix_title": "Description of the fix",
          "force_merge": false
        }
      ]
    }
  }
}
```

See `deployment/gcp/config.json` for the current list of backport commits.

## Common Operations

### Upgrading a Deployment

#### GCP/Remote Deployments

```bash
# Build new images
DEPLOYMENT=example docker compose -f ./deployment/example/compose.yml \
  --project-directory . \
  build

# Push to registry
DEPLOYMENT=example docker compose -f ./deployment/example/compose.yml push

# Rolling upgrade
python kgym.py upgrade example
```

#### Local Deployments

```bash
# Rebuild images
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml --project-directory . build

# Restart services
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml down
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml up -d
```

Or using kgym.py:

```bash
python kgym.py upgrade local
```

### Shutting Down

#### Local Deployment

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml down
```

To also remove volumes:

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml down -v
```

Or using kgym.py:

```bash
python kgym.py down local
```

#### GCP Deployment

```bash
python kgym.py down example
```

This gracefully shuts down all services across all configured servers.

### Viewing Logs

#### Local Deployment

```bash
# All services
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml logs -f

# Specific service
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml logs -f kscheduler
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml logs -f kbuilder

# Last N lines
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml logs --tail=100 kvmmanager
```

#### GCP Deployment

SSH to the relevant server:

```bash
gcloud compute ssh <vm-name>
docker logs -f kgym-scheduler

gcloud compute ssh <builder-vm-name>
docker logs -f kgym-builder
```

### Scaling Workers

#### Local Deployment

Scale using docker compose:

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml up -d --scale kvmmanager=10
```

Or edit `deployment/local/compose.yml`:

```yaml
services:
  kvmmanager:
    # ...
    deploy:
      replicas: 10
```

#### GCP Deployment

Edit service configuration in `config.json` to add more servers:

```json
{
  "servers": {
    "main": { "user": "ubuntu", "hostname": "..." },
    "builder": { "user": "ubuntu", "hostname": "..." },
    "vmmanager-1": { "user": "ubuntu", "hostname": "..." },
    "vmmanager-2": { "user": "ubuntu", "hostname": "..." },
    "vmmanager-3": { "user": "ubuntu", "hostname": "..." }
  },
  "services": {
    "kvmmanager": ["vmmanager-1", "vmmanager-2", "vmmanager-3"]
  }
}
```

Then run `python kgym.py upgrade example`.

## Troubleshooting

### Services Won't Start

Check Docker daemon status:

```bash
sudo systemctl status docker
sudo systemctl start docker
```

Validate compose file:

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml config
```

Check logs for errors:

```bash
DEPLOYMENT=local docker compose -f ./deployment/local/compose.yml logs kscheduler
```

### Workers Not Processing Jobs

1. Verify `kgym-runner.env` has correct RabbitMQ connection URL
2. Verify kmq service is running: `docker ps | grep kmq`
3. Check worker logs for connection errors

### Build Failures (kbuilder)

- Ensure container has privileged mode enabled (required for loop device access)
- Check disk space on build server
- Review build logs in job output

### KVM/QEMU Issues (kvmmanager)

- Verify `/dev/kvm` exists and is accessible: `ls -l /dev/kvm`
- Check CPU supports virtualization: `grep -E 'vmx|svm' /proc/cpuinfo`
- Ensure kvmmanager container has device access in compose.yml

For GCE backend, ensure VMs have nested virtualization enabled.

### Storage Access Issues

**GCS permission errors:**

Verify VM service account has Storage Object Admin role:

```bash
gcloud projects get-iam-policy YOUR_PROJECT_ID
```

**Local storage permission errors:**

Ensure storage directory is writable:

```bash
sudo chown -R $USER:$USER /mnt/bucket
sudo chmod -R 755 /mnt/bucket
```

**Missing userspace images:**

Verify images exist in storage:

```bash
# Local
ls -lh /mnt/bucket/userspace-images/

# GCS
gsutil ls gs://your-bucket-name/userspace-images/
```

### Network Connectivity Issues

**Services can't communicate:**

- Verify all services are on the same Docker network
- For GCP, verify VPC firewall rules allow traffic between VMs
- Check that RabbitMQ port (5672) is accessible between services

**Can't access dashboard:**

- Check kdashboard is running: `docker ps | grep dashboard`
- Verify port 3000 is exposed
- For GCP, use SSH tunnel:

```bash
gcloud compute ssh <main-vm-name> -- -L 3000:localhost:3000
```

Then access at http://localhost:3000

### Artifact Registry Authentication

If image push/pull fails:

```bash
# Reconfigure Docker authentication
gcloud auth configure-docker us-docker.pkg.dev

# Or use service account key
gcloud auth activate-service-account --key-file=key.json
gcloud auth configure-docker us-docker.pkg.dev
```

## Support

- API Documentation: Access `/docs` endpoint on running scheduler (e.g., http://localhost:8000/docs)