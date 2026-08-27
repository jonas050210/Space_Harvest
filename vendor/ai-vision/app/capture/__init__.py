"""Local session capture — video recording and still snapshots.

Privacy: frames never leave this machine. Recording starts only when
the user presses RECORD. Nothing is uploaded, streamed or analysed
off-device.
"""

from app.capture.recorder import RecordingInfo, SessionRecorder

__all__ = ["SessionRecorder", "RecordingInfo"]
