"""Pruebas del simulador realista (simulador/pista_virtual.py).

Se enfocan en los mecanismos que causaron fallas durante la calibración
de esta fase: la zona muerta no debe crear una diferencia de rueda que
el controlador nunca ordenó, y el robot debe poder recuperarse de
LINEA_PERDIDA en un tramo sin temporizador de reaparición.
"""

import unittest

import config
from simulador.pista_virtual import PistaVirtual, Tramo


class PruebasZonaMuerta(unittest.TestCase):
    def setUp(self):
        self._zona_muerta_original = config.ZONA_MUERTA
        self._vel_max_original = config.VEL_MAX
        config.ZONA_MUERTA = 30
        config.VEL_MAX = 100
        self.pista = PistaVirtual([Tramo(tipo="recta", longitud=1.0)], modo_ideal=False, semilla=1)

    def tearDown(self):
        config.ZONA_MUERTA = self._zona_muerta_original
        config.VEL_MAX = self._vel_max_original

    def test_por_debajo_del_umbral_da_cero(self):
        self.assertEqual(self.pista._aplicar_zona_muerta(29.0), 0.0)
        self.assertEqual(self.pista._aplicar_zona_muerta(-29.0), 0.0)

    def test_no_hay_salto_abrupto_en_el_umbral(self):
        # Una velocidad ordenada apenas por encima del umbral debe dar
        # una velocidad real pequeña, no saltar directo a un valor
        # grande: eso fue lo que encadenaba salidas de pista al mezclar
        # una rueda "apagada" con otra a velocidad alta.
        justo_encima = self.pista._aplicar_zona_muerta(config.ZONA_MUERTA + 1)
        self.assertLess(justo_encima, 10.0)

    def test_preserva_el_signo(self):
        self.assertGreater(self.pista._aplicar_zona_muerta(60.0), 0.0)
        self.assertLess(self.pista._aplicar_zona_muerta(-60.0), 0.0)

    def test_vel_max_no_se_amplifica(self):
        self.assertEqual(self.pista._aplicar_zona_muerta(config.VEL_MAX), config.VEL_MAX)

    def test_modo_ideal_no_aplica_zona_muerta(self):
        pista_ideal = PistaVirtual([Tramo(tipo="recta", longitud=1.0)], modo_ideal=True)
        self.assertEqual(pista_ideal._aplicar_zona_muerta(5.0), 5.0)


class PruebasRecuperacionLineaPerdida(unittest.TestCase):
    """Verifica que girar en el sitio pueda traer de vuelta al robot
    incluso cuando quedó muy lejos del carril, en un tramo sin
    temporizador de reaparición (a diferencia de "sin_linea").
    """

    def test_barrido_recupera_posicion_lejana(self):
        pista = PistaVirtual([Tramo(tipo="recta", longitud=30.0)], modo_ideal=False, semilla=1)
        pista.posicion_lateral = 8.0  # Muy lejos del carril (|pos| > ANCHO_PISTA).

        dt = config.PASO_SIMULACION_MS / 1000.0
        pasos_maximos = 500  # Suficientes para varias vueltas de búsqueda.
        recuperado = False
        for _ in range(pasos_maximos):
            pista.paso(-35, 35, dt)  # Girar en el sitio, como control.girar_en_sitio().
            if abs(pista.posicion_lateral) <= 1.0:
                recuperado = True
                break

        self.assertTrue(recuperado, "girar en el sitio debe poder recuperar una posición lejana")


if __name__ == "__main__":
    unittest.main()
