"""Herramienta interactiva de calibración: trackbars para ajustar en
vivo FILA_CHASIS, los límites de las ROI, el umbral de línea y los
rangos HSV de rojo/verde, viendo el resultado sobre un video real.

Uso:
    python calibrar.py --video videos/correctos/video1.mp4

Teclas: espacio pausar/reanudar, 'n' avanzar un fotograma en pausa,
'g' guardar los valores actuales en calibracion.json (config.py lo
carga automáticamente por encima de sus valores por defecto la próxima
vez que se importe), 'q'/Esc salir.

Este archivo puede abrir ventanas y leer trackbars (permitido por
CLAUDE.md junto con main.py y utils/visualizacion.py); las funciones de
vision/ que llama siguen siendo puras.
"""

import argparse
import json

import cv2

import config
from vision.captura import FuenteVideo
from vision.linea import EstadoLinea, detectar_linea, mascara_linea
from vision.preprocesamiento import preprocesar, recortar_zonas
from vision.senales import mascaras_color

NOMBRE_VENTANA = "Calibracion"

# Nombre de trackbar -> (atributo en config, máximo del trackbar). Los
# de fracción [0, 1] se escalan a un trackbar entero [0, 100] (OpenCV
# no soporta trackbars de punto flotante) y se dividen por 100 al leer.
TRACKBARS_FRACCION = [
    ("FILA_CHASIS x100", "FILA_CHASIS", 100),
    ("ROI_LINEA_INI x100", "ROI_LINEA_INICIO", 100),
    ("ROI_LINEA_FIN x100", "ROI_LINEA_FIN", 100),
    ("ROI_SENALES_INI x100", "ROI_SENALES_INICIO", 100),
    ("ROI_SENALES_FIN x100", "ROI_SENALES_FIN", 100),
]

TRACKBARS_ENTEROS = [
    ("Umbral linea", "_umbral_linea_manual", 255),
    ("Rojo H bajo 1", "ROJO_H_BAJO_1", 179),
    ("Rojo H alto 1", "ROJO_H_ALTO_1", 179),
    ("Rojo H bajo 2", "ROJO_H_BAJO_2", 179),
    ("Rojo H alto 2", "ROJO_H_ALTO_2", 179),
    ("Rojo S min", "ROJO_S_MIN", 255),
    ("Rojo V min", "ROJO_V_MIN", 255),
    ("Verde H bajo", "VERDE_H_BAJO", 179),
    ("Verde H alto", "VERDE_H_ALTO", 179),
    ("Verde S min", "VERDE_S_MIN", 255),
    ("Verde V min", "VERDE_V_MIN", 255),
]

# Claves que se guardan en calibracion.json: todas las de config salvo
# el umbral de línea manual, que no es un parámetro de config (ver
# _crear_trackbars).
CLAVES_A_GUARDAR = [atributo for _, atributo, _ in TRACKBARS_FRACCION]
CLAVES_A_GUARDAR += [atributo for _, atributo, _ in TRACKBARS_ENTEROS if atributo != "_umbral_linea_manual"]


def _crear_trackbars(valores_iniciales: dict) -> None:
    """Crea todos los trackbars de la ventana de calibración.

    Recibe: valores_iniciales (dict atributo -> valor actual, ya en la
        escala del trackbar: fracciones ×100, HSV en su escala nativa).
    Devuelve: nada.
    """
    cv2.namedWindow(NOMBRE_VENTANA)
    for nombre_trackbar, atributo, maximo in TRACKBARS_FRACCION + TRACKBARS_ENTEROS:
        cv2.createTrackbar(nombre_trackbar, NOMBRE_VENTANA, valores_iniciales[atributo], maximo, lambda _: None)


def _leer_trackbars() -> dict:
    """Lee el valor actual de todos los trackbars.

    Recibe: nada.
    Devuelve: dict atributo -> valor, con las fracciones ya divididas
        por 100 (de vuelta a [0, 1]) y los enteros HSV/umbral tal cual.
    """
    valores = {}
    for nombre_trackbar, atributo, _ in TRACKBARS_FRACCION:
        valores[atributo] = cv2.getTrackbarPos(nombre_trackbar, NOMBRE_VENTANA) / 100.0
    for nombre_trackbar, atributo, _ in TRACKBARS_ENTEROS:
        valores[atributo] = cv2.getTrackbarPos(nombre_trackbar, NOMBRE_VENTANA)
    return valores


def _guardar_calibracion(valores: dict) -> None:
    """Guarda los valores actuales (solo las claves de config, no el
    umbral manual) en calibracion.json.

    Recibe: valores (dict, salida de _leer_trackbars()).
    Devuelve: nada.
    """
    a_guardar = {clave: valores[clave] for clave in CLAVES_A_GUARDAR}
    with open(config.RUTA_CALIBRACION_VISION, "w", encoding="utf-8") as archivo:
        json.dump(a_guardar, archivo, indent=2, ensure_ascii=False)
    print(f"[calibrar] guardado en {config.RUTA_CALIBRACION_VISION}: {a_guardar}")


def _construir_mosaico_calibracion(preprocesado, roi_linea, roi_senales, valores):
    """Construye el mosaico de calibración: el fotograma original con
    las ROI dibujadas, y las tres máscaras (línea, roja, verde)
    calculadas con los valores actuales de los trackbars.

    Recibe: preprocesado (fotograma completo ya preprocesado),
        roi_linea, roi_senales (recortes de recortar_zonas()) y
        valores (dict de _leer_trackbars()).
    Devuelve: imagen BGR, el mosaico en una sola fila (original +
        3 máscaras en miniatura).
    """
    mascara_linea_img = mascara_linea(roi_linea, valores["_umbral_linea_manual"], config)

    roi_senales_hsv = cv2.cvtColor(roi_senales, cv2.COLOR_BGR2HSV)
    cfg_temporal = config_como_dict()
    for clave_hsv in (
        "ROJO_H_BAJO_1", "ROJO_H_ALTO_1", "ROJO_H_BAJO_2", "ROJO_H_ALTO_2", "ROJO_S_MIN", "ROJO_V_MIN",
        "VERDE_H_BAJO", "VERDE_H_ALTO", "VERDE_S_MIN", "VERDE_V_MIN",
    ):
        setattr(cfg_temporal, clave_hsv, valores[clave_hsv])
    mascara_roja, mascara_verde = mascaras_color(roi_senales_hsv, cfg_temporal)

    alto_lienzo = preprocesado.shape[0]
    ancho_miniatura = preprocesado.shape[1] // 3
    alto_miniatura = alto_lienzo // 3

    def _miniatura(imagen_binaria_o_bgr, etiqueta):
        if imagen_binaria_o_bgr.ndim == 2:
            imagen_bgr = cv2.cvtColor(imagen_binaria_o_bgr, cv2.COLOR_GRAY2BGR)
        else:
            imagen_bgr = imagen_binaria_o_bgr
        redimensionada = cv2.resize(imagen_bgr, (ancho_miniatura, alto_miniatura))
        cv2.putText(redimensionada, etiqueta, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        return redimensionada

    columna = cv2.vconcat([
        _miniatura(mascara_linea_img, "linea"),
        _miniatura(mascara_roja, "roja"),
        _miniatura(mascara_verde, "verde"),
    ])

    lienzo = preprocesado.copy()
    ancho = lienzo.shape[1]
    fila_chasis_px = round(alto_lienzo * valores["FILA_CHASIS"])
    fila_inicio_linea = round(fila_chasis_px * valores["ROI_LINEA_INICIO"])
    fila_fin_linea = round(fila_chasis_px * valores["ROI_LINEA_FIN"])
    fila_inicio_senales = round(fila_chasis_px * valores["ROI_SENALES_INICIO"])
    fila_fin_senales = round(fila_chasis_px * valores["ROI_SENALES_FIN"])
    cv2.rectangle(lienzo, (0, fila_inicio_linea), (ancho, fila_fin_linea), (0, 255, 0), 1)
    cv2.rectangle(lienzo, (0, fila_inicio_senales), (ancho, fila_fin_senales), (255, 0, 0), 1)
    cv2.line(lienzo, (0, fila_chasis_px), (ancho, fila_chasis_px), (0, 0, 255), 2)

    return cv2.hconcat([lienzo, columna])


def config_como_dict():
    """Envuelve el módulo config en un Namespace para poder combinarlo
    con los valores en vivo de los trackbars sin mutar config.py.

    Recibe: nada. Devuelve: argparse.Namespace con los atributos
        públicos (no-callable, sin "_" inicial) de config.
    """
    return argparse.Namespace(**{
        clave: valor for clave, valor in vars(config).items()
        if not clave.startswith("_") and not callable(valor)
    })


def ejecutar(ruta_video: str) -> None:
    """Corre el bucle de calibración sobre un video.

    Recibe: ruta_video (str).
    Devuelve: nada. Sale cuando el video termina o el usuario presiona 'q'/Esc.
    """
    fuente = FuenteVideo(ruta_video)
    estado_linea = EstadoLinea()

    valores_iniciales = {
        "FILA_CHASIS": round(config.FILA_CHASIS * 100),
        "ROI_LINEA_INICIO": round(config.ROI_LINEA_INICIO * 100),
        "ROI_LINEA_FIN": round(config.ROI_LINEA_FIN * 100),
        "ROI_SENALES_INICIO": round(config.ROI_SENALES_INICIO * 100),
        "ROI_SENALES_FIN": round(config.ROI_SENALES_FIN * 100),
        "_umbral_linea_manual": 127,
        "ROJO_H_BAJO_1": config.ROJO_H_BAJO_1,
        "ROJO_H_ALTO_1": config.ROJO_H_ALTO_1,
        "ROJO_H_BAJO_2": config.ROJO_H_BAJO_2,
        "ROJO_H_ALTO_2": config.ROJO_H_ALTO_2,
        "ROJO_S_MIN": config.ROJO_S_MIN,
        "ROJO_V_MIN": config.ROJO_V_MIN,
        "VERDE_H_BAJO": config.VERDE_H_BAJO,
        "VERDE_H_ALTO": config.VERDE_H_ALTO,
        "VERDE_S_MIN": config.VERDE_S_MIN,
        "VERDE_V_MIN": config.VERDE_V_MIN,
    }
    _crear_trackbars(valores_iniciales)

    def _procesar_y_mostrar(fotograma):
        preprocesado = preprocesar(fotograma, config)
        roi_linea, roi_senales, _, _ = recortar_zonas(preprocesado, config)
        valores = _leer_trackbars()
        mosaico = _construir_mosaico_calibracion(preprocesado, roi_linea, roi_senales, valores)
        cv2.imshow(NOMBRE_VENTANA, mosaico)
        return valores

    try:
        while True:
            ok, fotograma, _ = fuente.leer()
            if not ok:
                break

            valores = _procesar_y_mostrar(fotograma)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla in (ord("q"), 27):
                break
            if tecla == ord("g"):
                _guardar_calibracion(valores)
            if tecla == ord(" "):
                fuente.pausar(True)
                while True:
                    tecla_pausa = cv2.waitKey(0) & 0xFF
                    if tecla_pausa == ord(" "):
                        fuente.pausar(False)
                        break
                    if tecla_pausa in (ord("q"), 27):
                        return
                    if tecla_pausa == ord("g"):
                        _guardar_calibracion(_leer_trackbars())
                    if tecla_pausa == ord("n"):
                        ok, fotograma, _ = fuente.avanzar_un_fotograma()
                        if not ok:
                            return
                        _procesar_y_mostrar(fotograma)
    finally:
        fuente.liberar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    analizador = argparse.ArgumentParser(description="Herramienta de calibración interactiva.")
    analizador.add_argument("--video", required=True, help="Ruta a un video, p. ej. videos/correctos/video1.mp4")
    argumentos = analizador.parse_args()

    ejecutar(argumentos.video)
