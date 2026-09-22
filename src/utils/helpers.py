import cv2
import numpy as np


def resize_with_aspect(frame: np.ndarray, max_width: int = 640, max_height: int = 480) -> np.ndarray:
    """Redimensiona una imagen manteniendo proporción."""
    h, w = frame.shape[:2]
    scale = min(max_width / w, max_height / h) if w > 0 and h > 0 else 1.0
    if scale >= 1.0:
        return frame
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def draw_text(frame: np.ndarray, text: str, position=(10, 30), color=(0, 255, 255), font_scale=0.7):
    """Dibuja texto en un frame para depuración."""
    cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 2, cv2.LINE_AA)
    return frame
