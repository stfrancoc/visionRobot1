"""Pruebas de la máquina de estados (control/estados.py), con una
secuencia simulada manualmente (sin la pista virtual) para controlar
exactamente cada transición.
"""

import unittest

import config
from control.contratos import ResultadoLinea, ResultadoSenales
from control.estados import DETENIDO, LINEA_PERDIDA, PARE, REALINEANDO, REANUDAR, SEGUIR_LINEA, SIGA, MaquinaEstados

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
        # hacia la derecha, es decir, con la rueda izquierda más rápida
        # (misma convención que calcular(): error > 0 -> izquierda > derecha).
        comando = maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, t)
        t += paso
        self.assertEqual(comando.estado, LINEA_PERDIDA)
        self.assertGreater(LINEA_OK.error, 0)
        self.assertGreater(comando.izquierda, comando.derecha)

        # 9) Se recupera la línea antes del tiempo límite: pasa primero por
        # REALINEANDO (no avanza estando torcido) y solo llega a
        # SEGUIR_LINEA tras suficientes fotogramas seguidos ya alineado.
        comando = maquina.actualizar(LINEA_OK, SIN_SENAL, t)
        t += paso
        self.assertEqual(comando.estado, REALINEANDO)

        for _ in range(config.FOTOGRAMAS_REALINEADO_CONSECUTIVOS - 1):
            comando = maquina.actualizar(LINEA_OK, SIN_SENAL, t)
            self.assertEqual(comando.estado, REALINEANDO)
            t += paso

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

    def test_realineando_no_avanza_mientras_el_angulo_es_alto(self):
        # Al recuperar la línea con el chasis torcido (ángulo alto), la
        # velocidad de avance debe ser nula: solo gira hacia el ángulo,
        # no se lanza hacia adelante estando desalineado. El error de
        # posición puede seguir siendo alto (girando en el sitio no se
        # corrige): lo que decide la alineación es el ángulo.
        maquina = self.maquina
        torcido = ResultadoLinea(error=0.9, angulo=0.9, confianza=4, valida=True)

        maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, tiempo_actual=0.0)
        comando = maquina.actualizar(torcido, SIN_SENAL, tiempo_actual=0.1)

        self.assertEqual(comando.estado, REALINEANDO)
        self.assertEqual(comando.izquierda + comando.derecha, 0)
        # angulo>0 significa que el chasis ya está girado hacia ese lado:
        # para deshacerlo hay que girar en sentido contrario (derecha >
        # izquierda), no reforzarlo como en calcular().
        self.assertGreater(comando.derecha, comando.izquierda)

    def test_realineando_exige_varios_fotogramas_alineados_antes_de_seguir(self):
        # Un solo fotograma con ángulo bajo (ruido) no debe bastar para
        # pasar a SEGUIR_LINEA: se exige una racha de
        # FOTOGRAMAS_REALINEADO_CONSECUTIVOS fotogramas seguidos.
        maquina = self.maquina
        alineado = ResultadoLinea(error=0.9, angulo=0.1, confianza=4, valida=True)

        maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, tiempo_actual=0.0)
        # La transición LINEA_PERDIDA -> REALINEANDO (primer fotograma
        # con ángulo bajo) todavía no cuenta ningún fotograma de la
        # racha: el conteo empieza en la siguiente llamada, ya dentro
        # de _en_realineando. Hacen falta FOTOGRAMAS_REALINEADO_CONSECUTIVOS
        # llamadas más después de esa transición para completar la racha.
        for i in range(1, config.FOTOGRAMAS_REALINEADO_CONSECUTIVOS + 1):
            comando = maquina.actualizar(alineado, SIN_SENAL, tiempo_actual=0.1 * i)
            self.assertEqual(comando.estado, REALINEANDO)

        comando = maquina.actualizar(alineado, SIN_SENAL, tiempo_actual=0.1 * (config.FOTOGRAMAS_REALINEADO_CONSECUTIVOS + 1))
        self.assertEqual(comando.estado, SEGUIR_LINEA)

    def test_racha_de_alineacion_se_interrumpe_si_el_angulo_vuelve_a_subir(self):
        maquina = self.maquina
        alineado = ResultadoLinea(error=0.9, angulo=0.1, confianza=4, valida=True)
        torcido = ResultadoLinea(error=0.9, angulo=0.9, confianza=4, valida=True)

        maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, tiempo_actual=0.0)
        maquina.actualizar(alineado, SIN_SENAL, tiempo_actual=0.1)
        maquina.actualizar(torcido, SIN_SENAL, tiempo_actual=0.2)  # Rompe la racha.

        for i in range(config.FOTOGRAMAS_REALINEADO_CONSECUTIVOS - 1):
            comando = maquina.actualizar(alineado, SIN_SENAL, tiempo_actual=0.3 + 0.1 * i)
            self.assertEqual(comando.estado, REALINEANDO)

    def test_realineando_vuelve_a_linea_perdida_si_se_agota_el_tiempo(self):
        # Si el ángulo nunca baja del umbral (p. ej. ruido que no
        # converge), no debe quedarse en REALINEANDO para siempre.
        maquina = self.maquina
        torcido = ResultadoLinea(error=0.9, angulo=0.9, confianza=4, valida=True)

        maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, tiempo_actual=0.0)
        maquina.actualizar(torcido, SIN_SENAL, tiempo_actual=0.1)
        self.assertEqual(maquina.estado, REALINEANDO)

        comando = maquina.actualizar(torcido, SIN_SENAL, tiempo_actual=0.1 + config.TIEMPO_MAX_REALINEANDO)
        self.assertEqual(comando.estado, LINEA_PERDIDA)

    def test_realineando_vuelve_a_linea_perdida_si_la_linea_se_pierde_de_nuevo(self):
        maquina = self.maquina
        torcido = ResultadoLinea(error=0.9, angulo=0.9, confianza=4, valida=True)

        maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, tiempo_actual=0.0)
        maquina.actualizar(torcido, SIN_SENAL, tiempo_actual=0.1)
        self.assertEqual(maquina.estado, REALINEANDO)

        comando = maquina.actualizar(LINEA_PERDIDA_RESULTADO, SIN_SENAL, tiempo_actual=0.2)
        self.assertEqual(comando.estado, LINEA_PERDIDA)

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
