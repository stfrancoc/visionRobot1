"""Umbral adaptativo por K-Means para separar la línea (oscura) del
resto de la escena.

Un umbral fijo no aguanta cambios de iluminación entre videos ni sombras
dentro de un mismo video; K-Means agrupa los píxeles de la ROI por su
nivel de gris y el umbral se deriva de los centroides, adaptándose a
cada fotograma.

Se usa K=3, no K=2, porque la escena real tiene TRES poblaciones de
gris, no dos: la pista blanca (~220), la línea negra (~35) y el borde
de la mesa/madera que rodea la pista (~100-150). Con K=2, en cuanto la
madera ocupa suficiente área del cuadro, K-Means la agrupa junto con la
línea y el umbral salta al punto medio equivocado: medido sobre las
grabaciones test1-test4, el umbral pasaba de ~118 a ~163 y la máscara
de línea pasaba de ~15% a ~46% de píxeles blancos, marcando toda la
madera como si fuera línea (el robot seguía el borde de la pista en vez
de la línea, y terminaba saliéndose).

Con K=3 los tres grupos se separan, y el umbral se toma entre el
centroide más oscuro (la línea) y el intermedio (la madera): así tanto
la madera como la pista quedan FUERA de la máscara.

Función pura: recibe una imagen y parámetros, devuelve un resultado. No
abre ventanas ni lee trackbars (eso vive en main.py/calibrar.py).
"""

import numpy as np
from sklearn.cluster import KMeans

import config


def calcular_umbral(roi_gris: np.ndarray, tamano_muestra: int = None) -> float | None:
    """Calcula un umbral que deja SOLO la línea por debajo, usando
    K-Means sobre una submuestra aleatoria de píxeles de la ROI.

    Con config.KMEANS_GRUPOS = 3 (ver el docstring del módulo), el
    umbral se toma entre el centroide más oscuro (la línea) y el
    siguiente (la madera del borde de la pista), de modo que la madera
    quede fuera de la máscara. Con KMEANS_GRUPOS = 2 se comporta como
    antes: punto medio entre los dos únicos centroides.

    Recibe: roi_gris (imagen en escala de grises, un solo canal) y
        tamano_muestra (cuántos píxeles muestrear al azar; si es None
        usa config.TAMANO_MUESTRA_KMEANS).
    Devuelve: float con el umbral, o None si el centroide más oscuro y
        el siguiente quedan demasiado cerca (config.
        DIFERENCIA_MINIMA_CENTROIDES): en ese caso no hay separación
        clara en este fotograma (p. ej. la línea salió del cuadro y
        solo queda pista y madera) y quien llama debe conservar el
        umbral anterior en vez de adoptar uno que no significa nada.
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

    grupos = min(config.KMEANS_GRUPOS, len(np.unique(muestra)))
    if grupos < 2:
        return None

    kmeans = KMeans(n_clusters=grupos, n_init=config.KMEANS_N_INIT, random_state=config.KMEANS_SEMILLA)
    kmeans.fit(muestra)

    centroides = sorted(centroide[0] for centroide in kmeans.cluster_centers_)
    centroide_linea = centroides[0]
    centroide_siguiente = centroides[1]

    if centroide_siguiente - centroide_linea < config.DIFERENCIA_MINIMA_CENTROIDES:
        return None

    return (centroide_linea + centroide_siguiente) / 2.0
