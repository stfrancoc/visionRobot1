"""Adaptador asíncrono al protocolo discreto de master_pc/Robot.py."""

import importlib.util
import threading
import time
from pathlib import Path

from src.config import settings


class BluetoothRobotExecutor:
    """Traduce velocidades diferenciales a comandos w/s/a/d/x sin bloquear visión."""

    COMMAND_METHODS = {
        "w": "adelante",
        "s": "atras",
        "a": "izquierda",
        "d": "derecha",
        "x": "parar",
    }

    def __init__(self, mac_address=None, executor_path=None, port=None,
                 robot_factory=None, turn_deadband=None, min_pulse_interval=None,
                 max_pulse_interval=None):
        self.mac_address = mac_address or settings.BLUETOOTH_MAC
        self.executor_path = Path(executor_path or settings.ROBOT_EXECUTOR_PATH)
        self.port = settings.BLUETOOTH_PORT if port is None else port
        self.robot_factory = robot_factory
        self.turn_deadband = settings.ROBOT_TURN_DEADBAND if turn_deadband is None else turn_deadband
        self.min_pulse_interval = settings.ROBOT_MIN_PULSE_INTERVAL if min_pulse_interval is None else min_pulse_interval
        self.max_pulse_interval = settings.ROBOT_MAX_PULSE_INTERVAL if max_pulse_interval is None else max_pulse_interval
        self.robot = None
        self._condition = threading.Condition()
        self._desired_command = None
        self._desired_interval = self.min_pulse_interval
        self._closing = False
        self._connected = False
        self._thread = None
        self.last_error = None

    @staticmethod
    def map_speeds(left, right, turn_deadband=None):
        """Reduce el par a la primitiva direccional más cercana del firmware."""
        deadband = settings.ROBOT_TURN_DEADBAND if turn_deadband is None else turn_deadband
        left, right = float(left), float(right)
        if abs(left) < 8 and abs(right) < 8:
            return "x", 0.0
        if left < 0 and right < 0:
            return "s", min(255.0, (abs(left) + abs(right)) / 2)
        if left < 0 or right < 0:
            return "x", 0.0
        difference = left - right
        if difference > deadband:
            return "d", min(255.0, abs(difference))
        if difference < -deadband:
            return "a", min(255.0, abs(difference))
        return "w", min(255.0, (left + right) / 2)

    def _load_robot_class(self):
        path = self.executor_path
        if path.is_dir():
            path = path / "Robot.py"
        if not path.is_file():
            raise FileNotFoundError(f"No se encontró el executor Robot.py: {path}")
        spec = importlib.util.spec_from_file_location("reference_robot_executor", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"No se pudo cargar el executor: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Robot

    def connect(self):
        if not self.mac_address:
            raise ValueError("Configura BLUETOOTH_MAC en .env o indica --bluetooth-mac")
        factory = self.robot_factory or self._load_robot_class()
        self.robot = factory(self.mac_address, port=self.port)
        self.robot.conectar()
        self._connected = True
        self._closing = False
        self._thread = threading.Thread(target=self._send_loop, name="robot-bluetooth", daemon=True)
        self._thread.start()

    @property
    def connected(self):
        return self._connected and self.last_error is None

    def set_speeds(self, left, right):
        if not self.connected:
            return False
        command, intensity = self.map_speeds(left, right, self.turn_deadband)
        if command == "x":
            interval = self.min_pulse_interval
        else:
            pulse_duration = 0.03 if command in ("a", "d") else 0.10
            utilization = max(0.08, min(1.0, intensity / 255.0))
            interval = max(self.min_pulse_interval, pulse_duration / utilization)
            interval = min(self.max_pulse_interval, interval)
        with self._condition:
            self._desired_command = command
            self._desired_interval = interval
            self._condition.notify()
        return True

    def _send_loop(self):
        last_command = None
        last_sent_at = 0.0
        try:
            while True:
                with self._condition:
                    while self._desired_command is None and not self._closing:
                        self._condition.wait()
                    command = "x" if self._closing else self._desired_command
                    interval = self._desired_interval
                    if command == last_command:
                        if self._closing or command == "x":
                            break
                        remaining = interval - (time.monotonic() - last_sent_at)
                        if remaining > 0:
                            self._condition.wait(timeout=remaining)
                            continue
                getattr(self.robot, self.COMMAND_METHODS[command])()
                last_command = command
                last_sent_at = time.monotonic()
                if self._closing and command == "x":
                    break
        except Exception as error:
            self.last_error = error
            self._connected = False
            try:
                self.robot.cerrar()
            except Exception:
                pass

    def close(self):
        if self.robot is None:
            return
        if self._connected:
            with self._condition:
                self._closing = True
                self._condition.notify()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
        try:
            self.robot.cerrar()
        finally:
            self._connected = False