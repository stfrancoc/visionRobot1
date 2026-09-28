"""Contratos de datos entre visión, control y comunicación.

Estas dataclasses son el acuerdo entre el equipo de visión (que produce
ResultadoLinea y ResultadoSenales) y este módulo de control (que las
consume y produce ComandoRobot para el compañero de comunicación
Bluetooth). Todas tienen valores por defecto para poder desarrollar y
probar el control sin depender de que la visión ya esté lista.

No se deben cambiar los nombres ni los tipos de estos campos sin avisar
al resto del equipo, porque rompería la integración entre fases.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResultadoLinea:
    """Salida del módulo de visión que detecta la línea a seguir.

    error: desplazamiento lateral normalizado en [-1, 1]. Negativo si la
        línea está a la izquierda del centro del cuadro.
    angulo: inclinación estimada en [-1, 1], comparando la franja lejana
        con la cercana (anticipa curvas).
    confianza: número de franjas horizontales donde se encontró línea
        válida.
    valida: True si hay suficiente línea detectada para guiarse con ella.
    """

    error: float = 0.0
    angulo: float = 0.0
    confianza: int = 0
    valida: bool = False


@dataclass
class ResultadoSenales:
    """Salida del módulo de visión que detecta los octágonos PARE/SIGA.

    senal: "PARE", "SIGA" o None, ya confirmada temporalmente (varios
        fotogramas seguidos) por el módulo de visión.
    en_disparo: True si el centroide de la señal cruzó la línea de
        disparo, es decir que la señal ya está lo bastante cerca para
        actuar.
    """

    senal: Optional[str] = None
    en_disparo: bool = False


@dataclass
class ComandoRobot:
    """Comando final que se entrega a la interfaz SalidaRobot.

    izquierda, derecha: velocidad de cada rueda en [-VEL_MAX, VEL_MAX].
    estado: nombre del estado actual de la máquina de estados.
    accion: etiqueta discreta derivada de las velocidades ("AVANZAR",
        "GIRAR_IZQUIERDA", "GIRAR_DERECHA", "GIRAR_SOBRE_EJE" o
        "DETENER"), para adaptarnos al formato que finalmente espere el
        robot: si el Arduino recibe comandos discretos se usa 'accion',
        si recibe velocidades continuas se usan 'izquierda' y 'derecha'.
    """

    izquierda: int = 0
    derecha: int = 0
    estado: str = "SEGUIR_LINEA"
    accion: str = "DETENER"


def calcular_accion(izquierda: int, derecha: int, dif_giro: int) -> str:
    """Deriva la acción discreta a partir de las velocidades de las ruedas.

    Recibe: izquierda y derecha (velocidades enteras), dif_giro (umbral
        mínimo de diferencia entre ruedas para considerar que hay giro,
        viene de config.DIF_GIRO).
    Devuelve: una de "DETENER", "GIRAR_SOBRE_EJE", "GIRAR_IZQUIERDA",
        "GIRAR_DERECHA" o "AVANZAR".
    Complejidad: O(1).
    """
    if izquierda == 0 and derecha == 0:
        return "DETENER"

    diferencia = izquierda - derecha

    if izquierda * derecha < 0:
        return "GIRAR_SOBRE_EJE"

    if abs(diferencia) < dif_giro:
        return "AVANZAR"

    return "GIRAR_IZQUIERDA" if diferencia > 0 else "GIRAR_DERECHA"
