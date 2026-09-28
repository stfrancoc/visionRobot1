"""Configuración centralizada del proyecto.

Aquí viven todos los parámetros ajustables para que ningún módulo tenga
números mágicos. Este archivo solo contiene, por ahora, las secciones de
control y máquina de estados (rama feature/control-movimiento). Las
secciones de visión (línea, señales, cámara) las agregan los compañeros
responsables de esas fases.

Si existe `calibracion_control.json` en la raíz del proyecto, sus valores
tienen prioridad sobre los de esta sección (ver simulador/visor.py, que lo
genera al presionar 'g').
"""

import json
import os

RUTA_CALIBRACION_CONTROL = os.path.join(os.path.dirname(__file__), "calibracion_control.json")

# ==========================================================================
# CONTROL PD
# ==========================================================================

# Calibradas con simulador/calibrar_ganancias.py sobre el simulador
# REALISTA (latencia=150ms, motores con zona muerta/inercia, ruido de
# detección): con el simulador ideal convenía KP=20 KD=10 KA=10, pero
# esas ganancias oscilan bajo latencia real (error medio ~0.70 y
# oscilación medible). KP=5 KD=5 KA=10 es la mejor combinación
# encontrada bajo condiciones realistas (error medio ~0.53, sin
# salidas de pista) y es el punto de partida recomendado para la
# primera prueba con el robot físico.
KP = 5.0  # Ganancia proporcional: qué tanto giro (en unidades de velocidad de rueda) se aplica por unidad de error lateral en [-1, 1].
KD = 5.0  # Ganancia derivativa: amortigua oscilaciones reaccionando a qué tan rápido cambia el error suavizado.
KA = 10.0  # Ganancia sobre el ángulo estimado: anticipa curvas antes de que crezca el error lateral.

ALFA_SUAVIZADO = 0.4  # Peso del error nuevo en la media exponencial (0-1). Más alto = menos suavizado.

VEL_BASE = 60  # Velocidad de avance en tramo recto, con error y ángulo cercanos a cero.
VEL_MIN = 25  # Velocidad de avance mínima en curvas cerradas (error o ángulo altos).
VEL_MAX = 100  # Límite superior de velocidad para cada rueda, en ambos sentidos.

VEL_BUSQUEDA = 35  # Velocidad de giro sobre el eje al buscar la línea perdida.

DIF_GIRO = 8  # Diferencia mínima entre ruedas (unidades de velocidad) para considerar que el robot está girando.

# ==========================================================================
# SALIDA / COMUNICACIÓN
# ==========================================================================

FRECUENCIA_ENVIO = 15  # Frecuencia máxima (Hz) a la que se imprime/envía un ComandoRobot por SalidaConsola.

# ==========================================================================
# MÁQUINA DE ESTADOS
# ==========================================================================

TIEMPO_PARE = 3.0  # Segundos que el robot permanece detenido en el estado PARE.
TIEMPO_ENFRIAMIENTO = 4.0  # Segundos máximos en REANUDAR ignorando el rojo, incluso si no sale del cuadro.
TIEMPO_MAX_PERDIDA = 5.0  # Segundos máximos girando en sitio en LINEA_PERDIDA antes de detenerse y reportar.

# ==========================================================================
# SIMULACIÓN (simulador/pista_virtual.py) — no afecta al robot real, solo
# a qué tan exigente es la pista virtual para calibrar el control.
# ==========================================================================

LATENCIA_MS = 150  # Retardo estimado entre lo que ve la cámara y lo que hacen las ruedas (captura WiFi + procesamiento + Bluetooth).
PASO_SIMULACION_MS = 50  # Paso de tiempo de la simulación, equivalente a unos 20 fotogramas por segundo.

ZONA_MUERTA = 30  # Velocidad de rueda por debajo de la cual el motor real no arranca (PWM insuficiente).

TAU_MOTOR = 0.05  # Constante de tiempo (s) del filtro de primer orden que modela la inercia de cada motor.

RUIDO_ERROR = 0.03  # Desviación estándar del ruido gaussiano sumado al error de línea entregado al control.
RUIDO_ANGULO = 0.05  # Desviación estándar del ruido gaussiano sumado al ángulo estimado.
PROB_FRANJA_PERDIDA = 0.05  # Probabilidad de que un fotograma llegue con confianza reducida (una franja menos detectada).
PROB_LINEA_INVALIDA = 0.02  # Probabilidad de que un fotograma llegue con valida=False aunque el robot esté sobre la línea (desenfoque, sombras, franja de una señal).

SEMILLA_SIMULACION = 42  # Semilla fija del generador aleatorio, para que las corridas de calibración sean reproducibles.


def _cargar_calibracion():
    """Sobrescribe las constantes de control con valores calibrados desde JSON.

    Recibe: nada (lee `RUTA_CALIBRACION_CONTROL` si existe).
    Devuelve: nada, modifica las variables del módulo en su lugar.
    Complejidad: O(1), el archivo tiene un puñado de claves.
    """
    if not os.path.exists(RUTA_CALIBRACION_CONTROL):
        return
    with open(RUTA_CALIBRACION_CONTROL, "r", encoding="utf-8") as archivo:
        valores = json.load(archivo)
    globals().update({clave: valores[clave] for clave in valores if clave in globals()})


_cargar_calibracion()
