"""
FastAPI Backend for AI Image Cropper Cloudscape UI
Provides REST API endpoints for image processing.
Author: Gary Stafford
License: MIT
"""

import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image

from backend.config import (
    BATCH_IMAGE_QUALITY,
    DEFAULT_ASPECT_RATIO_PRECISION,
    DEFAULT_CONFIDENCE,
    DEFAULT_PADDING,
    DEFAULT_THRESHOLD,
    INFO_SEPARATOR_WIDTH,
    YOLO_MODEL_DIRECTORY,
)
from backend.cropper import (
    DETR_AVAILABLE,
    RFDETR_AVAILABLE,
    RTDETR_AVAILABLE,
    ULTRALYTICS_AVAILABLE,
    ImageCropper,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AI Image Cropper API",
    description="REST API for AI-powered image cropping",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create directories for uploaded and processed images
UPLOAD_DIR = Path("backend/uploads")
OUTPUT_DIR = Path("backend/outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Create models directory for storing YOLO and RF-DETR models
YOLO_MODEL_DIRECTORY.mkdir(exist_ok=True)

# Mount static directories
app.mount("/uploads", StaticFiles(directory="backend/uploads"), name="uploads")
app.mount("/outputs", StaticFiles(directory="backend/outputs"), name="outputs")


def _build_info_header(cropper: ImageCropper, method: str) -> List[str]:
    """Build the header section of info text."""
    width, height = cropper.original_dimensions
    info_lines = [
        "=" * INFO_SEPARATOR_WIDTH,
        "  IMAGE ANALYSIS",
        "=" * INFO_SEPARATOR_WIDTH,
        f"Original dimensions: {width} x {height} pixels",
        f"Aspect ratio: {width / height:.{DEFAULT_ASPECT_RATIO_PRECISION}f}:1",
        "",
        f"Detecting object using {method} method...",
    ]

    # Add model download warning for first-time use (only for models we can verify)
    from backend.config import YOLO_MODEL_PATH, RFDETR_MODEL_PATH

    if method == "yolo" and not YOLO_MODEL_PATH.exists():
        info_lines.extend(
            [
                "",
                "⚠️  FIRST-TIME SETUP: Downloading YOLO model (~300MB)...",
                "This may take 2-5 minutes. Please wait...",
                "",
            ]
        )
    elif method == "rf-detr" and not RFDETR_MODEL_PATH.exists():
        info_lines.extend(
            [
                "",
                "⚠️  FIRST-TIME SETUP: Downloading RF-DETR model (~1.4GB)...",
                "This may take 5-10 minutes. Please wait...",
                "",
            ]
        )
    # Note: DETR/RT-DETR download to HuggingFace cache on first use
    # We don't show a warning since we can't easily check if they're already cached

    return info_lines


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "message": "AI Image Cropper API",
        "status": "running",
        "yolo_available": ULTRALYTICS_AVAILABLE,
        "detr_available": DETR_AVAILABLE,
        "rtdetr_available": RTDETR_AVAILABLE,
    }


@app.get("/health")
async def health():
    """Health check endpoint for Docker healthchecks."""
    return {"status": "healthy"}


@app.post("/api/process")
async def process_image(
    file: UploadFile = File(...),
    method: str = Form("contour"),
    object_name: str = Form(""),
    confidence: float = Form(DEFAULT_CONFIDENCE),
    aspect_mode: str = Form("none"),
    custom_aspect_ratio: str = Form(""),
    padding: int = Form(DEFAULT_PADDING),
    threshold: int = Form(DEFAULT_THRESHOLD),
    selected_index: Optional[int] = Form(None),
    stored_detections: Optional[str] = Form(None),  # JSON string of detections
):
    """
    Process an image and return visualization and cropped result.

    Args:
        selected_index: Index of the object to select from stored detections (0-based)
        stored_detections: Previously stored detections as JSON to avoid re-running detection
    """
    logger.info(
        f"Processing image with method: {method}, selected_index: {selected_index}"
    )

    # Validate file extension
    file_extension = Path(file.filename).suffix.lower()
    valid_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    if file_extension not in valid_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_extension}'. Only JPEG, PNG, and WebP formats are supported.",
        )

    # Save uploaded file
    file_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{file_id}{file_extension}"

    try:
        with input_path.open("wb") as f:
            content = await file.read()
            f.write(content)

        # Create cropper instance
        cropper = ImageCropper(str(input_path), debug=False)
        cropper.load_image()

        # Build info text
        info_lines = _build_info_header(cropper, method)

        # Prepare target objects
        target_objects = [object_name] if object_name and object_name.strip() else None
        all_detections = []
        bounds = None
        detected_label = None
        detected_confidence = None

        # Use stored detections if available and selected_index is provided
        if stored_detections is not None and selected_index is not None:
            all_detections = json.loads(stored_detections)
            info_lines.append("Using previously detected objects...")
        else:
            # Run detection based on method
            if method == "contour":
                bounds = cropper.find_object_bounds_contour(threshold)
                detected_label = "Object"
            elif method == "saliency":
                bounds = cropper.find_object_bounds_saliency()
                detected_label = "Salient Region"
            elif method == "edge":
                bounds = cropper.find_object_bounds_edge()
                detected_label = "Edge-Detected Object"
            elif method == "grabcut":
                bounds = cropper.find_object_bounds_grabcut()
                detected_label = "Foreground Object"
            elif method == "detr":
                if not DETR_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="DETR requires 'transformers' and 'torch'. Install with: pip install transformers torch",
                    )
                all_detections = cropper.find_all_objects_detr(
                    target_objects, confidence
                )
            elif method == "rt-detr":
                if not RTDETR_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="RT-DETR requires 'transformers' and 'torch'. Install with: pip install transformers torch",
                    )
                all_detections = cropper.find_all_objects_rtdetr(
                    target_objects, confidence
                )
            elif method == "rf-detr":
                if not RFDETR_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="RF-DETR requires 'rfdetr'. Install with: pip install rfdetr",
                    )
                all_detections = cropper.find_all_objects_rfdetr(
                    target_objects, confidence
                )
            elif method == "yolo":
                if not ULTRALYTICS_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="YOLO requires 'ultralytics'. Install with: pip install ultralytics",
                    )
                all_detections = cropper.find_all_objects_yolo(
                    target_objects, confidence
                )

        # Handle detections
        selected_detection_index = None
        if all_detections and len(all_detections) > 0:
            # If selected_index is specified, use that detection
            if selected_index is not None and 0 <= selected_index < len(all_detections):
                selected_obj = all_detections[selected_index]
                selected_detection_index = selected_index
            else:
                # Auto-select best detection
                selected_obj = cropper.select_best_detection(all_detections)
                # Find the index of the selected object
                if selected_obj is not None:
                    for i, det in enumerate(all_detections):
                        if det["box"] == selected_obj["box"]:
                            selected_detection_index = i
                            break

            if selected_obj is not None:
                bounds = tuple(selected_obj["box"])
                detected_label = selected_obj["label"]
                detected_confidence = selected_obj["confidence"]
            else:
                all_detections = []

        if not all_detections or bounds is None:
            info_lines.append("No objects detected, falling back to contour method")
            bounds = cropper.find_object_bounds_contour()
            detected_label = "Object"

        if bounds is None:
            info_lines.append("No bounds detected, using full image")
            bounds = (
                0,
                0,
                cropper.original_dimensions[0],
                cropper.original_dimensions[1],
            )
            detected_label = "Full Image"

        info_lines.append(f"Initial bounds: {bounds}")

        # Add detection summary
        if all_detections:
            info_lines.append("")
            info_lines.append(f"All Detected Objects ({len(all_detections)}):")
            sorted_detections = sorted(
                all_detections, key=lambda x: x["confidence"], reverse=True
            )
            for i, det in enumerate(sorted_detections, 1):
                info_lines.append(f"     {i}. {det['label']}: {det['confidence']:.2f}")

        # Add selected object info
        info_lines.append("")
        if detected_label:
            if detected_confidence is not None:
                info_lines.append(
                    f"Selected: {detected_label} (confidence: {detected_confidence:.2f})"
                )
            else:
                info_lines.append(f"Selected: {detected_label}")

            if target_objects:
                info_lines.append(f"     (Searched for: {', '.join(target_objects)})")

        # Add padding if requested
        if padding > 0:
            bounds = cropper.add_padding(bounds, padding)
            info_lines.append(f"Bounds with {padding}% padding: {bounds}")

        # Adjust for aspect ratio based on selected mode
        if aspect_mode == "original":
            bounds = cropper.adjust_crop_for_aspect_ratio(bounds, None)
            info_lines.append(f"Bounds with original aspect ratio: {bounds}")
        elif aspect_mode == "custom":
            if custom_aspect_ratio and custom_aspect_ratio.strip():
                try:
                    if ":" in custom_aspect_ratio:
                        width, height = map(float, custom_aspect_ratio.split(":"))
                        target_ratio = width / height
                    else:
                        target_ratio = float(custom_aspect_ratio)

                    bounds = cropper.adjust_crop_for_aspect_ratio(bounds, target_ratio)
                    info_lines.append(
                        f"Bounds with custom aspect ratio {custom_aspect_ratio} ({target_ratio:.2f}): {bounds}"
                    )
                except (ValueError, ZeroDivisionError):
                    info_lines.append(
                        f"Invalid aspect ratio format: {custom_aspect_ratio}. Using detected bounds."
                    )

        # Create visualization
        detections_for_viz = all_detections if all_detections else None
        vis_image = cropper.visualize_detections(
            detections_for_viz, selected_detection_index, bounds
        )
        vis_image_rgb = cv2.cvtColor(vis_image, cv2.COLOR_BGR2RGB)

        # Save visualization
        vis_path = OUTPUT_DIR / f"{file_id}_vis.jpg"
        cv2.imwrite(str(vis_path), vis_image)

        # Create cropped image
        pil_image = Image.open(str(input_path))
        cropped = pil_image.crop(bounds)

        # Save cropped image
        cropped_path = OUTPUT_DIR / f"{file_id}_cropped.jpg"
        cropped.save(str(cropped_path))

        # Add final results to info
        crop_width = bounds[2] - bounds[0]
        crop_height = bounds[3] - bounds[1]

        info_lines.extend(
            [
                "",
                "=" * INFO_SEPARATOR_WIDTH,
                "  CROP COORDINATES",
                "=" * INFO_SEPARATOR_WIDTH,
                f"Left: {bounds[0]}, Upper: {bounds[1]}, Right: {bounds[2]}, Lower: {bounds[3]}",
                f"Crop dimensions: {crop_width} x {crop_height} pixels",
                f"Crop aspect ratio: {crop_width / crop_height:.{DEFAULT_ASPECT_RATIO_PRECISION}f}:1",
                "",
                "=" * INFO_SEPARATOR_WIDTH,
                "Processing complete!",
                "=" * INFO_SEPARATOR_WIDTH,
            ]
        )

        info_text = "\n".join(info_lines)

        return {
            "visualization_url": f"/outputs/{vis_path.name}",
            "cropped_url": f"/outputs/{cropped_path.name}",
            "info_text": info_text,
            "detections": all_detections if all_detections else [],
            "bounds": bounds,
        }

    except Exception as e:
        logger.exception("Error processing image")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch-crop")
async def batch_crop(
    file: UploadFile = File(...),
    method: str = Form("yolo"),
    object_name: str = Form(""),
    confidence: float = Form(DEFAULT_CONFIDENCE),
    aspect_mode: str = Form("none"),
    custom_aspect_ratio: str = Form(""),
    padding: int = Form(DEFAULT_PADDING),
    threshold: int = Form(DEFAULT_THRESHOLD),
):
    """
    Batch crop all detected objects from an image.
    """
    logger.info(f"Batch cropping with method: {method}")

    if method not in ["yolo", "detr", "rt-detr", "rf-detr"]:
        raise HTTPException(
            status_code=400,
            detail="Batch crop only works with YOLO, DETR, RT-DETR, or RF-DETR detection methods",
        )

    # Validate file extension
    file_extension = Path(file.filename).suffix.lower()
    valid_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    if file_extension not in valid_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_extension}'. Only JPEG, PNG, and WebP formats are supported.",
        )

    # Save uploaded file
    file_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{file_id}{file_extension}"

    try:
        with input_path.open("wb") as f:
            content = await file.read()
            f.write(content)

        # Load image and get detections
        cropper = ImageCropper(str(input_path))
        cropper.load_image()

        target_objects = [object_name] if object_name and object_name.strip() else None

        # Get all detections
        if method == "yolo":
            if not ULTRALYTICS_AVAILABLE:
                raise HTTPException(
                    status_code=400,
                    detail="YOLO requires 'ultralytics'. Install with: pip install ultralytics",
                )
            all_detections = cropper.find_all_objects_yolo(target_objects, confidence)
        elif method == "detr":
            if not DETR_AVAILABLE:
                raise HTTPException(
                    status_code=400,
                    detail="DETR requires 'transformers' and 'torch'. Install with: pip install transformers torch",
                )
            all_detections = cropper.find_all_objects_detr(target_objects, confidence)
        elif method == "rt-detr":
            if not RTDETR_AVAILABLE:
                raise HTTPException(
                    status_code=400,
                    detail="RT-DETR requires 'transformers' and 'torch'. Install with: pip install transformers torch",
                )
            all_detections = cropper.find_all_objects_rtdetr(target_objects, confidence)
        elif method == "rf-detr":
            if not RFDETR_AVAILABLE:
                raise HTTPException(
                    status_code=400,
                    detail="RF-DETR requires 'rfdetr'. Install with: pip install rfdetr",
                )
            all_detections = cropper.find_all_objects_rfdetr(target_objects, confidence)

        if not all_detections or len(all_detections) == 0:
            return {"files": [], "message": "❌ No objects detected to crop"}

        # Parse aspect ratio
        target_aspect_ratio = None
        if aspect_mode == "original":
            target_aspect_ratio = None
        elif aspect_mode == "custom" and custom_aspect_ratio:
            try:
                if ":" in custom_aspect_ratio:
                    w, h = map(float, custom_aspect_ratio.split(":"))
                    target_aspect_ratio = w / h
                else:
                    target_aspect_ratio = float(custom_aspect_ratio)
            except (ValueError, ZeroDivisionError):
                pass

        # Batch crop
        base_name = Path(file.filename).stem
        output_dir = OUTPUT_DIR / f"batch_{file_id}"
        output_dir.mkdir(exist_ok=True)

        cropped_files = cropper.batch_crop_detections(
            detections=all_detections,
            output_dir=str(output_dir),
            base_filename=base_name,
            padding_percent=padding,
            target_aspect_ratio=target_aspect_ratio,
            image_quality=BATCH_IMAGE_QUALITY,
        )

        # Convert absolute paths to relative URLs
        relative_paths = [
            f"/outputs/{output_dir.name}/{Path(f).name}" for f in cropped_files
        ]

        return {
            "files": relative_paths,
            "message": f"✅ Successfully cropped {len(cropped_files)} object(s). Files ready for download.",
        }

    except Exception as e:
        logger.exception("Batch crop error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cli-process")
async def cli_process_image(
    file: UploadFile = File(...),
    method: str = Form("contour"),
    object: List[str] = Form([]),  # Multiple objects support
    confidence: float = Form(0.7),
    keep_aspect: bool = Form(False),
    aspect_ratio: str = Form(""),
    padding: int = Form(0),
    threshold: int = Form(240),
    batch_crop: bool = Form(False),
    batch_output_dir: str = Form("cropped_images"),
    visualize: bool = Form(True),
    debug: bool = Form(False),
    crop_output: str = Form(""),
    vis_output: str = Form(""),
):
    """
    Process image using CLI-style parameters.
    Supports all features available in the command-line interface.
    """
    logger.info(
        f"CLI processing with method: {method}, batch_crop: {batch_crop}, objects: {object}"
    )

    # Validate file extension
    file_extension = Path(file.filename).suffix.lower()
    valid_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    if file_extension not in valid_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_extension}'. Only JPEG, PNG, and WebP formats are supported.",
        )

    # Save uploaded file
    file_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{file_id}{file_extension}"

    try:
        with input_path.open("wb") as f:
            content = await file.read()
            f.write(content)

        # Create cropper instance
        cropper = ImageCropper(str(input_path), debug=debug)
        cropper.load_image()

        # Build output text (mimics CLI output)
        output_lines = [
            "=" * INFO_SEPARATOR_WIDTH,
            "IMAGE ANALYSIS",
            "=" * INFO_SEPARATOR_WIDTH,
        ]
        width, height = cropper.original_dimensions
        output_lines.extend(
            [
                f"Original dimensions: {width} x {height} pixels",
                f"Aspect ratio: {width / height:.{DEFAULT_ASPECT_RATIO_PRECISION}f}:1",
                "",
            ]
        )

        # Handle batch crop mode
        if batch_crop:
            if method not in ["yolo", "detr", "rt-detr", "rf-detr"]:
                raise HTTPException(
                    status_code=400,
                    detail="Batch crop only works with YOLO, DETR, RT-DETR, or RF-DETR methods",
                )

            output_lines.append(f"Batch cropping all objects using {method} method...")

            # Prepare target objects
            target_objects = object if object and len(object) > 0 else None

            # Get all detections
            if method == "yolo":
                if not ULTRALYTICS_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="YOLO requires 'ultralytics'. Install with: pip install ultralytics",
                    )
                all_detections = cropper.find_all_objects_yolo(
                    target_objects, confidence
                )
            elif method == "detr":
                if not DETR_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="DETR requires 'transformers' and 'torch'",
                    )
                all_detections = cropper.find_all_objects_detr(
                    target_objects, confidence
                )
            elif method == "rt-detr":
                if not RTDETR_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="RT-DETR requires 'transformers' and 'torch'",
                    )
                all_detections = cropper.find_all_objects_rtdetr(
                    target_objects, confidence
                )
            elif method == "rf-detr":
                if not RFDETR_AVAILABLE:
                    raise HTTPException(
                        status_code=400,
                        detail="RF-DETR requires 'rfdetr'",
                    )
                all_detections = cropper.find_all_objects_rfdetr(
                    target_objects, confidence
                )

            if not all_detections:
                output_lines.append("❌ No objects detected!")
                return {"output": "\n".join(output_lines), "batch_files": []}

            output_lines.append(f"✓ Found {len(all_detections)} object(s)")

            # Parse aspect ratio
            target_aspect_ratio = None
            if keep_aspect:
                target_aspect_ratio = None  # Will use original image aspect
            elif aspect_ratio and aspect_ratio.strip():
                try:
                    if ":" in aspect_ratio:
                        w, h = map(float, aspect_ratio.split(":"))
                        target_aspect_ratio = w / h
                    else:
                        target_aspect_ratio = float(aspect_ratio)
                    output_lines.append(
                        f"Using custom aspect ratio: {target_aspect_ratio:.2f}:1"
                    )
                except (ValueError, ZeroDivisionError):
                    output_lines.append(
                        f"⚠️  WARNING: Invalid aspect ratio '{aspect_ratio}', ignoring"
                    )

            # Batch crop all detections
            base_name = Path(file.filename).stem
            output_dir = OUTPUT_DIR / f"batch_{file_id}"
            output_dir.mkdir(exist_ok=True)

            cropped_files = cropper.batch_crop_detections(
                detections=all_detections,
                output_dir=str(output_dir),
                base_filename=base_name,
                padding_percent=padding,
                target_aspect_ratio=target_aspect_ratio,
                image_quality=BATCH_IMAGE_QUALITY,
            )

            # Convert to relative URLs
            relative_paths = [
                f"/outputs/{output_dir.name}/{Path(f).name}" for f in cropped_files
            ]

            output_lines.extend(
                [
                    "",
                    f"✅ Successfully cropped {len(cropped_files)} object(s)",
                    f"Saved to: {output_dir}/",
                ]
            )
            for file_path in cropped_files:
                output_lines.append(f"  - {Path(file_path).name}")

            return {"output": "\n".join(output_lines), "batch_files": relative_paths}

        # Single object detection mode
        output_lines.append(f"Detecting object using {method} method...")

        # Prepare target objects
        target_objects = object if object and len(object) > 0 else None
        bounds = None
        detected_label = None
        detected_confidence = None
        all_detections = []

        # Run detection based on method
        if method == "contour":
            bounds = cropper.find_object_bounds_contour(threshold)
            detected_label = "Object"
        elif method == "saliency":
            bounds = cropper.find_object_bounds_saliency()
            detected_label = "Salient Region"
        elif method == "edge":
            bounds = cropper.find_object_bounds_edge()
            detected_label = "Edge-Detected Object"
        elif method == "grabcut":
            bounds = cropper.find_object_bounds_grabcut()
            detected_label = "Foreground Object"
        elif method == "detr":
            if not DETR_AVAILABLE:
                raise HTTPException(
                    status_code=400, detail="DETR requires 'transformers' and 'torch'"
                )
            all_detections = cropper.find_all_objects_detr(target_objects, confidence)
        elif method == "rt-detr":
            if not RTDETR_AVAILABLE:
                raise HTTPException(
                    status_code=400,
                    detail="RT-DETR requires 'transformers' and 'torch'",
                )
            all_detections = cropper.find_all_objects_rtdetr(target_objects, confidence)
        elif method == "rf-detr":
            if not RFDETR_AVAILABLE:
                raise HTTPException(
                    status_code=400,
                    detail="RF-DETR requires 'rfdetr'",
                )
            all_detections = cropper.find_all_objects_rfdetr(target_objects, confidence)
        elif method == "yolo":
            if not ULTRALYTICS_AVAILABLE:
                raise HTTPException(
                    status_code=400, detail="YOLO requires 'ultralytics'"
                )
            all_detections = cropper.find_all_objects_yolo(target_objects, confidence)

        # Handle AI detections
        if all_detections and len(all_detections) > 0:
            selected_obj = cropper.select_best_detection(all_detections)
            if selected_obj is not None:
                bounds = tuple(selected_obj["box"])
                detected_label = selected_obj["label"]
                detected_confidence = selected_obj["confidence"]

        # Fallback to contour if no detections
        if bounds is None:
            output_lines.append("No objects detected, falling back to contour method")
            bounds = cropper.find_object_bounds_contour()
            detected_label = "Object"

        output_lines.append(f"Initial bounds: {bounds}")

        # Add detection info
        if detected_label:
            if detected_confidence is not None:
                output_lines.append(
                    f"✓ Detected: {detected_label} (confidence: {detected_confidence:.2f})"
                )
            else:
                output_lines.append(f"✓ Detected: {detected_label}")

        # Add padding if requested
        if padding > 0:
            bounds = cropper.add_padding(bounds, padding)
            output_lines.append(f"Bounds with {padding}% padding: {bounds}")

        # Adjust for aspect ratio
        if keep_aspect:
            bounds = cropper.adjust_crop_for_aspect_ratio(bounds)
            output_lines.append(f"Bounds with original aspect ratio: {bounds}")
        elif aspect_ratio and aspect_ratio.strip():
            try:
                if ":" in aspect_ratio:
                    w, h = map(float, aspect_ratio.split(":"))
                    target_ratio = w / h
                else:
                    target_ratio = float(aspect_ratio)
                bounds = cropper.adjust_crop_for_aspect_ratio(bounds, target_ratio)
                output_lines.append(
                    f"Bounds with custom aspect ratio {aspect_ratio} ({target_ratio:.2f}:1): {bounds}"
                )
            except (ValueError, ZeroDivisionError):
                output_lines.append(
                    f"⚠️  WARNING: Invalid aspect ratio '{aspect_ratio}', using detected bounds"
                )

        # Print final coordinates
        crop_width = bounds[2] - bounds[0]
        crop_height = bounds[3] - bounds[1]

        output_lines.extend(
            [
                "",
                "=" * INFO_SEPARATOR_WIDTH,
                "CROP COORDINATES",
                "=" * INFO_SEPARATOR_WIDTH,
                f"Tuple format: {bounds}",
                f"Left: {bounds[0]}, Upper: {bounds[1]}, Right: {bounds[2]}, Lower: {bounds[3]}",
                "",
                f"Crop dimensions: {crop_width} x {crop_height} pixels",
                f"Crop aspect ratio: {crop_width / crop_height:.{DEFAULT_ASPECT_RATIO_PRECISION}f}:1",
                "=" * INFO_SEPARATOR_WIDTH,
            ]
        )

        # Create cropped image
        pil_image = Image.open(str(input_path))
        cropped = pil_image.crop(bounds)

        # Save cropped image
        cropped_path = OUTPUT_DIR / f"{file_id}_cropped.jpg"
        cropped.save(str(cropped_path))
        output_lines.append(f"✓ Cropped image saved to: {cropped_path.name}")
        output_lines.append(
            f"  New dimensions: {cropped.width} x {cropped.height} pixels"
        )

        result = {
            "output": "\n".join(output_lines),
            "cropped_url": f"/outputs/{cropped_path.name}",
        }

        # Create visualization if requested
        if visualize:
            detections_for_viz = all_detections if all_detections else None
            vis_image = cropper.visualize_detections(detections_for_viz, None, bounds)
            vis_path = OUTPUT_DIR / f"{file_id}_vis.jpg"
            cv2.imwrite(str(vis_path), vis_image)
            result["visualization_url"] = f"/outputs/{vis_path.name}"
            output_lines.append(f"✓ Visualization saved to: {vis_path.name}")

        # Update final output
        output_lines.append("")
        output_lines.append("✅ Processing complete!")
        result["output"] = "\n".join(output_lines)

        return result

    except Exception as e:
        logger.exception("CLI processing error")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
