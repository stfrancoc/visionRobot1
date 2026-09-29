"""Umbral adaptativo por K-Means para separar la línea (oscura) del
piso (claro).

Un umbral fijo no aguanta cambios de iluminación entre videos ni sombras
dentro de un mismo video; K-Means con K=2 separa los píxeles de la ROI
en dos grupos (línea y piso) y el punto medio entre sus centroides es
un umbral que se adapta a cada fotograma.

Función pura: recibe una imagen y parámetros, devuelve un resultado. No
abre ventanas ni lee trackbars (eso vive en main.py/calibrar.py).
"""

import numpy as np
from sklearn.cluster import KMeans

import config


def calcular_umbral(roi_gris: np.ndarray, tamano_muestra: int = None) -> float | None:
    """Calcula un umbral de separación línea/piso con K-Means (K=2)
    sobre una submuestra aleatoria de píxeles de la ROI.

    Recibe: roi_gris (imagen en escala de grises, un solo canal) y
        tamano_muestra (cuántos píxeles muestrear al azar; si es None
        usa config.TAMANO_MUESTRA_KMEANS).
    Devuelve: float con el punto medio entre los dos centroides, o None
        si los centroides quedan demasiado cerca (config.
        DIFERENCIA_MINIMA_CENTROIDES): en ese caso no hay separación
        clara línea/piso en este fotograma (p. ej. la línea salió del
        cuadro) y quien llama debe conservar el umbral anterior en vez
        de adoptar uno que no significa nada.
    Complejidad: O(tamano_muestra) para el ajuste de K-Means (no O(n)
        sobre todos los píxeles de la ROI).
    """
    if tamano_muestra is None:
        tamano_muestra = config.TAMANO_MUESTRA_KMEANS

    pixeles = roi_gris.reshape(-1, 1)
    cantidad_pixeles = pixeles.shape[0]
    tamano_muestra = min(tamano_muestra, cantidad_pixeles)

    indices_muestra = np.random.choice(cantidad_pixeles, size=tamano_muestra, replace=False)
    muestra = pixeles[indices_muestra].astype(np.float32)

    kmeans = KMeans(n_clusters=2, n_init=config.KMEANS_N_INIT, random_state=config.KMEANS_SEMILLA)
    kmeans.fit(muestra)

    centroides = sorted(centroide[0] for centroide in kmeans.cluster_centers_)
    centroide_oscuro, centroide_claro = centroides

    if centroide_claro - centroide_oscuro < config.DIFERENCIA_MINIMA_CENTROIDES:
        return None

    return (centroide_oscuro + centroide_claro) / 2.0
