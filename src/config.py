import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    CAMERA_URL = os.getenv("CAMERA_URL", "http://192.168.1.10:8080/video")
    CAPTURE_WIDTH = int(os.getenv("CAPTURE_WIDTH", "640"))
    CAPTURE_HEIGHT = int(os.getenv("CAPTURE_HEIGHT", "480"))
    FRAME_SKIP = int(os.getenv("FRAME_SKIP", "0"))
    KMEANS_CLUSTERS = int(os.getenv("KMEANS_CLUSTERS", "4"))
    KMEANS_MAX_ITER = int(os.getenv("KMEANS_MAX_ITER", "25"))
    KMEANS_DOWNSCALE = float(os.getenv("KMEANS_DOWNSCALE", "0.5"))
    PROCESS_WIDTH = int(os.getenv("PROCESS_WIDTH", "280"))
    ROTATION = int(os.getenv("ROTATION", "0"))
    LINE_ROI_START = float(os.getenv("LINE_ROI_START", "0.48"))
    SIGNAL_ROI_END = float(os.getenv("SIGNAL_ROI_END", "0.78"))
    LINE_RECALIBRATE_EVERY = int(os.getenv("LINE_RECALIBRATE_EVERY", "12"))
    LINE_THRESHOLD = int(os.getenv("LINE_THRESHOLD", "100"))
    LINE_MIN_BAND_PIXELS = int(os.getenv("LINE_MIN_BAND_PIXELS", "3"))
    SIGNAL_MIN_AREA = int(os.getenv("SIGNAL_MIN_AREA", "180"))
    SIGNAL_CONFIRM_HITS = int(os.getenv("SIGNAL_CONFIRM_HITS", "3"))
    SIGNAL_HISTORY_SIZE = int(os.getenv("SIGNAL_HISTORY_SIZE", "5"))
    SIGNAL_TRIGGER_Y = float(os.getenv("SIGNAL_TRIGGER_Y", "0.65"))
    STOP_SECONDS = float(os.getenv("STOP_SECONDS", "3.0"))
    RESUME_IGNORE_SECONDS = float(os.getenv("RESUME_IGNORE_SECONDS", "2.0"))
    BASE_SPEED = float(os.getenv("BASE_SPEED", "90"))
    KP = float(os.getenv("KP", "0.7"))
    KD = float(os.getenv("KD", "0.18"))
    KA = float(os.getenv("KA", "0.35"))
    MAX_TURN = float(os.getenv("MAX_TURN", "100"))
    LOST_LINE_CONFIDENCE = float(os.getenv("LOST_LINE_CONFIDENCE", "0.12"))
    CALIBRATION_FILE = Path(os.getenv("CALIBRATION_FILE", str(BASE_DIR / "calibration.json")))
    ROBOT_EXECUTOR_PATH = Path(os.getenv("ROBOT_EXECUTOR_PATH") or (
        BASE_DIR.parent / "robotEjecutor" / "practica-vision-artificial-robotica" / "master_pc"
    ))
    BLUETOOTH_MAC = os.getenv("BLUETOOTH_MAC", "")
    BLUETOOTH_PORT = int(os.getenv("BLUETOOTH_PORT", "1"))
    ROBOT_TURN_DEADBAND = float(os.getenv("ROBOT_TURN_DEADBAND", "25"))
    ROBOT_MIN_PULSE_INTERVAL = float(os.getenv("ROBOT_MIN_PULSE_INTERVAL", "0.14"))
    ROBOT_MAX_PULSE_INTERVAL = float(os.getenv("ROBOT_MAX_PULSE_INTERVAL", "0.8"))
    PHONE_CAMERA_HOST = os.getenv("PHONE_CAMERA_HOST", "0.0.0.0")
    PHONE_CAMERA_PORT = int(os.getenv("PHONE_CAMERA_PORT", "5000"))
    PHONE_CAMERA_TLS_CERT = os.getenv("PHONE_CAMERA_TLS_CERT", "")
    PHONE_CAMERA_TLS_KEY = os.getenv("PHONE_CAMERA_TLS_KEY", "")
    DEBUG_WINDOW_NAME = os.getenv("DEBUG_WINDOW_NAME", "Robot Vision")
    USE_MJPEG = os.getenv("USE_MJPEG", "false").lower() == "true"


settings = Settings()
