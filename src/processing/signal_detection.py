"""Módulo futuro para detectar señales geométricas.

Se analizarán octágonos rojos/verde para distinguir PARE y SIGA.
"""


class SignalDetector:
    def __init__(self):
        self.detected_signal = None

    def update(self, frame):
        # TODO: detectar contornos, aproximar polígonos y verificar geometría.
        return self.detected_signal
