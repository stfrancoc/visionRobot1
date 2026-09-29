"""Pruebas de SalidaAsincrona (comunicacion/salida_asincrona.py): que
enviar() no bloquee al llamador aunque la salida real sea lenta, y que
detener() sí actúe de inmediato.
"""

import time
import unittest

from comunicacion.salida import SalidaRobot
from comunicacion.salida_asincrona import SalidaAsincrona
from control.contratos import ComandoRobot

RETARDO_SIMULADO = 0.1  # Segundos que tarda cada envío, como el sleep del Robot del docente.


class SalidaLenta(SalidaRobot):
    """Salida de prueba que simula el bloqueo del Bluetooth real."""

    def __init__(self):
        self.enviados = []
        self.detenciones = 0
        self.cerrada = False

    def enviar(self, comando):
        time.sleep(RETARDO_SIMULADO)
        self.enviados.append(comando)

    def detener(self):
        self.detenciones += 1

    def cerrar(self):
        self.cerrada = True


class PruebasSalidaAsincrona(unittest.TestCase):
    def setUp(self):
        self.lenta = SalidaLenta()
        self.salida = SalidaAsincrona(self.lenta)

    def tearDown(self):
        self.salida.cerrar()

    def test_enviar_no_bloquea_al_llamador(self):
        comando = ComandoRobot(izquierda=60, derecha=60, accion="AVANZAR")

        inicio = time.perf_counter()
        for _ in range(5):
            self.salida.enviar(comando)
        duracion = time.perf_counter() - inicio

        # Cinco envíos síncronos tardarían 5 x RETARDO_SIMULADO = 0.5s.
        # Asíncronos deben retornar casi al instante.
        self.assertLess(duracion, RETARDO_SIMULADO)

    def test_el_comando_llega_a_la_salida_real(self):
        comando = ComandoRobot(izquierda=60, derecha=60, accion="AVANZAR")
        self.salida.enviar(comando)

        time.sleep(RETARDO_SIMULADO * 3)

        self.assertGreaterEqual(len(self.lenta.enviados), 1)
        self.assertEqual(self.lenta.enviados[0].accion, "AVANZAR")

    def test_solo_se_despacha_el_comando_mas_reciente(self):
        # Se encolan varios comandos más rápido de lo que la salida
        # real los despacha: el robot debe recibir el último, no una
        # cola de órdenes viejas que ejecutaría con retraso creciente.
        for indice in range(10):
            self.salida.enviar(ComandoRobot(izquierda=indice, derecha=indice, accion="AVANZAR"))

        time.sleep(RETARDO_SIMULADO * 4)

        self.assertLess(len(self.lenta.enviados), 10)
        self.assertEqual(self.lenta.enviados[-1].izquierda, 9)

    def test_detener_actua_de_inmediato(self):
        self.salida.enviar(ComandoRobot(izquierda=60, derecha=60, accion="AVANZAR"))
        self.salida.detener()

        # detener() no pasa por el hilo: debe haberse ejecutado ya.
        self.assertEqual(self.lenta.detenciones, 1)

    def test_cerrar_cierra_la_salida_real(self):
        self.salida.cerrar()
        self.assertTrue(self.lenta.cerrada)


if __name__ == "__main__":
    unittest.main()
