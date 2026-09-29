"""SalidaMBot: envuelve la clase Robot del docente (comunicacion/robot_mbot.py)
para que cumpla el contrato SalidaRobot.

El Robot del docente no acepta velocidades ni magnitudes por rueda: cada
método (adelante/atras/izquierda/derecha/parar) es un comando discreto
sin parámetros, cuya duración e intensidad decide el firmware Arduino
(fuera de este alcance). Por eso enviar() solo puede usar
comando.accion; comando.izquierda y comando.derecha se ignoran, porque
el robot no tiene forma de recibirlos.

A propósito no se agrega throttling propio aquí (a diferencia de
SalidaConsola, que sí limita su frecuencia con config.FRECUENCIA_ENVIO):
el objetivo de esta clase, por ahora, es medir el límite real de
Robot/firmware sin enmascararlo (ver pruebas/medir_robot.py). Si tras
medir se decide agregar throttling, debe ser una decisión explícita, no
un efecto secundario de copiar el patrón de SalidaConsola.
"""

import config
from comunicacion.robot_mbot import Robot
from control.contratos import ComandoRobot
from comunicacion.salida import SalidaRobot


class SalidaMBot(SalidaRobot):
    """Traduce un ComandoRobot continuo a los comandos discretos que
    entiende el mBot del docente, sobre una conexión Bluetooth real.
    """

    def __init__(self, mac_address: str | None = None):
        self._robot = Robot(mac_address or config.MAC_MBOT)

    def conectar(self) -> None:
        """Abre la conexión Bluetooth con el mBot.

        Recibe: nada. Devuelve: nada.
        """
        self._robot.conectar()

    def enviar(self, comando: ComandoRobot) -> None:
        """Traduce comando.accion a un método discreto de Robot.

        Recibe: comando (ComandoRobot; se usa solo comando.accion,
            comando.izquierda/derecha se ignoran porque el robot no
            acepta magnitudes de velocidad).
        Devuelve: nada.
        """
        if comando.accion == "AVANZAR":
            self._robot.adelante()
        elif comando.accion == "GIRAR_IZQUIERDA":
            self._robot.izquierda()
        elif comando.accion == "GIRAR_DERECHA":
            self._robot.derecha()
        elif comando.accion == "GIRAR_SOBRE_EJE":
            # El firmware de Robot.py NO tiene un giro sobre el eje real:
            # turnLeft()/turnRight() (ver arduinoFinal.ino) ponen ambos
            # motores en el mismo sentido, con lo que el mBot gira con
            # un radio amplio, no sobre su propio centro. Se usa el
            # signo de comando.derecha para decidir el lado (misma
            # convención que control/contratos.py:calcular_accion:
            # derecha>izquierda gira el chasis hacia la derecha),
            # sabiendo que el movimiento resultante no es el giro en
            # sitio que la máquina de estados asume al pedirlo.
            if comando.derecha > comando.izquierda:
                self._robot.derecha()
            else:
                self._robot.izquierda()
        else:  # "DETENER"
            self._robot.parar()

    def detener(self) -> None:
        """Fuerza la parada inmediata del mBot.

        Recibe: nada. Devuelve: nada.
        """
        self._robot.parar()

    def cerrar(self) -> None:
        """Detiene el mBot y cierra la conexión Bluetooth.

        Recibe: nada. Devuelve: nada.
        """
        self._robot.parar()
        self._robot.cerrar()
