"""Canonical body pose topology (index pairs of the 33-landmark pose model).

Static data extracted verbatim from the official MediaPipe project
(``mediapipe/python/solutions/pose_connections.py``, Apache-2.0,
https://github.com/google-ai-edge/mediapipe). Vendored like the face/hand
topologies so no runtime introspection of legacy modules is needed.

Landmark ids (pose model): 0 nose, 7/8 ears, 11/12 shoulders,
13/14 elbows, 15/16 wrists, 23/24 hips, 25/26 knees, 27/28 ankles,
29/30 heels, 31/32 foot indices.
"""

from __future__ import annotations

POSE_CONNECTIONS: frozenset[tuple[int, int]] = frozenset([
    (0, 1),
    (0, 4),
    (1, 2),
    (2, 3),
    (3, 7),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (11, 23),
    (12, 14),
    (12, 24),
    (13, 15),
    (14, 16),
    (15, 17),
    (15, 19),
    (15, 21),
    (16, 18),
    (16, 20),
    (16, 22),
    (17, 19),
    (18, 20),
    (23, 24),
    (23, 25),
    (24, 26),
    (25, 27),
    (26, 28),
    (27, 29),
    (27, 31),
    (28, 30),
    (28, 32),
    (29, 31),
    (30, 32),
])
