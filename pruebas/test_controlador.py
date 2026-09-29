"""Pruebas del controlador PD (control/controlador.py)."""

import unittest

import config
from control.contratos import ResultadoLinea
from control.controlador import ControladorPD


class PruebasControladorPD(unittest.TestCase):
    def setUp(self):
        self.controlador = ControladorPD()

    def test_error_cero_da_ruedas_iguales(self):
        resultado = ResultadoLinea(error=0.0, angulo=0.0, confianza=4, valida=True)
        izquierda, derecha = self.controlador.calcular(resultado, dt=0.05)
        self.assertEqual(izquierda, derecha)

    def test_error_positivo_hace_izquierda_mayor_que_derecha(self):
        resultado = ResultadoLinea(error=0.5, angulo=0.0, confianza=4, valida=True)
        izquierda, derecha = self.controlador.calcular(resultado, dt=0.05)
        self.assertGreater(izquierda, derecha)

    def test_error_negativo_hace_derecha_mayor_que_izquierda(self):
        resultado = ResultadoLinea(error=-0.5, angulo=0.0, confianza=4, valida=True)
        izquierda, derecha = self.controlador.calcular(resultado, dt=0.05)
        self.assertGreater(derecha, izquierda)

    def test_velocidades_nunca_exceden_vel_max(self):
        resultado = ResultadoLinea(error=1.0, angulo=1.0, confianza=4, valida=True)
        for _ in range(50):
            izquierda, derecha = self.controlador.calcular(resultado, dt=0.05)
            self.assertLessEqual(abs(izquierda), config.VEL_MAX)
            self.assertLessEqual(abs(derecha), config.VEL_MAX)

    def test_velocidad_baja_en_curvas(self):
        recta = ResultadoLinea(error=0.0, angulo=0.0, confianza=4, valida=True)
        curva = ResultadoLinea(error=0.9, angulo=0.9, confianza=4, valida=True)

        izquierda_recta, derecha_recta = self.controlador.calcular(recta, dt=0.05)
        velocidad_recta = (izquierda_recta + derecha_recta) / 2.0

        self.controlador.reiniciar()
        izquierda_curva, derecha_curva = self.controlador.calcular(curva, dt=0.05)
        velocidad_curva = (izquierda_curva + derecha_curva) / 2.0

        self.assertLess(velocidad_curva, velocidad_recta)

    def test_dt_cero_no_rompe_nada(self):
        resultado = ResultadoLinea(error=0.3, angulo=0.1, confianza=4, valida=True)
        try:
            izquierda, derecha = self.controlador.calcular(resultado, dt=0.0)
        except ZeroDivisionError:
            self.fail("calcular() no debe dividir por cero cuando dt=0")
        self.assertIsInstance(izquierda, int)
        self.assertIsInstance(derecha, int)

    def test_dt_cero_no_produce_termino_derivativo_espurio(self):
        # Con dt=0 (típico en la primera llamada, antes de tener un dt
        # real) no hay una tasa de cambio confiable: el término
        # derivativo debe omitirse en vez de dividir por un dt mínimo
        # artificial, que amplificaría cualquier error pequeño y
        # saturaría las ruedas de golpe.
        resultado = ResultadoLinea(error=0.05, angulo=0.0, confianza=4, valida=True)
        izquierda, derecha = self.controlador.calcular(resultado, dt=0.0)
        self.assertLess(abs(izquierda), config.VEL_MAX)
        self.assertLess(abs(derecha), config.VEL_MAX)

    def test_detener_da_velocidades_cero(self):
        self.assertEqual(self.controlador.detener(), (0, 0))

    def test_reiniciar_limpia_estado_interno(self):
        resultado = ResultadoLinea(error=0.8, angulo=0.5, confianza=4, valida=True)
        self.controlador.calcular(resultado, dt=0.05)
        self.controlador.reiniciar()
        self.assertEqual(self.controlador.error_suavizado, 0.0)
        self.assertEqual(self.controlador.error_anterior, 0.0)

    def test_girar_en_sitio_da_signos_opuestos(self):
        izquierda, derecha = self.controlador.girar_en_sitio(1)
        self.assertEqual(izquierda, -derecha)
        self.assertNotEqual(izquierda, 0)

    def test_realinear_no_avanza(self):
        resultado = ResultadoLinea(error=0.9, angulo=0.5, confianza=4, valida=True)
        izquierda, derecha = self.controlador.realinear(resultado)
        self.assertEqual(izquierda + derecha, 0)

    def test_realinear_angulo_cero_no_gira(self):
        resultado = ResultadoLinea(error=0.9, angulo=0.0, confianza=4, valida=True)
        izquierda, derecha = self.controlador.realinear(resultado)
        self.assertEqual((izquierda, derecha), (0, 0))

    def test_realinear_respeta_piso_minimo_con_angulo_pequeno(self):
        # Un ángulo pequeño no debe producir un comando por debajo de
        # ZONA_MUERTA: el motor real no reaccionaría y el chasis
        # quedaría a merced de la inercia residual del giro anterior
        # (ver VEL_MIN_REALINEACION en config.py).
        resultado = ResultadoLinea(error=0.9, angulo=0.05, confianza=4, valida=True)
        izquierda, derecha = self.controlador.realinear(resultado)
        self.assertGreaterEqual(abs(izquierda), config.VEL_MIN_REALINEACION)

    def test_realinear_gira_en_sentido_contrario_al_angulo(self):
        # angulo>0 significa que el chasis ya está girado hacia ese
        # lado: para deshacerlo (llevar el ángulo a 0) hay que girar en
        # el sentido CONTRARIO, no reforzarlo como haría calcular() para
        # corregir una posición lateral.
        positivo = ResultadoLinea(error=0.9, angulo=0.05, confianza=4, valida=True)
        negativo = ResultadoLinea(error=0.9, angulo=-0.05, confianza=4, valida=True)
        izquierda_pos, derecha_pos = self.controlador.realinear(positivo)
        izquierda_neg, derecha_neg = self.controlador.realinear(negativo)
        self.assertGreater(derecha_pos, izquierda_pos)
        self.assertGreater(izquierda_neg, derecha_neg)


if __name__ == "__main__":
    unittest.main()
