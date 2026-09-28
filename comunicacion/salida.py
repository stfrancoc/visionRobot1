"""Interfaz de salida hacia el robot y sus implementaciones de prueba.

La comunicación real por Bluetooth con el Arduino la implementa otro
integrante del equipo (el docente entrega la lógica del
microcontrolador). Aquí solo se define el contrato SalidaRobot y unas
implementaciones de prueba para desarrollar y calibrar sin el robot
físico: SalidaConsola, SalidaNula y SalidaRegistro.
"""

import csv
import time

import config
from control.contratos import ComandoRobot


class SalidaRobot:
    """Contrato que debe cumplir cualquier salida hacia el robot."""

    def enviar(self, comando: ComandoRobot) -> None:
        """Entrega un ComandoRobot al robot (o a quien lo simule).

        Recibe: comando (ComandoRobot). Devuelve: nada.
        """
        raise NotImplementedError

    def detener(self) -> None:
        """Fuerza velocidades en cero de inmediato.

        Recibe: nada. Devuelve: nada.
        """
        raise NotImplementedError

    def cerrar(self) -> None:
        """Libera los recursos usados por la salida (archivos, puertos).

        Recibe: nada. Devuelve: nada.
        """
        raise NotImplementedError


class SalidaConsola(SalidaRobot):
    """Imprime cada comando en consola, limitando la frecuencia a
    config.FRECUENCIA_ENVIO para no saturar la terminal.
    """

    def __init__(self):
        self._periodo_minimo = 1.0 / config.FRECUENCIA_ENVIO
        self._ultimo_envio = 0.0

    def enviar(self, comando: ComandoRobot) -> None:
        ahora = time.monotonic()
        if ahora - self._ultimo_envio < self._periodo_minimo:
            return
        self._ultimo_envio = ahora
        print(
            f"[SalidaConsola] estado={comando.estado} accion={comando.accion} "
            f"izq={comando.izquierda} der={comando.derecha}"
        )

    def detener(self) -> None:
        print("[SalidaConsola] DETENER izq=0 der=0")

    def cerrar(self) -> None:
        pass


class SalidaNula(SalidaRobot):
    """No hace nada. Útil para pruebas donde solo importa el cálculo de
    control, no la salida.
    """

    def enviar(self, comando: ComandoRobot) -> None:
        pass

    def detener(self) -> None:
        pass

    def cerrar(self) -> None:
        pass


class SalidaRegistro(SalidaRobot):
    """Guarda cada comando enviado en un archivo CSV, para analizar
    después el comportamiento del control (métricas para el póster).
    """

    _ENCABEZADO = ["tiempo", "estado", "accion", "izquierda", "derecha"]

    def __init__(self, ruta_csv: str):
        self._archivo = open(ruta_csv, "w", newline="", encoding="utf-8")
        self._escritor = csv.writer(self._archivo)
        self._escritor.writerow(self._ENCABEZADO)

    def enviar(self, comando: ComandoRobot) -> None:
        self._escritor.writerow(
            [time.monotonic(), comando.estado, comando.accion, comando.izquierda, comando.derecha]
        )

    def detener(self) -> None:
        self._escritor.writerow([time.monotonic(), "DETENER", "DETENER", 0, 0])

    def cerrar(self) -> None:
        self._archivo.close()


# ---------------------------------------------------------------------------
# Punto de integración para el compañero de Bluetooth
# ---------------------------------------------------------------------------
# Aquí se agregará SalidaBluetooth(SalidaRobot), que abre el puerto serie o
# el socket Bluetooth en __init__, y en enviar(comando) traduce el
# ComandoRobot al formato que espera el Arduino:
#   - Si el Arduino espera velocidades continuas: usar comando.izquierda y
#     comando.derecha (enteros en [-VEL_MAX, VEL_MAX], el signo indica
#     sentido de giro de cada rueda).
#   - Si el Arduino espera comandos discretos: usar comando.accion
#     ("AVANZAR", "GIRAR_IZQUIERDA", "GIRAR_DERECHA", "GIRAR_SOBRE_EJE",
#     "DETENER").
# detener() debe enviar el comando de parada inmediata (no esperar a la
# siguiente llamada a enviar). cerrar() debe liberar el puerto/socket.
