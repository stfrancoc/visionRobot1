"""Simulador cinemático de la pista y el robot, con las imperfecciones
del pipeline real: latencia de control, motores con zona muerta e
inercia, y ruido/fallos de detección.

En cada paso, la diferencia entre las velocidades de rueda que decide
nuestro código cambia la orientación del robot, y la orientación cambia
su posición lateral respecto a la línea: es un lazo cerrado, igual que
en la pista física. A eso se le suma:

- Latencia: la latencia total del lazo cerrado se reparte en dos tramos
  físicamente distintos, cada uno con su propia cola. El ResultadoLinea
  que se entrega al control corresponde a la posición de hace
  LATENCIA_PERCEPCION_MS (cámara + WiFi + procesamiento de visión), y
  el comando que mueve las ruedas es el que se emitió hace
  LATENCIA_ACTUACION_MS (Bluetooth + firmware). Son dos tramos
  consecutivos del mismo lazo, no dos veces el mismo retardo: la
  latencia total percibida por el lazo es la suma de ambos, no el
  doble de una sola.
- Motores reales: zona muerta (no arrancan con PWM bajo) e inercia
  (filtro de primer orden, no saltan al valor ordenado).
- Ruido y fallos de detección: ruido gaussiano en error/ángulo,
  confianza reducida ocasional y fotogramas inválidos aunque el robot
  esté sobre la línea.

Con modo_ideal=True se desactivan las tres imperfecciones (equivalente
al simulador de la fase anterior), para poder comparar directamente
contra el simulador realista.

A partir de la posición y orientación simuladas se generan un
ResultadoLinea y un ResultadoSenales coherentes con lo que vería la
visión real.
"""

import random
from collections import deque
from dataclasses import dataclass

import config
from control.contratos import ResultadoLinea, ResultadoSenales

ANCHO_PISTA = 1.0  # Media pista en las mismas unidades que la posición lateral: error=1 significa salirse por el borde.
GANANCIA_ORIENTACION = 0.05  # Qué tanto cambia la orientación por unidad de diferencia de ruedas y de dt.
GANANCIA_POSICION = 0.8  # Qué tanto cambia la posición lateral por unidad de (orientación × velocidad de avance × dt).
GANANCIA_CURVATURA = 0.012  # Qué tanto empuja la curvatura del tramo a la posición lateral por unidad de (velocidad de avance × dt).
DISTANCIA_FRANJA_LEJANA = 0.35  # Fracción de la pista que se "adelanta" para estimar el ángulo (curva próxima).
ORIENTACION_MAXIMA = 1.5  # Máximo ángulo relativo a la línea (radianes-equivalente) durante seguimiento normal; más allá el robot ya está de costado.
VELOCIDAD_AVANCE_UMBRAL_GIRO = 5.0  # |velocidad_avance| por debajo de este umbral se considera "girando en el sitio" (búsqueda), no avanzando.

# Campo de visión angular de la cámara (misma escala arbitraria que
# `orientacion`): coincide con ORIENTACION_MAXIMA, el ángulo más allá
# del cual el chasis ya se considera "de costado" en seguimiento
# normal. Mientras el chasis gira buscando la línea, esta sigue siendo
# visible solo si su rumbo actual cae dentro de este ángulo; fuera de
# él, la línea existe pero está fuera de cuadro, igual que le pasaría a
# una cámara real con un ángulo de visión limitado.
ANGULO_CAMPO_VISION = ORIENTACION_MAXIMA

# Cuánto vale una "vuelta completa" del chasis en la escala arbitraria
# de `orientacion` (no son radianes reales). Calibrado para que, girando
# en el sitio a VEL_BUSQUEDA, una vuelta complete tome ~2 segundos: con
# GANANCIA_ORIENTACION=0.05 y una diferencia de ruedas típica de
# 2×VEL_BUSQUEDA=70, el cambio es 3.5/segundo, así que 2s de giro dan
# VUELTA_COMPLETA≈7.0. Sin esto, `orientacion` crecería sin límite en
# una sola dirección mientras el robot gira buscando siempre hacia el
# mismo lado, y nunca volvería a caer dentro de ANGULO_CAMPO_VISION.
VUELTA_COMPLETA = 7.0


@dataclass
class Tramo:
    """Un tramo de pista con longitud y curvatura o evento constantes.

    tipo: "recta", "curva", "pare", "siga", "sin_linea".
    longitud: duración del tramo en segundos simulados.
    curvatura: cuánto se desplaza el centro de la línea por unidad de
        avance (positivo = curva a la derecha, negativo = izquierda).
    nombre: etiqueta corta para identificar el tramo en las métricas
        por tramo (p. ej. "curva_cerrada", "s_derecha").
    """

    tipo: str
    longitud: float
    curvatura: float = 0.0
    nombre: str = ""

    def __post_init__(self):
        if not self.nombre:
            self.nombre = self.tipo


def crear_pista_calibracion() -> list[Tramo]:
    """Construye la secuencia de tramos usada para calibrar el control.

    Recibe: nada.
    Devuelve: lista de Tramo con, en orden: recta, curva suave a la
        derecha, curva cerrada a la izquierda, tramo con señal PARE
        acercándose, tramo con señal SIGA, curva muy cerrada (radio
        mínimo visto en los videos de ensayo), tramo en S (derecha
        seguida de izquierda), tramo sin línea (pérdida) y recuperación.
    Complejidad: O(1).
    """
    return [
        Tramo(tipo="recta", longitud=4.0, curvatura=0.0, nombre="recta_inicial"),
        Tramo(tipo="curva", longitud=6.0, curvatura=0.35, nombre="curva_suave_derecha"),
        Tramo(tipo="curva", longitud=6.0, curvatura=-0.7, nombre="curva_cerrada_izquierda"),
        Tramo(tipo="pare", longitud=6.0, curvatura=0.0, nombre="pare"),
        Tramo(tipo="recta", longitud=2.0, curvatura=0.0, nombre="recta_post_pare"),
        Tramo(tipo="siga", longitud=4.0, curvatura=0.0, nombre="siga"),
        Tramo(tipo="curva", longitud=4.0, curvatura=1.1, nombre="curva_muy_cerrada"),
        Tramo(tipo="recta", longitud=1.5, curvatura=0.0, nombre="recta_entre_curvas"),
        Tramo(tipo="curva", longitud=3.0, curvatura=0.9, nombre="s_derecha"),
        Tramo(tipo="curva", longitud=3.0, curvatura=-0.9, nombre="s_izquierda"),
        Tramo(tipo="sin_linea", longitud=3.0, curvatura=0.0, nombre="sin_linea"),
        Tramo(tipo="recta", longitud=4.0, curvatura=0.0, nombre="recta_final"),
    ]


class PistaVirtual:
    """Modelo cinemático 2D del robot sobre una pista de tramos, con
    latencia de control, motores con zona muerta/inercia, ruido y
    fallos de detección (o sin ninguno de estos, en modo_ideal).
    """

    def __init__(self, tramos: list[Tramo], modo_ideal: bool = False, semilla: int | None = None):
        self.tramos = tramos
        self.modo_ideal = modo_ideal
        semilla_efectiva = semilla if semilla is not None else config.SEMILLA_SIMULACION
        self.aleatorio = random.Random(semilla_efectiva)

        self.posicion_lateral = 0.0  # 0 = centrado en la línea; -1..1 = hacia el borde.
        self.orientacion = 0.0  # Ángulo relativo a la línea; 0 = alineado.
        self.avance_tramo = 0.0
        self.indice_tramo = 0
        self.distancia_total = 0.0
        self.tiempo_total = 0.0
        self.fuera_de_pista_eventos = 0
        self._fuera_de_pista_anterior = False

        # True mientras el chasis está girando en el sitio buscando la
        # línea. Se usa para decidir con qué criterio se evalúa la
        # visibilidad: en seguimiento normal, un umbral de distancia
        # decide cuándo se pierde la línea; una vez en búsqueda, solo el
        # ángulo del chasis decide cuándo se recupera (girar en el sitio
        # no acerca al robot lateralmente, así que exigir de nuevo el
        # umbral de distancia dejaría la búsqueda sin salida posible).
        self._buscando_activamente = False

        # Velocidad real de cada rueda tras zona muerta + inercia (lo que
        # de verdad mueve el chasis), separada del comando recién emitido.
        self._velocidad_real_izquierda = 0.0
        self._velocidad_real_derecha = 0.0

        # Dos tramos de latencia distintos y consecutivos del mismo lazo,
        # cada uno con su propia cola: percepción (cámara+WiFi+visión,
        # cola de estado) y actuación (Bluetooth+firmware, cola de
        # comandos). Sumados dan la latencia total del lazo cerrado; no
        # se debe aplicar el total a cada cola por separado, porque eso
        # duplicaría el retardo real.
        if modo_ideal:
            self._pasos_percepcion = 0
            self._pasos_actuacion = 0
        else:
            self._pasos_percepcion = max(0, round(config.LATENCIA_PERCEPCION_MS / config.PASO_SIMULACION_MS))
            self._pasos_actuacion = max(0, round(config.LATENCIA_ACTUACION_MS / config.PASO_SIMULACION_MS))

        # Cola de comandos pendientes de aplicarse (retardo de actuación) y
        # de estados pasados pendientes de "observarse" (retardo de
        # percepción). Se inicializan llenas (comando y estado en reposo)
        # para que el arranque de la simulación ya tenga de dónde leer.
        self._cola_comandos = deque([(0, 0)] * self._pasos_actuacion, maxlen=self._pasos_actuacion or None)
        self._cola_estado = deque(
            [(0.0, 0.0, self.indice_tramo, self.avance_tramo, False)] * self._pasos_percepcion,
            maxlen=self._pasos_percepcion or None,
        )

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

    def _aplicar_zona_muerta(self, velocidad_ordenada: float) -> float:
        """Aplica la zona muerta del motor a una velocidad ordenada.

        Por debajo de ZONA_MUERTA el motor no arranca (0.0). Por encima,
        en vez de dejar un salto brusco justo en el umbral (que
        convertiría una orden pequeña pero real, p. ej. 5, en una
        diferencia enorme entre ruedas si la otra rueda pide 70), se
        comprime linealmente [ZONA_MUERTA, VEL_MAX] a [0, VEL_MAX]: la
        velocidad real crece de forma continua desde 0 apenas se supera
        el umbral, como en un motor real que sí responde algo distinto
        cerca de su punto de arranque en vez de un escalón perfecto.

        Recibe: velocidad_ordenada (float, comando de una rueda).
        Devuelve: float, velocidad tras la zona muerta.
        Complejidad: O(1).
        """
        if self.modo_ideal:
            return velocidad_ordenada

        signo = 1.0 if velocidad_ordenada >= 0 else -1.0
        magnitud = abs(velocidad_ordenada)
        if magnitud < config.ZONA_MUERTA:
            return 0.0

        rango_util = config.VEL_MAX - config.ZONA_MUERTA
        if rango_util <= 0:
            return signo * config.VEL_MAX

        magnitud_comprimida = (magnitud - config.ZONA_MUERTA) * (config.VEL_MAX / rango_util)
        return signo * min(magnitud_comprimida, config.VEL_MAX)

    def _actualizar_velocidad_real(self, objetivo_izquierda: float, objetivo_derecha: float, dt: float) -> None:
        """Acerca la velocidad real de cada rueda a su objetivo con un
        filtro de primer orden (inercia del motor), tras la zona muerta.

        Recibe: objetivo_izquierda, objetivo_derecha (comandos ya
            retrasados por la latencia) y dt (segundos del paso).
        Devuelve: nada; actualiza _velocidad_real_izquierda/derecha.
        Complejidad: O(1).
        """
        objetivo_izquierda = self._aplicar_zona_muerta(objetivo_izquierda)
        objetivo_derecha = self._aplicar_zona_muerta(objetivo_derecha)

        if self.modo_ideal:
            self._velocidad_real_izquierda = objetivo_izquierda
            self._velocidad_real_derecha = objetivo_derecha
            return

        # Filtro exponencial de primer orden: v += (objetivo - v) * dt/tau.
        factor = min(1.0, dt / config.TAU_MOTOR)
        self._velocidad_real_izquierda += (objetivo_izquierda - self._velocidad_real_izquierda) * factor
        self._velocidad_real_derecha += (objetivo_derecha - self._velocidad_real_derecha) * factor

    def paso(self, izquierda: int, derecha: int, dt: float) -> None:
        """Avanza la simulación un paso de tiempo dt.

        Recibe: izquierda, derecha (velocidades de rueda decididas por
            el controlador para ESTE instante) y dt (segundos).
        Devuelve: nada; encola el comando (se aplicará con retardo de
            LATENCIA_ACTUACION_MS), avanza la cinemática con el comando
            que le corresponde a este paso según esa cola, y guarda el
            estado resultante en el historial de observación (que se
            leerá con retardo de LATENCIA_PERCEPCION_MS).
        Complejidad: O(1) (las colas tienen tamaño fijo).
        """
        tramo = self.tramo_actual()
        if tramo is None:
            return

        if self._pasos_actuacion == 0:
            comando_a_aplicar = (izquierda, derecha)
        else:
            # Leer primero el comando más viejo de la cola y recién
            # después encolar el nuevo: si se encolara antes de leer,
            # con maxlen=_pasos_actuacion el comando recién emitido
            # desplazaría al más viejo y se leería a sí mismo en la
            # misma llamada, dando un paso menos de retardo del
            # configurado.
            comando_a_aplicar = self._cola_comandos[0]
            self._cola_comandos.append((izquierda, derecha))

        self._actualizar_velocidad_real(comando_a_aplicar[0], comando_a_aplicar[1], dt)
        velocidad_izquierda = self._velocidad_real_izquierda
        velocidad_derecha = self._velocidad_real_derecha
        velocidad_avance = (velocidad_izquierda + velocidad_derecha) / 2.0

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
            diferencia_ruedas = velocidad_izquierda - velocidad_derecha
            self.orientacion += GANANCIA_ORIENTACION * diferencia_ruedas * dt

            girando_en_sitio = abs(velocidad_avance) < VELOCIDAD_AVANCE_UMBRAL_GIRO and abs(diferencia_ruedas) > 0
            self._buscando_activamente = girando_en_sitio

            if girando_en_sitio:
                # La orientación es aquí el rumbo real del chasis, que
                # sigue girando siempre hacia el mismo lado mientras
                # busca: sin una noción de "vuelta completa" crecería
                # para siempre y nunca volvería a caer dentro del campo
                # de visión. Se envuelve como un ángulo real (equivalente
                # a wrap a [-π, π]), así que tras suficiente rotación
                # vuelve a acercarse a 0 desde el lado opuesto, cruzando
                # de nuevo ANGULO_CAMPO_VISION de forma continua.
                self.orientacion = (self.orientacion + VUELTA_COMPLETA / 2) % VUELTA_COMPLETA - VUELTA_COMPLETA / 2
            else:
                # El límite de ORIENTACION_MAXIMA solo aplica en
                # seguimiento normal, para que el ángulo reportado no se
                # dispare mientras se sigue la línea.
                self.orientacion = max(-ORIENTACION_MAXIMA, min(ORIENTACION_MAXIMA, self.orientacion))

            # La posición lateral cambia por el rumbo y por la curvatura
            # del tramo en todo momento (también al girar en el sitio,
            # donde velocidad_avance es ~0 y por lo tanto este término se
            # anula naturalmente sin necesitar un caso especial).
            self.posicion_lateral -= GANANCIA_POSICION * self.orientacion * velocidad_avance * dt
            self.posicion_lateral += GANANCIA_CURVATURA * tramo.curvatura * velocidad_avance * dt

            fuera_de_pista = abs(self.posicion_lateral) > ANCHO_PISTA
            if fuera_de_pista and not self._fuera_de_pista_anterior:
                self.fuera_de_pista_eventos += 1
            self._fuera_de_pista_anterior = fuera_de_pista

        self.distancia_total += abs(velocidad_avance) * dt
        self.tiempo_total += dt

        # El progreso dentro del tramo avanza con el tiempo, no con la
        # distancia recorrida: así un tramo "sin_linea" también termina
        # cuando el robot gira en sitio buscando la línea (velocidad de
        # avance ~0), igual que ocurriría con un temporizador en la pista real.
        self.avance_tramo += dt
        if self.avance_tramo >= tramo.longitud:
            self.avance_tramo = 0.0
            self.indice_tramo += 1

        if self._pasos_percepcion > 0:
            self._cola_estado.append(
                (self.posicion_lateral, self.orientacion, self.indice_tramo, self.avance_tramo, self._buscando_activamente)
            )

    def _con_ruido(self, valor: float, desviacion: float) -> float:
        """Agrega ruido gaussiano opcional a un valor.

        Recibe: valor (float) y desviacion (desviación estándar; se
            ignora si modo_ideal es True o desviacion es 0).
        Devuelve: valor perturbado.
        Complejidad: O(1).
        """
        if self.modo_ideal or desviacion <= 0:
            return valor
        return valor + self.aleatorio.gauss(0.0, desviacion)

    def _estado_observado(self) -> tuple[float, float, int, float, bool]:
        """Devuelve (posicion, orientacion, indice_tramo, avance_tramo,
        buscando_activamente) tal como los "vería" la visión ahora
        mismo: el estado real si no hay latencia de percepción
        configurada, o el estado de hace LATENCIA_PERCEPCION_MS si sí la
        hay.

        Recibe: nada.
        Devuelve: tupla con el estado retrasado usado para generar los
            resultados de visión.
        Complejidad: O(1).
        """
        if self._pasos_percepcion == 0:
            return self.posicion_lateral, self.orientacion, self.indice_tramo, self.avance_tramo, self._buscando_activamente
        return self._cola_estado[0]

    def generar_resultado_linea(self) -> ResultadoLinea:
        """Genera un ResultadoLinea coherente con el estado observado
        (retrasado por la latencia si corresponde), con ruido y fallos
        de detección opcionales.

        Recibe: nada.
        Devuelve: ResultadoLinea con error y angulo derivados de la
            posición/orientación observadas, o valida=False si el robot
            (en el instante observado) estaba fuera de la pista, en la
            primera mitad de un tramo "sin_linea", girando fuera del
            campo de visión, o si un fallo aleatorio de detección lo
            marca inválido pese a estar sobre la línea.
        Complejidad: O(1).
        """
        posicion, orientacion, indice_tramo, avance_tramo, buscando_activamente = self._estado_observado()
        tramo = self.tramos[indice_tramo] if indice_tramo < len(self.tramos) else None

        linea_ausente = tramo is not None and tramo.tipo == "sin_linea" and avance_tramo < tramo.longitud * 0.5

        # El criterio de visibilidad es distinto para perder la línea que
        # para recuperarla, porque girar en el sitio no acerca al robot
        # lateralmente (solo cambia su rumbo): en seguimiento normal, un
        # umbral de distancia decide cuándo la línea sale de la pista y
        # arranca la búsqueda; una vez en búsqueda, solo el ángulo del
        # chasis decide cuándo vuelve a estar dentro del campo de visión
        # de la cámara (si se exigiera de nuevo el umbral de distancia,
        # la búsqueda no tendría salida posible mientras el robot siga
        # girando sin avanzar).
        if buscando_activamente:
            perdida = abs(orientacion) > ANGULO_CAMPO_VISION
        else:
            perdida = abs(posicion) > ANCHO_PISTA

        if tramo is None or linea_ausente or perdida:
            return ResultadoLinea(error=0.0, angulo=0.0, confianza=0, valida=False)

        if not self.modo_ideal and self.aleatorio.random() < config.PROB_LINEA_INVALIDA:
            return ResultadoLinea(error=0.0, angulo=0.0, confianza=0, valida=False)

        error = self._con_ruido(max(-1.0, min(1.0, posicion / ANCHO_PISTA)), config.RUIDO_ERROR)
        posicion_lejana = posicion + orientacion * DISTANCIA_FRANJA_LEJANA
        angulo = self._con_ruido(max(-1.0, min(1.0, (posicion_lejana - posicion) / ANCHO_PISTA)), config.RUIDO_ANGULO)

        confianza = 4
        if not self.modo_ideal and self.aleatorio.random() < config.PROB_FRANJA_PERDIDA:
            confianza = 2

        return ResultadoLinea(error=error, angulo=angulo, confianza=confianza, valida=True)

    def generar_resultado_senales(self) -> ResultadoSenales:
        """Genera un ResultadoSenales coherente con el tramo observado
        (retrasado por la latencia si corresponde).

        Recibe: nada.
        Devuelve: ResultadoSenales con senal="PARE" o "SIGA" cuando el
            tramo observado es de ese tipo, marcando en_disparo=True
            solo en la mitad final del tramo (simula que la señal se
            acerca).
        Complejidad: O(1).
        """
        _, _, indice_tramo, avance_tramo, _ = self._estado_observado()
        tramo = self.tramos[indice_tramo] if indice_tramo < len(self.tramos) else None

        if tramo is None or tramo.tipo not in ("pare", "siga"):
            return ResultadoSenales(senal=None, en_disparo=False)

        senal = "PARE" if tramo.tipo == "pare" else "SIGA"
        en_disparo = avance_tramo >= tramo.longitud * 0.5
        return ResultadoSenales(senal=senal, en_disparo=en_disparo)
