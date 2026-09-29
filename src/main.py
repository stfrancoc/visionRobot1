import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.camera.stream import CameraStream
from src.config import settings
from src.processing.kmeans_segment import KMeansSegmenter
from src.utils.helpers import draw_text


def main():
    """Punto de entrada principal del sistema de visión local.

    Este flujo sigue una estructura modular para que luego puedas incorporar:
    - detección de línea,
    - análisis de octágonos para PARE/SIGA,
    - control del robot.
    """
    stream = CameraStream(url=settings.CAMERA_URL, width=settings.CAPTURE_WIDTH, height=settings.CAPTURE_HEIGHT)
    segmenter = KMeansSegmenter()

    if not stream.connect():
        print("[Main] No se pudo iniciar la captura. Revisa la URL de la cámara en .env")
        return

    try:
        frame_count = 0
        while True:
            frame = stream.read_frame()
            if frame is None:
                continue

            frame_count += 1

            # Se salta algunos frames opcionalmente para reducir carga en pruebas
            if settings.FRAME_SKIP > 0 and frame_count % (settings.FRAME_SKIP + 1) != 0:
                continue

            kmeans_result = segmenter.segment(frame)

            # Visualización de depuración
            debug = cv2.cvtColor(kmeans_result, cv2.COLOR_BGR2RGB)
            debug = cv2.cvtColor(debug, cv2.COLOR_RGB2BGR)
            draw_text(debug, f"KMeans clusters: {settings.KMEANS_CLUSTERS}", position=(10, 30))
            draw_text(debug, f"Frame: {frame_count}", position=(10, 70))

            # TODO: aquí vendrá la lógica de seguimiento de línea.
            # TODO: aquí se añadirá la detección geométrica de PARE/SIGA.
            # TODO: aquí se integrará la lógica de control del robot.

            cv2.imshow(settings.DEBUG_WINDOW_NAME, debug)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        stream.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
