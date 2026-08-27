"""Canonical hand skeleton topology (index pairs of the 21-landmark hand model).

Static data extracted verbatim from the official MediaPipe project
(``mediapipe/python/solutions/hands_connections.py``, Apache-2.0,
https://github.com/google-ai-edge/mediapipe). Vendored like the face mesh
topology so no runtime introspection of legacy modules is needed.

Landmark ids: 0 = wrist, 1-4 = thumb, 5-8 = index, 9-12 = middle,
13-16 = ring, 17-20 = pinky.
"""

from __future__ import annotations

HAND_CONNECTIONS: frozenset[tuple[int, int]] = frozenset([
    (0, 1),
    (0, 5),
    (0, 17),
    (1, 2),
    (2, 3),
    (3, 4),
    (5, 6),
    (5, 9),
    (6, 7),
    (7, 8),
    (9, 10),
    (9, 13),
    (10, 11),
    (11, 12),
    (13, 14),
    (13, 17),
    (14, 15),
    (15, 16),
    (17, 18),
    (18, 19),
    (19, 20),
])
