"""Pruebas del control por zonas (control/controlador.py)."""

import unittest

import config
from control.contratos import ResultadoLinea
from control.controlador import ControladorZonas


class PruebasControladorZonas(unittest.TestCase):
    def setUp(self):
        self.controlador = ControladorZonas()

    def test_error_cero_avanza(self):
        resultado = ResultadoLinea(error=0.0, angulo=0.0, confianza=4, valida=True)
        izquierda, derecha = self.controlador.calcular(resultado)
        self.assertEqual(izquierda, derecha)
        self.assertGreater(izquierda, 0)

    def test_zona_centrado_siempre_avanza(self):
        # Un error pequeño, por debajo de ZONA_CENTRADO, nunca debe
        # producir un giro, sin importar cuántos fotogramas pasen.
        resultado = ResultadoLinea(error=config.ZONA_CENTRADO / 2, angulo=0.0, confianza=4, valida=True)
        for _ in range(20):
            izquierda, derecha = self.controlador.calcular(resultado)
            self.assertEqual(izquierda, derecha)

    def test_error_positivo_fuerte_gira_hacia_la_derecha(self):
        # Convención real (verificada contra control/contratos.py:
        # calcular_accion y comunicacion/salida_mbot.py): derecha >
        # izquierda -> "GIRAR_DERECHA" -> Robot.derecha(). El chasis
        # gira hacia el lado de la rueda con la señal MÁS ALTA.
        # error>0 (línea a la derecha) debe hacer que el chasis gire
        # hacia la derecha, así que derecha > izquierda.
        resultado = ResultadoLinea(error=config.ZONA_FUERTE + 0.1, angulo=0.0, confianza=4, valida=True)
        # Deja que el error suavizado converja antes de comprobar el giro.
        for _ in range(10):
            izquierda, derecha = self.controlador.calcular(resultado)
        self.assertGreater(derecha, izquierda)

    def test_error_negativo_fuerte_gira_hacia_la_izquierda(self):
        resultado = ResultadoLinea(error=-(config.ZONA_FUERTE + 0.1), angulo=0.0, confianza=4, valida=True)
        for _ in range(10):
            izquierda, derecha = self.controlador.calcular(resultado)
        self.assertGreater(izquierda, derecha)

    def test_senales_nunca_exceden_vel_max(self):
        resultado = ResultadoLinea(error=1.0, angulo=1.0, confianza=4, valida=True)
        for _ in range(50):
            izquierda, derecha = self.controlador.calcular(resultado)
            self.assertLessEqual(abs(izquierda), config.VEL_MAX)
            self.assertLessEqual(abs(derecha), config.VEL_MAX)

    def test_zona_leve_alterna_giro_y_avance(self):
        # Con GIROS_POR_AVANCE_ZONA_LEVE=1 y AVANCES_POR_GIRO_ZONA_LEVE=1
        # (valores por defecto), la zona leve debe alternar mitad giros,
        # mitad avances, sin importar la fase exacta en la que se
        # empiece a observar (no se asume alineación con el inicio del
        # ciclo interno del controlador).
        error_leve = (config.ZONA_CENTRADO + config.ZONA_FUERTE) / 2
        resultado = ResultadoLinea(error=error_leve, angulo=0.0, confianza=4, valida=True)

        # Deja que el error suavizado entre de lleno a zona leve primero.
        for _ in range(10):
            self.controlador.calcular(resultado)

        comandos = [self.controlador.calcular(resultado) for _ in range(8)]
        tipos = ["GIRO" if izquierda != derecha else "AVANCE" for izquierda, derecha in comandos]
        self.assertEqual(tipos.count("GIRO"), 4)
        self.assertEqual(tipos.count("AVANCE"), 4)
        # Nunca dos avances seguidos, ni dos giros seguidos (relación 1:1).
        for anterior, siguiente in zip(tipos, tipos[1:]):
            self.assertNotEqual(anterior, siguiente)

    def test_zona_fuerte_encadena_varios_giros_seguidos(self):
        resultado = ResultadoLinea(error=1.0, angulo=0.0, confianza=4, valida=True)

        # Deja que el error suavizado entre de lleno a zona fuerte.
        for _ in range(10):
            self.controlador.calcular(resultado)

        longitud_ciclo = config.GIROS_CONSECUTIVOS_ZONA_FUERTE + 1
        comandos = [self.controlador.calcular(resultado) for _ in range(longitud_ciclo)]
        tipos = ["GIRO" if izquierda != derecha else "AVANCE" for izquierda, derecha in comandos]
        # En cualquier ventana de longitud_ciclo comandos debe haber
        # exactamente un avance intercalado entre los giros.
        self.assertEqual(tipos.count("AVANCE"), 1)
        self.assertEqual(tipos.count("GIRO"), config.GIROS_CONSECUTIVOS_ZONA_FUERTE)

    def test_histeresis_evita_parpadeo_en_la_frontera(self):
        # Un error suavizado que ronda justo el umbral de ZONA_CENTRADO
        # no debe hacer que la zona alterne en cada fotograma: una vez
        # en zona leve, debe *quedarse* ahí hasta bajar claramente del
        # margen de histéresis, no apenas cruzar el umbral de vuelta.
        error_borde_alto = ResultadoLinea(error=config.ZONA_CENTRADO + 0.01, angulo=0.0, confianza=4, valida=True)
        error_borde_bajo = ResultadoLinea(error=config.ZONA_CENTRADO - 0.01, angulo=0.0, confianza=4, valida=True)

        for _ in range(10):
            self.controlador.calcular(error_borde_alto)
        self.assertEqual(self.controlador.zona_actual, "LEVE")

        # Un solo fotograma apenas por debajo del umbral (dentro del
        # margen de histéresis) no debe bastar para volver a CENTRADO.
        self.controlador.calcular(error_borde_bajo)
        self.assertEqual(self.controlador.zona_actual, "LEVE")

    def test_detener_da_senales_cero(self):
        self.assertEqual(self.controlador.detener(), (0, 0))

    def test_reiniciar_limpia_estado_interno(self):
        resultado = ResultadoLinea(error=0.8, angulo=0.5, confianza=4, valida=True)
        self.controlador.calcular(resultado)
        self.controlador.reiniciar()
        self.assertEqual(self.controlador.error_suavizado, 0.0)
        self.assertEqual(self.controlador.zona_actual, "CENTRADO")

    def test_girar_busqueda_da_senal_del_mismo_signo(self):
        # Ya no hay giro sobre el eje: ambas ruedas deben tener el MISMO
        # signo (o una en 0), nunca signos opuestos.
        izquierda, derecha = self.controlador.girar_busqueda(1)
        self.assertFalse(izquierda < 0 < derecha or derecha < 0 < izquierda)
        self.assertNotEqual((izquierda, derecha), (0, 0))

    def test_girar_busqueda_respeta_la_direccion(self):
        # direccion=1 (línea estaba a la derecha) debe girar el chasis
        # hacia la derecha: derecha > izquierda (ver convención en
        # test_error_positivo_fuerte_gira_hacia_la_derecha arriba).
        izquierda_derecha, derecha_derecha = self.controlador.girar_busqueda(1)
        izquierda_izquierda, derecha_izquierda = self.controlador.girar_busqueda(-1)
        self.assertGreater(derecha_derecha, izquierda_derecha)
        self.assertGreater(izquierda_izquierda, derecha_izquierda)


if __name__ == "__main__":
    unittest.main()
