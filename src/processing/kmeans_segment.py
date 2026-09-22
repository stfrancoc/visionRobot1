import cv2
import numpy as np
from sklearn.cluster import KMeans

from src.config import settings


class KMeansSegmenter:
    """Prueba de concepto: segmentación por K-means por cuadro.

    Este módulo se mantiene separado para que luego pueda ser reemplazado o
    combinado con segmentación HSV y operaciones morfológicas.
    """

    def __init__(self, n_clusters: int = None, max_iter: int = None, downscale: float = None):
        self.n_clusters = n_clusters or settings.KMEANS_CLUSTERS
        self.max_iter = max_iter or settings.KMEANS_MAX_ITER
        self.downscale = downscale if downscale is not None else settings.KMEANS_DOWNSCALE

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Reduce la resolución de la imagen para acelerar el cálculo del K-means en tiempo real."""
        if self.downscale < 1.0 and self.downscale > 0:
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (max(1, int(w * self.downscale)), max(1, int(h * self.downscale))))
            return small
        return frame

    def segment(self, frame: np.ndarray) -> np.ndarray:
        """Aplica K-Means sobre el frame original y devuelve una máscara/imagen segmentada."""
        small = self.preprocess(frame)

        # Convertimos a un array 2D de píxeles: (N, 3)
        pixels = small.reshape((-1, 3)).astype(np.float32)

        # K-Means clásico de scikit-learn
        kmeans = KMeans(n_clusters=self.n_clusters, n_init=10, max_iter=self.max_iter, random_state=42)
        labels = kmeans.fit_predict(pixels)

        # Reemplazar cada píxel por el centroide del clúster asignado
        segmented = kmeans.cluster_centers_[labels].reshape(small.shape)

        # Redimensiona de regreso si hubo downscale
        if self.downscale < 1.0 and self.downscale > 0:
            segmented = cv2.resize(segmented.astype(np.uint8), (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_NEAREST)

        return segmented.astype(np.uint8)


def run_kmeans_demo(frame: np.ndarray, n_clusters: int = None) -> np.ndarray:
    """Helper simple para pruebas rápidas en local. Retorna la imagen segmentada."""
    segmenter = KMeansSegmenter(n_clusters=n_clusters or settings.KMEANS_CLUSTERS)
    return segmenter.segment(frame)


if __name__ == "__main__":
    # Demo local con cámara web (si la tienes disponible)
    import time

    cap = cv2.VideoCapture(0)
    seg = KMeansSegmenter()

    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir la cámara local.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        segmented = seg.segment(frame)
        cv2.imshow("Original", frame)
        cv2.imshow("KMeans", segmented)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
