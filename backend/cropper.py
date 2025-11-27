"""
AI Image Cropper
Analyzes an image to find object boundaries and provides accurate crop coordinates.
Author: Gary Stafford
License: MIT
"""

# Standard library imports
import argparse
import datetime
import logging
import os
import sys
import traceback
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# Third-party imports
import cv2
import numpy as np
from PIL import Image

# Local imports
from backend.config import (
    BATCH_IMAGE_QUALITY,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_EDGE_DILATE_ITERATIONS,
    DEFAULT_EDGE_HIGH_THRESHOLD,
    DEFAULT_EDGE_LOW_THRESHOLD,
    DEFAULT_GRABCUT_ITERATIONS,
    DEFAULT_GRABCUT_MARGIN,
    DEFAULT_PADDING_PERCENT,
    DEFAULT_RTDETR_CONFIDENCE,
    DEFAULT_THRESHOLD,
    DEFAULT_YOLO_CONFIDENCE,
    RFDETR_MODEL_PATH,
    RTDETR_MODEL_NAME,
    WARMUP_IMAGE_SIZE,
    YOLO_MODEL_PATH,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress RF-DETR logging messages
# This suppresses the "Model is not optimized for inference" message
logging.getLogger('rfdetr.detr').setLevel(logging.ERROR)

# Suppress TF32 deprecation warnings from dependencies
# Dependencies (transformers, accelerate, ultralytics) use the old TF32 API
# but this is an internal dependency issue, not our code
warnings.filterwarnings(
    'ignore',
    message='.*allow_tf32.*',
    category=UserWarning
)

# Suppress torch.meshgrid indexing deprecation warning
# This is triggered internally by PyTorch dependencies
warnings.filterwarnings(
    'ignore',
    message='.*torch.meshgrid.*indexing argument.*',
    category=UserWarning
)

# Optional deep learning imports
try:
    from transformers import DetrImageProcessor, DetrForObjectDetection
    import torch

    DETR_AVAILABLE = True
except ImportError:
    DETR_AVAILABLE = False

try:
    from transformers import RTDetrImageProcessor, RTDetrForObjectDetection
    import torch

    RTDETR_AVAILABLE = True
except ImportError:
    RTDETR_AVAILABLE = False

try:
    from ultralytics import YOLO as UltralyticsYOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False

try:
    from rfdetr import RFDETRLarge

    RFDETR_AVAILABLE = True
except ImportError:
    RFDETR_AVAILABLE = False

# Global model cache to avoid reloading
_yolo_model_cache = None
_rfdetr_model_cache = None

# COCO dataset class names mapping (COCO ID -> class name)
# RF-DETR uses COCO dataset IDs which are not contiguous
COCO_CLASS_NAMES = {
    1: "person",
    2: "bicycle",
    3: "car",
    4: "motorcycle",
    5: "airplane",
    6: "bus",
    7: "train",
    8: "truck",
    9: "boat",
    10: "traffic light",
    11: "fire hydrant",
    13: "stop sign",
    14: "parking meter",
    15: "bench",
    16: "bird",
    17: "cat",
    18: "dog",
    19: "horse",
    20: "sheep",
    21: "cow",
    22: "elephant",
    23: "bear",
    24: "zebra",
    25: "giraffe",
    27: "backpack",
    28: "umbrella",
    31: "handbag",
    32: "tie",
    33: "suitcase",
    34: "frisbee",
    35: "skis",
    36: "snowboard",
    37: "sports ball",
    38: "kite",
    39: "baseball bat",
    40: "baseball glove",
    41: "skateboard",
    42: "surfboard",
    43: "tennis racket",
    44: "bottle",
    46: "wine glass",
    47: "cup",
    48: "fork",
    49: "knife",
    50: "spoon",
    51: "bowl",
    52: "banana",
    53: "apple",
    54: "sandwich",
    55: "orange",
    56: "broccoli",
    57: "carrot",
    58: "hot dog",
    59: "pizza",
    60: "donut",
    61: "cake",
    62: "chair",
    63: "couch",
    64: "potted plant",
    65: "bed",
    67: "dining table",
    70: "toilet",
    72: "tv",
    73: "laptop",
    74: "mouse",
    75: "remote",
    76: "keyboard",
    77: "cell phone",
    78: "microwave",
    79: "oven",
    80: "toaster",
    81: "sink",
    82: "refrigerator",
    84: "book",
    85: "clock",
    86: "vase",
    87: "scissors",
    88: "teddy bear",
    89: "hair drier",
    90: "toothbrush",
}


class ImageCropper:
    def __init__(self, image_path: str, debug: bool = False) -> None:
        self.image_path = image_path
        self.image = None
        self.original_dimensions = None
        self.debug = debug

    def load_image(self) -> Tuple[int, int]:
        """Load image and get dimensions."""
        self.image = cv2.imread(self.image_path)
        if self.image is None:
            raise ValueError(f"Could not load image from {self.image_path}")

        height, width = self.image.shape[:2]
        self.original_dimensions = (width, height)
        logger.info(
            f"Loaded image: {width} x {height} pixels, aspect ratio: {width / height:.2f}:1"
        )
        return self.original_dimensions

    def find_object_bounds_contour(
        self, threshold_value: int = DEFAULT_THRESHOLD
    ) -> Tuple[int, int, int, int]:
        """
        Find object boundaries using edge detection and contours.
        Works well for images with clear foreground/background separation.
        """
        # Convert to grayscale
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)

        # Apply threshold to separate foreground from background
        _, thresh = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY_INV)

        # Save debug images if requested
        epoch_num = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.debug:
            cv2.imwrite(f"debug_1_grayscale_{epoch_num}.jpg", gray)
            cv2.imwrite(f"debug_2_threshold_{epoch_num}.jpg", thresh)
            logger.debug(
                f"Saved debug_1_grayscale_{epoch_num}.jpg and debug_2_threshold_{epoch_num}.jpg"
            )

        # Find contours
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        logger.info(f"Found {len(contours)} contour(s)")

        if not contours:
            logger.warning("No contours found!")
            logger.info(
                f"The threshold value ({threshold_value}) may be too high or too low."
            )
            logger.info(
                "TIP: Try adjusting --threshold. Lower values (e.g., 200) detect more, higher values (e.g., 250) detect less"
            )
            logger.info("TIP: Use --debug to see the grayscale and threshold images")
            logger.info("Falling back to full image dimensions.")
            return (0, 0, self.original_dimensions[0], self.original_dimensions[1])

        # Get the largest contour (assumed to be the main object)
        largest_contour = max(contours, key=cv2.contourArea)
        contour_area = cv2.contourArea(largest_contour)
        image_area = self.original_dimensions[0] * self.original_dimensions[1]
        area_ratio = (contour_area / image_area) * 100

        logger.info(f"Largest contour covers {area_ratio:.1f}% of image")

        if area_ratio > 95:
            logger.warning("Detected region covers >95% of image")
            logger.info("Detection may not be working correctly")
            logger.info("TIP: Try a different --threshold value or --method")

        x, y, w, h = cv2.boundingRect(largest_contour)

        # Save debug image with contours if requested
        epoch_num = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.debug:
            debug_contours = self.image.copy()
            cv2.drawContours(debug_contours, [largest_contour], -1, (0, 255, 0), 3)
            cv2.rectangle(debug_contours, (x, y), (x + w, y + h), (255, 0, 0), 3)
            cv2.imwrite(f"debug_3_contours_{epoch_num}.jpg", debug_contours)
            logger.debug(
                f"Saved debug_3_contours_{epoch_num}.jpg (green=contour, blue=bounding box)"
            )

        return (x, y, x + w, y + h)

    def find_object_bounds_saliency(self) -> Tuple[int, int, int, int]:
        """
        Find object boundaries using saliency detection.
        Identifies visually interesting regions.
        """
        # Create saliency detector
        saliency = cv2.saliency.StaticSaliencyFineGrained_create()
        success, saliency_map = saliency.computeSaliency(self.image)

        if not success:
            logger.warning("Saliency detection failed. Using contour method.")
            return self.find_object_bounds_contour()

        # Threshold the saliency map
        saliency_map = (saliency_map * 255).astype("uint8")
        _, thresh_map = cv2.threshold(
            saliency_map, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
        )

        # Find contours in the saliency map
        contours, _ = cv2.findContours(
            thresh_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return self.find_object_bounds_contour()

        # Get bounding box of all salient regions
        all_points = np.vstack(contours)
        x, y, w, h = cv2.boundingRect(all_points)

        return (x, y, x + w, y + h)

    def find_object_bounds_edge(
        self,
        low_threshold: int = DEFAULT_EDGE_LOW_THRESHOLD,
        high_threshold: int = DEFAULT_EDGE_HIGH_THRESHOLD,
    ) -> Tuple[int, int, int, int]:
        """
        Find object boundaries using Canny edge detection.
        Fast method that works well for objects with clear edges.

        Args:
            low_threshold: Lower threshold for Canny edge detection (default: 50)
            high_threshold: Upper threshold for Canny edge detection (default: 150)
        """
        # Convert to grayscale
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Apply Canny edge detection
        edges = cv2.Canny(blurred, low_threshold, high_threshold)

        # Dilate edges to close gaps
        kernel = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=DEFAULT_EDGE_DILATE_ITERATIONS)

        # Save debug images if requested
        epoch_num = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.debug:
            cv2.imwrite(f"debug_1_edges_{epoch_num}.jpg", edges)
            cv2.imwrite(f"debug_2_dilated_{epoch_num}.jpg", dilated)
            logger.debug(
                f"Saved debug_1_edges_{epoch_num}.jpg and debug_2_dilated_{epoch_num}.jpg"
            )
        # Find contours
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        logger.info(f"Found {len(contours)} contour(s) from edges")

        if not contours:
            logger.warning("No edges found!")
            logger.info(
                "TIP: Try adjusting edge detection thresholds or use a different method"
            )
            logger.info("Falling back to full image dimensions.")
            return (0, 0, self.original_dimensions[0], self.original_dimensions[1])

        # Get the largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)

        # Save debug image with contours if requested
        epoch_num = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.debug:
            debug_edges = self.image.copy()
            cv2.drawContours(debug_edges, [largest_contour], -1, (0, 255, 0), 3)
            cv2.rectangle(debug_edges, (x, y), (x + w, y + h), (255, 0, 0), 3)
            cv2.imwrite(f"debug_3_edge_contours_{epoch_num}.jpg", debug_edges)
            logger.debug(f"Saved debug_3_edge_contours_{epoch_num}.jpg")

        return (x, y, x + w, y + h)

    def find_object_bounds_grabcut(
        self, iterations: int = DEFAULT_GRABCUT_ITERATIONS
    ) -> Tuple[int, int, int, int]:
        """
        Find object boundaries using GrabCut algorithm.
        Performs foreground/background segmentation assuming the object is centered.

        Args:
            iterations: Number of GrabCut iterations (default: 5)
        """
        # Create a mask
        mask = np.zeros(self.image.shape[:2], np.uint8)

        # Define an initial rectangle (assuming object is somewhat centered)
        # Use configurable margin from edges
        height, width = self.image.shape[:2]
        margin_x = int(width * DEFAULT_GRABCUT_MARGIN)
        margin_y = int(height * DEFAULT_GRABCUT_MARGIN)
        rect = (margin_x, margin_y, width - 2 * margin_x, height - 2 * margin_y)

        # Initialize background and foreground models
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)

        logger.info(f"Running GrabCut with {iterations} iterations...")

        # Apply GrabCut
        cv2.grabCut(
            self.image,
            mask,
            rect,
            bgd_model,
            fgd_model,
            iterations,
            cv2.GC_INIT_WITH_RECT,
        )

        # Create binary mask (0 and 2 are background, 1 and 3 are foreground)
        mask2 = np.where((mask == 2) | (mask == 0), 0, 1).astype("uint8")

        # Save debug images if requested
        epoch_num = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.debug:
            cv2.imwrite(f"debug_1_grabcut_mask_{epoch_num}.jpg", mask2 * 255)
            logger.debug(f"Saved debug_1_grabcut_mask_{epoch_num}.jpg")

        # Find contours in the mask
        contours, _ = cv2.findContours(
            mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        logger.info(f"Found {len(contours)} contour(s) from GrabCut")

        if not contours:
            logger.warning("GrabCut segmentation failed!")
            logger.info("TIP: Try a different method or adjust the image")
            logger.info("Falling back to initial rectangle.")
            return (rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3])

        # Get the largest contour (main foreground object)
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)

        # Save debug image with result if requested
        epoch_num = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.debug:
            # Apply mask to show segmented object
            segmented = self.image * mask2[:, :, np.newaxis]
            cv2.rectangle(segmented, (x, y), (x + w, y + h), (0, 255, 0), 3)
            cv2.imwrite(f"debug_2_grabcut_result_{epoch_num}.jpg", segmented)
            logger.debug(f"Saved debug_2_grabcut_result_{epoch_num}.jpg")

        return (x, y, x + w, y + h)

    def find_all_objects_detr(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> List[Dict[str, Union[str, float, List[int]]]]:
        """
        Find all objects using DETR and return full detection information.

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, returns all detected objects
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            list: List of detection dictionaries with keys:
                  'label' (str), 'confidence' (float), 'box' (list of 4 ints)
                  Empty list if no objects detected or DETR unavailable.
        """
        if not DETR_AVAILABLE:
            logger.warning(
                "DETR not available. Install with: uv add transformers torch"
            )
            return []

        try:
            # Suppress warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                os.environ["TRANSFORMERS_VERBOSITY"] = "error"

                processor = DetrImageProcessor.from_pretrained(
                    "facebook/detr-resnet-50"
                )
                model = DetrForObjectDetection.from_pretrained(
                    "facebook/detr-resnet-50"
                )

            # Prepare image
            pil_image = Image.open(self.image_path)
            inputs = processor(images=pil_image, return_tensors="pt")

            # Run inference
            with torch.no_grad():
                outputs = model(**inputs)

            # Post-process results
            target_sizes = torch.tensor([pil_image.size[::-1]])
            results = processor.post_process_object_detection(
                outputs, target_sizes=target_sizes, threshold=confidence_threshold
            )[0]

            # Process all detections
            all_detected = []
            filtered_objects = []

            for score, label, box in zip(
                results["scores"], results["labels"], results["boxes"]
            ):
                label_name = model.config.id2label[label.item()]
                confidence = score.item()
                box_coords = [int(coord) for coord in box.tolist()]

                detection = {
                    "label": label_name,
                    "confidence": confidence,
                    "box": box_coords,
                }

                all_detected.append(detection)

                # Flexible matching: case-insensitive and partial match
                if target_objects is None:
                    filtered_objects.append(detection)
                else:
                    for target in target_objects:
                        if (
                            target.lower() in label_name.lower()
                            or label_name.lower() in target.lower()
                        ):
                            filtered_objects.append(detection)
                            break

            # Return filtered objects if target_objects specified, otherwise all detected
            return filtered_objects if target_objects is not None else all_detected

        except Exception as e:
            logger.error(f"DETR detection failed: {e}")
            return []

    def find_object_bounds_detr(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> Tuple[int, int, int, int]:
        """
        Find object boundaries using DETR (Detection Transformer).
        State-of-the-art object detection with 91 COCO categories.

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, detects the largest/most confident object
            confidence_threshold: Minimum confidence score (0-1)
        Returns:
            tuple: (left, upper, right, lower) crop coordinates
        """
        if not DETR_AVAILABLE:
            logger.warning(
                "DETR not available. Install with: uv add transformers torch"
            )
            logger.info("Falling back to contour method.")
            return self.find_object_bounds_contour()

        logger.info("Loading DETR model (this may take a moment on first run)...")

        detected_objects = self.find_all_objects_detr(
            target_objects, confidence_threshold
        )

        if not detected_objects:
            logger.info("No objects detected with sufficient confidence.")
            logger.info("Try lowering --confidence or using a different method.")
            return self.find_object_bounds_contour()

        # Get the object with highest confidence (or largest if tied)
        best_object = self.select_best_detection(detected_objects)

        for obj in detected_objects:
            logger.info(
                f"Detected: {obj['label']} (confidence: {obj['confidence']:.2f}) at {obj['box']}"
            )

        logger.info(
            f"Using: {best_object['label']} (confidence: {best_object['confidence']:.2f})"
        )

        box = best_object["box"]
        return (box[0], box[1], box[2], box[3])

    def find_all_objects_rtdetr(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_RTDETR_CONFIDENCE,
    ) -> List[Dict[str, Union[str, float, List[int]]]]:
        """
        Find all objects using RT-DETR (Real-Time DETR) and return full detection information.

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, returns all detected objects
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            list: List of detection dictionaries with keys:
                  'label' (str), 'confidence' (float), 'box' (list of 4 ints)
                  Empty list if no objects detected or RT-DETR unavailable.
        """
        if not RTDETR_AVAILABLE:
            logger.warning(
                "RT-DETR not available. Install with: uv add transformers torch"
            )
            return []

        try:
            # Suppress warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                os.environ["TRANSFORMERS_VERBOSITY"] = "error"

                processor = RTDetrImageProcessor.from_pretrained(RTDETR_MODEL_NAME)
                model = RTDetrForObjectDetection.from_pretrained(RTDETR_MODEL_NAME)

            # Prepare image
            pil_image = Image.open(self.image_path)
            inputs = processor(images=pil_image, return_tensors="pt")

            # Run inference
            with torch.no_grad():
                outputs = model(**inputs)

            # Post-process results
            target_sizes = torch.tensor([pil_image.size[::-1]])
            results = processor.post_process_object_detection(
                outputs, target_sizes=target_sizes, threshold=confidence_threshold
            )[0]

            # Process all detections
            all_detected = []
            filtered_objects = []

            for score, label, box in zip(
                results["scores"], results["labels"], results["boxes"]
            ):
                label_name = model.config.id2label[label.item()]
                confidence = score.item()
                box_coords = [int(coord) for coord in box.tolist()]

                detection = {
                    "label": label_name,
                    "confidence": confidence,
                    "box": box_coords,
                }

                all_detected.append(detection)

                # Flexible matching: case-insensitive and partial match
                if target_objects is None:
                    filtered_objects.append(detection)
                else:
                    for target in target_objects:
                        if (
                            target.lower() in label_name.lower()
                            or label_name.lower() in target.lower()
                        ):
                            filtered_objects.append(detection)
                            break

            # Return filtered objects if target_objects specified, otherwise all detected
            return filtered_objects if target_objects is not None else all_detected

        except Exception as e:
            logger.error(f"RT-DETR detection failed: {e}")
            return []

    def find_object_bounds_rtdetr(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_RTDETR_CONFIDENCE,
    ) -> Tuple[int, int, int, int]:
        """
        Find object boundaries using RT-DETR (Real-Time Detection Transformer).
        Faster version of DETR with similar accuracy, supports COCO categories.

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, detects the largest/most confident object
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            tuple: (left, upper, right, lower) crop coordinates
        """
        if not RTDETR_AVAILABLE:
            logger.warning(
                "RT-DETR not available. Install with: uv add transformers torch"
            )
            logger.info("Falling back to contour method.")
            return self.find_object_bounds_contour()

        logger.info("Loading RT-DETR model (this may take a moment on first run)...")

        detected_objects = self.find_all_objects_rtdetr(
            target_objects, confidence_threshold
        )

        if not detected_objects:
            logger.info("No objects detected with sufficient confidence.")
            logger.info("Try lowering --confidence or using a different method.")
            return self.find_object_bounds_contour()

        # Get the object with highest confidence (or largest if tied)
        best_object = self.select_best_detection(detected_objects)

        for obj in detected_objects:
            logger.info(
                f"Detected: {obj['label']} (confidence: {obj['confidence']:.2f}) at {obj['box']}"
            )

        logger.info(
            f"Using: {best_object['label']} (confidence: {best_object['confidence']:.2f})"
        )

        box = best_object["box"]
        return (box[0], box[1], box[2], box[3])

    def find_all_objects_yolo(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_YOLO_CONFIDENCE,
    ) -> List[Dict[str, Union[str, float, List[int]]]]:
        """
        Find all objects using YOLO and return full detection information.

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, returns all detected objects
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            list: List of detection dictionaries with keys:
                  'label' (str), 'confidence' (float), 'box' (list of 4 ints)
                  Empty list if no objects detected or YOLO unavailable.
        """
        if not ULTRALYTICS_AVAILABLE:
            logger.warning(
                "YOLO (ultralytics) not available. Install with: uv add ultralytics"
            )
            return []

        try:
            # Load YOLO model (cached to avoid reloading)
            global _yolo_model_cache
            if _yolo_model_cache is None:
                logger.info("Loading YOLO model for the first time...")
                _yolo_model_cache = UltralyticsYOLO(YOLO_MODEL_PATH)
                logger.info("YOLO model loaded successfully")
                # Warm up the model with a dummy inference to ensure it's fully initialized
                logger.info("Warming up YOLO model...")
                try:
                    # Create a small dummy image for warmup
                    dummy_image = np.zeros(
                        (WARMUP_IMAGE_SIZE, WARMUP_IMAGE_SIZE, 3), dtype=np.uint8
                    )
                    temp_path = "/tmp/dummy_warmup.jpg"
                    cv2.imwrite(temp_path, dummy_image)
                    _ = _yolo_model_cache(temp_path, conf=0.1, verbose=False)
                    logger.info("YOLO model warmup completed")
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception as warmup_error:
                    logger.warning(f"YOLO warmup failed: {warmup_error}")

            model = _yolo_model_cache

            # Run inference
            logger.info(f"Running YOLO inference on {self.image_path}")
            results = model(self.image_path, conf=confidence_threshold, verbose=False)
            logger.info("YOLO inference completed, processing results...")

            # Process results
            all_detected = []
            filtered_objects = []

            logger.debug(f"Processing {len(results)} result(s) from YOLO")
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    logger.debug("No boxes found in this result")
                    continue
                logger.debug(f"Processing {len(boxes)} detection(s)")
                for box in boxes:
                    # Get box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].item()
                    class_id = int(box.cls[0].item())
                    label_name = model.names[class_id]

                    box_coords = [int(x1), int(y1), int(x2), int(y2)]

                    detection = {
                        "label": label_name,
                        "confidence": confidence,
                        "box": box_coords,
                    }

                    all_detected.append(detection)

                    # Flexible matching: case-insensitive and partial match
                    if target_objects is None:
                        filtered_objects.append(detection)
                    else:
                        for target in target_objects:
                            if (
                                target.lower() in label_name.lower()
                                or label_name.lower() in target.lower()
                            ):
                                filtered_objects.append(detection)
                                break

            # Return filtered objects if target_objects specified, otherwise all detected
            final_detections = (
                filtered_objects if target_objects is not None else all_detected
            )
            logger.debug(f"Returning {len(final_detections)} detection(s)")
            return final_detections

        except Exception as e:
            logger.error(f"YOLO detection failed: {e}")
            traceback.print_exc()
            return []

    def find_object_bounds_yolo(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_YOLO_CONFIDENCE,
    ) -> Tuple[int, int, int, int]:
        """
        Find object boundaries using YOLO (You Only Look Once).
        Fast and accurate object detection.

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, detects the largest/most confident object
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            tuple: (left, upper, right, lower) crop coordinates
        """
        if not ULTRALYTICS_AVAILABLE:
            logger.warning(
                "YOLO (ultralytics) not available. Install with: uv add ultralytics"
            )
            logger.info("Falling back to contour method.")
            return self.find_object_bounds_contour()

        logger.info("Loading YOLO model (this may take a moment on first run)...")

        detected_objects = self.find_all_objects_yolo(
            target_objects, confidence_threshold
        )

        if not detected_objects:
            logger.info("No objects detected with sufficient confidence.")
            logger.info("Try lowering --confidence or using a different method.")
            return self.find_object_bounds_contour()

        # Get the object with highest confidence (or largest if tied)
        best_object = self.select_best_detection(detected_objects)

        for obj in detected_objects:
            logger.info(
                f"Detected: {obj['label']} (confidence: {obj['confidence']:.2f}) at {obj['box']}"
            )

        logger.info(
            f"Using: {best_object['label']} (confidence: {best_object['confidence']:.2f})"
        )

        box = best_object["box"]
        return (box[0], box[1], box[2], box[3])

    def find_all_objects_rfdetr(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_YOLO_CONFIDENCE,
    ) -> List[Dict[str, Union[str, float, List[int]]]]:
        """
        Find all objects using RF-DETR and return full detection information.

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, returns all detected objects
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            list: List of detection dictionaries with keys:
                  'label' (str), 'confidence' (float), 'box' (list of 4 ints)
                  Empty list if no objects detected or RF-DETR unavailable.
        """
        if not RFDETR_AVAILABLE:
            logger.warning("RF-DETR not available. Install with: uv add rfdetr")
            return []

        try:
            # Load RF-DETR model (cached to avoid reloading)
            global _rfdetr_model_cache
            if _rfdetr_model_cache is None:
                logger.info("Loading RF-DETR model for the first time...")
                # Check if model file exists
                if RFDETR_MODEL_PATH.exists():
                    logger.info(f"Loading existing model from: {RFDETR_MODEL_PATH}")
                    _rfdetr_model_cache = RFDETRLarge(
                        pretrain_weights=str(RFDETR_MODEL_PATH)
                    )
                else:
                    logger.info("Model not found, downloading to default location...")
                    logger.info(f"Model will be cached at: {RFDETR_MODEL_PATH}")
                    # Let rfdetr download to its default location first
                    _rfdetr_model_cache = RFDETRLarge()
                    # Note: On first run, model downloads to ~/.cache/roboflow/
                    # We accept this behavior rather than trying to override it
                logger.info("RF-DETR model loaded successfully")

            model = _rfdetr_model_cache

            # Run inference
            logger.info(f"Running RF-DETR inference on {self.image_path}")
            detections = model.predict(self.image_path, threshold=confidence_threshold)
            logger.info("RF-DETR inference completed, processing results...")

            # Process results - RF-DETR returns a Supervision Detections object
            all_detected = []
            filtered_objects = []

            # RF-DETR returns a supervision.detection.core.Detections object
            # with xyxy, confidence, and class_id arrays
            if detections.xyxy is not None and len(detections.xyxy) > 0:
                logger.debug(
                    f"Processing {len(detections.xyxy)} detection(s) from RF-DETR"
                )

                for i in range(len(detections.xyxy)):
                    # Get box coordinates
                    x1, y1, x2, y2 = detections.xyxy[i]
                    confidence = float(detections.confidence[i])
                    class_id = int(detections.class_id[i])

                    # Get label name from COCO class names mapping
                    # RF-DETR uses COCO dataset IDs (e.g., 85=clock, 86=vase)
                    label_name = COCO_CLASS_NAMES.get(class_id, f"class_{class_id}")

                    box_coords = [int(x1), int(y1), int(x2), int(y2)]

                    detection = {
                        "label": label_name,
                        "confidence": confidence,
                        "box": box_coords,
                    }

                    all_detected.append(detection)

                    # Filter by target objects if specified
                    if target_objects is None or label_name in target_objects:
                        filtered_objects.append(detection)
                        logger.debug(
                            f"Found target: {label_name} (conf: {confidence:.2f}) at {box_coords}"
                        )

            # Return filtered objects if target specified, otherwise all objects
            result_objects = filtered_objects if target_objects else all_detected

            logger.info(
                f"RF-DETR detected {len(all_detected)} total objects, "
                f"returning {len(result_objects)} after filtering"
            )

            return result_objects

        except Exception as e:
            logger.error(f"RF-DETR detection failed: {str(e)}")
            logger.debug(traceback.format_exc())
            return []

    def find_object_bounds_rfdetr(
        self,
        target_objects: Optional[List[str]] = None,
        confidence_threshold: float = DEFAULT_YOLO_CONFIDENCE,
    ) -> Tuple[int, int, int, int]:
        """
        Find object bounds using RF-DETR deep learning (fastest DETR variant).

        Args:
            target_objects: List of object names to detect (e.g., ['couch', 'chair'])
                          If None, detects the largest/most confident object
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            tuple: (left, upper, right, lower) crop coordinates
        """
        if not RFDETR_AVAILABLE:
            logger.warning("RF-DETR not available. Install with: uv add rfdetr")
            logger.info("Falling back to contour method.")
            return self.find_object_bounds_contour()

        logger.info("Loading RF-DETR model (this may take a moment on first run)...")

        detected_objects = self.find_all_objects_rfdetr(
            target_objects, confidence_threshold
        )

        if not detected_objects:
            logger.info("No objects detected with sufficient confidence.")
            logger.info("Try lowering --confidence or using a different method.")
            return self.find_object_bounds_contour()

        # Get the object with highest confidence (or largest if tied)
        best_object = self.select_best_detection(detected_objects)

        for obj in detected_objects:
            logger.info(
                f"Detected: {obj['label']} (confidence: {obj['confidence']:.2f}) at {obj['box']}"
            )

        logger.info(
            f"Using: {best_object['label']} (confidence: {best_object['confidence']:.2f})"
        )

        box = best_object["box"]
        return (box[0], box[1], box[2], box[3])

    def select_best_detection(
        self, detections: List[Dict[str, Union[str, float, List[int]]]]
    ) -> Optional[Dict[str, Union[str, float, List[int]]]]:
        """
        Select the best detection from a list based on confidence and area.

        Args:
            detections: List of detection dictionaries

        Returns:
            dict: The best detection, or None if list is empty
        """
        if not detections:
            return None

        return max(
            detections,
            key=lambda x: (
                x["confidence"],
                (x["box"][2] - x["box"][0]) * (x["box"][3] - x["box"][1]),  # area
            ),
        )

    def visualize_detections(
        self,
        detections: Optional[List[Dict[str, Union[str, float, List[int]]]]],
        selected_index: Optional[int] = None,
        selected_bounds: Optional[Tuple[int, int, int, int]] = None,
    ) -> np.ndarray:
        """
        Visualize all detections with highlighting for the selected one.

        Args:
            detections: List of detection dictionaries, or None for non-AI methods
            selected_index: Index of the selected detection (0-based), or None
            selected_bounds: Tuple (left, upper, right, lower) of selected crop, or None

        Returns:
            numpy.ndarray: Visualization image in BGR format
        """
        vis_image = self.image.copy()

        if detections and len(detections) > 0:
            # Draw all detected objects
            for i, detection in enumerate(detections):
                det_box = detection["box"]
                det_label = detection["label"]
                det_conf = detection["confidence"]

                # Check if this is the selected object
                is_selected = False
                if selected_index is not None and i == selected_index:
                    is_selected = True
                elif selected_bounds is not None:
                    is_selected = (
                        det_box[0] == selected_bounds[0]
                        and det_box[1] == selected_bounds[1]
                        and det_box[2] == selected_bounds[2]
                        and det_box[3] == selected_bounds[3]
                    )

                # Use green for selected, yellow for others
                color = (0, 255, 0) if is_selected else (0, 255, 255)  # BGR
                thickness = 3 if is_selected else 2

                # Draw bounding box
                cv2.rectangle(
                    vis_image,
                    (det_box[0], det_box[1]),
                    (det_box[2], det_box[3]),
                    color,
                    thickness,
                )

                # Add label
                label_text = f"{det_label}: {det_conf:.2f}"
                (text_width, text_height), baseline = cv2.getTextSize(
                    label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                )

                label_y = max(det_box[1] - 10, text_height + 10)

                # Draw background for label
                cv2.rectangle(
                    vis_image,
                    (det_box[0], label_y - text_height - baseline - 5),
                    (det_box[0] + text_width + 10, label_y + baseline),
                    color,
                    -1,
                )

                # Draw label text (black for visibility)
                cv2.putText(
                    vis_image,
                    label_text,
                    (det_box[0] + 5, label_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 0),
                    2,
                )
        elif selected_bounds:
            # No detections list, just draw the selected crop box
            left, upper, right, lower = selected_bounds
            cv2.rectangle(vis_image, (left, upper), (right, lower), (0, 255, 0), 3)

        # Add coordinates at the top for the selected crop
        if selected_bounds:
            left, upper, right, lower = selected_bounds
            coord_text = f"Selected Crop: ({left}, {upper}, {right}, {lower})"
            cv2.putText(
                vis_image,
                coord_text,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

        return vis_image

    def adjust_crop_for_aspect_ratio(
        self,
        bounds: Tuple[int, int, int, int],
        target_aspect_ratio: Optional[float] = None,
    ) -> Tuple[int, int, int, int]:
        """
        Adjust crop bounds to maintain a specific aspect ratio.
        If target_aspect_ratio is None, uses original image aspect ratio.

        Args:
            bounds: Tuple (left, upper, right, lower) of current crop
            target_aspect_ratio: Desired aspect ratio (width / height)

        Returns:
            tuple: Adjusted (left, upper, right, lower) crop bounds
        """
        left, upper, right, lower = bounds
        crop_width = right - left
        crop_height = lower - upper

        if target_aspect_ratio is None:
            # Use original image aspect ratio
            target_aspect_ratio = (
                self.original_dimensions[0] / self.original_dimensions[1]
            )

        current_aspect_ratio = crop_width / crop_height

        if abs(current_aspect_ratio - target_aspect_ratio) < 0.01:
            # Already close enough
            return bounds

        if current_aspect_ratio > target_aspect_ratio:
            # Current crop is too wide, need to increase height
            new_height = int(crop_width / target_aspect_ratio)
            height_diff = new_height - crop_height
            upper = max(0, upper - height_diff // 2)
            lower = min(self.original_dimensions[1], lower + height_diff // 2)

            # Adjust if we hit boundaries
            if upper == 0:
                lower = min(self.original_dimensions[1], new_height)
            elif lower == self.original_dimensions[1]:
                upper = max(0, self.original_dimensions[1] - new_height)
        else:
            # Current crop is too tall, need to increase width
            new_width = int(crop_height * target_aspect_ratio)
            width_diff = new_width - crop_width
            left = max(0, left - width_diff // 2)
            right = min(self.original_dimensions[0], right + width_diff // 2)

            # Adjust if we hit boundaries
            if left == 0:
                right = min(self.original_dimensions[0], new_width)
            elif right == self.original_dimensions[0]:
                left = max(0, self.original_dimensions[0] - new_width)

        return (left, upper, right, lower)

    def add_padding(
        self,
        bounds: Tuple[int, int, int, int],
        padding_percent: int = DEFAULT_PADDING_PERCENT,
    ) -> Tuple[int, int, int, int]:
        """Add padding around the detected bounds (as percentage).
        Args:
            bounds: Tuple (left, upper, right, lower) of current crop
            padding_percent: Padding percentage to add around the bounds
        Returns:
            tuple: New (left, upper, right, lower) crop bounds with padding
        """
        left, upper, right, lower = bounds
        width = right - left
        height = lower - upper

        padding_x = int(width * padding_percent / 100)
        padding_y = int(height * padding_percent / 100)

        left = max(0, left - padding_x)
        upper = max(0, upper - padding_y)
        right = min(self.original_dimensions[0], right + padding_x)
        lower = min(self.original_dimensions[1], lower + padding_y)

        return (left, upper, right, lower)

    def visualize_crop(
        self, bounds: Tuple[int, int, int, int], output_path: Optional[str] = None
    ) -> np.ndarray:
        """Visualize the crop area on the original image.

        Args:
            bounds: Tuple (left, upper, right, lower) of current crop
            output_path: Optional path to save the visualization image

        Returns:
            np.ndarray: Image with visualization overlay
        """
        left, upper, right, lower = bounds

        # Create a copy of the image
        vis_image = self.image.copy()

        # Draw rectangle
        cv2.rectangle(vis_image, (left, upper), (right, lower), (0, 255, 0), 3)

        # Add text with coordinates
        text = f"Crop: ({left}, {upper}, {right}, {lower})"
        cv2.putText(
            vis_image, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
        )

        if output_path:
            cv2.imwrite(output_path, vis_image)
            logger.info(f"Visualization saved to: {output_path}")

        # Display the image
        cv2.imshow("Crop Preview (Press any key to close)", vis_image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        return vis_image

    def crop_and_save(
        self, bounds: Tuple[int, int, int, int], output_path: str
    ) -> Image.Image:
        """Crop the image and save it."""
        left, upper, right, lower = bounds

        # Use PIL for cropping (more straightforward)
        pil_image = Image.open(self.image_path)
        cropped = pil_image.crop(bounds)
        cropped.save(output_path)

        logger.info(f"Cropped image saved to: {output_path}")
        logger.info(f"New dimensions: {cropped.width} x {cropped.height} pixels")
        return cropped

    def batch_crop_detections(
        self,
        detections: List[Dict[str, Union[str, float, List[int]]]],
        output_dir: str,
        base_filename: str,
        padding_percent: int = 0,
        target_aspect_ratio: Optional[float] = None,
        image_quality: int = 95,
    ) -> List[str]:
        """
        Crop all detections and save them as individual files.

        Args:
            detections: List of detection dictionaries with 'box', 'label', 'confidence'
            output_dir: Directory to save cropped images
            base_filename: Base name for output files (without extension)
            padding_percent: Padding percentage to add around each detection
            target_aspect_ratio: Target aspect ratio (None to skip adjustment)
            image_quality: JPEG quality (1-95)

        Returns:
            List of paths to saved files
        """

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        cropped_files = []
        pil_image = Image.open(self.image_path)

        for i, detection in enumerate(detections):
            try:
                # Get bounds from detection
                box = detection.get("box")
                if box is None:
                    logger.error(f"Object {i}: No 'box' key in detection: {detection}")
                    continue

                bounds = tuple(box) if isinstance(box, list) else box
                label = detection["label"]
                conf = detection["confidence"]

                # Apply padding
                if padding_percent > 0:
                    bounds = self.add_padding(bounds, padding_percent)
                    if bounds is None:
                        logger.error(f"Object {i}: add_padding returned None!")
                        continue

                # Apply aspect ratio if needed
                if target_aspect_ratio is not None:
                    bounds = self.adjust_crop_for_aspect_ratio(
                        bounds, target_aspect_ratio
                    )
                    if bounds is None:
                        logger.error(
                            f"Object {i}: adjust_crop_for_aspect_ratio returned None!"
                        )
                        continue

                # Crop the image
                cropped = pil_image.crop(bounds)

                # Generate filename
                output_filename = f"{base_filename}_{i}_{label}_{conf:.2f}.jpg"
                output_file_path = output_path / output_filename

                # Save cropped image
                cropped.save(output_file_path, "JPEG", quality=image_quality)
                cropped_files.append(str(output_file_path))

                logger.info(f"Saved: {output_file_path}")

            except Exception as e:
                logger.error(f"Error cropping object {i}: {e}")
                logger.error(traceback.format_exc())
                continue

        return cropped_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze image and provide accurate crop coordinates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Detection Methods:
  contour   - Fast, works well with clear backgrounds
  saliency  - Identifies visually interesting regions
  edge      - Fast edge detection using Canny algorithm
  grabcut   - Foreground/background segmentation (best for centered objects)
  detr      - State-of-the-art deep learning (requires: pip install transformers torch)
  rt-detr   - Real-time DETR, faster with similar accuracy (requires: pip install transformers torch)
  rf-detr   - Roboflow DETR, highly accurate detection (requires: pip install rfdetr)
  yolo      - Fast and accurate deep learning (requires: pip install ultralytics)

Examples:
  # Basic usage with contour detection
  python image_cropper.py image.jpg --visualize --crop-output output.jpg

  # Use YOLO to detect and crop a couch with custom aspect ratio
  python image_cropper.py living_room.jpg --method yolo --object couch --aspect-ratio 16:9 --crop-output couch.jpg

  # Use DETR with specific objects and padding
  python image_cropper.py photo.jpg --method detr --object person --confidence 0.8 --padding 10 --crop-output person.jpg

  # Batch crop all detected objects (YOLO/DETR only)
  python image_cropper.py family.jpg --method yolo --batch-crop --batch-output-dir ./people

  # Batch crop with custom aspect ratio and padding
  python image_cropper.py room.jpg --method detr --batch-crop --aspect-ratio 4:3 --padding 15
        """,
    )
    parser.add_argument("image_path", help="Path to the input image")
    parser.add_argument(
        "--method",
        choices=[
            "contour",
            "saliency",
            "edge",
            "grabcut",
            "detr",
            "rt-detr",
            "rf-detr",
            "yolo",
        ],
        default="contour",
        help="Detection method to use (default: contour)",
    )
    parser.add_argument(
        "--object",
        type=str,
        action="append",
        help="Target object(s) to detect (e.g., --object couch --object chair). "
        "Only works with detr/yolo methods. Can be specified multiple times.",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.7,
        help="Confidence threshold for deep learning methods (0-1, default: 0.7)",
    )
    parser.add_argument(
        "--keep-aspect", action="store_true", help="Maintain original aspect ratio"
    )
    parser.add_argument(
        "--aspect-ratio",
        type=str,
        help="Custom aspect ratio (e.g., 16:9, 4:3, 1.5, 2.35:1)",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=0,
        help="Add padding around object (percentage, 0-50)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=240,
        help="Threshold value for contour detection (0-255)",
    )
    parser.add_argument(
        "--batch-crop",
        action="store_true",
        help="Crop all detected objects individually (only works with yolo/detr)",
    )
    parser.add_argument(
        "--batch-output-dir",
        type=str,
        default="cropped_images",
        help="Output directory for batch crop (default: cropped_images)",
    )
    parser.add_argument(
        "--visualize", action="store_true", help="Show visualization of crop area"
    )
    parser.add_argument(
        "--crop-output", type=str, help="Save cropped image to this path"
    )
    parser.add_argument(
        "--vis-output", type=str, help="Save visualization to this path"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save debug images showing detection process (contour method only)",
    )

    args = parser.parse_args()

    # Check if deep learning methods are available
    if args.method == "detr" and not DETR_AVAILABLE:
        print("ERROR: DETR method requires additional packages.")
        print("Install with: pip install transformers torch")
        sys.exit(1)

    if args.method == "rt-detr" and not RTDETR_AVAILABLE:
        print("ERROR: RT-DETR method requires additional packages.")
        print("Install with: pip install transformers torch")
        sys.exit(1)

    if args.method == "rf-detr" and not RFDETR_AVAILABLE:
        print("ERROR: RF-DETR method requires additional packages.")
        print("Install with: pip install rfdetr")
        sys.exit(1)

    if args.method == "yolo" and not ULTRALYTICS_AVAILABLE:
        print("ERROR: YOLO method requires additional packages.")
        print("Install with: pip install ultralytics")
        sys.exit(1)

    # Validate batch crop requirements
    if args.batch_crop and args.method not in ["yolo", "detr", "rt-detr", "rf-detr"]:
        print(
            "ERROR: Batch crop only works with YOLO, DETR, RT-DETR, or RF-DETR methods."
        )
        sys.exit(1)

    # Validate aspect ratio arguments
    if args.keep_aspect and args.aspect_ratio:
        print("ERROR: Cannot use both --keep-aspect and --aspect-ratio together.")
        sys.exit(1)

    # Create cropper instance
    cropper = ImageCropper(args.image_path, debug=args.debug)

    # Load image
    print("\n" + "=" * 60)
    print("IMAGE ANALYSIS")
    print("=" * 60)
    cropper.load_image()

    # Handle batch crop mode
    if args.batch_crop:
        print(f"\nBatch cropping all objects using {args.method} method...")

        # Get all detections
        if args.method == "yolo":
            all_detections = cropper.find_all_objects_yolo(args.object, args.confidence)
        elif args.method == "detr":
            all_detections = cropper.find_all_objects_detr(args.object, args.confidence)
        elif args.method == "rt-detr":
            all_detections = cropper.find_all_objects_rtdetr(
                args.object, args.confidence
            )
        elif args.method == "rf-detr":
            all_detections = cropper.find_all_objects_rfdetr(
                args.object, args.confidence
            )

        if not all_detections:
            print("No objects detected!")
            sys.exit(1)

        print(f"Found {len(all_detections)} object(s)")

        # Parse aspect ratio
        target_aspect_ratio = None
        if args.keep_aspect:
            target_aspect_ratio = None  # Will use original image aspect
        elif args.aspect_ratio:
            try:
                if ":" in args.aspect_ratio:
                    w, h = map(float, args.aspect_ratio.split(":"))
                    target_aspect_ratio = w / h
                else:
                    target_aspect_ratio = float(args.aspect_ratio)
                print(f"Using custom aspect ratio: {target_aspect_ratio:.2f}:1")
            except (ValueError, ZeroDivisionError):
                print(f"WARNING: Invalid aspect ratio '{args.aspect_ratio}', ignoring")

        # Batch crop all detections
        base_name = Path(args.image_path).stem

        cropped_files = cropper.batch_crop_detections(
            detections=all_detections,
            output_dir=args.batch_output_dir,
            base_filename=base_name,
            padding_percent=args.padding,
            target_aspect_ratio=target_aspect_ratio,
            image_quality=BATCH_IMAGE_QUALITY,
        )

        print(f"\n✅ Successfully cropped {len(cropped_files)} object(s)")
        print(f"Saved to: {args.batch_output_dir}/")
        for file in cropped_files:
            print(f"  - {Path(file).name}")

        sys.exit(0)

    # Single object detection mode
    print(f"\nDetecting object using {args.method} method...")

    if args.method == "contour":
        bounds = cropper.find_object_bounds_contour(args.threshold)
    elif args.method == "saliency":
        bounds = cropper.find_object_bounds_saliency()
    elif args.method == "edge":
        bounds = cropper.find_object_bounds_edge()
    elif args.method == "grabcut":
        bounds = cropper.find_object_bounds_grabcut()
    elif args.method == "detr":
        bounds = cropper.find_object_bounds_detr(args.object, args.confidence)
    elif args.method == "rt-detr":
        bounds = cropper.find_object_bounds_rtdetr(args.object, args.confidence)
    elif args.method == "rf-detr":
        bounds = cropper.find_object_bounds_rfdetr(args.object, args.confidence)
    elif args.method == "yolo":
        bounds = cropper.find_object_bounds_yolo(args.object, args.confidence)

    print(f"Initial bounds: {bounds}")

    # Add padding if requested
    if args.padding > 0:
        bounds = cropper.add_padding(bounds, args.padding)
        print(f"Bounds with {args.padding}% padding: {bounds}")

    # Adjust for aspect ratio if requested
    if args.keep_aspect:
        bounds = cropper.adjust_crop_for_aspect_ratio(bounds)
        print(f"Bounds with original aspect ratio: {bounds}")
    elif args.aspect_ratio:
        try:
            if ":" in args.aspect_ratio:
                w, h = map(float, args.aspect_ratio.split(":"))
                target_ratio = w / h
            else:
                target_ratio = float(args.aspect_ratio)
            bounds = cropper.adjust_crop_for_aspect_ratio(bounds, target_ratio)
            print(
                f"Bounds with custom aspect ratio {args.aspect_ratio} ({target_ratio:.2f}:1): {bounds}"
            )
        except (ValueError, ZeroDivisionError):
            print(
                f"WARNING: Invalid aspect ratio '{args.aspect_ratio}', using detected bounds"
            )

    # Print final results
    print("\n" + "=" * 60)
    print("CROP COORDINATES")
    print("=" * 60)
    print(f"Tuple format: {bounds}")
    print(
        f"Left: {bounds[0]}, Upper: {bounds[1]}, Right: {bounds[2]}, Lower: {bounds[3]}"
    )

    crop_width = bounds[2] - bounds[0]
    crop_height = bounds[3] - bounds[1]
    print(f"\nCrop dimensions: {crop_width} x {crop_height} pixels")
    print(f"Crop aspect ratio: {crop_width / crop_height:.2f}:1")
    print("=" * 60)

    # Visualize if requested
    if args.visualize or args.vis_output:
        cropper.visualize_crop(bounds, args.vis_output)

    # Save cropped image if requested
    if args.crop_output:
        cropper.crop_and_save(bounds, args.crop_output)


if __name__ == "__main__":
    main()
