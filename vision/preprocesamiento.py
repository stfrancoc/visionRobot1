"""Preprocesamiento de fotogramas: redimensionado, suavizado y recorte
de las regiones de interés (ROI) de línea y señales.

Funciones puras: reciben una imagen (y config) y devuelven resultados,
sin abrir ventanas ni leer trackbars (eso vive en main.py/calibrar.py).
"""

import cv2
import numpy as np

import config


def preprocesar(fotograma: np.ndarray, cfg=config) -> np.ndarray:
    """Redimensiona y suaviza un fotograma para el resto del pipeline.

    La rotación (si el stream llega girado porque el teléfono guarda la
    orientación como metadato en vez de rotar los píxeles) se aplica en
    vision/captura.py, ANTES de que el fotograma llegue aquí: esta
    función asume que ya está en la orientación correcta.

    Recibe: fotograma (imagen BGR de OpenCV) y cfg (módulo config, o uno
        compatible para pruebas: se usa por parámetro, no importado
        directo, para poder probar con valores distintos sin mutar el
        config real).
    Devuelve: imagen redimensionada a cfg.ANCHO_PROCESO de ancho
        (manteniendo la proporción original) y suavizada con
        GaussianBlur.
    Complejidad: O(ancho × alto) del fotograma de entrada.
    """
    alto_original, ancho_original = fotograma.shape[:2]
    escala = cfg.ANCHO_PROCESO / ancho_original
    alto_nuevo = round(alto_original * escala)

    redimensionado = cv2.resize(fotograma, (cfg.ANCHO_PROCESO, alto_nuevo))

    kernel = cfg.KERNEL_GAUSSIANO
    suavizado = cv2.GaussianBlur(redimensionado, (kernel, kernel), 0)

    return suavizado


def recortar_zonas(imagen: np.ndarray, cfg=config) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Recorta la ROI de línea y la ROI de señales de un fotograma ya
    preprocesado, descartando la franja inferior donde aparece el
    chasis del propio robot.

    La cámara del teléfono va montada sobre el mBot mirando adelante y
    abajo: el tercio inferior del cuadro es chasis/baterías, no piso.
    Las baterías son verdes y serían un falso positivo directo de SIGA
    (también verde) si no se descartaran antes de buscar señales. Por
    eso ninguna ROI incluye nada en fila >= cfg.FILA_CHASIS.

    Recibe: imagen (imagen ya preprocesada, ver preprocesar()) y cfg
        (módulo config o compatible, igual que preprocesar()).
    Devuelve: (roi_linea, roi_senales, desplazamiento_y_linea,
        desplazamiento_y_senales). Los desplazamientos son la fila (en
        píxeles, en la imagen de entrada) donde empieza cada ROI: se
        necesitan para volver a ubicar en el fotograma completo
        cualquier coordenada calculada dentro de la ROI recortada.
    Complejidad: O(1) (slicing de NumPy, sin copiar datos).
    """
    alto = imagen.shape[0]
    fila_chasis = round(alto * cfg.FILA_CHASIS)
    altura_disponible = fila_chasis

    fila_inicio_linea = round(altura_disponible * cfg.ROI_LINEA_INICIO)
    fila_fin_linea = round(altura_disponible * cfg.ROI_LINEA_FIN)
    fila_inicio_senales = round(altura_disponible * cfg.ROI_SENALES_INICIO)
    fila_fin_senales = round(altura_disponible * cfg.ROI_SENALES_FIN)

    roi_linea = imagen[fila_inicio_linea:fila_fin_linea, :]
    roi_senales = imagen[fila_inicio_senales:fila_fin_senales, :]

    return roi_linea, roi_senales, fila_inicio_linea, fila_inicio_senales
