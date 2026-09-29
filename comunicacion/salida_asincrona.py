"""SalidaAsincrona: envuelve cualquier SalidaRobot para que enviar()
no bloquee el ciclo de visión.

El Robot del docente (comunicacion/robot_mbot.py) hace un
time.sleep(0.1) después de cada comando Bluetooth. Como main.py llamaba
a enviar() dentro del mismo hilo que procesa la imagen, ese sleep se
sumaba al ciclo completo: medido en las grabaciones test1-test4 con el
robot conectado, el pipeline bajaba a ~9 FPS y ~104ms de latencia
total, contra ~59 FPS y ~5ms procesando los mismos videos sin robot.
Esos 104ms superan el umbral de ~80-100ms que la calibración del
simulador identificó como el punto donde el lazo de control se
degrada.

Aquí enviar() solo deja el comando en una casilla y retorna de
inmediato; un hilo aparte toma el último comando disponible y lo envía
al robot a su propio ritmo. El ciclo de visión recupera su velocidad y
el robot sigue recibiendo comandos tan seguido como el Bluetooth
permita.

Se guarda SOLO el último comando, no una cola: si la visión produce
comandos más rápido de lo que el Bluetooth los despacha, encolarlos
haría que el robot ejecute órdenes viejas con retraso creciente
(exactamente el problema que vision/captura.py evita descartando
fotogramas viejos). Un comando de control solo tiene sentido si es el
más reciente.
"""

import threading

from comunicacion.salida import SalidaRobot
from control.contratos import ComandoRobot


class SalidaAsincrona(SalidaRobot):
    """Envuelve otra SalidaRobot y hace sus envíos en un hilo aparte."""

    def __init__(self, salida_real: SalidaRobot):
        """Arranca el hilo despachador.

        Recibe: salida_real (SalidaRobot a la que se delegan los
            envíos, p. ej. SalidaMBot).
        Devuelve: nada.
        """
        self._salida_real = salida_real
        self._comando_pendiente = None
        self._candado = threading.Lock()
        self._hay_comando = threading.Event()
        self._detener = False
        self._hilo = threading.Thread(target=self._despachar, daemon=True)
        self._hilo.start()

    def _despachar(self) -> None:
        """Bucle del hilo despachador: toma el último comando dejado
        por enviar() y lo entrega a la salida real.

        Recibe: nada. Devuelve: nada (corre hasta que se pide detener).
        """
        while not self._detener:
            if not self._hay_comando.wait(timeout=0.1):
                continue

            with self._candado:
                comando = self._comando_pendiente
                self._comando_pendiente = None
                self._hay_comando.clear()

            if comando is not None:
                self._salida_real.enviar(comando)

    def enviar(self, comando: ComandoRobot) -> None:
        """Deja el comando para que el hilo despachador lo envíe.

        Retorna de inmediato: no espera a que el Bluetooth termine. Si
        ya había un comando pendiente sin despachar, se reemplaza (ver
        el docstring del módulo: siempre gana el más reciente).

        Recibe: comando (ComandoRobot). Devuelve: nada.
        """
        with self._candado:
            self._comando_pendiente = comando
        self._hay_comando.set()

    def detener(self) -> None:
        """Detiene el robot de inmediato, en el hilo que llama.

        No pasa por el hilo despachador a propósito: detener() se usa
        para parar el robot (incluso en un cierre por excepción) y debe
        ejecutarse ya, no quedar pendiente en una casilla que quizá
        nadie llegue a despachar. También descarta cualquier comando de
        movimiento pendiente, para que el despachador no mueva el robot
        justo después de haberlo detenido.

        Recibe: nada. Devuelve: nada.
        """
        with self._candado:
            self._comando_pendiente = None
            self._hay_comando.clear()
        self._salida_real.detener()

    def cerrar(self) -> None:
        """Detiene el hilo despachador y cierra la salida real.

        Recibe: nada. Devuelve: nada.
        """
        self._detener = True
        self._hay_comando.set()
        self._hilo.join(timeout=1.0)
        self._salida_real.cerrar()
