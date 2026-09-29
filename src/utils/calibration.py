"""Calibrador local HSV/umbral con OpenCV Trackbars y guardado JSON."""

import json
from pathlib import Path

import cv2
import numpy as np

from src.config import settings


TRACKBARS = {
    "red_low": (0, 0, 0), "red_high": (10, 255, 255),
    "red2_low": (170, 0, 0), "red2_high": (179, 255, 255),
    "green_low": (55, 0, 0), "green_high": (85, 255, 255),
}


def save_calibration(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as calibration:
        json.dump(values, calibration, indent=2)


def run_calibrator(source):
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"No se pudo abrir la fuente de calibración: {source}")

    window = "HSV Calibration"
    cv2.namedWindow(window)
    for name, initial in TRACKBARS.items():
        for channel, value in zip(("H", "S", "V"), initial):
            maximum = 179 if channel == "H" else 255
            cv2.createTrackbar(f"{name}_{channel}", window, value, maximum, lambda _: None)
    cv2.createTrackbar("line_threshold", window, settings.LINE_THRESHOLD, 255, lambda _: None)
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                if capture.get(cv2.CAP_PROP_FRAME_COUNT) > 0:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            values = {}
            preview = {}
            for name in ("red_low", "red2_low", "green_low"):
                low = [cv2.getTrackbarPos(f"{name}_{channel}", window) for channel in ("H", "S", "V")]
                high_name = name.replace("low", "high")
                high = [cv2.getTrackbarPos(f"{high_name}_{channel}", window) for channel in ("H", "S", "V")]
                values[name], values[high_name] = low, high
                preview[name] = cv2.inRange(hsv, np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
            red = cv2.bitwise_or(preview["red_low"], preview["red2_low"])
            combined = cv2.bitwise_or(red, preview["green_low"])
            cv2.imshow("Calibration Mask", combined)
            cv2.imshow("Calibration Source", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                values["line_threshold"] = cv2.getTrackbarPos("line_threshold", window)
                save_calibration(settings.CALIBRATION_FILE, values)
                print(f"[Calibration] Guardada en {settings.CALIBRATION_FILE}")
            elif key in (ord("q"), 27):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()