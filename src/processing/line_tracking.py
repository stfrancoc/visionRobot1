"""Módulo futuro para seguimiento de línea.

Aquí se calculará el centroide de la línea detectada, el error respecto al centro
visual y la señal de corrección para el controlador del robot.
"""


class LineTracker:
    def __init__(self):
        self.error = 0.0

    def update(self, segmented_frame):
        # TODO: calcular contorno, centroides y error.
        return self.error
