"""Orientación, escalado y extracción de las ROI del pipeline."""

import cv2

from src.config import settings


class FramePreprocessor:
    def __init__(self, width=None, rotation=None):
        self.width = width or settings.PROCESS_WIDTH
        self.rotation = settings.ROTATION if rotation is None else rotation

    def process(self, frame):
        rotation = self.rotation % 360
        if rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif rotation != 0:
            raise ValueError("ROTATION debe ser 0, 90, 180 o 270")

        height, source_width = frame.shape[:2]
        target_height = max(1, round(height * self.width / source_width))
        frame = cv2.resize(frame, (self.width, target_height), interpolation=cv2.INTER_AREA)
        frame = cv2.GaussianBlur(frame, (3, 3), 0.6)
        usable_height = max(1, int(frame.shape[0] * (2.0 / 3.0)))
        usable = frame[:usable_height]
        line_start = min(usable_height - 1, max(0, int(usable_height * settings.LINE_ROI_START)))
        signal_end = min(usable_height, max(1, int(usable_height * settings.SIGNAL_ROI_END)))
        return {
            "frame": frame,
            "usable": usable,
            "line": usable[line_start:],
            "signals": usable[:signal_end],
            "line_y": line_start,
            "signal_y": 0,
        }