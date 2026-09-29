"""Script de prueba manual (NO es unittest) para vision/captura.py,
vision/preprocesamiento.py y vision/linea.py: abre un video, dibuja las
ROI de línea y señales, la detección de línea (centros de franja, la
línea que los une, la máscara) y muestra FPS y error.

Sirve para verificar antes de escribir el resto de la detección:
1. Que la orientación del video sea correcta (si sale acostado, ajustar
   config.ROTACION).
2. Que FILA_CHASIS/ROI_LINEA_*/ROI_SENALES_* queden bien ubicadas
   (el chasis fuera de cuadro, la línea dentro de su ROI, las señales
   dentro de la suya).
3. Que los centros de franja detectados caigan sobre la línea real.

Uso:
    python -m pruebas.probar_captura_preprocesamiento videos/correctos/video4.mp4

Controles: 'q' salir, espacio pausar/reanudar, 'n' avanzar un fotograma
en pausa, 'm' mostrar/ocultar la máscara binaria en una ventana aparte.
"""

import argparse
import time

import cv2

import config
from vision.captura import FuenteVideo
from vision.linea import EstadoLinea, analizar_franjas, detectar_linea
from vision.preprocesamiento import preprocesar, recortar_zonas

NOMBRE_VENTANA = "Captura, preprocesamiento y linea"
NOMBRE_VENTANA_MASCARA = "Mascara"


def _dibujar_rois(lienzo, fila_chasis, fila_inicio_linea, fila_fin_linea, fila_inicio_senales, fila_fin_senales):
    """Dibuja los rectángulos de ROI y la línea de FILA_CHASIS.

    Recibe: lienzo (imagen sobre la que dibujar, se modifica en el
        sitio) y las filas (en píxeles) que delimitan cada zona.
    Devuelve: nada.
    Complejidad: O(1).
    """
    ancho = lienzo.shape[1]

    cv2.rectangle(lienzo, (0, fila_inicio_linea), (ancho, fila_fin_linea), (0, 255, 0), 1)
    cv2.rectangle(lienzo, (0, fila_inicio_senales), (ancho, fila_fin_senales), (255, 0, 0), 1)
    cv2.line(lienzo, (0, fila_chasis), (ancho, fila_chasis), (0, 0, 255), 2)


def _dibujar_deteccion_linea(lienzo, resultado, mascara, fila_offset_roi, cfg):
    """Dibuja los centros de franja, la línea que los une y el texto
    de error/ángulo/confianza sobre el fotograma completo.

    Recibe: lienzo (imagen del fotograma completo, se modifica en el
        sitio), resultado (ResultadoLinea de detectar_linea()), mascara
        (máscara binaria usada), fila_offset_roi (fila, en el fotograma
        completo, donde empieza la ROI de línea: los centros de franja
        vienen en coordenadas de la ROI, hay que desplazarlos) y cfg
        (módulo config).
    Devuelve: nada.
    Complejidad: O(N_FRANJAS).
    """
    alto_roi, ancho_roi = mascara.shape
    limites_franja = [round(alto_roi * i / cfg.N_FRANJAS) for i in range(cfg.N_FRANJAS + 1)]

    centros = analizar_franjas(mascara, resultado.error, cfg)

    puntos = []
    for indice, centro_col in enumerate(centros):
        fila_centro_roi = (limites_franja[indice] + limites_franja[indice + 1]) // 2
        fila_centro_lienzo = fila_centro_roi + fila_offset_roi

        if centro_col is None:
            cv2.line(
                lienzo,
                (0, fila_centro_lienzo), (ancho_roi, fila_centro_lienzo),
                (0, 0, 128), 1,
            )
            continue

        punto = (round(centro_col), fila_centro_lienzo)
        puntos.append(punto)
        cv2.circle(lienzo, punto, 4, (0, 255, 255), -1)

    for punto_anterior, punto_siguiente in zip(puntos, puntos[1:]):
        cv2.line(lienzo, punto_anterior, punto_siguiente, (0, 255, 255), 2)

    color_estado = (0, 255, 0) if resultado.valida else (0, 0, 255)
    texto = f"error={resultado.error:+.2f} angulo={resultado.angulo:+.2f} confianza={resultado.confianza}/{cfg.N_FRANJAS}"
    cv2.putText(lienzo, texto, (5, lienzo.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_estado, 2)


def ejecutar_prueba(ruta_video: str) -> None:
    """Corre el bucle de prueba sobre un video.

    Recibe: ruta_video (str, ruta a un archivo en videos/correctos/ o
        videos/fallos/).
    Devuelve: nada. Sale cuando el video termina o el usuario presiona 'q'.
    Complejidad: O(n) sobre la cantidad de fotogramas del video.
    """
    fuente = FuenteVideo(ruta_video)
    estado_linea = EstadoLinea()
    cv2.namedWindow(NOMBRE_VENTANA)
    mostrar_mascara = False

    tiempo_fotograma_anterior = time.perf_counter()
    fps = 0.0

    def _procesar_y_mostrar(fotograma):
        nonlocal fps
        preprocesado = preprocesar(fotograma, config)
        roi_linea, roi_senales, fila_inicio_linea, fila_inicio_senales = recortar_zonas(preprocesado, config)

        resultado, mascara = detectar_linea(roi_linea, estado_linea, config)

        alto = preprocesado.shape[0]
        fila_chasis = round(alto * config.FILA_CHASIS)
        fila_fin_linea = round(fila_chasis * config.ROI_LINEA_FIN)
        fila_fin_senales = round(fila_chasis * config.ROI_SENALES_FIN)

        lienzo = preprocesado.copy()
        _dibujar_rois(lienzo, fila_chasis, fila_inicio_linea, fila_fin_linea, fila_inicio_senales, fila_fin_senales)
        _dibujar_deteccion_linea(lienzo, resultado, mascara, fila_inicio_linea, config)
        cv2.putText(lienzo, f"FPS: {fps:.1f}", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow(NOMBRE_VENTANA, lienzo)
        if mostrar_mascara:
            cv2.imshow(NOMBRE_VENTANA_MASCARA, mascara)
        elif cv2.getWindowProperty(NOMBRE_VENTANA_MASCARA, cv2.WND_PROP_VISIBLE) == 1:
            cv2.destroyWindow(NOMBRE_VENTANA_MASCARA)

    try:
        while True:
            ok, fotograma, _ = fuente.leer()
            if not ok:
                break

            ahora = time.perf_counter()
            duracion_fotograma = ahora - tiempo_fotograma_anterior
            tiempo_fotograma_anterior = ahora
            if duracion_fotograma > 0:
                fps = 1.0 / duracion_fotograma

            _procesar_y_mostrar(fotograma)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord("q"):
                break
            if tecla == ord("m"):
                mostrar_mascara = not mostrar_mascara
            if tecla == ord(" "):
                fuente.pausar(True)
                while True:
                    tecla_pausa = cv2.waitKey(0) & 0xFF
                    if tecla_pausa == ord(" "):
                        fuente.pausar(False)
                        break
                    if tecla_pausa == ord("q"):
                        return
                    if tecla_pausa == ord("m"):
                        mostrar_mascara = not mostrar_mascara
                        _procesar_y_mostrar(fotograma)
                    if tecla_pausa == ord("n"):
                        ok, fotograma, _ = fuente.avanzar_un_fotograma()
                        if not ok:
                            return
                        _procesar_y_mostrar(fotograma)
    finally:
        fuente.liberar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    analizador = argparse.ArgumentParser(description="Prueba manual de captura, preprocesamiento y deteccion de linea.")
    analizador.add_argument("ruta_video", help="Ruta a un video, p. ej. videos/correctos/video4.mp4")
    argumentos = analizador.parse_args()

    ejecutar_prueba(argumentos.ruta_video)
