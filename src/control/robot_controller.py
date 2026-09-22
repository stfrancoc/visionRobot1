"""Módulo futuro para control de motores.

Aquí se integrará la lógica de control proporcional/derivativa con la salida de
la visión para mover el robot en tiempo real.
"""


class RobotController:
    def __init__(self):
        self.left_speed = 0
        self.right_speed = 0

    def update(self, line_error: float, signal: str = None):
        # TODO: aplicar lógica de control (P, PD) y comandar motores
        return self.left_speed, self.right_speed
