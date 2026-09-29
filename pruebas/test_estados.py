"""Pruebas de la máquina de estados (control/estados.py), con una
secuencia simulada manualmente (sin la pista virtual) para controlar
exactamente cada transición.
"""

import unittest

import config
from control.contratos import ResultadoLinea, ResultadoSenales
from control.estados import DETENIDO, LINEA_PERDIDA, PARE, REANUDAR, SEGUIR_LINEA, SIGA, MaquinaEstados

LINEA_OK = ResultadoLinea(error=0.1, angulo=0.0, confianza=4, valida=True)
LINEA_PERDIDA_RESULTADO = ResultadoLinea(error=0.0, angulo=0.0, confianza=0, valida=False)
SIN_SENAL = ResultadoSenales(senal=None, en_disparo=False)
PARE_LEJOS = ResultadoSenales(senal="PARE", en_disparo=False)
PARE_CERCA = ResultadoSenales(senal="PARE", en_disparo=True)
SIGA_CERCA = ResultadoSenales(senal="SIGA", en_disparo=True)


class PruebasMaquinaEstados(unittest.TestCase):
    def setUp(self):
        self.maquina = MaquinaEstados()

    def test_pare_da_velocidades_exactamente_cero(self):
        self.maquina.actualizar(LINEA_OK, PARE_CERCA, tiempo_actual=0.0)
        self.assertEqual(self.maquina.estado, PARE)

        comando = self.maquina.actualizar(LINEA_OK, PARE_CERCA, tiempo_actual=0.5)
        self.assertEqual(comando.izquierda, 0)
        self.assertEqual(comando.derecha, 0)
        self.assertEqual(comando.estado, PARE)

    def test_secuencia_completa_recorrido(self):
        t = 0.0
        paso = 0.1
        maquina = self.maquina

        # 1) Línea recta, sin señales: debe seguir en SEGUIR_LINEA.
        for _ in range(5):
            comando = maquina.actualizar(LINEA_OK, SIN_SENAL, t)
            t += paso
        self.assertEqual(comando.estado, SEGUIR_LINEA)

        # 2) Rojo lejos (sin disparo): no debe frenar todavía.
        for _ in range(5):
            comando = maquina.actualizar(LINEA_OK, PARE_LEJOS, t)
            t += paso
        self.assertEqual(comando.estado, SEGUIR_LINEA)

        # 3) Rojo en disparo: debe frenar (pasar a PARE).
        comando = maquina.actualizar(LINEA_OK, PARE_CERCA, t)
        t += paso
        self.assertEqual(comando.estado, PARE)
        self.assertEqual((comando.izquierda, comando.derecha), (0, 0))

        # 4) Espera durante TIEMPO_PARE: sigue detenido hasta que se cumpla.
        tiempo_entrada_pare = maquina.tiempo_entrada_estado
        while t - tiempo_entrada_pare < config.TIEMPO_PARE:
            comando = maquina.actualizar(LINEA_OK, PARE_CERCA, t)
            self.assertEqual(comando.estado, PARE)
            self.assertEqual((comando.izquierda, comando.derecha), (0, 0))
            t += paso

        # 5) Al cumplirse el tiempo, pasa a REANUDAR ignorando el mismo rojo.
        comando = maquina.actualizar(LINEA_OK, PARE_CERCA, t)
        t += paso
        self.assertEqual(comando.estado, REANUDAR)

        for _ in range(3):
            comando = maquina.actualizar(LINEA_OK, PARE_CERCA, t)
            self.assertEqual(comando.estado, REANUDAR)
            t += paso

        # 6) El rojo desaparece del cuadro: vuelve a SEGUIR_LINEA.
        comando = maquina.actualizar(LINEA_OK, SIN_SENAL, t)
        t += paso
        self.assertEqual(comando.estado, SEGUIR_LINEA)

        # 7) Señal SIGA: se registra y se vuelve de inmediato a SEGUIR_LINEA.
        comando = maquina.actualizar(LINEA_OK, SIGA_CERCA, t)
        t += paso
        self.assertIn(comando.estado, (SIGA, SEGUIR_LINEA))
        comando = maquina.actualizar(LINEA_OK, SIN_SENAL, t)
        t += paso
        self.assertEqual(comando.estado, SEGUIR_LINEA)

        # 8) Se pierde la línea girando hacia el lado correcto: si el
        # último error fue positivo (línea a la derecha), debe girar
        # hacia la derecha, es decir, con la rueda derecha más rápida
        # (misma convención que calcular_accion(): derecha > izquierda
        # -> "GIRAR_DERECHA" -> Robot.derecha()).
        comando = maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, t)
        t += paso
        self.assertEqual(comando.estado, LINEA_PERDIDA)
        self.assertGreater(LINEA_OK.error, 0)
        self.assertGreater(comando.derecha, comando.izquierda)

        # 9) Se recupera la línea antes del tiempo límite: no hay estado
        # intermedio (ya no existe el giro sobre el eje, así que
        # "realinear sin avanzar" no es una acción física posible): se
        # retoma el control por zonas de inmediato.
        comando = maquina.actualizar(LINEA_OK, SIN_SENAL, t)
        t += paso
        self.assertEqual(comando.estado, SEGUIR_LINEA)

        # 10) Se pierde otra vez y esta vez no se recupera: debe detenerse
        # al llegar a TIEMPO_MAX_PERDIDA.
        comando = maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, t)
        t += paso
        self.assertEqual(comando.estado, LINEA_PERDIDA)
        tiempo_entrada_perdida = maquina.tiempo_entrada_estado

        while t - tiempo_entrada_perdida < config.TIEMPO_MAX_PERDIDA:
            comando = maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, t)
            t += paso

        comando = maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, t)
        self.assertEqual(comando.estado, DETENIDO)
        self.assertEqual((comando.izquierda, comando.derecha), (0, 0))

    def test_linea_perdida_busca_con_giro_de_radio_amplio(self):
        # La búsqueda ya no es un giro sobre el eje: ambas señales de
        # rueda deben tener el mismo signo (o una en 0), nunca opuestas.
        maquina = self.maquina
        maquina.actualizar(LINEA_OK, SIN_SENAL, tiempo_actual=0.0)  # Fija signo_ultimo_error > 0.
        comando = maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, tiempo_actual=0.1)

        self.assertEqual(comando.estado, LINEA_PERDIDA)
        self.assertFalse(comando.izquierda < 0 < comando.derecha or comando.derecha < 0 < comando.izquierda)

    def test_registro_de_eventos_tiene_motivo_y_tiempos_crecientes(self):
        maquina = self.maquina
        maquina.actualizar(LINEA_OK, PARE_CERCA, tiempo_actual=1.0)
        maquina.actualizar(LINEA_OK, PARE_CERCA, tiempo_actual=1.0 + config.TIEMPO_PARE)

        eventos = maquina.obtener_eventos()
        self.assertGreaterEqual(len(eventos), 2)
        for tiempo, estado_anterior, estado_nuevo, motivo in eventos:
            self.assertIsInstance(motivo, str)
            self.assertNotEqual(motivo, "")
            self.assertNotEqual(estado_anterior, estado_nuevo)

        tiempos = [evento[0] for evento in eventos]
        self.assertEqual(tiempos, sorted(tiempos))


if __name__ == "__main__":
    unittest.main()
