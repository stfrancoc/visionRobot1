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
    """Verifica que girar en el sitio pueda volver a hacer visible la
    línea (vía el ángulo del chasis) incluso cuando el robot quedó muy
    lejos lateralmente, en un tramo sin temporizador de reaparición (a
    diferencia de "sin_linea"). Girar en el sitio no acerca al robot
    lateralmente (la posición no cambia), así que la recuperación se
    mide por si vuelve a reportar valida=True, no por la posición.
    """

    def test_giro_en_sitio_recupera_visibilidad_pese_a_posicion_lejana(self):
        pista = PistaVirtual([Tramo(tipo="recta", longitud=30.0)], modo_ideal=False, semilla=1)
        dt = config.PASO_SIMULACION_MS / 1000.0

        # Empuja la posición lateral lejos del carril a través de paso(),
        # no asignando el atributo directamente: así la cola de estado
        # retrasado (que modela la latencia de percepción) también queda
        # coherente con la posición lejana, igual que en el uso real.
        pista.posicion_lateral = 8.0
        for _ in range(pista._pasos_percepcion + 1):
            pista.paso(0, 0, dt)

        pasos_maximos = 500  # Suficientes para varias vueltas de búsqueda.
        recuperado = False
        for _ in range(pasos_maximos):
            pista.paso(-35, 35, dt)  # Girar en el sitio, como control.girar_en_sitio().
            resultado = pista.generar_resultado_linea()
            if resultado.valida:
                recuperado = True
                break

        self.assertTrue(recuperado, "girar en el sitio debe volver a hacer visible la línea por ángulo")
        # La posición lateral no cambia por girar en el sitio: sigue
        # lejos, y el error se satura cerca del límite (el ruido de
        # sensor puede empujarlo un poco más allá) en vez de bloquear
        # la validez.
        self.assertGreater(abs(resultado.error), 0.9)


if __name__ == "__main__":
    unittest.main()
