"""Controlador PD para el seguimiento de línea.

Traduce un ResultadoLinea (error lateral y ángulo) en velocidades para
las dos ruedas del robot. No conoce estados ni señales: solo hace
control. La máquina de estados (control/estados.py) decide cuándo
llamarlo, cuándo pedir un giro en sitio y cuándo reiniciarlo.
"""

import config
from control.contratos import ResultadoLinea

DT_MINIMO = 1e-3  # Umbral por debajo del cual dt se considera "casi cero" y se omite el término derivativo.


class ControladorPD:
    """Calcula velocidades de rueda a partir del error de línea, con
    suavizado exponencial del error y término derivativo por tiempo real.
    """

    def __init__(self):
        self.error_suavizado = 0.0
        self.error_anterior = 0.0

    def calcular(self, resultado_linea: ResultadoLinea, dt: float) -> tuple[int, int]:
        """Calcula las velocidades de las ruedas para seguir la línea.

        Recibe: resultado_linea (ResultadoLinea con error y angulo en
            [-1, 1]) y dt (segundos transcurridos desde el cálculo
            anterior).
        Devuelve: (izquierda, derecha) en enteros, recortados a
            [-VEL_MAX, VEL_MAX].
        Complejidad: O(1).
        """
        self.error_suavizado = (
            config.ALFA_SUAVIZADO * resultado_linea.error
            + (1 - config.ALFA_SUAVIZADO) * self.error_suavizado
        )

        # Si dt es cero o casi cero no hay una tasa de cambio confiable
        # que calcular (dividir por un dt artificialmente pequeño
        # amplificaría el error y saturaría las ruedas de golpe): en ese
        # caso se omite el término derivativo en vez de inventarlo.
        if dt > DT_MINIMO:
            delta_error = (self.error_suavizado - self.error_anterior) / dt
        else:
            delta_error = 0.0
        self.error_anterior = self.error_suavizado

        giro = (
            config.KP * self.error_suavizado
            + config.KD * delta_error
            + config.KA * resultado_linea.angulo
        )

        severidad_curva = max(abs(resultado_linea.error), abs(resultado_linea.angulo))
        severidad_curva = min(severidad_curva, 1.0)
        velocidad = config.VEL_BASE - severidad_curva * (config.VEL_BASE - config.VEL_MIN)

        izquierda = velocidad + giro
        derecha = velocidad - giro

        return self._recortar(izquierda), self._recortar(derecha)

    def girar_en_sitio(self, direccion: int) -> tuple[int, int]:
        """Calcula velocidades para girar sobre el propio eje, buscando
        la línea perdida.

        Recibe: direccion (signo del último error válido: positivo si la
            línea estaba a la derecha del centro, negativo si estaba a
            la izquierda).
        Devuelve: (izquierda, derecha) con VEL_BUSQUEDA y signos
            opuestos, girando hacia el lado donde se vio la línea por
            última vez. Usa la misma convención que calcular(): rueda
            izquierda más rápida gira el chasis hacia la derecha, igual
            que cuando error > 0 hace izquierda > derecha.
        Complejidad: O(1).
        """
        signo = 1 if direccion >= 0 else -1
        izquierda = signo * config.VEL_BUSQUEDA
        derecha = -signo * config.VEL_BUSQUEDA
        return self._recortar(izquierda), self._recortar(derecha)

    def detener(self) -> tuple[int, int]:
        """Devuelve velocidades en cero para ambas ruedas.

        Recibe: nada.
        Devuelve: (0, 0).
        Complejidad: O(1).
        """
        return 0, 0

    def reiniciar(self) -> None:
        """Limpia el estado interno del controlador.

        Se debe llamar al salir de PARE (o de LINEA_PERDIDA) para que el
        término derivativo no dé un salto al reanudar el seguimiento.

        Recibe: nada. Devuelve: nada.
        Complejidad: O(1).
        """
        self.error_suavizado = 0.0
        self.error_anterior = 0.0

    @staticmethod
    def _recortar(velocidad: float) -> int:
        """Recorta una velocidad a [-VEL_MAX, VEL_MAX] y la vuelve entera.

        Recibe: velocidad (float, puede exceder el rango).
        Devuelve: int dentro de [-VEL_MAX, VEL_MAX].
        Complejidad: O(1).
        """
        velocidad_recortada = max(-config.VEL_MAX, min(config.VEL_MAX, velocidad))
        return int(round(velocidad_recortada))
