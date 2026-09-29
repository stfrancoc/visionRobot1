"""Clase Robot original del docente (repositorio
practica-vision-artificial-robotica, carpeta master_pc/Robot.py), copiada
aquí sin modificar porque esa carpeta no está versionada en este repo
(ver .gitignore): así comunicacion/salida_mbot.py no depende de una ruta
externa que solo existe en la máquina de quien la clonó.

No se le ha cambiado ni una línea a propósito, para que siga siendo
exactamente el contrato Bluetooth que el docente entrega. Cualquier
adaptación (throttling, nombres en español, etc.) va en
comunicacion/salida_mbot.py, que es el que sí sigue las convenciones de
CLAUDE.md.
"""

import socket
import time


class Robot:
    def __init__(self, mac_address: str, port: int = 1):
        self.mac_address = mac_address
        self.port = port
        self.bluetooth_socket = None

    def conectar(self):
        self.bluetooth_socket = socket.socket(
            socket.AF_BLUETOOTH,
            socket.SOCK_STREAM,
            socket.BTPROTO_RFCOMM
        )

        try:
            print(f"Conectando a {self.mac_address}...")
            self.bluetooth_socket.connect((self.mac_address, self.port))
            print("Conexión establecida")
        except OSError:
            self.cerrar()
            raise

    def _enviar(self, comando: str):
        if self.bluetooth_socket is None:
            raise RuntimeError("El robot no está conectado")

        self.bluetooth_socket.sendall(comando.encode("utf-8"))
        print(f"Comando enviado: {comando}")
        time.sleep(0.1)

    def adelante(self):
        self._enviar("w")

    def atras(self):
        self._enviar("s")

    def izquierda(self):
        self._enviar("a")

    def derecha(self):
        self._enviar("d")

    def parar(self):
        self._enviar("x")

    def cerrar(self):
        if self.bluetooth_socket is not None:
            self.bluetooth_socket.close()
            self.bluetooth_socket = None
            print("Conexión cerrada")
