"""Mosaico de depuración para main.py: el fotograma original con las
ROI/detecciones dibujadas encima, junto a las tres máscaras binarias
(línea, roja, verde), en una sola imagen para mostrar o guardar.

Este módulo SÍ puede dibujar (rectangle, circle, line, putText) y
combinar imágenes: es el lugar permitido por CLAUDE.md para eso, junto
con main.py y calibrar.py. Las funciones de vision/ siguen siendo
puras y no se tocan aquí.
"""

import cv2
import numpy as np

import config
from vision.linea import analizar_franjas


def _dibujar_rois(lienzo, fila_chasis, fila_inicio_linea, fila_fin_linea, fila_inicio_senales, fila_fin_senales):
    """Dibuja los rectángulos de ROI de línea/señales y la línea de
    FILA_CHASIS sobre el lienzo.

    Recibe: lienzo (imagen BGR, se modifica en el sitio) y las filas
        (en píxeles) que delimitan cada zona.
    Devuelve: nada.
    """
    ancho = lienzo.shape[1]
    cv2.rectangle(lienzo, (0, fila_inicio_linea), (ancho, fila_fin_linea), (0, 255, 0), 1)
    cv2.rectangle(lienzo, (0, fila_inicio_senales), (ancho, fila_fin_senales), (255, 0, 0), 1)
    cv2.line(lienzo, (0, fila_chasis), (ancho, fila_chasis), (0, 0, 255), 2)


def _dibujar_linea_disparo(lienzo, fila_inicio_senales, fila_fin_senales, cfg=config):
    """Dibuja la línea de disparo (Y_DISPARO) dentro de la ROI de señales.

    Recibe: lienzo (se modifica en el sitio), fila_inicio_senales,
        fila_fin_senales (píxeles en el lienzo) y cfg (módulo config).
    Devuelve: nada.
    """
    alto_roi_senales = fila_fin_senales - fila_inicio_senales
    fila_disparo = fila_inicio_senales + round(alto_roi_senales * cfg.Y_DISPARO)
    ancho = lienzo.shape[1]
    cv2.line(lienzo, (0, fila_disparo), (ancho, fila_disparo), (0, 165, 255), 1)


def _dibujar_deteccion_linea(lienzo, resultado_linea, mascara_linea_img, fila_offset_roi, cfg=config):
    """Dibuja los centros de franja de la línea, la línea que los une y
    marca (en rojo tenue) las franjas sin centro válido.

    Recibe: lienzo (se modifica en el sitio), resultado_linea
        (ResultadoLinea), mascara_linea_img (máscara de
        vision/linea.py, usada solo para recalcular los centros de
        franja a dibujar), fila_offset_roi (fila del lienzo donde
        empieza la ROI de línea) y cfg (módulo config).
    Devuelve: nada.
    """
    alto_roi, ancho_roi = mascara_linea_img.shape
    limites_franja = [round(alto_roi * i / cfg.N_FRANJAS) for i in range(cfg.N_FRANJAS + 1)]
    centros = analizar_franjas(mascara_linea_img, resultado_linea.error, cfg)

    puntos = []
    for indice, centro_col in enumerate(centros):
        fila_centro_lienzo = (limites_franja[indice] + limites_franja[indice + 1]) // 2 + fila_offset_roi
        if centro_col is None:
            cv2.line(lienzo, (0, fila_centro_lienzo), (ancho_roi, fila_centro_lienzo), (0, 0, 128), 1)
            continue
        punto = (round(centro_col), fila_centro_lienzo)
        puntos.append(punto)
        cv2.circle(lienzo, punto, 4, (0, 255, 255), -1)

    for punto_anterior, punto_siguiente in zip(puntos, puntos[1:]):
        cv2.line(lienzo, punto_anterior, punto_siguiente, (0, 255, 255), 2)


def _dibujar_deteccion_senales(lienzo, resultado_senales):
    """Dibuja los candidatos de señal (boundingRect + etiqueta de color
    y área) detectados en este fotograma.

    Recibe: lienzo (se modifica en el sitio), resultado_senales
        (ResultadoSenales, con candidatos ya en coordenadas del
        fotograma completo: ver vision/senales.py:detectar_senales).
    Devuelve: nada.
    """
    for candidato in resultado_senales.candidatos:
        x, y, ancho, alto = candidato["bounding_rect"]
        color_dibujo = (0, 0, 255) if candidato["color"] == "PARE" else (0, 255, 0)
        cv2.rectangle(lienzo, (x, y), (x + ancho, y + alto), color_dibujo, 2)
        cv2.putText(
            lienzo, f"{candidato['color']} area={int(candidato['area'])}",
            (x, max(0, y - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_dibujo, 1,
        )


def _dibujar_texto_estado(lienzo, comando, resultado_linea, resultado_senales, fps, latencia_total_s):
    """Escribe el texto de depuración (estado, error, ángulo, confianza,
    acción, FPS, latencia) en la esquina del lienzo.

    Recibe: lienzo (se modifica en el sitio), comando (ComandoRobot de
        este fotograma), resultado_linea, resultado_senales, fps
        (float) y latencia_total_s (float, segundos).
    Devuelve: nada.
    """
    color_estado = (0, 255, 0) if resultado_linea.valida else (0, 0, 255)
    lineas_texto = [
        f"estado={comando.estado} accion={comando.accion}",
        f"error={resultado_linea.error:+.2f} angulo={resultado_linea.angulo:+.2f} confianza={resultado_linea.confianza}",
        f"senal={resultado_senales.senal} en_disparo={resultado_senales.en_disparo}",
        f"FPS={fps:.1f} latencia_total={latencia_total_s * 1000:.1f}ms",
    ]
    for indice, texto in enumerate(lineas_texto):
        y = lienzo.shape[0] - 15 - (len(lineas_texto) - 1 - indice) * 18
        color = color_estado if indice == 1 else (255, 255, 255)
        cv2.putText(lienzo, texto, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def _redimensionar_para_mosaico(imagen, ancho_objetivo, alto_objetivo):
    """Redimensiona una imagen (color o de un solo canal) al tamaño de
    celda del mosaico, convirtiendo a BGR si hace falta.

    Recibe: imagen (array 2D u 3D), ancho_objetivo, alto_objetivo (int).
    Devuelve: imagen BGR (alto_objetivo, ancho_objetivo, 3).
    """
    if imagen.ndim == 2:
        imagen = cv2.cvtColor(imagen, cv2.COLOR_GRAY2BGR)
    return cv2.resize(imagen, (ancho_objetivo, alto_objetivo))


def construir_mosaico(
    fotograma_preprocesado,
    resultado_linea,
    resultado_senales,
    mascara_linea_img,
    comando,
    fila_chasis,
    fila_inicio_linea,
    fila_fin_linea,
    fila_inicio_senales,
    fila_fin_senales,
    fps,
    latencia_total_s,
    cfg=config,
):
    """Construye el mosaico completo de depuración: el fotograma
    original con ROI/detecciones/texto dibujados, junto a las tres
    máscaras binarias en miniatura.

    Recibe: fotograma_preprocesado (imagen BGR ya redimensionada y
        suavizada, ver vision/preprocesamiento.py), resultado_linea,
        resultado_senales (salidas de visión de este fotograma),
        mascara_linea_img (máscara de vision/linea.py), comando
        (ComandoRobot emitido este fotograma), fila_chasis,
        fila_inicio_linea, fila_fin_linea, fila_inicio_senales,
        fila_fin_senales (píxeles en el fotograma preprocesado), fps,
        latencia_total_s (float) y cfg (módulo config o compatible).
    Devuelve: imagen BGR (el original a la izquierda, ancho normal;
        las tres máscaras en miniatura apiladas a la derecha).
    Complejidad: O(ancho × alto) del fotograma (dibujar es O(N_FRANJAS)
        y O(candidatos), ambos despreciables frente al resize).
    """
    lienzo = fotograma_preprocesado.copy()
    _dibujar_rois(lienzo, fila_chasis, fila_inicio_linea, fila_fin_linea, fila_inicio_senales, fila_fin_senales)
    _dibujar_linea_disparo(lienzo, fila_inicio_senales, fila_fin_senales, cfg)
    _dibujar_deteccion_linea(lienzo, resultado_linea, mascara_linea_img, fila_inicio_linea, cfg)
    _dibujar_deteccion_senales(lienzo, resultado_senales)
    _dibujar_texto_estado(lienzo, comando, resultado_linea, resultado_senales, fps, latencia_total_s)

    alto_lienzo = lienzo.shape[0]
    ancho_miniatura = lienzo.shape[1] // 3
    alto_miniatura = alto_lienzo // 3

    mascara_roja, mascara_verde = resultado_senales.mascaras if resultado_senales.mascaras else (
        np.zeros_like(mascara_linea_img), np.zeros_like(mascara_linea_img)
    )

    miniaturas = [
        _redimensionar_para_mosaico(mascara_linea_img, ancho_miniatura, alto_miniatura),
        _redimensionar_para_mosaico(mascara_roja, ancho_miniatura, alto_miniatura),
        _redimensionar_para_mosaico(mascara_verde, ancho_miniatura, alto_miniatura),
    ]
    etiquetas = ["mascara linea", "mascara roja", "mascara verde"]
    for miniatura, etiqueta in zip(miniaturas, etiquetas):
        cv2.putText(miniatura, etiqueta, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    columna_miniaturas = np.zeros((alto_lienzo, ancho_miniatura, 3), dtype=np.uint8)
    for indice, miniatura in enumerate(miniaturas):
        columna_miniaturas[indice * alto_miniatura:(indice + 1) * alto_miniatura, :] = miniatura

    return np.hstack([lienzo, columna_miniaturas])
