"""Seguimiento clásico de línea con franjas y K-Means dinámico K=2."""

import json

import cv2
import numpy as np

from src.config import settings


class LineTracker:
    def __init__(self, recalibrate_every=None, calibration_file=None):
        self.recalibrate_every = max(1, recalibrate_every or settings.LINE_RECALIBRATE_EVERY)
        self.calibration_file = calibration_file or settings.CALIBRATION_FILE
        self.frame_count = 0
        self.threshold = settings.LINE_THRESHOLD
        self.previous_error = 0.0
        self.last_result = None
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    def _configured_threshold(self):
        try:
            with open(self.calibration_file, "r", encoding="utf-8") as calibration:
                return int(json.load(calibration).get("line_threshold", settings.LINE_THRESHOLD))
        except (OSError, ValueError, TypeError):
            return settings.LINE_THRESHOLD

    def _dynamic_threshold(self, gray):
        sample = cv2.resize(gray, (max(1, gray.shape[1] // 3), max(1, gray.shape[0] // 3)))
        pixels = sample.reshape((-1, 1)).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        _, labels, centers = cv2.kmeans(pixels, 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        centers = centers.flatten()
        self.threshold = int(np.mean(centers))
        return centers

    @staticmethod
    def _runs(columns):
        indices = np.flatnonzero(columns)
        if indices.size == 0:
            return []
        splits = np.where(np.diff(indices) > 1)[0] + 1
        return [group for group in np.split(indices, splits) if group.size]

    def update(self, line_roi):
        gray = cv2.cvtColor(line_roi, cv2.COLOR_BGR2GRAY) if line_roi.ndim == 3 else line_roi.copy()
        self.frame_count += 1
        if self.frame_count == 1:
            self.threshold = self._configured_threshold()
        if self.frame_count % self.recalibrate_every == 0:
            centers = self._dynamic_threshold(gray)
        else:
            centers = None
        _, mask = cv2.threshold(gray, self.threshold, 255, cv2.THRESH_BINARY_INV)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)

        height, width = mask.shape
        band_height = max(1, height // 4)
        centers_by_band = []
        visible = 0
        for band_index in range(4):
            y0 = band_index * band_height
            y1 = height if band_index == 3 else min(height, (band_index + 1) * band_height)
            projection = np.count_nonzero(mask[y0:y1], axis=0)
            runs = [run for run in self._runs(projection >= max(1, settings.LINE_MIN_BAND_PIXELS))
                    if 2 <= run.size <= max(3, int(width * 0.35))]
            if not runs:
                continue
            expected_x = width * 0.5 + self.previous_error * width * 0.5
            chosen = min(runs, key=lambda run: abs(float(run.mean()) - expected_x))
            centers_by_band.append((float(chosen.mean()), (y0 + y1) * 0.5))
            visible += 1

        if centers_by_band:
            weights = np.array([1.0 + y / max(1, height) for _, y in centers_by_band])
            x_values = np.array([x for x, _ in centers_by_band])
            center_x = float(np.average(x_values, weights=weights))
            error = (center_x - width / 2) / max(1, width / 2)
            if len(centers_by_band) >= 2:
                top_x, bottom_x = centers_by_band[0][0], centers_by_band[-1][0]
                angle = float(np.degrees(np.arctan2(bottom_x - top_x, height)))
            else:
                angle = 0.0
            confidence = min(1.0, visible / 4.0) * min(1.0, float(np.count_nonzero(mask)) / max(1, height * width * 0.18))
            self.previous_error = float(error)
        else:
            error, angle, confidence = self.previous_error, 0.0, 0.0

        result = {"error": float(error), "angle": angle, "confidence": float(confidence),
                  "mask": mask, "threshold": self.threshold, "band_centers": centers_by_band,
                  "kmeans_centers": None if centers is None else centers.tolist()}
        self.last_result = result
        return result
