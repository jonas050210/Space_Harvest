"""Utility helpers: paths, logging, FPS meter, process monitor."""

from app.utils.fps import FPSMeter
from app.utils.logging_setup import get_logger, set_debug, setup_logging
from app.utils.performance import ProcessMonitor
from app.utils.paths import (
    PROJECT_ROOT,
    data_dir,
    logs_dir,
    models_dir,
    settings_path,
)

__all__ = [
    "FPSMeter",
    "get_logger",
    "set_debug",
    "setup_logging",
    "ProcessMonitor",
    "PROJECT_ROOT",
    "data_dir",
    "logs_dir",
    "models_dir",
    "settings_path",
]
