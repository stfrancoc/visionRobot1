import time
from typing import Optional

import cv2
import numpy as np

from src.config import settings


class CameraStream:
    """Wrapper para conectar con flujos de cámara IP o MJPEG desde celular."""

    def __init__(self, url: Optional[str] = None, width: int = None, height: int = None):
        self.url = url or settings.CAMERA_URL
        self.width = width or settings.CAPTURE_WIDTH
        self.height = height or settings.CAPTURE_HEIGHT
        self.capture = None
        self._connected = False

    def connect(self) -> bool:
        """Abre la conexión con la cámara IP."""
        self.capture = cv2.VideoCapture(self.url)
        if not self.capture.isOpened():
            print(f"[Camera] No se pudo abrir la URL: {self.url}")
            return False

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._connected = True
        print(f"[Camera] Conectado a: {self.url}")
        return True

    def read_frame(self) -> Optional[np.ndarray]:
        """Lee un frame del stream. Devuelve None si no hay contenido."""
        if self.capture is None:
            return None

        ok, frame = self.capture.read()
        if not ok or frame is None:
            return None

        return frame

    def close(self):
        """Cierra la conexión con la cámara."""
        if self.capture is not None:
            self.capture.release()
        self._connected = False
        print("[Camera] Conexión cerrada.")

    @property
    def connected(self) -> bool:
        return self._connected


if __name__ == "__main__":
    cam = CameraStream()
    if cam.connect():
        try:
            while True:
                frame = cam.read_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue

                cv2.imshow("Camera Test", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            cam.close()
            cv2.destroyAllWindows()
