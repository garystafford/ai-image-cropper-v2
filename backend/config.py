"""
Configuration file for AI Image Cropper
Contains all constants and default values used throughout the application.
Author: Gary Stafford
License: MIT
"""

from pathlib import Path

# Get the absolute path to the backend directory
_BACKEND_DIR = Path(__file__).parent.resolve()

# UI Logo Path
CROP_LOGO_PATH = _BACKEND_DIR / "crop.png"

# Model Paths
YOLO_MODEL_DIRECTORY = _BACKEND_DIR / "models"
YOLO_MODEL_PATH = YOLO_MODEL_DIRECTORY / "yolo12x.pt"
RFDETR_MODEL_PATH = YOLO_MODEL_DIRECTORY / "rf-detr-large.pth"

# UI Display Settings
UI_IMAGE_HEIGHT = 400
UI_RESULT_MAX_HEIGHT = 400  # Max height for result image to prevent very tall images
LOGO_SIZE = 48

# Processing Defaults
DEFAULT_CONFIDENCE = 0.5
DEFAULT_PADDING = 8
DEFAULT_THRESHOLD = 240
DEFAULT_ASPECT_RATIO_PRECISION = 2

# Detection Method Defaults
DEFAULT_CONFIDENCE_THRESHOLD = 0.7  # DETR default
DEFAULT_YOLO_CONFIDENCE = 0.5
DEFAULT_PADDING_PERCENT = 5
DEFAULT_GRABCUT_ITERATIONS = 5

# RT-DETR Model Settings
RTDETR_MODEL_NAME = "PekingU/rtdetr_r101vd_coco_o365"
DEFAULT_RTDETR_CONFIDENCE = 0.5  # RT-DETR default

# Edge Detection Defaults
DEFAULT_EDGE_LOW_THRESHOLD = 50
DEFAULT_EDGE_HIGH_THRESHOLD = 150
DEFAULT_EDGE_DILATE_ITERATIONS = 2

# Info Display
INFO_SEPARATOR_WIDTH = 12

# Server Settings
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 7860
SHARE_PUBLICLY = False

# Validation
VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Batch Processing
BATCH_OUTPUT_DIR = _BACKEND_DIR / "cropped_images"
BATCH_IMAGE_QUALITY = 95

# GrabCut Defaults
DEFAULT_GRABCUT_MARGIN = 0.1  # 10% margin from edges for initial rectangle

# YOLO Warmup
WARMUP_IMAGE_SIZE = 100  # Size of dummy image for model warmup

# Slider Ranges
CONFIDENCE_MIN = 0.1
CONFIDENCE_MAX = 1.0
CONFIDENCE_STEP = 0.05

THRESHOLD_MIN = 50
THRESHOLD_MAX = 250
THRESHOLD_STEP = 5

PADDING_MIN = 0
PADDING_MAX = 50
PADDING_STEP = 1
