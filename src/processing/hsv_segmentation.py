"""Máscaras HSV clásicas para señales rojas y verdes."""

import json

import cv2
import numpy as np

from src.config import settings


class HSVSegmenter:
    def __init__(self, calibration_file=None):
        self.calibration_file = calibration_file or settings.CALIBRATION_FILE
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def _calibration(self):
        defaults = {
            "red_low": [0, 90, 65], "red_high": [10, 255, 255],
            "red2_low": [170, 90, 65], "red2_high": [179, 255, 255],
            "green_low": [55, 75, 55], "green_high": [85, 255, 255],
        }
        try:
            with open(self.calibration_file, "r", encoding="utf-8") as calibration:
                data = json.load(calibration)
            defaults.update({key: data[key] for key in defaults if key in data})
        except (OSError, ValueError, TypeError):
            pass
        return defaults

    def masks(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        calibration = self._calibration()
        red = cv2.inRange(hsv, np.array(calibration["red_low"], np.uint8), np.array(calibration["red_high"], np.uint8))
        red2 = cv2.inRange(hsv, np.array(calibration["red2_low"], np.uint8), np.array(calibration["red2_high"], np.uint8))
        green = cv2.inRange(hsv, np.array(calibration["green_low"], np.uint8), np.array(calibration["green_high"], np.uint8))
        red = cv2.bitwise_or(red, red2)
        red = self._clean(red)
        green = self._clean(green)
        return {"PARE": red, "SIGA": green}

    def _clean(self, mask):
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)

    def process(self, frame):
        """Compatibilidad: devuelve la máscara combinada de rojo y verde."""
        masks = self.masks(frame)
        return cv2.bitwise_or(masks["PARE"], masks["SIGA"])
