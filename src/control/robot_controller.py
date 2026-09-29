"""Control diferencial lógico con PD y máquina de estados."""

import time

from src.config import settings


class RobotController:
    FOLLOW = "SEGUIR_LÍNEA"
    STOP = "PARE"
    RESUME = "REANUDAR"
    GO = "SIGA"
    LOST = "LÍNEA_PERDIDA"

    def __init__(self):
        self.left_speed = 0.0
        self.right_speed = 0.0
        self.state = self.FOLLOW
        self.previous_error = 0.0
        self.last_error = 0.0
        self.stop_until = 0.0
        self.ignore_red_until = 0.0

    @staticmethod
    def _limit(value, minimum=0.0, maximum=255.0):
        return max(minimum, min(maximum, value))

    def update(self, line_error: float, signal: str = None, angle: float = 0.0,
               confidence: float = 1.0, now=None):
        now = time.monotonic() if now is None else now
        if self.state == self.STOP:
            if now < self.stop_until:
                self.left_speed = self.right_speed = 0.0
                return self.left_speed, self.right_speed
            self.state = self.RESUME
            self.ignore_red_until = now + settings.RESUME_IGNORE_SECONDS
        elif self.state == self.RESUME and now >= self.ignore_red_until:
            self.state = self.FOLLOW
        elif self.state == self.GO:
            self.state = self.FOLLOW

        if signal == "PARE" and self.state != self.RESUME and now >= self.ignore_red_until:
            self.state = self.STOP
            self.stop_until = now + settings.STOP_SECONDS
            self.left_speed = self.right_speed = 0.0
            return self.left_speed, self.right_speed
        if signal == "SIGA":
            self.state = self.GO

        if confidence < settings.LOST_LINE_CONFIDENCE:
            self.state = self.LOST
            turn = settings.KP * self.last_error * settings.MAX_TURN
            self.left_speed = self._limit(settings.BASE_SPEED + turn)
            self.right_speed = self._limit(settings.BASE_SPEED - turn)
            return self.left_speed, self.right_speed

        delta_error = line_error - self.previous_error
        turn = settings.KP * line_error * settings.MAX_TURN + settings.KD * delta_error * settings.MAX_TURN
        turn += settings.KA * angle * settings.MAX_TURN / 45.0
        turn = self._limit(turn, -settings.MAX_TURN, settings.MAX_TURN)
        self.left_speed = self._limit(settings.BASE_SPEED + turn)
        self.right_speed = self._limit(settings.BASE_SPEED - turn)
        self.previous_error = line_error
        self.last_error = line_error
        if self.state == self.LOST:
            self.state = self.FOLLOW
        return self.left_speed, self.right_speed

    def stop(self):
        self.left_speed = self.right_speed = 0.0
