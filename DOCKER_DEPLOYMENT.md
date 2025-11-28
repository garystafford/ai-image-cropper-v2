# Docker Deployment Guide

This guide explains how to deploy the AI Image Cropper application using Docker and Docker Swarm.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 1.29+ (or Docker Compose V2)
- Docker Swarm initialized (for swarm deployment)
- Python 3.12+ (for local development)

## Project Structure

The project includes the following Docker-related files:

- `Dockerfile.backend` - Backend Python/FastAPI application
- `Dockerfile.frontend` - Frontend React/Vite application
- `docker-compose.yml` - Docker Swarm stack configuration
- `nginx-lb.conf` - Nginx load balancer configuration
- `.dockerignore` - Files to exclude from Docker builds

## Quick Start with Docker Compose

### 1. Build the Images

The docker-compose.yml is configured to build for `linux/amd64` (x86_64) platform to support CUDA acceleration.

```bash
docker-compose build
```

**Note for Apple Silicon (ARM64) Macs:**

- Docker Desktop will automatically use emulation to build x86_64 images
- This may be slower than native builds but ensures compatibility with x86_64 deployment servers
- The images will run on x86_64 Linux servers with CUDA support

### 2. Run with Docker Compose (Non-Swarm)

For local development or testing:

```bash
docker-compose up
```

**Note**: For non-Swarm deployment, you need to change the network driver in `docker-compose.yml` from `overlay` to `bridge`.

Access the application:

- **Load Balancer**: <http://localhost:8080> (main entry point)
- **Frontend** (via LB): <http://localhost:8080/>
- **Backend API** (via LB): <http://localhost:8080/api/>
- **Health Check**: <http://localhost:8080/health>

Note: Backend (8000) and Frontend (80) ports are not directly exposed; all traffic goes through the nginx load balancer on port 8080.

## Docker Swarm Deployment

### 1. Initialize Docker Swarm

If not already initialized:

```bash
docker swarm init
```

### 2. Build Images

Build the images before deploying to the swarm (images are built for linux/amd64):

```bash
docker-compose build
```

### 3. Deploy the Stack

```bash
docker stack deploy -c docker-compose.yml image-cropper
```

### 4. Verify Deployment

Check the services:

```bash
docker stack services image-cropper
```

Check individual service status:

```bash
docker service ls
docker service ps image-cropper_backend
docker service ps image-cropper_frontend
docker service ps image-cropper_nginx-lb
```

### 5. View Logs

```bash
# Backend logs
docker service logs -f image-cropper_backend

# Frontend logs
docker service logs -f image-cropper_frontend

# Load balancer logs
docker service logs -f image-cropper_nginx-lb
```

### 6. Scale Services

Scale the backend service:

```bash
docker service scale image-cropper_backend=3
```

Scale the frontend service:

```bash
docker service scale image-cropper_frontend=3
```

### 7. Update Services

To update a service with zero downtime:

```bash
# Rebuild the image
docker-compose build backend

# Update the service
docker service update --image ai-image-cropper-backend:1.0 image-cropper_backend
```

### 8. Remove the Stack

```bash
docker stack rm image-cropper
```

## Service Configuration

### Backend Service

- **Image**: `ai-image-cropper-backend:1.0`
- **Python Version**: 3.12
- **Replicas**: 1 (default, can be scaled up)
- **Port**: 8000 (internal, not exposed)
- **Resources**:
  - CPU: 1.0-4.0 cores
  - Memory: 4-8GB (8GB required for RF-DETR on CPU)
- **Volumes**:
  - uploads → `/app/uploads` (uploaded images)
  - outputs → `/app/outputs` (processed images)
  - cropped_images → `/app/cropped_images` (batch cropped images)
  - models → `/app/backend/models` (cached ML models - YOLO, RF-DETR, etc.)
- **Dependency Management**: Uses `uv` for fast Python package installation
- **PyTorch**: CUDA 12.1 support on Linux (configured via platform markers)
- **Supported Methods**: YOLO, DETR, RT-DETR, RF-DETR, Contour, Saliency, Edge, GrabCut

**⚠️ Performance Note**: RF-DETR requires significant memory (8GB+) and is very slow on CPU (several minutes per image). For CPU-only deployments, use **RT-DETR** or **YOLO** for better performance.

### Frontend Service

- **Image**: `ai-image-cropper-frontend:1.0`
- **Replicas**: 1 (default, can be scaled up)
- **Port**: 80 (internal, not exposed)
- **Resources**:
  - CPU: 0.1-0.5 cores
  - Memory: 128-512MB

### Nginx Load Balancer

- **Replicas**: 1
- **Port**: 8080 (exposed)
- **Resources**:
  - CPU: 0.1-0.25 cores
  - Memory: 128-256MB

## Networking

The services communicate through an overlay network called `app-network`. The load balancer routes:

- `/api/*` → Backend service
- `/*` → Frontend service

## Volumes

Persistent volumes are created for:

- `backend-uploads` - Uploaded images
- `backend-outputs` - Processed images
- `backend-cropped` - Cropped images
- `backend-models` - **Cached ML models** (YOLO, RF-DETR, etc.)

**Model Caching**: The `backend-models` volume persists downloaded ML models across container restarts and updates. This significantly speeds up container startup, as models (especially RF-DETR at ~200MB) are downloaded only once and reused.

## Health Checks

All services include health checks:

- **Backend**: Uses `curl` to check `/health` endpoint every 30s (60s startup grace period)
- **Frontend**: Uses `wget` to check nginx health every 30s (10s startup grace period)
- **Load Balancer**: Built-in nginx health endpoint at `/health`

## Resource Management

Resource limits are configured to prevent service overload:

### Backend

- Limits: 2 CPU cores, 4GB RAM
- Reservations: 0.5 CPU cores, 2GB RAM

### Frontend

- Limits: 0.5 CPU cores, 512MB RAM
- Reservations: 0.1 CPU cores, 128MB RAM

## Deployment Strategies

The stack uses rolling updates with:

- **Update parallelism**: 1 (one service at a time)
- **Update delay**: 10s between updates
- **Update order**: start-first (start new before stopping old)
- **Rollback**: Automatic on failure

## Troubleshooting

### Check Service Status

```bash
docker stack ps image-cropper --no-trunc
```

### Inspect Service Details

```bash
docker service inspect image-cropper_backend
```

### Access Service Container

```bash
# Get container ID
docker ps | grep image-cropper_backend

# Access shell
docker exec -it <container_id> /bin/bash
```

### View Network Details

```bash
docker network inspect image-cropper_app-network
```

### Remove Dangling Resources

```bash
docker system prune -a
```

### RF-DETR Performance Issues and Model Selection

#### Problem: "Error processing image" or Container OOM Kills (Exit Code 137)

If you're experiencing image processing errors or seeing containers repeatedly restart with exit code 137, this is typically an **Out of Memory (OOM)** issue, especially when using RF-DETR on CPU.

**Check for OOM kills:**

```bash
docker service ps image-cropper_backend --no-trunc --format "table {{.ID}}\t{{.CurrentState}}\t{{.Error}}"
```

If you see `"task: non-zero exit (137)"`, the container was killed due to insufficient memory.

**Check Docker Desktop memory allocation:**

```bash
docker info 2>/dev/null | grep -i "total memory"
```

#### Model Performance Comparison (CPU)

| Model   | Size   | Speed           | Memory Usage | Accuracy  | Recommendation     |
| ------- | ------ | --------------- | ------------ | --------- | ------------------ |
| YOLO    | 114MB  | Sub-second      | ~2GB         | Excellent | **Best for speed** |
| RT-DETR | ~200MB | Seconds         | ~3GB         | Excellent | **Best for CPU**   |
| RF-DETR | 1.5GB  | Several minutes | 6-8GB+       | Excellent | **GPU only**       |

#### Recommended Solutions

##### Option 1: Use RT-DETR (Strongly Recommended for CPU)

RT-DETR provides similar accuracy to RF-DETR with much better CPU performance:

1. Access the UI at <http://localhost:8080>
2. Select **RT-DETR** from the "Detection Method" dropdown
3. Process images normally

RT-DETR is already cached in the models volume and works excellently on CPU.

##### Option 2: Use YOLO (Fastest)

For maximum speed on CPU:

1. Select **YOLO** from the dropdown
2. Adjust confidence threshold as needed
3. Excellent accuracy for most use cases

##### Option 3: Increase Docker Desktop Memory (For RF-DETR)

If you must use RF-DETR on CPU:

1. Open Docker Desktop → Settings (⚙️) → Resources → Advanced
2. Increase Memory to at least **12GB** (16GB recommended)
3. Click "Apply & Restart"
4. Wait for Docker to restart
5. Redeploy the stack:

```bash
# Update docker-compose.yml memory limits to match your allocation
# Change line 38: memory: 12G
docker stack deploy -c docker-compose.yml image-cropper
```

##### Option 4: Deploy on GPU-Enabled Host (Best for RF-DETR)

For production use of RF-DETR, deploy on a host with NVIDIA GPU:

- Install nvidia-container-toolkit
- Update docker-compose.yml to include GPU reservations
- RF-DETR will run in seconds instead of minutes

#### Verify Model Cache

Check which models are cached:

```bash
docker run --rm -v image-cropper_backend-models:/models alpine ls -lh /models
```

All models persist across container restarts, so they only download once.

## Recent Updates (v1.0)

### RF-DETR Batch Crop Support

The backend now supports RF-DETR (Roboflow DETR) for batch cropping operations:

- Added `rf-detr` to allowed batch crop methods in frontend, backend API, and CLI
- Updated validation checks across all processing endpoints
- RF-DETR provides highly accurate object detection with batch processing capabilities

### Docker Configuration Improvements

- **Python 3.12**: Updated from Python 3.13 to match project requirements
- **uv Package Manager**: Integrated modern `uv` dependency management for faster builds
- **Platform-Specific PyTorch**: Automatic CUDA 12.1 on Linux/Windows, CPU version on macOS
- **Environment Variables**: Backend now respects `UPLOADS_DIR`, `OUTPUTS_DIR`, and `CROPPED_DIR` environment variables for Docker compatibility
- **Health Checks**: Simplified to use `curl` instead of Python requests library
- **Cross-Platform**: Fully compatible with Windows, Linux, and macOS (both Docker and local development)

## Production Considerations

1. **TLS/SSL**: Add TLS certificates to the nginx load balancer
2. **Secrets Management**: Use Docker secrets for sensitive data
3. **Monitoring**: Integrate with monitoring tools (Prometheus, Grafana)
4. **Logging**: Configure centralized logging (ELK, Splunk)
5. **Backup**: Regular backups of persistent volumes
6. **Security**:
   - Run containers as non-root users
   - Scan images for vulnerabilities
   - Implement network policies
   - Use private registry for images
7. **GPU Support**: For CUDA acceleration, deploy on nodes with NVIDIA GPUs and Docker with nvidia-container-toolkit

## Environment Variables

You can customize behavior by modifying the environment section in `docker-compose.yml`:

```yaml
environment:
  - PYTHONUNBUFFERED=1
  - UPLOADS_DIR=/app/uploads
  - OUTPUTS_DIR=/app/outputs
  - CROPPED_DIR=/app/cropped_images
```

## Multi-Node Swarm

For production deployments across multiple nodes:

1. **Add worker nodes**:

```bash
# On manager node, get join token
docker swarm join-token worker

# On worker nodes, run the join command
docker swarm join --token <token> <manager-ip>:2377
```

2. **Deploy with constraints**:
   Modify `docker-compose.yml` to add placement constraints:

```yaml
deploy:
  placement:
    constraints:
      - node.role == worker
```

## Support

For issues or questions, refer to the main README.md or open an issue on GitHub.
