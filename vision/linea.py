"""Detección de la línea a seguir: máscara binaria, análisis por
franjas horizontales y el ResultadoLinea que consume control/.

Escena real (confirmada con videos/correctos/ y videos/fallos/): pista
blanca con una línea negra ancha vista DE FRENTE, no un piso en
perspectiva que se estreche a lo lejos. Por eso el ancho de la línea es
aproximadamente constante en todo el cuadro (ver ANCHO_TIPICO_PX en
config.py) y no depende de en qué franja se mida.

Funciones puras: reciben una imagen/máscara y config, devuelven
resultados. No abren ventanas ni leen trackbars.

Complejidad: O(alto × ancho) de la ROI para mascara_linea() (una pasada
de OpenCV por operación); O(alto × ancho) para analizar_franjas() (la
proyección por columnas recorre cada píxel una vez, el resto es lineal
en el ancho); detectar_linea() es la suma de ambas.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

import config
from control.contratos import ResultadoLinea
from vision.umbral_kmeans import calcular_umbral


@dataclass
class EstadoLinea:
    """Estado que debe conservarse entre fotogramas para detectar_linea().

    umbral_actual: último umbral válido de K-Means (se reutiliza
        mientras no toque recalcularlo o K-Means no encuentre una
        separación clara).
    fotogramas_desde_kmeans: contador para saber cuándo recalcular el
        umbral (cada config.PERIODO_KMEANS fotogramas).
    centro_anterior: último centro de línea conocido, en fracción de
        ancho [-1, 1] respecto al centro de la ROI (0 = centrado). Se
        usa como referencia para la franja más cercana al chasis
        cuando no hay una franja inferior con la que comparar.
    """

    umbral_actual: float = 127.0
    # Arranca ya "vencido" (en vez de 0) para que el primer fotograma
    # SIEMPRE calcule el umbral con K-Means en vez de usar el valor por
    # defecto de umbral_actual, que no tiene por qué ser apropiado para
    # la iluminación real del video.
    fotogramas_desde_kmeans: int = field(default_factory=lambda: 10**9)
    centro_anterior: float = 0.0


def mascara_linea(roi: np.ndarray, umbral: float, cfg=config) -> np.ndarray:
    """Genera la máscara binaria línea/piso de una ROI.

    Recibe: roi (imagen BGR de la región de interés), umbral (float,
        ver vision/umbral_kmeans.py) y cfg (módulo config o compatible).
    Devuelve: máscara binaria (uint8, 255 = línea) tras escala de
        grises, threshold BINARY_INV (la línea es oscura: por debajo
        del umbral) y apertura+cierre morfológicos para limpiar ruido.
    Complejidad: O(alto × ancho) de la ROI.
    """
    gris = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(gris, umbral, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((cfg.KERNEL_MORFOLOGICO, cfg.KERNEL_MORFOLOGICO), np.uint8)
    abierta = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel)
    cerrada = cv2.morphologyEx(abierta, cv2.MORPH_CLOSE, kernel)

    return cerrada


def _tramos_continuos(fila_binaria: np.ndarray) -> list[tuple[int, int]]:
    """Encuentra los tramos continuos de columnas en 255 (línea) de una
    proyección binaria de una sola fila.

    Recibe: fila_binaria (array 1D de 0/255, una fila de la máscara o
        la suma por columnas ya binarizada).
    Devuelve: lista de (columna_inicio, columna_fin) con fin exclusivo,
        uno por cada tramo continuo de columnas en 255.
    Complejidad: O(ancho).
    """
    es_linea = fila_binaria > 0
    cambios = np.diff(es_linea.astype(np.int8))
    inicios = list(np.where(cambios == 1)[0] + 1)
    fines = list(np.where(cambios == -1)[0] + 1)

    if es_linea[0]:
        inicios.insert(0, 0)
    if es_linea[-1]:
        fines.append(len(es_linea))

    return list(zip(inicios, fines))


def _ancho_equivalente(franja: np.ndarray, inicio: int, fin: int) -> float:
    """Ancho "equivalente" de un tramo: su área real dividida por la
    altura de la franja, en vez del ancho crudo de su bounding box.

    Una línea recta y una línea inclinada del mismo grosor ocupan la
    misma ÁREA dentro de una franja, pero la inclinada proyecta un
    ancho de bounding box mucho mayor (un segmento a 45° de 70px de
    grosor proyecta ~140px de ancho). Filtrar por ancho de bbox
    confunde esa inclinación normal con ruido; el área normalizada por
    la altura de franja no varía con la inclinación, así que separa
    mejor la línea real (inclinada o no) de algo genuinamente más
    ancho, como la franja transversal de una señal (que sí llena por
    completo su bounding box).

    Recibe: franja (recorte de la máscara para esta franja), inicio,
        fin (columnas del tramo dentro de esa franja).
    Devuelve: float, área del tramo (píxeles en 255) dividida por la
        altura de la franja en píxeles.
    Complejidad: O(alto_franja × (fin - inicio)).
    """
    alto_franja = franja.shape[0]
    area = int((franja[:, inicio:fin] > 0).sum())
    return area / alto_franja


def analizar_franjas(mascara: np.ndarray, centro_anterior: float, cfg=config) -> list[float | None]:
    """Divide la máscara en N_FRANJAS horizontales y estima el centro
    de la línea en cada una.

    Recibe: mascara (máscara binaria de mascara_linea()), centro_anterior
        (float en fracción de ancho [-1, 1], usado como referencia para
        la franja más cercana al chasis, la última) y cfg (módulo
        config o compatible).
    Devuelve: lista de N_FRANJAS elementos, cada uno el centro de la
        línea en esa franja (float, columna en píxeles dentro de la
        ROI) o None si la franja no tiene un tramo de línea válido (sea
        porque no hay ningún tramo aceptable, o porque el elegido por
        ancho quedó demasiado lejos de la franja vecina: ver
        UMBRAL_CONTINUIDAD_PX). El orden va de la franja MÁS LEJANA
        (índice 0) a la MÁS CERCANA al chasis (índice N_FRANJAS-1): así
        la selección voraz avanza de abajo hacia arriba, de la franja
        más confiable (más cerca del robot, menos ambigüedad) hacia la
        menos confiable.
    Complejidad: O(alto × ancho) de la máscara.
    """
    alto, ancho = mascara.shape
    limites_franja = np.linspace(0, alto, cfg.N_FRANJAS + 1, dtype=int)

    centros_de_abajo_hacia_arriba = []
    centro_referencia_px = (centro_anterior + 1) / 2 * ancho
    hay_referencia_confiable = False

    for indice_franja in range(cfg.N_FRANJAS - 1, -1, -1):
        fila_inicio = limites_franja[indice_franja]
        fila_fin = limites_franja[indice_franja + 1]
        franja = mascara[fila_inicio:fila_fin, :]

        proyeccion = franja.sum(axis=0)
        fila_binaria = (proyeccion > 0).astype(np.uint8) * 255

        tramos = _tramos_continuos(fila_binaria)
        tramos_validos = [
            (inicio, fin) for inicio, fin in tramos
            if (fin - inicio) >= cfg.ANCHO_MIN_PX
            and _ancho_equivalente(franja, inicio, fin) <= cfg.ANCHO_EQUIVALENTE_MAX_PX
        ]

        if not tramos_validos:
            centros_de_abajo_hacia_arriba.append(None)
            continue

        # Entre los tramos válidos puede haber ruido angosto (reflejos
        # del sensor, bordes) que por casualidad quede más cerca de la
        # referencia que la línea real, sobre todo si la referencia ya
        # viene desviada de un fotograma anterior con error. Por eso
        # primero se descartan los tramos mucho más angostos (por área
        # equivalente) que el más ancho disponible en ESTA franja (la
        # línea real casi siempre es el tramo más ancho, el ruido es
        # angosto): solo entre los que queden se desempata por cercanía
        # a la referencia.
        ancho_maximo_en_franja = max(_ancho_equivalente(franja, inicio, fin) for inicio, fin in tramos_validos)
        candidatos = [
            (inicio, fin) for inicio, fin in tramos_validos
            if _ancho_equivalente(franja, inicio, fin) >= ancho_maximo_en_franja * cfg.PROPORCION_MINIMA_ANCHO_CANDIDATO
        ]

        centro_tramo_elegido = min(
            candidatos,
            key=lambda tramo: abs((tramo[0] + tramo[1]) / 2 - centro_referencia_px),
        )
        centro_px = (centro_tramo_elegido[0] + centro_tramo_elegido[1]) / 2

        # Continuidad entre franjas: si el centro elegido se aleja
        # demasiado de la franja vecina ya confirmada, es más probable
        # que se haya enganchado a ruido que a un giro real de la línea
        # (la línea no puede saltar de posición de una franja a la
        # siguiente). Esa franja se marca inválida, y su centro NO se
        # usa como referencia para la próxima: de lo contrario, un
        # engancho incorrecto se autoconfirma y contamina el resto del
        # fotograma (y, vía centro_anterior, también fotogramas
        # siguientes).
        if hay_referencia_confiable and abs(centro_px - centro_referencia_px) > cfg.UMBRAL_CONTINUIDAD_PX:
            centros_de_abajo_hacia_arriba.append(None)
            continue

        centros_de_abajo_hacia_arriba.append(centro_px)
        centro_referencia_px = centro_px
        hay_referencia_confiable = True

    return list(reversed(centros_de_abajo_hacia_arriba))


def detectar_linea(roi: np.ndarray, estado_linea: EstadoLinea, cfg=config) -> tuple[ResultadoLinea, np.ndarray]:
    """Orquesta la detección de línea sobre una ROI: umbral adaptativo,
    máscara, análisis por franjas y el ResultadoLinea final.

    Recibe: roi (imagen BGR de la ROI de línea, ver
        vision/preprocesamiento.py:recortar_zonas), estado_linea
        (EstadoLinea, se modifica en el sitio para el siguiente
        fotograma) y cfg (módulo config o compatible).
    Devuelve: (resultado, mascara).
        resultado: ResultadoLinea con error y ángulo en [-1, 1] (0 =
            centrado/alineado, calculados con las franjas más cercana y
            más lejana válidas), confianza = número de franjas válidas,
            y valida=True si hay al menos cfg.FRANJAS_MINIMAS_VALIDAS.
        mascara: máscara binaria usada, para depuración/visualización.
    Complejidad: O(alto × ancho) de la ROI.
    """
    gris = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    if estado_linea.fotogramas_desde_kmeans >= cfg.PERIODO_KMEANS:
        nuevo_umbral = calcular_umbral(gris)
        if nuevo_umbral is not None:
            estado_linea.umbral_actual = nuevo_umbral
        estado_linea.fotogramas_desde_kmeans = 0
    else:
        estado_linea.fotogramas_desde_kmeans += 1

    mascara = mascara_linea(roi, estado_linea.umbral_actual, cfg)
    centros = analizar_franjas(mascara, estado_linea.centro_anterior, cfg)

    centros_validos = [(indice, centro) for indice, centro in enumerate(centros) if centro is not None]
    confianza = len(centros_validos)

    if confianza < cfg.FRANJAS_MINIMAS_VALIDAS:
        return ResultadoLinea(error=0.0, angulo=0.0, confianza=confianza, valida=False), mascara

    ancho = mascara.shape[1]
    centro_cuadro = ancho / 2

    indice_cercana, centro_cercana = centros_validos[-1]
    indice_lejana, centro_lejana = centros_validos[0]

    error = (centro_cercana - centro_cuadro) / centro_cuadro
    error = max(-1.0, min(1.0, error))

    if indice_lejana == indice_cercana:
        angulo = 0.0
    else:
        angulo = (centro_lejana - centro_cercana) / centro_cuadro
        angulo = max(-1.0, min(1.0, angulo))

    estado_linea.centro_anterior = error

    return ResultadoLinea(error=error, angulo=angulo, confianza=confianza, valida=True), mascara
