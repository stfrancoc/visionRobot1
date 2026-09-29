"""Detección temporal de señales octagonales rojas y verdes, sin ML."""

from collections import deque

import cv2
import numpy as np

from src.config import settings
from src.processing.hsv_segmentation import HSVSegmenter


class SignalDetector:
    def __init__(self, segmenter=None):
        self.segmenter = segmenter or HSVSegmenter()
        self.history = deque(maxlen=max(1, settings.SIGNAL_HISTORY_SIZE))
        self.detected_signal = None
        self.last_detection = None
        self._reported = False
        self._reported_label = None

    def _find_candidates(self, mask, label):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        height, width = mask.shape
        candidates = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < settings.SIGNAL_MIN_AREA:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                continue
            polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
            if not 7 <= len(polygon) <= 9:
                continue
            x, y, box_width, box_height = cv2.boundingRect(polygon)
            box_area = box_width * box_height
            extent = area / max(1, box_area)
            circularity = 4.0 * np.pi * area / (perimeter * perimeter)
            aspect = box_width / max(1, box_height)
            if not 0.55 <= extent <= 0.95 or not 0.55 <= circularity <= 1.05 or not 0.7 <= aspect <= 1.3:
                continue
            candidates.append({"label": label, "bbox": (x, y, box_width, box_height),
                               "center": (x + box_width / 2, y + box_height / 2),
                               "area": float(area), "triggered": (y + box_height / 2) / max(1, height) >= settings.SIGNAL_TRIGGER_Y})
        return candidates

    def update(self, frame):
        masks = self.segmenter.masks(frame)
        candidates = self._find_candidates(masks["PARE"], "PARE") + self._find_candidates(masks["SIGA"], "SIGA")
        candidates.sort(key=lambda candidate: candidate["area"], reverse=True)
        self.last_detection = candidates[0] if candidates else None
        label = self.last_detection["label"] if self.last_detection else None
        triggered_label = None
        if self.last_detection and self.last_detection["triggered"]:
            triggered_label = label
        if triggered_label and triggered_label != self._reported_label:
            self._reported = False
        self.history.append((label, triggered_label is not None))
        hits = sum(item == (triggered_label, True) for item in self.history) if triggered_label else 0
        if triggered_label and hits >= settings.SIGNAL_CONFIRM_HITS and not self._reported:
            self.detected_signal = triggered_label
            self._reported = True
            self._reported_label = triggered_label
            return triggered_label
        if label is None:
            self._reported = False
            self._reported_label = None
            self.detected_signal = None
        return None

    def reset(self):
        self.history.clear()
        self.detected_signal = None
        self.last_detection = None
        self._reported = False
        self._reported_label = None
