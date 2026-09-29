"""Pruebas de detección de línea (vision/linea.py, vision/umbral_kmeans.py)
con imágenes sintéticas generadas con NumPy.

La escena real es una pista blanca con una línea negra ANCHA vista de
frente (no un piso en perspectiva): las imágenes sintéticas usan
dimensiones parecidas a un fotograma real (ANCHO_PROCESO=480) y un
ancho de línea real (grosor, no bounding box) cercano al medido en los
videos, para que los umbrales de config.py (calibrados en esa escala)
tengan sentido en las pruebas.
"""

import unittest

import numpy as np

import config
from vision.linea import EstadoLinea, _ancho_equivalente, analizar_franjas, detectar_linea, mascara_linea

ALTO = 400
ANCHO = 480
ANCHO_LINEA = 70
GRIS_PISO = 220
GRIS_LINEA = 30


def _roi_linea_recta(centro_columna: int) -> np.ndarray:
    """Construye una ROI sintética con una línea vertical recta.

    Recibe: centro_columna (int, columna donde centrar la línea).
    Devuelve: imagen BGR (ALTO, ANCHO, 3).
    """
    roi = np.full((ALTO, ANCHO, 3), GRIS_PISO, dtype=np.uint8)
    inicio = max(0, centro_columna - ANCHO_LINEA // 2)
    fin = min(ANCHO, centro_columna + ANCHO_LINEA // 2)
    roi[:, inicio:fin] = GRIS_LINEA
    return roi


class PruebasDeteccionLinea(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoLinea()

    def test_linea_centrada_da_error_cero(self):
        roi = _roi_linea_recta(ANCHO // 2)
        resultado, _ = detectar_linea(roi, self.estado, config)
        self.assertTrue(resultado.valida)
        self.assertAlmostEqual(resultado.error, 0.0, delta=0.05)
        self.assertAlmostEqual(resultado.angulo, 0.0, delta=0.05)
        self.assertEqual(resultado.confianza, config.N_FRANJAS)

    def test_linea_a_la_derecha_da_error_positivo(self):
        roi = _roi_linea_recta(ANCHO // 2 + 100)
        resultado, _ = detectar_linea(roi, self.estado, config)
        self.assertTrue(resultado.valida)
        self.assertGreater(resultado.error, 0.0)

    def test_linea_a_la_izquierda_da_error_negativo(self):
        roi = _roi_linea_recta(ANCHO // 2 - 100)
        resultado, _ = detectar_linea(roi, self.estado, config)
        self.assertTrue(resultado.valida)
        self.assertLess(resultado.error, 0.0)

    def test_linea_diagonal_da_angulo_distinto_de_cero(self):
        # La línea se desplaza hacia la derecha conforme se acerca al
        # robot (fila mayor = más cerca): anticipa una curva a la
        # derecha, así que el ángulo debe tener signo negativo (la
        # franja lejana queda a la izquierda de la cercana), igual
        # convención que el resto del proyecto.
        roi = np.full((ALTO, ANCHO, 3), GRIS_PISO, dtype=np.uint8)
        for fila in range(ALTO):
            centro_col = int(150 + (fila / ALTO) * 180)
            inicio = max(0, centro_col - ANCHO_LINEA // 2)
            fin = min(ANCHO, centro_col + ANCHO_LINEA // 2)
            roi[fila, inicio:fin] = GRIS_LINEA

        resultado, _ = detectar_linea(roi, self.estado, config)
        self.assertTrue(resultado.valida)
        self.assertLess(resultado.angulo, 0.0)

    def test_franja_transversal_ancha_se_descarta(self):
        # Simula la franja negra que hay debajo de cada señal: mucho
        # más ancha que la línea, cruzando dos franjas horizontales.
        # Esas franjas deben quedar inválidas (None) sin arrastrar el
        # centro de línea, no confundirse con la línea real.
        roi = _roi_linea_recta(ANCHO // 2)
        roi[150:200, :] = GRIS_LINEA

        resultado, mascara = detectar_linea(roi, self.estado, config)
        centros = analizar_franjas(mascara, 0.0, config)

        self.assertIn(None, centros)
        self.assertTrue(resultado.valida)
        self.assertAlmostEqual(resultado.error, 0.0, delta=0.05)

    def test_linea_saliendo_por_el_borde_reduce_confianza(self):
        # La línea se desplaza hacia la derecha lo bastante rápido
        # como para salir del cuadro en las franjas más lejanas: esas
        # franjas deben quedar inválidas, pero las franjas cercanas
        # (donde la línea sigue dentro del cuadro) deben seguir dando
        # un resultado válido con error cercano a la saturación.
        roi = np.full((ALTO, ANCHO, 3), GRIS_PISO, dtype=np.uint8)
        for fila in range(ALTO):
            centro_col = int(240 + (fila / ALTO) * 400)
            inicio = max(0, centro_col - ANCHO_LINEA // 2)
            fin = min(ANCHO, centro_col + ANCHO_LINEA // 2)
            if inicio < ANCHO:
                roi[fila, inicio:fin] = GRIS_LINEA

        resultado, _ = detectar_linea(roi, self.estado, config)
        self.assertTrue(resultado.valida)
        self.assertLess(resultado.confianza, config.N_FRANJAS)
        self.assertGreater(resultado.error, 0.8)

    def test_linea_muy_inclinada_no_se_descarta_por_ancho_de_bbox(self):
        # Una línea de grosor normal (ANCHO_LINEA=70) muy inclinada
        # DENTRO DE UNA SOLA FRANJA proyecta un bounding box mucho más
        # ancho que su grosor real (geometría normal, no ruido): esto
        # NO debe descartarse por "demasiado ancho". Se concentra toda
        # la inclinación (200px de desplazamiento) dentro de la altura
        # de una sola franja, para que el bbox proyectado en ESA franja
        # (~270px) supere claramente ANCHO_EQUIVALENTE_MAX_PX, pero el
        # área siga siendo la de una línea de grosor normal.
        alto_franja = ALTO // config.N_FRANJAS
        roi = np.full((ALTO, ANCHO, 3), GRIS_PISO, dtype=np.uint8)
        for fila in range(alto_franja):
            centro_col = int(150 + (fila / alto_franja) * 200)
            inicio = max(0, centro_col - ANCHO_LINEA // 2)
            fin = min(ANCHO, centro_col + ANCHO_LINEA // 2)
            roi[fila, inicio:fin] = GRIS_LINEA
        # El resto de la línea sigue recta, alineada con el final de la
        # inclinación, para que las demás franjas se detecten normal.
        centro_recto = 150 + 200
        inicio_recto = max(0, centro_recto - ANCHO_LINEA // 2)
        fin_recto = min(ANCHO, centro_recto + ANCHO_LINEA // 2)
        roi[alto_franja:, inicio_recto:fin_recto] = GRIS_LINEA

        resultado, mascara = detectar_linea(roi, self.estado, config)
        self.assertTrue(resultado.valida)
        self.assertGreaterEqual(resultado.confianza, config.FRANJAS_MINIMAS_VALIDAS)

        # Verificación directa del filtro sobre la franja inclinada
        # (índice 0, la primera): su ancho equivalente (área / altura
        # de franja) debe quedar por debajo de ANCHO_EQUIVALENTE_MAX_PX,
        # aunque su bbox no.
        franja = mascara[:alto_franja, :]
        proyeccion = franja.sum(axis=0)
        columnas_con_linea = np.where(proyeccion > 0)[0]
        ancho_bbox = columnas_con_linea[-1] - columnas_con_linea[0]
        ancho_equiv = _ancho_equivalente(franja, columnas_con_linea[0], columnas_con_linea[-1] + 1)

        self.assertGreater(ancho_bbox, config.ANCHO_EQUIVALENTE_MAX_PX)  # el bbox SÍ supera el límite
        self.assertLess(ancho_equiv, config.ANCHO_EQUIVALENTE_MAX_PX)  # pero el área normalizada se mantiene razonable

    def test_franja_transversal_se_descarta_por_area_no_por_ancho(self):
        # La franja transversal de una señal llena por completo su
        # bounding box (relleno=1.0): a diferencia de una línea
        # inclinada (que deja huecos triangulares en los extremos), su
        # ancho equivalente (área/altura) es igual a su ancho real, muy
        # por encima de cualquier línea real. Prueba directa del
        # criterio de área, no solo del resultado final de
        # detectar_linea() (ver test_franja_transversal_ancha_se_descarta).
        alto_franja = 76
        franja_transversal = np.full((alto_franja, ANCHO), 255, dtype=np.uint8)
        ancho_equiv_transversal = _ancho_equivalente(franja_transversal, 0, ANCHO)
        self.assertGreater(ancho_equiv_transversal, config.ANCHO_EQUIVALENTE_MAX_PX)

        franja_linea_inclinada = np.zeros((alto_franja, ANCHO), dtype=np.uint8)
        for fila in range(alto_franja):
            centro_col = int(150 + (fila / alto_franja) * 100)
            inicio = max(0, centro_col - ANCHO_LINEA // 2)
            fin = min(ANCHO, centro_col + ANCHO_LINEA // 2)
            franja_linea_inclinada[fila, inicio:fin] = 255
        ancho_equiv_linea = _ancho_equivalente(franja_linea_inclinada, 0, ANCHO)
        self.assertLess(ancho_equiv_linea, config.ANCHO_EQUIVALENTE_MAX_PX)

    def test_sin_linea_en_el_cuadro_da_invalida(self):
        roi = np.full((ALTO, ANCHO, 3), GRIS_PISO, dtype=np.uint8)
        resultado, _ = detectar_linea(roi, self.estado, config)
        self.assertFalse(resultado.valida)
        self.assertEqual(resultado.confianza, 0)

    def test_mascara_linea_es_binaria_y_marca_la_linea(self):
        roi = _roi_linea_recta(ANCHO // 2)
        mascara = mascara_linea(roi, umbral=125.0, cfg=config)
        valores_unicos = set(np.unique(mascara).tolist())
        self.assertTrue(valores_unicos.issubset({0, 255}))
        # El centro de la ROI (donde está la línea) debe quedar marcado.
        self.assertEqual(mascara[ALTO // 2, ANCHO // 2], 255)

    def _roi_con_ruido_en_franja_lejana(self):
        """ROI con línea recta en el centro para todas las franjas
        EXCEPTO la más lejana (índice 0), donde en su lugar hay un
        tramo de ruido del mismo ancho que la línea pero muy lejos de
        ella: al no haber línea real en esa franja, el tramo de ruido
        es el único candidato y "gana" por defecto, sin que el criterio
        de ancho lo descarte. Sirve para probar la continuidad
        aislada del criterio de ancho.
        """
        alto_franja = ALTO // config.N_FRANJAS
        roi = _roi_linea_recta(240)
        roi[0:alto_franja, :] = GRIS_PISO  # borra la línea real en la franja más lejana
        roi[0:alto_franja, 400:470] = GRIS_LINEA  # y pone ahí el ruido, lejos del centro
        return roi

    def test_continuidad_descarta_franja_lejos_de_la_vecina(self):
        # Sin línea real en la franja más lejana, el tramo de ruido es
        # el único candidato y sería aceptado por el criterio de ancho
        # (nada con qué compararlo). La continuidad debe descartarlo
        # de todas formas, por estar demasiado lejos del centro ya
        # confirmado por la franja vecina (que sigue la línea real).
        roi = self._roi_con_ruido_en_franja_lejana()
        resultado, mascara = detectar_linea(roi, self.estado, config)
        centros = analizar_franjas(mascara, 0.0, config)

        self.assertIsNone(centros[0])
        # Las demás franjas, sobre la línea real, deben seguir válidas.
        self.assertTrue(resultado.valida)
        self.assertAlmostEqual(resultado.error, 0.0, delta=0.05)

    def test_continuidad_no_contamina_el_estado_para_el_siguiente_fotograma(self):
        # Si una franja se descarta por continuidad, su centro NO debe
        # quedar como referencia para el fotograma siguiente (evita que
        # un engancho a ruido se autoconfirme de un fotograma al otro).
        roi = self._roi_con_ruido_en_franja_lejana()
        detectar_linea(roi, self.estado, config)

        # centro_anterior debe reflejar la línea real (cerca de 0), no
        # haberse contaminado con el ruido descartado.
        self.assertAlmostEqual(self.estado.centro_anterior, 0.0, delta=0.1)

    def test_estado_conserva_umbral_entre_llamadas_dentro_del_periodo(self):
        roi = _roi_linea_recta(ANCHO // 2)
        detectar_linea(roi, self.estado, config)
        umbral_tras_primera = self.estado.umbral_actual

        for _ in range(config.PERIODO_KMEANS - 1):
            detectar_linea(roi, self.estado, config)

        self.assertEqual(self.estado.umbral_actual, umbral_tras_primera)


if __name__ == "__main__":
    unittest.main()
