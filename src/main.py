import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.camera.stream import CameraStream
from src.camera.web_camera import BrowserCameraServer
from src.config import settings
from src.control.bluetooth_executor import BluetoothRobotExecutor
from src.control.robot_controller import RobotController
from src.processing.hsv_segmentation import HSVSegmenter
from src.processing.line_tracking import LineTracker
from src.processing.preprocessing import FramePreprocessor
from src.processing.signal_detection import SignalDetector
from src.utils.calibration import run_calibrator
from src.utils.helpers import draw_text


def make_mosaic(original, line_mask, signal_mask, annotated):
    tile_size = (280, 180)
    tiles = []
    for image in (original, cv2.cvtColor(line_mask, cv2.COLOR_GRAY2BGR),
                  cv2.cvtColor(signal_mask, cv2.COLOR_GRAY2BGR), annotated):
        tiles.append(cv2.resize(image, tile_size, interpolation=cv2.INTER_AREA))
    return np.vstack((np.hstack((tiles[0], tiles[1])), np.hstack((tiles[2], tiles[3]))))


def main():
    parser = argparse.ArgumentParser(description="Visión clásica para robot seguidor de línea")
    parser.add_argument("--source", default=settings.CAMERA_URL, help="URL IP, índice de cámara o ruta de vídeo")
    parser.add_argument("--calibrate", action="store_true", help="Abrir calibrador HSV/umbral; S guarda en JSON")
    parser.add_argument("--robot", action="store_true", help="Conectar al robot Bluetooth de master_pc/Robot.py")
    parser.add_argument("--bluetooth-mac", default=settings.BLUETOOTH_MAC, help="MAC Bluetooth RFCOMM del robot")
    parser.add_argument("--executor-path", default=str(settings.ROBOT_EXECUTOR_PATH), help="Carpeta master_pc o ruta a Robot.py")
    parser.add_argument("--phone-camera", action="store_true", help="Recibir video desde la cámara del navegador móvil")
    parser.add_argument("--host", default=settings.PHONE_CAMERA_HOST, help="Interfaz de red del servidor web")
    parser.add_argument("--port", type=int, default=settings.PHONE_CAMERA_PORT, help="Puerto del servidor web de cámara")
    parser.add_argument("--tls-cert", default=settings.PHONE_CAMERA_TLS_CERT, help="Certificado HTTPS confiable para el teléfono")
    parser.add_argument("--tls-key", default=settings.PHONE_CAMERA_TLS_KEY, help="Clave privada del certificado HTTPS")
    args = parser.parse_args()
    if args.calibrate:
        run_calibrator(args.source)
        return

    if args.phone_camera:
        stream = BrowserCameraServer(
            host=args.host,
            port=args.port,
            tls_cert=args.tls_cert,
            tls_key=args.tls_key,
        )
    else:
        stream = CameraStream(url=args.source, width=settings.CAPTURE_WIDTH, height=settings.CAPTURE_HEIGHT)
    preprocessor = FramePreprocessor()
    line_tracker = LineTracker()
    hsv_segmenter = HSVSegmenter()
    signal_detector = SignalDetector(hsv_segmenter)
    controller = RobotController()
    robot = None
    started = stream.start() if args.phone_camera else stream.connect()
    if not started:
        print("[Main] No se pudo iniciar la captura. Revisa --source o CAMERA_URL en .env")
        return
    if args.robot:
        robot = BluetoothRobotExecutor(args.bluetooth_mac, args.executor_path)
        try:
            robot.connect()
        except Exception:
            stream.close()
            raise
        print("[Main] Robot conectado; comandos Bluetooth en hilo independiente.")

    frame_count = 0
    try:
        while True:
            frame = stream.read_frame()
            if frame is None:
                time.sleep(0.005)
                continue
            frame_count += 1
            if settings.FRAME_SKIP > 0 and frame_count % (settings.FRAME_SKIP + 1) != 0:
                continue

            stages = preprocessor.process(frame)
            line = line_tracker.update(stages["line"])
            signal = signal_detector.update(stages["signals"])
            left, right = controller.update(line["error"], signal, line["angle"], line["confidence"])
            if robot is not None:
                robot.set_speeds(left, right)
                if robot.last_error is not None:
                    print(f"[Bluetooth] Envío detenido: {robot.last_error}")
                    robot.last_error = None

            annotated = stages["frame"].copy()
            cv2.line(annotated, (0, stages["line_y"]), (annotated.shape[1] - 1, stages["line_y"]), (255, 180, 0), 1)
            detection = signal_detector.last_detection
            if detection:
                x, y, width, height = detection["bbox"]
                cv2.rectangle(annotated, (x, y), (x + width, y + height), (0, 255, 0), 2)
                draw_text(annotated, detection["label"], (x, max(20, y - 6)))
            draw_text(annotated, f"{controller.state} | error {line['error']:.2f} | conf {line['confidence']:.2f}")
            draw_text(annotated, f"angle {line['angle']:.1f} | L {left:.0f} R {right:.0f} | frame {frame_count}", (10, 58))

            signal_masks = hsv_segmenter.masks(stages["signals"])
            signal_mask = cv2.bitwise_or(signal_masks["PARE"], signal_masks["SIGA"])
            cv2.imshow(settings.DEBUG_WINDOW_NAME, make_mosaic(stages["frame"], line["mask"], signal_mask, annotated))
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("c"):
                run_calibrator(args.source)
    finally:
        controller.stop()
        if robot is not None:
            robot.set_speeds(0, 0)
            robot.close()
        stream.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
