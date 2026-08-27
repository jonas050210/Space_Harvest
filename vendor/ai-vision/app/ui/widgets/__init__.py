"""Reusable GUI widgets of the main window."""

from app.ui.widgets.analysis_panel import AnalysisPanel
from app.ui.widgets.ai_panel import AIPanel
from app.ui.widgets.camera_panel import CameraPanel
from app.ui.widgets.gaze_panel import GazePanel
from app.ui.widgets.header_bar import HeaderBar
from app.ui.widgets.image_panel import ImagePanel
from app.ui.widgets.insights_panel import InsightsPanel
from app.ui.widgets.modules_panel import ModulesPanel
from app.ui.widgets.status_panel import StatusPanel
from app.ui.widgets.system_panel import SystemPanel
from app.ui.widgets.video_widget import VideoWidget
from app.ui.widgets.vision_panel import VisionPanel
from app.ui.widgets.live_state_panel import LiveStatePanel
from app.ui.widgets.preview_workspace import PreviewWorkspace
from app.ui.widgets.image_analysis_panel import ImageAnalysisPanel
from app.ui.widgets.gallery_panel import GalleryPanel
from app.ui.widgets.activity_bar import ActivityBar
from app.ui.widgets.inspector_panel import InspectorPanel
from app.ui.widgets.vision_controls import VisionControlsPanel

__all__ = [
    "AIPanel",
    "AnalysisPanel",
    "ActivityBar",
    "CameraPanel",
    "GalleryPanel",
    "GazePanel",
    "HeaderBar",
    "ImageAnalysisPanel",
    "ImagePanel",
    "InsightsPanel",
    "InspectorPanel",
    "LiveStatePanel",
    "ModulesPanel",
    "PreviewWorkspace",
    "StatusPanel",
    "SystemPanel",
    "VideoWidget",
    "VisionControlsPanel",
    "VisionPanel",
]
