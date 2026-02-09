# AI Image Cropper Version 2.0

[![Build Status](https://img.shields.io/github/actions/workflow/status/garystafford/ai-image-cropper-v2/ci.yml?branch=main&style=flat-square)](https://github.com/garystafford/ai-image-cropper-v2/actions)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Intelligent image cropping tool with multiple detection methods including You Only Look Once (YOLO), DEtection TRansformer (DETR), Real-Time DEtection TRansformer (RT-DETR), Roboflow DETR (RF-DETR), and traditional computer vision algorithms. Available as both a React web interface and a command-line tool. See the blog post, [Enhanced AI-Powered Smart Image Cropping Workflow v2](https://garystafford.medium.com/enhanced-ai-powered-smart-image-cropping-workflow-v2-81aa593fb5bf) for more details.

![Preview](./assets/ui-preview.jpg)

## Features

### Detection Methods

- **RF-DETR** - Roboflow DETR, highly accurate detection
- **RT-DETR** - Real-time DETR with faster inference and similar accuracy
- **DETR** - State-of-the-art transformer-based detection
- **YOLO** - Fast and accurate deep learning (recommended)
- **Contour** - Fast, works well with clear backgrounds
- **Saliency** - Identifies visually interesting regions
- **Edge** - Canny edge detection
- **GrabCut** - Foreground/background segmentation

### Capabilities

- 🎯 **Object Detection**: Detect specific objects (person, car, couch, etc.)
- 📐 **Custom Aspect Ratios**: Set target aspect ratios (16:9, 4:3, 1:1, custom)
- 🔲 **Smart Padding**: Add breathing room around detected objects
- 🎨 **Batch Processing**: Crop all detected objects individually
- 🖼️ **Multiple Formats**: JPEG, PNG, WebP support
- 🌐 **Web UI (User Interface)**: Modern React interface with AWS Cloudscape Design
- ⌨️ **CLI (Command-Line Interface)**: Full command-line interface for automation
- 🖥️ **Cross-Platform**: Windows, macOS, and Linux support
- ⚡ **GPU Acceleration**: NVIDIA CUDA GPU acceleration or CPU fallback

## Deployment Options

The application supports three deployment models:

### Local Development

Run the backend and frontend directly on your machine with Python and Node.js. Supports GPU acceleration with NVIDIA CUDA or CPU-only inference. See [Quick Start](#quick-start) below.

### Docker Swarm (Self-Hosted)

Deploy as a multi-service Docker Swarm stack with an nginx load balancer, persistent volumes for ML model caching, and rolling updates. See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for the full guide.

### AWS ECS Fargate (Cloud)

Deploy to AWS using CloudFormation templates that provision the full stack: CloudFront CDN, WAF, Cognito authentication, Application Load Balancer, and ECS Fargate. The deployment is automated via a single script:

```bash
# 1. Configure parameters
cp cloudformation/common-parameters.json.example cloudformation/common-parameters.json
# Edit common-parameters.json with your VPC, subnet, and security group IDs

# 2. Deploy infrastructure
./deploy-cloudformation.sh

# 3. Build and push Docker images, register task definition, update service
./update_ecs_task.sh
```

#### AWS Architecture

```mermaid
graph TB
    User([User]) --> Route53

    subgraph DNS
        Route53[Route 53<br/>app.example.com]
    end

    Route53 --> CloudFront

    subgraph CDN ["CloudFront CDN"]
        CloudFront[CloudFront Distribution<br/>HTTPS + X-Origin-Verify header]
    end

    CloudFront --> WAF

    subgraph Security ["Security Layer"]
        WAF[AWS WAF WebACL<br/>Validates X-Origin-Verify header]
        Cognito[Cognito User Pool<br/>Username/password auth]
    end

    WAF --> ALB

    subgraph VPC ["VPC"]
        ALB[Application Load Balancer<br/>HTTPS with Cognito auth action]
        ALB -- "Unauthenticated" --> Cognito
        Cognito -- "Authenticated" --> ALB

        subgraph ECS ["ECS Fargate"]
            Frontend[Frontend Container<br/>React + nginx :80]
            Backend[Backend Container<br/>FastAPI :8000]
        end

        ALB --> Frontend
        Frontend --> Backend

        EFS[(EFS<br/>ML Model Storage)]
        Backend --> EFS
    end

    subgraph Registry ["Container Registry"]
        ECR[ECR Repositories<br/>frontend + backend images]
    end

    ECR -.-> ECS

    ACM[ACM Certificates<br/>*.example.com] -.-> CloudFront
    ACM -.-> ALB

    SSM[SSM Parameter Store<br/>Origin verify secret] -.-> CloudFront
    SSM -.-> WAF
```

#### CloudFormation Stack Deployment Order

```mermaid
graph LR
    S1[01 - ECR] --> S2[02 - EFS]
    S2 --> S3[03 - ALB]
    S3 --> S4[04 - IAM]
    S4 --> S5[05 - Cluster]
    S5 --> S6[06 - Service]
    S6 --> S7[07 - Cognito]
    S7 --> S8[08 - ALB Update<br/>+ WAF + Cognito]
    S8 --> S9[09 - CloudFront<br/>+ Route 53]

    style S7 fill:#f9f,stroke:#333
    style S8 fill:#f9f,stroke:#333
    style S9 fill:#f9f,stroke:#333
```

Steps 7-9 (highlighted) are optional and deploy automatically when `AppDomainName`, `CognitoDomainPrefix`, `HostedZoneId`, and `CloudFrontCertificateArn` are configured in `common-parameters.json`.

#### Request Flow

```mermaid
sequenceDiagram
    participant User
    participant CF as CloudFront
    participant WAF as WAF WebACL
    participant ALB as ALB
    participant Cognito as Cognito
    participant ECS as ECS Fargate

    User->>CF: HTTPS request (app.example.com)
    CF->>WAF: Forward + X-Origin-Verify header
    WAF->>WAF: Validate header matches secret

    alt Invalid or missing header
        WAF-->>CF: 403 Forbidden
        CF-->>User: 403 Forbidden
    end

    WAF->>ALB: Request passes WAF
    ALB->>ALB: authenticate-cognito action

    alt Not authenticated
        ALB-->>User: 302 Redirect to Cognito login
        User->>Cognito: Login with username/password
        Cognito-->>User: 302 Redirect back with auth code
        User->>CF: Follow redirect with auth code
        CF->>WAF: Forward + header
        WAF->>ALB: Pass
        ALB->>ALB: Exchange code for session cookie
    end

    ALB->>ECS: Forward to target group
    ECS-->>ALB: Response
    ALB-->>CF: Response
    CF-->>User: Response
```

See [cloudformation/README.md](cloudformation/README.md) and [cloudformation/PARAMETERS.md](cloudformation/PARAMETERS.md) for full documentation.

## Quick Start

### NVIDIA GPU-based Installation

**Prerequisites:** NVIDIA GPU with [CUDA 12.1 drivers](https://www.nvidia.com/Download/index.aspx), Python 3.12+, [uv package manager](https://docs.astral.sh/uv/)

```bash
# 1. Install uv (if not installed)
# Windows:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and install dependencies (includes GPU-enabled PyTorch)
git clone https://github.com/garystafford/ai-image-cropper-v2.git
cd ai-image-cropper-v2
uv sync

# 3. Test GPU detection
# Windows:
.venv\Scripts\activate
python test_gpu.py

# macOS/Linux:
source .venv/bin/activate
python test_gpu.py

# 4. Run detection
python -m backend.cropper sample_images/sample_image_00001.jpg --method rf-detr
```

**Note:** On first run, AI models automatically download (~200MB-1.4GB depending on method). PyTorch with CUDA support is automatically installed via the CUDA repository configured in `pyproject.toml`.

### CPU-Only Installation (No GPU)

If you don't have an NVIDIA GPU, you can manually install the CPU-only version after running `uv sync`:

```bash
# First run normal sync
uv sync

# Then override with CPU-only PyTorch
uv pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**Note:** CPU inference will be significantly slower (~3-5x) than GPU-accelerated inference.

## Web UI (optional)

```bash
cd frontend && npm install && cd ..
uvicorn backend.api:app --reload  # Terminal 1
cd frontend && npm run dev         # Terminal 2 - Opens http://localhost:5173
```

## Usage

The AI Image Cropper provides two different interfaces to suit your needs:

### 1. Command-Line Interface (CLI)

The CLI provides full automation capabilities for batch processing and scripting.

#### Basic Usage

```bash
# Using entry point (recommended)
uv run crop-cli image.jpg --visualize --crop-output output.jpg

# Or directly with Python (from root directory)
python -m backend.cropper image.jpg --visualize --crop-output output.jpg
```

#### Single Object Detection

```bash
# Detect and crop a couch with custom aspect ratio
uv run crop-cli living_room.jpg --method yolo --object couch --aspect-ratio 16:9 --crop-output couch.jpg

# Detect person with RT-DETR (faster than DETR)
uv run crop-cli photo.jpg --method rt-detr --object person --confidence 0.5 --padding 10 --crop-output person.jpg

# Detect person with RF-DETR (highly accurate)
uv run crop-cli photo.jpg --method rf-detr --object person --confidence 0.5 --padding 10 --crop-output person.jpg

# Detect person with DETR, add padding
uv run crop-cli photo.jpg --method detr --object person --confidence 0.8 --padding 10 --crop-output person.jpg

# Use contour detection with visualization
uv run crop-cli product.jpg --method contour --threshold 200 --padding 5 --visualize
```

#### Batch Processing

Batch processing automatically crops all detected objects and saves them separately:

```bash
# Detect and crop all people in a family photo
uv run crop-cli family.jpg --method yolo --batch-crop --batch-output-dir ./people

# Batch crop with RT-DETR for faster processing
uv run crop-cli room.jpg --method rt-detr --batch-crop --confidence 0.5

# Batch crop with custom aspect ratio and padding (DETR)
uv run crop-cli room.jpg --method detr --batch-crop --aspect-ratio 4:3 --padding 15

# Batch crop all objects (no specific object filter)
uv run crop-cli scene.jpg --method yolo --batch-crop --confidence 0.7
```

#### CLI Options

```text
positional arguments:
  image_path            Path to the input image

options:
  --method              Detection method: contour, saliency, edge, grabcut, detr, rt-detr, rf-detr, yolo
  --object              Target object(s) to detect (can specify multiple times)
  --confidence          Confidence threshold for deep learning methods (0-1, default: 0.7)
  --keep-aspect         Maintain original aspect ratio
  --aspect-ratio        Custom aspect ratio (e.g., 16:9, 4:3, 1.5, 2.35:1)
  --padding             Padding percentage around object (default: 5)
  --threshold           Threshold value for contour detection (default: 240)
  --visualize           Display detection visualization window
  --crop-output         Save cropped image to specified path
  --batch-crop          Crop all detected objects individually (YOLO/RT-DETR/DETR/RF-DETR)
  --batch-output-dir    Output directory for batch crop (default: cropped_images)
  --image-quality       JPEG quality for saved images (1-100, default: 95)
  --debug               Save debug images during processing
```

### 2. React Web Interface (AWS Cloudscape)

The React UI provides a modern, professional interface using AWS Cloudscape Design System.

#### Prerequisites

- Node.js 18+
- Backend and frontend dependencies installed (see [Quick Start](#quick-start))

#### Start React App

You need to run both the backend API and the frontend development server:

**Terminal 1 - Backend API:**

```bash
# From project root
uvicorn backend.api:app --reload
```

The API will start on `http://localhost:8000`

**Terminal 2 - Frontend Dev Server:**

```bash
# From project root
cd frontend
npm run dev
```

The UI will start on `http://localhost:5173` (or next available port)

#### Using React UI

The React UI provides a modern, professional interface with AWS Cloudscape Design:

1. Upload images via drag-and-drop or file picker
2. Select detection method and configure parameters
3. View real-time processing with visual feedback
4. Download individual crops or batch process multiple objects
5. See detailed processing information and statistics

#### Production Build

To create an optimized production build:

```bash
cd frontend
npm run build
```

The build output will be in `frontend/dist/` and can be served by any static file server.

## Request/Response Flow

```mermaid
sequenceDiagram
    participant User
    participant UI as Web UI / CLI / API
    participant Core as ImageCropper Engine
    participant Detector as Detection Method<br/>(CV or AI Model)
    participant GPU as GPU/CPU
    participant Storage as File System

    User->>UI: Upload image + parameters
    UI->>Core: Load image
    Core->>Storage: Read image file
    Storage-->>Core: Image data
    Core-->>UI: Image loaded

    UI->>Core: Request detection
    Core->>Detector: Run detection

    alt AI Model (YOLO/DETR/RT-DETR/RF-DETR)
        Detector->>GPU: Process on GPU/CPU
        GPU-->>Detector: Bounding boxes
    else Computer Vision (Contour/Saliency/Edge)
        Detector->>Detector: Process locally
    end

    Detector-->>Core: Detection results

    Core->>Core: Add padding
    Core->>Core: Adjust aspect ratio
    Core->>Storage: Save cropped image
    Storage-->>Core: File saved

    Core-->>UI: Cropped image + visualization + metadata
    UI-->>User: Display results
```

The swimlane diagram shows the request/response flow from user input through the system layers: the user interface accepts the request, the ImageCropper engine coordinates processing, detection methods (computer vision or AI models) run on GPU/CPU, and results flow back through the layers to the user.

## Configuration

### Dependencies (pyproject.toml)

Project dependencies are managed in `pyproject.toml`. Common dependency management commands:

```bash
# Add a new package
uv add package-name

# Add a dev dependency
uv add --dev package-name

# Remove a package
uv remove package-name

# Update all dependencies
uv lock --upgrade

# Update a specific package
uv lock --upgrade-package package-name

# Sync environment with lock file
uv sync

# List installed packages
uv pip list

# Show outdated packages
uv pip list --outdated
```

### Application Settings (backend/config.py)

All default values are stored in `backend/config.py` for easy customization:

```python
# UI Display Settings
UI_IMAGE_HEIGHT = 400           # Height for input/visualization images
UI_RESULT_MAX_HEIGHT = 400      # Max height for result image (prevents very tall images)

# Processing Defaults
DEFAULT_CONFIDENCE = 0.5
DEFAULT_PADDING = 8
DEFAULT_THRESHOLD = 240

# Detection Method Defaults
DEFAULT_YOLO_CONFIDENCE = 0.5
DEFAULT_RTDETR_CONFIDENCE = 0.5     # RT-DETR
DEFAULT_CONFIDENCE_THRESHOLD = 0.7  # DETR
DEFAULT_GRABCUT_MARGIN = 0.1        # GrabCut initial rectangle margin
DEFAULT_GRABCUT_ITERATIONS = 5      # GrabCut iteration count
WARMUP_IMAGE_SIZE = 100             # YOLO model warmup image size

# Model Paths
RTDETR_MODEL_NAME = "PekingU/rtdetr_r101vd_coco_o365"

# Batch Processing
BATCH_OUTPUT_DIR = "cropped_images"
BATCH_IMAGE_QUALITY = 95

# Server Settings
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 7860
```

## Tips

- **YOLO** is the fastest and most accurate for common objects
- **RT-DETR** offers a balance between speed and accuracy, faster than DETR with similar results
- **RF-DETR** provides highly accurate detection
- **DETR** provides detailed object detection but is slower than YOLO, RT-DETR, and RF-DETR
- For best results, use padding of 5-10%
- Batch mode works only with YOLO, RT-DETR, DETR, and RF-DETR methods
- Common detectable objects: person, car, couch, chair, dog, cat, bottle, laptop, bicycle, etc.
- Use `--visualize` in CLI to preview detection before cropping

## Troubleshooting

### Image Format Error

Ensure your image is JPEG (.jpg, .jpeg), PNG (.png), or WebP (.webp)

### Model Download on First Run

YOLO, RT-DETR, and RF-DETR will download their model files on first use (may take 2-5 minutes for YOLO v12 X-Large, 2-5 minutes for RT-DETR, 5-10 minutes for RF-DETR Large ~1.4GB)

### DETR/RT-DETR/RF-DETR Memory Usage

DETR, RT-DETR, and RF-DETR require more memory than YOLO. RT-DETR is more efficient than DETR. RF-DETR requires significant memory due to its model size. For large images or limited memory, consider using YOLO or RT-DETR instead.

### No Objects Detected

- Lower the confidence threshold
- Try a different detection method
- Verify the object name is in the model's vocabulary

## Development

### Code Quality

```bash
# Format code with Black
uvx black .

# Check formatting without applying
uvx black . --check

# Lint with Ruff
uvx ruff check .

# Fix auto-fixable issues
uvx ruff check . --fix

# Format code with Ruff formatter
uvx ruff format .

# Remove unused imports with autoflake
uvx autoflake --remove-all-unused-imports --in-place --recursive backend/

# Lint shell scripts with ShellCheck
shellcheck *.sh

# Lint Markdown files with markdownlint
npx markdownlint-cli "**/*.md" --ignore node_modules --ignore frontend/node_modules

# Build package
uvx hatch build
```

### Environment Management

```bash
# Create/recreate virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux

.venv\Scripts\activate     # Windows

# Deactivate virtual environment
deactivate

# Clean and reinstall all dependencies
rm -rf .venv uv.lock
uv sync

# Show Python version in use
uv python --version

# List available Python versions
uv python list
```

## Project Structure

```text
ai-image-cropper-v2/
├── .github/
│   └── workflows/
│       └── ci.yml                 # CI pipeline (lint, format, build)
├── backend/                       # Backend Python application
│   ├── __init__.py
│   ├── api.py                     # FastAPI REST API
│   ├── cropper.py                 # Core processing engine + CLI
│   ├── config.py                  # Configuration constants
│   ├── models/                    # YOLO/RF-DETR model files (auto-downloaded)
│   ├── cropped_images/            # Default batch crop output
│   ├── uploads/                   # Uploaded files (API)
│   └── outputs/                   # Processed outputs (API)
├── frontend/                      # React frontend application
│   ├── src/                       # React source code
│   ├── public/                    # Static assets
│   ├── package.json               # npm dependencies
│   ├── vite.config.js             # Vite configuration
│   └── index.html                 # HTML entry point
├── cloudformation/                # AWS CloudFormation templates
│   ├── 01-ecr-repositories.yaml   # ECR container registries
│   ├── 02-efs-storage.yaml        # Elastic File System
│   ├── 03-load-balancer.yaml      # ALB + WAF + Cognito auth
│   ├── 04-iam-roles.yaml         # IAM roles for ECS
│   ├── 05-ecs-cluster.yaml        # ECS Fargate cluster
│   ├── 06-ecs-service.yaml        # ECS service and task definition
│   ├── 07-ecs-application.yaml    # Alternate combined application template
│   ├── 08-cognito.yaml            # Cognito User Pool (optional)
│   ├── 09-cloudfront.yaml         # CloudFront + Route 53 (optional)
│   ├── common-parameters.json.example  # Example parameters file
│   ├── PARAMETERS.md              # Detailed parameter documentation
│   └── README.md                  # CloudFormation deployment guide
├── sample_images/                 # Sample images for testing
├── Dockerfile.backend             # Backend Docker image
├── Dockerfile.frontend            # Frontend Docker image
├── docker-compose.yml             # Docker Swarm stack configuration
├── nginx-lb.conf                  # Nginx load balancer configuration
├── deploy-cloudformation.sh       # CloudFormation deployment script
├── update_ecs_task.sh             # ECS image build and deploy script
├── test_gpu.py                    # GPU/CUDA availability test
├── pyproject.toml                 # Python project configuration (uv)
├── .markdownlint.json             # Markdownlint configuration
├── .python-version                # Python version (3.12)
├── uv.lock                        # Python dependency lock file
├── CHANGELOG.md                   # Version history
├── DOCKER_DEPLOYMENT.md           # Docker Swarm deployment guide
├── LICENSE                        # MIT license
└── README.md                      # This file
```

## Requirements

- **Python**: 3.12+
- **Package Manager**: [uv](https://docs.astral.sh/uv/)
- **Key Dependencies**:
  - fastapi >= 0.121.1
  - opencv-python >= 4.12.0
  - ultralytics >= 8.3.0 (YOLO)
  - transformers >= 4.30.0 (DETR and RT-DETR)
  - rfdetr >= 1.3.0 (RF-DETR)
  - torch >= 2.0.0
  - numpy >= 2.2.0
  - pillow >= 11.0.0

See [`pyproject.toml`](pyproject.toml) for complete dependency list.

## Why Python 3.12?

This project uses Python 3.12 to ensure compatibility with PyTorch and CUDA 12.1 for GPU acceleration:

- **CUDA 12.1 Support**: PyTorch with CUDA 12.1 has guaranteed compatibility with Python 3.12 (PyTorch 2.1+)
- **GPU Acceleration**: Python 3.13 requires PyTorch 2.5+ for CUDA 12.1 support, which has limited availability
- **Stability**: Python 3.12 provides a stable, well-tested environment for all AI/ML dependencies
- **Cross-Platform**: Ensures consistency between local development, CI/CD pipelines, and Docker deployments

If you're using CPU-only inference, Python 3.13 will work, but we standardize on 3.12 for consistency across all deployment scenarios.

## License

This project is open source and available under the [MIT License](LICENSE).

## Disclaimer

The contents of this repository represent my viewpoints and not those of my past or current employers, including Amazon Web Services (AWS). All third-party libraries, modules, plugins, and SDKs are the property of their respective owners.
