"""Pruebas de detección de señales (vision/senales.py) con imágenes
sintéticas generadas con NumPy/OpenCV: octágonos rojo y verde dibujados
con fillPoly (la forma real de las señales de la pista), y formas que
deben rechazarse (franja transversal muy alargada, círculo).

La forma sintética es un octágono porque es lo que se midió en la
imagen de referencia de las señales definitivas: 8 vértices, extensión
0.824-0.826, aspecto 1.00, circularidad 0.910 — un octágono regular
(ver el docstring de vision/senales.py).
"""

import unittest

import cv2
import numpy as np

import config
from vision.senales import ConfirmadorSenales, buscar_octagonos, detectar_senales, mascaras_color

ALTO = 300
ANCHO = 300
GRIS_FONDO = (200, 200, 200)  # BGR: fondo neutro, ni rojo ni verde.

ROJO_BGR = (20, 20, 200)  # Rojo saturado, dentro de ROJO_H_BAJO_1/ROJO_S_MIN/ROJO_V_MIN.
VERDE_BGR = (20, 180, 20)  # Verde saturado, dentro de VERDE_H_BAJO/VERDE_H_ALTO.
ROSADO_BGR = (180, 140, 230)  # Matiz distinto al rojo de la señal: no debe pasar mascaras_color().


def _vertices_octagono(centro: tuple[int, int], radio: int) -> np.ndarray:
    """Genera los 8 vértices de un octágono regular (la forma real de
    la señal).

    Recibe: centro (x, y) y radio (px, del centro a cada vértice).
    Devuelve: array (8, 2) int32, listo para cv2.fillPoly.
    """
    angulos = np.linspace(0, 2 * np.pi, 8, endpoint=False) + np.pi / 8
    cx, cy = centro
    vertices = np.array([
        (cx + radio * np.cos(angulo), cy + radio * np.sin(angulo))
        for angulo in angulos
    ], dtype=np.int32)
    return vertices


def _imagen_con_octagono(color_bgr, centro=(150, 150), radio=60, con_texto=False) -> np.ndarray:
    """Construye una imagen BGR sintética con un octágono relleno.

    Recibe: color_bgr (tupla BGR de la señal), centro, radio y
        con_texto (si True, dibuja "PARE" en blanco encima, como el
        texto que llevan las señales reales: el cierre morfológico de
        mascaras_color() debe tapar esos huecos para que el contorno
        siga siendo un octágono).
    Devuelve: imagen BGR (ALTO, ANCHO, 3).
    """
    imagen = np.full((ALTO, ANCHO, 3), GRIS_FONDO, dtype=np.uint8)
    vertices = _vertices_octagono(centro, radio)
    cv2.fillPoly(imagen, [vertices], color_bgr)

    if con_texto:
        cv2.putText(
            imagen, "PARE", (centro[0] - radio // 2, centro[1] + 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
        )

    return imagen


def _imagen_con_rectangulo(color_bgr, centro=(150, 150), medio_ancho=60, medio_alto=40) -> np.ndarray:
    """Construye una imagen BGR sintética con un rectángulo relleno del
    color dado (debe rechazarse: un rectángulo no es un octágono, y
    falla por vértices, extensión y circularidad).
    """
    imagen = np.full((ALTO, ANCHO, 3), GRIS_FONDO, dtype=np.uint8)
    x, y = centro
    cv2.rectangle(
        imagen,
        (x - medio_ancho, y - medio_alto), (x + medio_ancho, y + medio_alto),
        color_bgr, -1,
    )
    return imagen


def _imagen_con_franja_transversal(color_bgr, fila=150, grosor=35) -> np.ndarray:
    """Construye una imagen BGR sintética con una franja que cruza todo
    el ancho del cuadro (debe rechazarse: su relación de aspecto es muy
    superior a ASPECTO_SENAL_MAX).
    """
    imagen = np.full((ALTO, ANCHO, 3), GRIS_FONDO, dtype=np.uint8)
    cv2.rectangle(imagen, (0, fila - grosor // 2), (ANCHO - 1, fila + grosor // 2), color_bgr, -1)
    return imagen


def _imagen_con_circulo(color_bgr, centro=(150, 150), radio=60) -> np.ndarray:
    """Construye una imagen BGR sintética con un círculo relleno del
    color dado (debe rechazarse: approxPolyDP le da más vértices que
    una señal, y su circularidad supera CIRCULARIDAD_SENAL_MAX).
    """
    imagen = np.full((ALTO, ANCHO, 3), GRIS_FONDO, dtype=np.uint8)
    cv2.circle(imagen, centro, radio, color_bgr, -1)
    return imagen


class PruebasMascarasColor(unittest.TestCase):
    def test_mascara_roja_detecta_rojo_y_no_verde(self):
        imagen = _imagen_con_octagono(ROJO_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, mascara_verde = mascaras_color(hsv, config)
        self.assertGreater(int((mascara_roja > 0).sum()), 0)
        self.assertEqual(int((mascara_verde > 0).sum()), 0)

    def test_mascara_verde_detecta_verde_y_no_rojo(self):
        imagen = _imagen_con_octagono(VERDE_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, mascara_verde = mascaras_color(hsv, config)
        self.assertGreater(int((mascara_verde > 0).sum()), 0)
        self.assertEqual(int((mascara_roja > 0).sum()), 0)

    def test_mascara_roja_no_confunde_rosado(self):
        imagen = _imagen_con_octagono(ROSADO_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, _ = mascaras_color(hsv, config)
        self.assertEqual(int((mascara_roja > 0).sum()), 0)


class PruebasBuscarOctagonos(unittest.TestCase):
    def test_octagono_rojo_se_detecta(self):
        imagen = _imagen_con_octagono(ROJO_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, _ = mascaras_color(hsv, config)
        candidatos = buscar_octagonos(mascara_roja, "PARE", config)
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["color"], "PARE")
        cx, cy = candidatos[0]["centroide"]
        self.assertAlmostEqual(cx, 150, delta=5)
        self.assertAlmostEqual(cy, 150, delta=5)

    def test_octagono_verde_se_detecta(self):
        imagen = _imagen_con_octagono(VERDE_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        _, mascara_verde = mascaras_color(hsv, config)
        candidatos = buscar_octagonos(mascara_verde, "SIGA", config)
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["color"], "SIGA")

    def test_rectangulo_rojo_se_rechaza(self):
        # Las señales son octágonos: un rectángulo del mismo color
        # (p. ej. un objeto rojo cualquiera en la escena) debe
        # descartarse por vértices, extensión y circularidad.
        imagen = _imagen_con_rectangulo(ROJO_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, _ = mascaras_color(hsv, config)
        candidatos = buscar_octagonos(mascara_roja, "PARE", config)
        self.assertEqual(candidatos, [])

    def test_franja_transversal_se_rechaza_por_aspecto(self):
        # La franja sobre la que van montadas las señales cruza todo el
        # ancho del cuadro: su relación de aspecto supera con creces
        # ASPECTO_SENAL_MAX y debe descartarse aunque sea del color de
        # una señal.
        imagen = _imagen_con_franja_transversal(ROJO_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, _ = mascaras_color(hsv, config)
        candidatos = buscar_octagonos(mascara_roja, "PARE", config)
        self.assertEqual(candidatos, [])

    def test_circulo_rojo_se_rechaza(self):
        imagen = _imagen_con_circulo(ROJO_BGR)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, _ = mascaras_color(hsv, config)
        candidatos = buscar_octagonos(mascara_roja, "PARE", config)
        self.assertEqual(candidatos, [])

    def test_texto_blanco_encima_no_rompe_la_deteccion(self):
        imagen = _imagen_con_octagono(ROJO_BGR, con_texto=True)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, _ = mascaras_color(hsv, config)
        candidatos = buscar_octagonos(mascara_roja, "PARE", config)
        self.assertEqual(len(candidatos), 1)

    def test_octagono_parcialmente_fuera_del_cuadro_se_detecta(self):
        # Solo la punta izquierda queda fuera del cuadro (centro en
        # x=40 con radio=60): sigue siendo reconocible como octágono.
        # Si se recortara la mitad o más, deja de tener forma de
        # octágono (aspecto y vértices cambian) y es correcto
        # rechazarlo: no es un caso de este filtro, es una limitación
        # física de identificar una forma truncada por la mitad.
        imagen = _imagen_con_octagono(ROJO_BGR, centro=(40, 150), radio=60)
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, _ = mascaras_color(hsv, config)
        candidatos = buscar_octagonos(mascara_roja, "PARE", config)
        self.assertEqual(len(candidatos), 1)

    def test_con_rojo_y_verde_cada_mascara_da_su_propio_candidato(self):
        imagen = np.full((ALTO, ANCHO, 3), GRIS_FONDO, dtype=np.uint8)
        vertices_rojo = _vertices_octagono((80, 150), 50)
        vertices_verde = _vertices_octagono((220, 150), 50)
        cv2.fillPoly(imagen, [vertices_rojo], ROJO_BGR)
        cv2.fillPoly(imagen, [vertices_verde], VERDE_BGR)

        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
        mascara_roja, mascara_verde = mascaras_color(hsv, config)

        candidatos_rojos = buscar_octagonos(mascara_roja, "PARE", config)
        candidatos_verdes = buscar_octagonos(mascara_verde, "SIGA", config)
        self.assertEqual(len(candidatos_rojos), 1)
        self.assertEqual(len(candidatos_verdes), 1)


class PruebasConfirmadorSenales(unittest.TestCase):
    def setUp(self):
        self.confirmador = ConfirmadorSenales()

    def test_no_confirma_con_una_sola_aparicion(self):
        candidato = {"color": "PARE", "centroide": (10, 10), "area": 1000}
        resultado = self.confirmador.actualizar(candidato, None, config)
        self.assertIsNone(resultado)

    def test_confirma_tras_suficientes_apariciones_consecutivas(self):
        candidato = {"color": "PARE", "centroide": (10, 10), "area": 1000}
        resultado = None
        for _ in range(config.CONFIRMAR_N):
            resultado = self.confirmador.actualizar(candidato, None, config)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["color"], "PARE")

    def test_una_aparicion_fugaz_no_alcanza_a_confirmar(self):
        candidato = {"color": "PARE", "centroide": (10, 10), "area": 1000}
        resultado = self.confirmador.actualizar(candidato, None, config)
        resultado = self.confirmador.actualizar(None, None, config)
        self.assertIsNone(resultado)


class PruebasDetectarSenales(unittest.TestCase):
    def setUp(self):
        self.confirmador = ConfirmadorSenales()

    def test_detectar_senales_confirma_tras_varios_fotogramas(self):
        imagen = _imagen_con_octagono(ROJO_BGR, con_texto=True)
        resultado = None
        for _ in range(config.CONFIRMAR_M):
            resultado = detectar_senales(imagen, 0, self.confirmador, config)
        self.assertEqual(resultado.senal, "PARE")
        self.assertTrue(len(resultado.candidatos) >= 1)
        self.assertIsNotNone(resultado.mascaras)

    def test_detectar_senales_sin_senal_da_none(self):
        imagen = np.full((ALTO, ANCHO, 3), GRIS_FONDO, dtype=np.uint8)
        resultado = detectar_senales(imagen, 0, self.confirmador, config)
        self.assertIsNone(resultado.senal)
        self.assertFalse(resultado.en_disparo)

    def test_desplazamiento_y_se_suma_al_centroide_de_los_candidatos(self):
        imagen = _imagen_con_octagono(ROJO_BGR)
        desplazamiento_y = 40
        resultado = detectar_senales(imagen, desplazamiento_y, self.confirmador, config)
        self.assertEqual(len(resultado.candidatos), 1)
        _, y_centroide = resultado.candidatos[0]["centroide"]
        self.assertAlmostEqual(y_centroide, 150 + desplazamiento_y, delta=5)

    def test_en_disparo_se_activa_cuando_el_centroide_cruza_y_disparo(self):
        alto_roi = ALTO
        y_disparo_px = config.Y_DISPARO * alto_roi
        centro_cerca = (150, int(y_disparo_px) + 20)
        imagen = _imagen_con_octagono(ROJO_BGR, centro=centro_cerca, radio=40)

        resultado = None
        for _ in range(config.CONFIRMAR_M):
            resultado = detectar_senales(imagen, 0, self.confirmador, config)
        self.assertEqual(resultado.senal, "PARE")
        self.assertTrue(resultado.en_disparo)


if __name__ == "__main__":
    unittest.main()
