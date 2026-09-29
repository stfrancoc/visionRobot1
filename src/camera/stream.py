import threading
import time
from typing import Optional

import cv2
import numpy as np

from src.config import settings


class CameraStream:
    """Lee cámara, stream IP o archivo de vídeo en un hilo de captura."""

    def __init__(self, url: Optional[str] = None, width: int = None, height: int = None):
        self.url = settings.CAMERA_URL if url is None else url
        if isinstance(self.url, str) and self.url.isdigit():
            self.url = int(self.url)
        self.width = width or settings.CAPTURE_WIDTH
        self.height = height or settings.CAPTURE_HEIGHT
        self.capture = None
        self._connected = False
        self._thread = None
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._frame_id = 0
        self.source = None

    def connect(self) -> bool:
        """Abre la fuente y comienza a conservar únicamente el frame más reciente."""
        self.capture = cv2.VideoCapture(self.url)

        if not self.capture.isOpened():
            print(f"[Camera] No se pudo abrir la URL: {self.url}")
            if isinstance(self.url, str) and self.url.lower().startswith(("http://", "https://", "rtsp://")):
                print("[Camera] Intentando fallback a la cámara local (device 0)...")
            else:
                return False
            self.capture = cv2.VideoCapture(0)

        if not self.capture.isOpened():
            print(f"[Camera] Tampoco se pudo abrir la cámara local. Verifica la URL o la cámara del PC.")
            return False

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._connected = True
        self.source = self.url if isinstance(self.url, str) else "Cámara local"
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        self._thread.start()
        print(f"[Camera] Captura iniciada: {self.source}")
        return True

    def _capture_loop(self):
        while not self._stop_event.is_set():
            ok, frame = self.capture.read()
            if not ok or frame is None:
                if self.capture.get(cv2.CAP_PROP_FRAME_COUNT) > 0:
                    self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.01)
                continue
            with self._frame_lock:
                self._latest_frame = frame
                self._frame_id += 1

    def read_frame(self) -> Optional[np.ndarray]:
        """Devuelve una copia del último frame disponible sin bloquear la captura."""
        with self._frame_lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def close(self):
        """Cierra la conexión con la cámara."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self.capture is not None:
            self.capture.release()
        with self._frame_lock:
            self._latest_frame = None
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
