"""Shared helpers for turning detector/model images into line masks."""

from __future__ import annotations

import cv2
import numpy as np


def decode_line_map_png(raw: bytes, *, source: str) -> tuple[np.ndarray, np.ndarray]:
    """Decode a grayscale image into ``True=line`` mask and 0..1 confidence.

    Both local detectors and cloud image editing may return black-on-white or
    white-on-black images. The border median is a stable background heuristic;
    Otsu then avoids a provider-specific fixed threshold.
    """

    gray = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"{source} returned an invalid image")
    normalized = gray.astype(np.float32) / 255.0
    border = np.concatenate(
        (normalized[0], normalized[-1], normalized[:, 0], normalized[:, -1])
    )
    confidence = 1.0 - normalized if float(np.median(border)) >= 0.5 else normalized
    _, mask = cv2.threshold(
        np.clip(confidence * 255, 0, 255).astype(np.uint8),
        0,
        255,
        cv2.THRESH_BINARY | cv2.THRESH_OTSU,
    )
    return mask > 0, confidence
