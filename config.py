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

# CALIBRAR CON VIDEO: provisionales, calibradas con
# simulador/calibrar_ganancias.py sobre el simulador REALISTA (latencia
# total=150ms repartida en percepción+actuación, motores con zona
# muerta/inercia, ruido de detección), no con datos reales de la visión.
# Del último barrido (364 combinaciones, tras agregar el estado
# REALINEANDO) se eligió deliberadamente la combinación más conservadora
# — menor cantidad de salidas de pista y menor oscilación — en vez de la
# de mayor porcentaje de tiempo en seguimiento: el simulador todavía
# sobreestima el error de reingreso tras perder la línea (ver
# capturas/reporte_calibracion.md), así que optimizar agresivamente
# contra ese error no es confiable. Deberán recalibrarse en cuanto haya
# video real.
KP = 10.0  # Ganancia proporcional: qué tanto giro (en unidades de velocidad de rueda) se aplica por unidad de error lateral en [-1, 1].
KD = 15.0  # Ganancia derivativa: amortigua oscilaciones reaccionando a qué tan rápido cambia el error suavizado.
KA = 15.0  # Ganancia sobre el ángulo estimado: anticipa curvas antes de que crezca el error lateral.

ALFA_SUAVIZADO = 0.4  # Peso del error nuevo en la media exponencial (0-1). Más alto = menos suavizado.

VEL_BASE = 60  # CALIBRAR CON VIDEO. Velocidad de avance en tramo recto, con error y ángulo cercanos a cero.

# CALIBRAR CON VIDEO. Velocidad de avance mínima en curvas cerradas
# (error o ángulo altos). Con 25 quedaba demasiado cerca de
# ZONA_MUERTA=18 (solo 7 unidades de margen sobre un rango de 100):
# cualquier giro, aunque fuera pequeño, hacía que una rueda cayera por
# debajo del umbral y perdiera corrección por completo. 38 deja ~20
# unidades de margen.
VEL_MIN = 38

# Límite superior de velocidad para cada rueda, en ambos sentidos: el
# rango de ComandoRobot.izquierda/derecha es [-VEL_MAX, VEL_MAX] = [-100,
# 100], NO el PWM 0-255 del Arduino. El compañero de Bluetooth reescala
# este rango a PWM en su propio código; aquí nunca se habla en unidades
# de PWM. Si esa reescala cambiara de convención, KP/KD/KA habría que
# recalibrarlos, porque dependen de esta escala (ver simulador/calibrar_ganancias.py).
VEL_MAX = 100

VEL_BUSQUEDA = 35  # CALIBRAR CON VIDEO. Velocidad de giro sobre el eje al buscar la línea perdida.

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

# Un seguidor de línea real que recupera la línea girando sobre su eje no
# avanza estando torcido: sigue girando (con avance nulo) hasta quedar
# alineado, y solo entonces retoma el seguimiento normal. REALINEANDO es
# ese estado intermedio entre LINEA_PERDIDA y SEGUIR_LINEA.
#
# El umbral de alineación se mide sobre 'angulo' (orientación estimada
# del chasis respecto a la línea), no sobre 'error' (desplazamiento
# lateral): con avance nulo el robot solo puede corregir su rumbo
# girando, nunca su posición lateral (eso requiere avanzar, que es
# justamente lo que hace después SEGUIR_LINEA, ya con el chasis
# derecho). Usar 'error' como criterio dejaría a REALINEANDO sin salida
# posible siempre que la posición quedó lejos del centro al perder la
# línea, porque girar en el sitio nunca la acerca.
ERROR_REALINEADO = 0.35  # |angulo| por debajo de este umbral se considera "suficientemente alineado" para retomar el seguimiento normal.
FOTOGRAMAS_REALINEADO_CONSECUTIVOS = 3  # Cuántos fotogramas seguidos con |angulo| < ERROR_REALINEADO se exigen antes de pasar a SEGUIR_LINEA (evita salir por un solo fotograma de ruido).

# Velocidad mínima de giro (en magnitud) que usa realinear() siempre que
# el ángulo no sea prácticamente cero, igual que VEL_MIN evita que
# calcular() caiga en zona muerta en curvas suaves. Sin este piso,
# KP_REALINEACION * angulo da un comando por debajo de ZONA_MUERTA
# precisamente cuando el ángulo ya es pequeño (la zona donde el robot
# está a punto de terminar de alinearse): el motor real no reacciona a
# un comando anulado por zona muerta, así que el chasis queda a merced
# de la inercia residual del giro de búsqueda anterior, que puede
# sacarlo del campo de visión de nuevo antes de completar la
# alineación. Debe superar ZONA_MUERTA con margen.
# CALIBRAR CON VIDEO.
VEL_MIN_REALINEACION = 22
TIEMPO_MAX_REALINEANDO = 2.0  # Segundos máximos intentando alinearse antes de volver a LINEA_PERDIDA (si la línea vuelve a salir del cuadro, no tiene sentido seguir girando despacio ahí mismo).
KP_REALINEACION = 25.0  # CALIBRAR CON VIDEO. Ganancia proporcional usada solo en REALINEANDO: gira hacia el ángulo, sin componente derivativa, para converger de forma simple y predecible.

# ==========================================================================
# SIMULACIÓN (simulador/pista_virtual.py) — no afecta al robot real, solo
# a qué tan exigente es la pista virtual para calibrar el control.
# ==========================================================================

# La latencia total del lazo cerrado (150ms estimados) se reparte en dos
# tramos físicamente distintos, cada uno con su propia cola en
# pista_virtual.py: percepción (captura por WiFi + procesamiento de
# visión, hasta tener un ResultadoLinea) y actuación (Bluetooth +
# firmware, hasta que el comando mueve las ruedas). Aplicar el total a
# cada cola por separado duplicaría el retardo real a 300ms.
#
# CALIBRAR CON VIDEO: son estimaciones. El barrido de latencia (ver
# capturas/reporte_calibracion.md) muestra que el sistema es estable
# hasta ~80ms totales y se degrada abruptamente a partir de ~100ms, así
# que medir la latencia real del pipeline (WiFi + procesamiento +
# Bluetooth) es un requisito de diseño, no solo un ajuste fino: si el
# pipeline real excede ese umbral, ninguna ganancia de control lo
# compensa y hay que reducir la latencia misma (menor resolución,
# menos preprocesamiento, FRECUENCIA_ENVIO más alta).
LATENCIA_PERCEPCION_MS = 120  # Retardo entre que la cámara captura el fotograma y la visión entrega un ResultadoLinea.
LATENCIA_ACTUACION_MS = 30  # Retardo entre que se emite un ComandoRobot y las ruedas realmente lo ejecutan (Bluetooth + firmware).

PASO_SIMULACION_MS = 50  # Paso de tiempo de la simulación, equivalente a unos 20 fotogramas por segundo.

ZONA_MUERTA = 18  # CALIBRAR CON VIDEO (medir en el robot real con una rampa de PWM). Velocidad de rueda por debajo de la cual el motor real no arranca (PWM insuficiente).

TAU_MOTOR = 0.05  # CALIBRAR CON VIDEO. Constante de tiempo (s) del filtro de primer orden que modela la inercia de cada motor.

RUIDO_ERROR = 0.03  # CALIBRAR CON VIDEO. Desviación estándar del ruido gaussiano sumado al error de línea entregado al control.
RUIDO_ANGULO = 0.05  # CALIBRAR CON VIDEO. Desviación estándar del ruido gaussiano sumado al ángulo estimado.
PROB_FRANJA_PERDIDA = 0.05  # CALIBRAR CON VIDEO. Probabilidad de que un fotograma llegue con confianza reducida (una franja menos detectada).
PROB_LINEA_INVALIDA = 0.02  # CALIBRAR CON VIDEO. Probabilidad de que un fotograma llegue con valida=False aunque el robot esté sobre la línea (desenfoque, sombras, franja de una señal).

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
