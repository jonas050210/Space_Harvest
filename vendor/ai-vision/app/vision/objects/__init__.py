"""Object detection and tracking modules."""

from app.vision.objects.detection import ObjectDetectionModule
from app.vision.objects.labels import COCO_LABELS
from app.vision.objects.tracker import ObjectTracker
from app.vision.objects.tracking import ObjectTrackingModule

__all__ = [
    "ObjectDetectionModule",
    "ObjectTrackingModule",
    "ObjectTracker",
    "COCO_LABELS",
]
