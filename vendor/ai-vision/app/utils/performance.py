"""Lightweight CPU/RAM usage of the current process.

Implemented with the standard library only (no psutil dependency).
The CPU value is the share of one CPU core used by this process
(all threads), so on multi-core machines it may exceed 100%.
RAM is the process' maximum resident set size where the platform
provides it; otherwise the value is ``None`` and the UI hides it.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable, Optional


def _win32_rss_mb() -> Optional[float]:
    """Resident set size on Windows via ctypes (no psutil dependency).

    Isolated helper so tests can exercise the platform branch.
    """
    try:
        import ctypes

        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _Counters()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            ctypes.sizeof(counters),
        )
        if not ok:
            return None
        return round(counters.WorkingSetSize / (1024.0 * 1024.0), 1)
    except Exception:  # noqa: BLE001 — measurement must never crash
        return None


class ProcessMonitor:
    """Periodic sampler for process CPU usage and resident memory."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last_cpu_time = self._cpu_time()
        self._last_wall = self._clock()

    @staticmethod
    def _cpu_time() -> float:
        """Total process CPU time (user + system, all threads) in seconds."""
        times = os.times()
        return times.user + times.system

    def cpu_percent(self) -> Optional[float]:
        """CPU share of one core used since the previous call (0..100+)."""
        cpu_now = self._cpu_time()
        wall_now = self._clock()
        cpu_delta = cpu_now - self._last_cpu_time
        wall_delta = wall_now - self._last_wall
        self._last_cpu_time = cpu_now
        self._last_wall = wall_now
        if wall_delta <= 0:
            return None
        return round(cpu_delta / wall_delta * 100.0, 1)

    @staticmethod
    def memory_mb() -> Optional[float]:
        """Resident set size in MB; ``None`` where the platform provides
        no measurement (the UI then shows „—", honestly)."""
        if sys.platform == "win32":
            return _win32_rss_mb()
        try:
            import resource  # noqa: PLC0415 — POSIX only

            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except (ImportError, OSError, ValueError):
            return None
        # Linux reports KiB; macOS reports bytes.
        if sys.platform == "darwin":
            return round(rss / (1024.0 * 1024.0), 1)
        return round(rss / 1024.0, 1)
