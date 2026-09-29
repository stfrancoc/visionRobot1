"""Detección de las señales PARE (roja) y SIGA (verde): segmentación
por color, búsqueda de la forma por contornos y confirmación temporal
para evitar falsos positivos de un solo fotograma.

Las señales definitivas son OCTÁGONOS rojo (PARE) y verde (SIGA) con
texto blanco y borde oscuro. Los umbrales de forma se calibraron
midiendo la imagen de referencia entregada por el equipo: 8 vértices,
extensión 0.824-0.826 (el valor teórico de un octágono regular es
0.828), aspecto 1.00 y circularidad 0.910.

El texto blanco abre huecos dentro de la máscara de color; el cierre
morfológico de mascaras_color() los tapa para que findContours vea un
octágono lleno y no un anillo.

Los rangos HSV siguen marcados "CALIBRAR CON VIDEO REAL" en
config.py: se fijaron con colores sintéticos y conviene afinarlos con
calibrar.py sobre la pista real, porque la iluminación del salón
cambia el matiz que ve la cámara.

Nota sobre un modo de falla conocido y NO corregido aquí a propósito:
cuando la señal PARE tapa la línea, buscar_octagonos() puede fallar
(el borde de la señal no es un octágono limpio para la cámara) pero,
sobre todo, vision/linea.py puede enganchar el borde oscuro de la señal
como si fuera la línea en las franjas que quedan tapadas. Corregirlo
en vision/linea.py no tiene sentido porque ese módulo no sabe nada de
señales; se resuelve en la integración (main.py), que sí conoce la
ROI y el color de la señal detectada aquí y puede invalidar las
franjas de línea contaminadas por ella.

Funciones puras: reciben una imagen/máscara y config, devuelven
resultados. No abren ventanas ni leen trackbars (eso vive en
main.py/calibrar.py). La única excepción de estado es
ConfirmadorSenales, que existe justamente para conservar historial
entre fotogramas (igual que EstadoLinea en vision/linea.py).

Complejidad: O(alto × ancho) de la ROI para mascaras_color() (un par de
pasadas de OpenCV por operación); O(alto × ancho + V log V) para
buscar_octagonos(), donde V es la cantidad de píxeles de contorno
(findContours es lineal en los píxeles de la máscara, approxPolyDP es
lineal en los vértices del contorno de entrada); ConfirmadorSenales.actualizar()
es O(CONFIRMAR_M) por color; detectar_senales() es la suma de todo lo
anterior.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

import config
from control.contratos import ResultadoSenales

ROJO = "PARE"
VERDE = "SIGA"


def mascaras_color(roi_hsv: np.ndarray, cfg=config) -> tuple[np.ndarray, np.ndarray]:
    """Genera las máscaras binarias de rojo (PARE) y verde (SIGA) de una
    ROI en HSV.

    El rojo se construye como la unión de dos rangos de matiz (el rojo
    da la vuelta al 0 en la rueda de color de OpenCV: 0-179). El verde
    es un solo rango, limitado para no invadir el cian del chasis.
    Ambas máscaras se limpian con apertura (quita ruido suelto) y
    cierre (tapa los huecos que dejan las letras blancas de PARE/SIGA
    dentro del octágono).

    Recibe: roi_hsv (imagen en espacio HSV, ver cv2.cvtColor con
        COLOR_BGR2HSV) y cfg (módulo config o compatible).
    Devuelve: (mascara_roja, mascara_verde), binarias (uint8, 255 =
        color detectado).
    Complejidad: O(alto × ancho) de la ROI.
    """
    rango_rojo_1 = cv2.inRange(
        roi_hsv,
        (cfg.ROJO_H_BAJO_1, cfg.ROJO_S_MIN, cfg.ROJO_V_MIN),
        (cfg.ROJO_H_ALTO_1, 255, 255),
    )
    rango_rojo_2 = cv2.inRange(
        roi_hsv,
        (cfg.ROJO_H_BAJO_2, cfg.ROJO_S_MIN, cfg.ROJO_V_MIN),
        (cfg.ROJO_H_ALTO_2, 255, 255),
    )
    mascara_roja = cv2.bitwise_or(rango_rojo_1, rango_rojo_2)

    mascara_verde = cv2.inRange(
        roi_hsv,
        (cfg.VERDE_H_BAJO, cfg.VERDE_S_MIN, cfg.VERDE_V_MIN),
        (cfg.VERDE_H_ALTO, 255, 255),
    )

    kernel = np.ones((cfg.KERNEL_MORFOLOGICO_SENALES, cfg.KERNEL_MORFOLOGICO_SENALES), np.uint8)
    mascaras_limpias = []
    for mascara in (mascara_roja, mascara_verde):
        abierta = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
        cerrada = cv2.morphologyEx(abierta, cv2.MORPH_CLOSE, kernel)
        mascaras_limpias.append(cerrada)

    return mascaras_limpias[0], mascaras_limpias[1]


def buscar_octagonos(mascara: np.ndarray, color: str, cfg=config) -> list[dict]:
    """Busca contornos con la forma de la señal (rombo/rectángulo) en
    una máscara de color, filtrando en cascada por área, número de
    vértices, extensión, relación de aspecto y circularidad.

    El nombre conserva "octagonos" por compatibilidad con el resto del
    código y las pruebas; la forma que realmente busca es la de las
    señales de la pista (ver el docstring del módulo), no un octágono.

    El filtrado en cascada evita calcular approxPolyDP/momentos sobre
    contornos que ya se descartaron por un criterio más barato (área).

    Recibe: mascara (binaria, de mascaras_color()), color ("PARE" o
        "SIGA", solo para etiquetar los candidatos) y cfg (módulo
        config o compatible).
    Devuelve: lista de dicts, uno por candidato que pasó todos los
        filtros, con claves color, centroide (tupla x, y en píxeles
        dentro de la ROI/máscara), area, bounding_rect (x, y, ancho,
        alto) y numero_vertices. Si hay varios candidatos, se
        conserva solo el de mayor área.
    Complejidad: O(alto × ancho de la mascara + suma de vértices de
        contorno de entrada de cada approxPolyDP).
    """
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidatos = []
    for contorno in contornos:
        area = cv2.contourArea(contorno)
        if area < cfg.AREA_MINIMA_SENAL_PX:
            continue

        perimetro = cv2.arcLength(contorno, True)
        aproximado = cv2.approxPolyDP(contorno, 0.02 * perimetro, True)
        numero_vertices = len(aproximado)
        if not (cfg.VERTICES_SENAL_MIN <= numero_vertices <= cfg.VERTICES_SENAL_MAX):
            continue

        x, y, ancho, alto = cv2.boundingRect(contorno)
        area_rect = ancho * alto
        if area_rect == 0:
            continue

        extension = area / area_rect
        if not (cfg.EXTENSION_SENAL_MIN <= extension <= cfg.EXTENSION_SENAL_MAX):
            continue

        aspecto = ancho / alto
        if not (cfg.ASPECTO_SENAL_MIN <= aspecto <= cfg.ASPECTO_SENAL_MAX):
            continue

        if perimetro == 0:
            continue
        circularidad = 4 * np.pi * area / (perimetro ** 2)
        if not (cfg.CIRCULARIDAD_SENAL_MIN <= circularidad <= cfg.CIRCULARIDAD_SENAL_MAX):
            continue

        momentos = cv2.moments(contorno)
        if momentos["m00"] == 0:
            continue
        centroide = (momentos["m10"] / momentos["m00"], momentos["m01"] / momentos["m00"])

        candidatos.append({
            "color": color,
            "centroide": centroide,
            "area": area,
            "bounding_rect": (x, y, ancho, alto),
            "numero_vertices": numero_vertices,
        })

    if not candidatos:
        return []

    return [max(candidatos, key=lambda candidato: candidato["area"])]


@dataclass
class ConfirmadorSenales:
    """Confirma una señal solo si aparece en varios fotogramas
    recientes, para no reaccionar a un falso positivo de un solo
    fotograma (ruido de la máscara, un reflejo).

    Mantiene, por color, un historial de los últimos CONFIRMAR_M
    fotogramas (True si hubo candidato ese fotograma, False si no).
    Se confirma cuando al menos CONFIRMAR_N de esas entradas son True.
    """

    historial_rojo: deque = field(default_factory=lambda: deque(maxlen=config.CONFIRMAR_M))
    historial_verde: deque = field(default_factory=lambda: deque(maxlen=config.CONFIRMAR_M))

    def actualizar(self, candidato_rojo: Optional[dict], candidato_verde: Optional[dict], cfg=config) -> Optional[dict]:
        """Registra el fotograma actual y decide si hay una señal
        confirmada.

        Recibe: candidato_rojo, candidato_verde (dict de
            buscar_octagonos() o None si no hubo candidato de ese
            color este fotograma) y cfg (módulo config o compatible).
        Devuelve: el dict del candidato confirmado (el de mayor área
            entre los colores confirmados, si ambos lo estuvieran a la
            vez) o None si ninguno alcanza CONFIRMAR_N apariciones en
            los últimos CONFIRMAR_M fotogramas.
        Complejidad: O(CONFIRMAR_M) (cuenta el historial de ambos colores).
        """
        self.historial_rojo.append(candidato_rojo is not None)
        self.historial_verde.append(candidato_verde is not None)

        confirmados = []
        if sum(self.historial_rojo) >= cfg.CONFIRMAR_N and candidato_rojo is not None:
            confirmados.append(candidato_rojo)
        if sum(self.historial_verde) >= cfg.CONFIRMAR_N and candidato_verde is not None:
            confirmados.append(candidato_verde)

        if not confirmados:
            return None
        return max(confirmados, key=lambda candidato: candidato["area"])


def detectar_senales(roi_bgr: np.ndarray, desplazamiento_y: int, confirmador: ConfirmadorSenales, cfg=config) -> ResultadoSenales:
    """Orquesta la detección de señales sobre una ROI: segmentación por
    color, búsqueda de octágonos, confirmación temporal y el
    ResultadoSenales final.

    Recibe: roi_bgr (imagen BGR de la ROI de señales, ver
        vision/preprocesamiento.py:recortar_zonas), desplazamiento_y
        (fila, en el fotograma completo, donde empieza esta ROI: se
        suma a las coordenadas de centroide para que en_disparo se
        calcule y se reporte en coordenadas del fotograma completo,
        no de la ROI) y confirmador (ConfirmadorSenales, se modifica
        en el sitio) y cfg (módulo config o compatible).
    Devuelve: ResultadoSenales con senal ("PARE"/"SIGA"/None),
        en_disparo (True si el centroide confirmado ya cruzó
        Y_DISPARO), candidatos (los de este fotograma, antes de
        confirmar, con el centroide ya desplazado) y mascaras
        (mascara_roja, mascara_verde).
    Complejidad: O(alto × ancho) de la ROI.
    """
    roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mascara_roja, mascara_verde = mascaras_color(roi_hsv, cfg)

    candidatos_rojos = buscar_octagonos(mascara_roja, ROJO, cfg)
    candidatos_verdes = buscar_octagonos(mascara_verde, VERDE, cfg)

    candidato_rojo = candidatos_rojos[0] if candidatos_rojos else None
    candidato_verde = candidatos_verdes[0] if candidatos_verdes else None

    todos_candidatos = candidatos_rojos + candidatos_verdes
    for candidato in todos_candidatos:
        x_centroide, y_centroide = candidato["centroide"]
        candidato["centroide"] = (x_centroide, y_centroide + desplazamiento_y)

    confirmado = confirmador.actualizar(candidato_rojo, candidato_verde, cfg)

    if confirmado is None:
        return ResultadoSenales(senal=None, en_disparo=False, candidatos=todos_candidatos, mascaras=(mascara_roja, mascara_verde))

    _, y_centroide_confirmado = confirmado["centroide"]
    alto_roi = roi_bgr.shape[0]
    y_disparo_px = cfg.Y_DISPARO * alto_roi + desplazamiento_y
    en_disparo = y_centroide_confirmado >= y_disparo_px

    return ResultadoSenales(
        senal=confirmado["color"],
        en_disparo=en_disparo,
        candidatos=todos_candidatos,
        mascaras=(mascara_roja, mascara_verde),
    )
