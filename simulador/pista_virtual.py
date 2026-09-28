"""Simulador cinemático simple de la pista y el robot.

Permite calibrar el controlador y la máquina de estados sin robot y sin
visión real. En cada paso, la diferencia entre las velocidades de rueda
que decide nuestro código cambia la orientación del robot, y la
orientación cambia su posición lateral respecto a la línea: es un lazo
cerrado, igual que en la pista física.

A partir de la posición y orientación simuladas se generan un
ResultadoLinea y un ResultadoSenales coherentes, con ruido opcional,
para que se comporten como la salida real de los módulos de visión.
"""

import random
from dataclasses import dataclass

from control.contratos import ResultadoLinea, ResultadoSenales

ANCHO_PISTA = 1.0  # Media pista en las mismas unidades que la posición lateral: error=1 significa salirse por el borde.
GANANCIA_ORIENTACION = 0.05  # Qué tanto cambia la orientación por unidad de diferencia de ruedas y de dt.
GANANCIA_POSICION = 0.8  # Qué tanto cambia la posición lateral por unidad de (orientación × velocidad de avance × dt).
GANANCIA_CURVATURA = 0.012  # Qué tanto empuja la curvatura del tramo a la posición lateral por unidad de (velocidad de avance × dt).
DISTANCIA_FRANJA_LEJANA = 0.35  # Fracción de la pista que se "adelanta" para estimar el ángulo (curva próxima).
ORIENTACION_MAXIMA = 1.5  # Máximo ángulo relativo a la línea (radianes-equivalente); más allá el robot ya está de costado.


@dataclass
class Tramo:
    """Un tramo de pista con longitud y curvatura o evento constantes.

    tipo: "recta", "curva", "pare", "siga", "sin_linea".
    longitud: duración del tramo en segundos simulados.
    curvatura: cuánto se desplaza el centro de la línea por unidad de
        avance (positivo = curva a la derecha, negativo = izquierda).
    """

    tipo: str
    longitud: float
    curvatura: float = 0.0


def crear_pista_calibracion() -> list[Tramo]:
    """Construye la secuencia de tramos usada para calibrar el control.

    Recibe: nada.
    Devuelve: lista de Tramo con, en orden: recta, curva suave a la
        derecha, curva cerrada a la izquierda, tramo con señal PARE
        acercándose, tramo con señal SIGA, tramo sin línea (pérdida) y
        recuperación.
    Complejidad: O(1).
    """
    return [
        Tramo(tipo="recta", longitud=4.0, curvatura=0.0),
        Tramo(tipo="curva", longitud=6.0, curvatura=0.35),
        Tramo(tipo="curva", longitud=6.0, curvatura=-0.7),
        Tramo(tipo="pare", longitud=6.0, curvatura=0.0),
        Tramo(tipo="recta", longitud=2.0, curvatura=0.0),
        Tramo(tipo="siga", longitud=4.0, curvatura=0.0),
        Tramo(tipo="sin_linea", longitud=3.0, curvatura=0.0),
        Tramo(tipo="recta", longitud=4.0, curvatura=0.0),
    ]


class PistaVirtual:
    """Modelo cinemático 2D simplificado del robot sobre una pista de
    tramos, con generación de ResultadoLinea/ResultadoSenales.
    """

    def __init__(self, tramos: list[Tramo], ruido: float = 0.0, semilla: int | None = None):
        self.tramos = tramos
        self.ruido = ruido
        self.aleatorio = random.Random(semilla)

        self.posicion_lateral = 0.0  # 0 = centrado en la línea; -1..1 = hacia el borde.
        self.orientacion = 0.0  # Ángulo relativo a la línea; 0 = alineado.
        self.avance_tramo = 0.0
        self.indice_tramo = 0
        self.distancia_total = 0.0
        self.fuera_de_pista_eventos = 0
        self._fuera_de_pista_anterior = False

    def tramo_actual(self) -> Tramo | None:
        """Devuelve el tramo en el que está el robot, o None si terminó.

        Recibe: nada. Devuelve: Tramo o None.
        Complejidad: O(1).
        """
        if self.indice_tramo >= len(self.tramos):
            return None
        return self.tramos[self.indice_tramo]

    def terminado(self) -> bool:
        """Indica si el robot ya recorrió todos los tramos.

        Recibe: nada. Devuelve: bool.
        Complejidad: O(1).
        """
        return self.tramo_actual() is None

    def paso(self, izquierda: int, derecha: int, dt: float) -> None:
        """Avanza la simulación un paso de tiempo dt.

        Recibe: izquierda, derecha (velocidades de rueda decididas por
            el controlador) y dt (segundos).
        Devuelve: nada; actualiza la posición y orientación internas.
        Complejidad: O(1).
        """
        tramo = self.tramo_actual()
        if tramo is None:
            return

        velocidad_avance = (izquierda + derecha) / 2.0

        # Mientras la línea está fuera de cuadro (primera mitad del tramo
        # "sin_linea") no hay ninguna referencia visual con la que
        # actualizar posición u orientación: el robot gira buscando, pero
        # eso no es observable hasta que la visión reencuentra la línea.
        # Al reencontrarla se asume que quedó centrado en su dirección
        # (orientación 0), igual que ocurre en la pista real al recuperar
        # el seguimiento.
        en_busqueda_ciega = tramo.tipo == "sin_linea" and self.avance_tramo < tramo.longitud * 0.5
        if en_busqueda_ciega:
            self.orientacion = 0.0
        else:
            # diferencia_ruedas > 0 (izquierda más rápida) gira el chasis
            # hacia la derecha, igual que en el robot real: por eso resta
            # de la posición lateral en vez de sumar (así corrige un error
            # positivo, "línea a la derecha", moviendo el chasis hacia la
            # derecha).
            diferencia_ruedas = izquierda - derecha
            self.orientacion += GANANCIA_ORIENTACION * diferencia_ruedas * dt
            self.orientacion = max(-ORIENTACION_MAXIMA, min(ORIENTACION_MAXIMA, self.orientacion))

            # La posición lateral solo cambia por el rumbo cuando el robot
            # efectivamente avanza (o retrocede): girar en el sitio, con
            # velocidad de avance ~0, no debería desplazar el centroide.
            self.posicion_lateral -= GANANCIA_POSICION * self.orientacion * velocidad_avance * dt
            self.posicion_lateral += GANANCIA_CURVATURA * tramo.curvatura * velocidad_avance * dt

            fuera_de_pista = abs(self.posicion_lateral) > ANCHO_PISTA
            if fuera_de_pista and not self._fuera_de_pista_anterior:
                self.fuera_de_pista_eventos += 1
            self._fuera_de_pista_anterior = fuera_de_pista

        self.distancia_total += abs(velocidad_avance) * dt

        # El progreso dentro del tramo avanza con el tiempo, no con la
        # distancia recorrida: así un tramo "sin_linea" también termina
        # cuando el robot gira en sitio buscando la línea (velocidad de
        # avance ~0), igual que ocurriría con un temporizador en la pista real.
        self.avance_tramo += dt
        if self.avance_tramo >= tramo.longitud:
            self.avance_tramo = 0.0
            self.indice_tramo += 1

    def _con_ruido(self, valor: float) -> float:
        """Agrega ruido uniforme opcional a un valor.

        Recibe: valor (float). Devuelve: valor perturbado.
        Complejidad: O(1).
        """
        if self.ruido <= 0:
            return valor
        return valor + self.aleatorio.uniform(-self.ruido, self.ruido)

    def generar_resultado_linea(self) -> ResultadoLinea:
        """Genera un ResultadoLinea coherente con el estado simulado.

        Recibe: nada.
        Devuelve: ResultadoLinea con error y angulo derivados de la
            posición lateral y la orientación, o valida=False si el
            robot se salió de la pista, o si el tramo actual es
            "sin_linea" y todavía está en su primera mitad (simula que
            la línea reaparece, ya buscada, en la segunda mitad del
            tramo, igual que la señal PARE se confirma a mitad de su
            tramo en generar_resultado_senales).
        Complejidad: O(1).
        """
        tramo = self.tramo_actual()
        linea_ausente = tramo is not None and tramo.tipo == "sin_linea" and self.avance_tramo < tramo.longitud * 0.5
        if tramo is None or linea_ausente or abs(self.posicion_lateral) > ANCHO_PISTA:
            return ResultadoLinea(error=0.0, angulo=0.0, confianza=0, valida=False)

        error = self._con_ruido(max(-1.0, min(1.0, self.posicion_lateral / ANCHO_PISTA)))
        posicion_lejana = self.posicion_lateral + self.orientacion * DISTANCIA_FRANJA_LEJANA
        angulo = self._con_ruido(max(-1.0, min(1.0, (posicion_lejana - self.posicion_lateral) / ANCHO_PISTA)))

        return ResultadoLinea(error=error, angulo=angulo, confianza=4, valida=True)

    def generar_resultado_senales(self) -> ResultadoSenales:
        """Genera un ResultadoSenales coherente con el tramo simulado.

        Recibe: nada.
        Devuelve: ResultadoSenales con senal="PARE" o "SIGA" cuando el
            tramo actual es de ese tipo, marcando en_disparo=True solo
            en la mitad final del tramo (simula que la señal se acerca).
        Complejidad: O(1).
        """
        tramo = self.tramo_actual()
        if tramo is None or tramo.tipo not in ("pare", "siga"):
            return ResultadoSenales(senal=None, en_disparo=False)

        senal = "PARE" if tramo.tipo == "pare" else "SIGA"
        en_disparo = self.avance_tramo >= tramo.longitud * 0.5
        return ResultadoSenales(senal=senal, en_disparo=en_disparo)
