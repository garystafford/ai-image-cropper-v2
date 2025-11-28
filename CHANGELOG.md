# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-11-28

### Added

- RF-DETR (Roboflow DETR) detection method for highly accurate object detection
- RT-DETR (Real-Time DETR) for faster inference with similar accuracy to DETR
- DETR (DEtection TRansformer) state-of-the-art transformer-based detection
- YOLO v12 X-Large model support for fast and accurate deep learning detection
- Traditional computer vision methods: Contour, Saliency, Edge, and GrabCut
- React web interface using AWS Cloudscape Design System
- FastAPI REST API backend for image processing
- Command-line interface (CLI) with full automation capabilities
- Batch processing support for cropping all detected objects individually
- Custom aspect ratio support (16:9, 4:3, 1:1, custom ratios)
- Smart padding around detected objects
- GPU acceleration with NVIDIA CUDA 12.1 support
- CPU fallback for systems without GPU
- Docker Swarm deployment configuration
- Multi-service architecture with nginx load balancer
- Health check endpoints for all services
- Persistent volume support for ML model caching
- Cross-platform support (Windows, macOS, Linux)
- Multiple image format support (JPEG, PNG, WebP)

### Changed

- **Standardized Python version to 3.12** across all environments (local, CI/CD, Docker)
- Updated CI/CD workflows to use Python 3.12 for CUDA 12.1 compatibility
- Migrated to `uv` package manager for faster dependency installation
- Configured platform-specific PyTorch installation (CUDA 12.1 on Linux/Windows, CPU on macOS)
- Updated project structure documentation
- Enhanced README with CUDA compatibility explanation

### Fixed

- Python version inconsistencies between CI/CD (3.13) and Docker/local (3.12)
- PyTorch CUDA compatibility issues with Python 3.13
- Environment variable handling in Docker containers for upload/output directories

### Documentation

- Added comprehensive README with quick start guide
- Created Docker deployment guide with troubleshooting section
- Added "Why Python 3.12?" section explaining CUDA compatibility requirements
- Documented all detection methods with performance comparisons
- Added model performance comparison table (YOLO, RT-DETR, RF-DETR)
- Created request/response flow diagram
- Documented resource requirements and memory considerations
- Added frontend-specific documentation

### Technical Details

- Python: 3.12+
- PyTorch: 2.0.0+ with CUDA 12.1 support
- YOLO: Ultralytics 8.3.0+
- Transformers: 4.30.0+ (for DETR and RT-DETR)
- RF-DETR: 1.3.0+
- FastAPI: 0.121.1+
- React: 18+ with AWS Cloudscape components
- Docker: Multi-service architecture with overlay networking

### Known Issues

- RF-DETR requires significant memory (6-8GB+) and is slow on CPU (several minutes per image)
- Recommended to use RT-DETR or YOLO for CPU-only deployments
- First run downloads models automatically (may take 2-10 minutes depending on method)

### Performance Notes

- **YOLO**: Sub-second inference, ~2GB memory, 114MB model size - Best for speed
- **RT-DETR**: Seconds inference, ~3GB memory, ~200MB model size - Best for CPU
- **RF-DETR**: Minutes on CPU, 6-8GB+ memory, 1.5GB model size - Best with GPU only
- **DETR**: Moderate speed, ~3GB memory - Good accuracy
- **Traditional CV**: Milliseconds inference, minimal memory - Fast but less accurate

## [Unreleased]

### Planned

- Unit tests with pytest and coverage reporting
- Additional detection methods
- Batch processing optimizations
- Enhanced error handling and validation
- Performance benchmarking suite
- GPU memory optimization for RF-DETR

---

## Release Notes

### Version 1.0.0

This is the initial production release of AI Image Cropper v2, featuring multiple AI-powered detection methods, a modern React web interface, comprehensive CLI tools, and full Docker Swarm deployment support. The application provides intelligent image cropping with GPU acceleration and supports various use cases from quick batch processing to high-accuracy object detection.

**Upgrade Notes:**

- Python 3.12 is required for CUDA 12.1 GPU acceleration
- Use `uv` package manager for dependency installation
- Docker deployments automatically configure CUDA support on Linux/Windows
- Model files are cached in volumes to avoid re-downloading

**Migration from Previous Versions:**

- This is the first stable release (v2.0 of the original project)
- No migration needed for new installations
- Ensure Python 3.12+ is installed before upgrading

---

[1.0.0]: https://github.com/garystafford/ai-image-cropper-v2/releases/tag/v1.0.0
