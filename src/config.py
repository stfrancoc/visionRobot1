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
    DEBUG_WINDOW_NAME = os.getenv("DEBUG_WINDOW_NAME", "Robot Vision")
    USE_MJPEG = os.getenv("USE_MJPEG", "false").lower() == "true"


settings = Settings()
