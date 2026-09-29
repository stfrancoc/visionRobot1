"""Máquina de estados del robot seguidor de línea.

Combina las salidas de visión (ResultadoLinea, ResultadoSenales) con el
ControladorZonas para decidir, en cada fotograma, qué ComandoRobot
enviar. Implementa los estados y transiciones de la sección 3.4 del
README: SEGUIR_LINEA, PARE, REANUDAR, SIGA y LINEA_PERDIDA. Se agrega un
estado adicional:
- DETENIDO: al que se llega solo si LINEA_PERDIDA agota
  TIEMPO_MAX_PERDIDA: mantiene las ruedas en cero y no se abandona solo,
  porque "detenerse y reportarlo" debe ser un estado final visible y no
  una vuelta silenciosa a SEGUIR_LINEA.

Nota sobre LINEA_PERDIDA: el mBot real (ver comunicacion/robot_mbot.py)
no tiene un giro sobre el propio eje; izquierda()/derecha() giran de
radio amplio, moviendo ambos motores hacia adelante. Esto significa que
"buscar la línea" YA desplaza al robot hacia adelante mientras gira, a
diferencia de un giro en sitio que solo cambiaría el rumbo.

Por ahora, al recuperar la línea se retoma el control por zonas
directamente (sin un estado intermedio como el REALINEANDO de una
versión anterior). El riesgo que REALINEANDO evitaba sigue existiendo:
el chasis puede quedar torcido justo al recuperar la línea, y avanzar
de inmediato con AVANZAR (en vez de solo girar) puede volver a sacarlo
de la pista antes de corregir el rumbo — con giros de radio amplio este
riesgo es incluso mayor que con un giro sobre el eje, porque cada giro
de corrección ya avanza al robot en la dirección en la que está
torcido. Se eliminó de todas formas porque, sin giro sobre el eje, un
estado que "gire sin avanzar en absoluto" ya no es una acción física
que el firmware pueda ejecutar tal cual.

Si en las pruebas con el robot real se observa que, tras recuperar la
línea, el robot vuelve a salirse de la pista en los primeros
fotogramas: la solución es reintroducir un estado intermedio (p. ej.
REALINEANDO) que, al recuperar la línea, envíe SOLO comandos de giro
(izquierda()/derecha(), nunca adelante()) hasta que el error baje de un
umbral, y solo entonces pase a SEGUIR_LINEA. Esto SÍ es posible con
este firmware (girar sin mezclar avance no requiere un giro sobre el
eje, solo no llamar a adelante() todavía) y sería la forma correcta de
recuperar el propósito original de REALINEANDO sin depender de un
movimiento que el mBot no tiene.

El tiempo siempre llega como parámetro (tiempo_actual); esta clase nunca
llama a time.time(), para poder probarla con secuencias simuladas.
"""

import config
from control.contratos import ComandoRobot, ResultadoLinea, ResultadoSenales, calcular_accion
from control.controlador import ControladorZonas

SEGUIR_LINEA = "SEGUIR_LINEA"
PARE = "PARE"
REANUDAR = "REANUDAR"
SIGA = "SIGA"
LINEA_PERDIDA = "LINEA_PERDIDA"
DETENIDO = "DETENIDO"


class MaquinaEstados:
    """Orquesta las transiciones entre estados y produce el ComandoRobot
    de cada fotograma.
    """

    def __init__(self):
        self.controlador = ControladorZonas()
        self.estado = SEGUIR_LINEA
        self.signo_ultimo_error = 1
        self.tiempo_entrada_estado = 0.0
        self.eventos = []

    def actualizar(
        self,
        resultado_linea: ResultadoLinea,
        resultado_senales: ResultadoSenales,
        tiempo_actual: float,
    ) -> ComandoRobot:
        """Avanza la máquina de estados un fotograma y produce el comando.

        Recibe: resultado_linea, resultado_senales (salidas de visión) y
            tiempo_actual (segundos, reloj monótono provisto por quien
            llama).
        Devuelve: ComandoRobot con las señales de rueda, el estado y la
            acción derivada.
        Complejidad: O(1).
        """
        if resultado_linea.valida and resultado_linea.error != 0:
            self.signo_ultimo_error = 1 if resultado_linea.error > 0 else -1

        manejador = {
            SEGUIR_LINEA: self._en_seguir_linea,
            PARE: self._en_pare,
            REANUDAR: self._en_reanudar,
            SIGA: self._en_siga,
            LINEA_PERDIDA: self._en_linea_perdida,
            DETENIDO: self._en_detenido,
        }[self.estado]

        izquierda, derecha = manejador(resultado_linea, resultado_senales, tiempo_actual)

        accion = calcular_accion(izquierda, derecha, config.DIF_GIRO)
        return ComandoRobot(izquierda=izquierda, derecha=derecha, estado=self.estado, accion=accion)

    def obtener_eventos(self) -> list[tuple[float, str, str, str]]:
        """Devuelve el historial de cambios de estado registrados.

        Recibe: nada.
        Devuelve: lista de tuplas (tiempo, estado_anterior, estado_nuevo,
            motivo), en orden cronológico.
        Complejidad: O(1) (devuelve la referencia; el historial crece
            O(1) por transición).
        """
        return self.eventos

    def _cambiar_estado(self, nuevo_estado: str, tiempo_actual: float, motivo: str) -> None:
        """Registra una transición de estado y actualiza el estado actual.

        Recibe: nuevo_estado, tiempo_actual, motivo (texto corto para el
            registro de eventos).
        Devuelve: nada.
        Complejidad: O(1).
        """
        self.eventos.append((tiempo_actual, self.estado, nuevo_estado, motivo))
        self.estado = nuevo_estado
        self.tiempo_entrada_estado = tiempo_actual

    def _en_seguir_linea(self, resultado_linea, resultado_senales, tiempo_actual):
        if resultado_senales.senal == "PARE" and resultado_senales.en_disparo:
            self._cambiar_estado(PARE, tiempo_actual, "PARE confirmado en disparo")
            return self.controlador.detener()

        if resultado_senales.senal == "SIGA" and resultado_senales.en_disparo:
            self._cambiar_estado(SIGA, tiempo_actual, "SIGA confirmado en disparo")
            return self.controlador.calcular(resultado_linea)

        if not resultado_linea.valida:
            self._cambiar_estado(LINEA_PERDIDA, tiempo_actual, "línea inválida")
            return self.controlador.girar_busqueda(self.signo_ultimo_error)

        return self.controlador.calcular(resultado_linea)

    def _en_pare(self, resultado_linea, resultado_senales, tiempo_actual):
        if tiempo_actual - self.tiempo_entrada_estado >= config.TIEMPO_PARE:
            self.controlador.reiniciar()
            self._cambiar_estado(REANUDAR, tiempo_actual, "tiempo de PARE cumplido")
            return self.controlador.calcular(resultado_linea)

        return self.controlador.detener()

    def _en_reanudar(self, resultado_linea, resultado_senales, tiempo_actual):
        rojo_ausente = resultado_senales.senal != "PARE"
        tiempo_agotado = tiempo_actual - self.tiempo_entrada_estado >= config.TIEMPO_ENFRIAMIENTO

        if rojo_ausente or tiempo_agotado:
            motivo = "rojo fuera de cuadro" if rojo_ausente else "tiempo de enfriamiento cumplido"
            self._cambiar_estado(SEGUIR_LINEA, tiempo_actual, motivo)

        if not resultado_linea.valida:
            self._cambiar_estado(LINEA_PERDIDA, tiempo_actual, "línea inválida en REANUDAR")
            return self.controlador.girar_busqueda(self.signo_ultimo_error)

        return self.controlador.calcular(resultado_linea)

    def _en_siga(self, resultado_linea, resultado_senales, tiempo_actual):
        self._cambiar_estado(SEGUIR_LINEA, tiempo_actual, "evento SIGA registrado")
        return self.controlador.calcular(resultado_linea)

    def _en_linea_perdida(self, resultado_linea, resultado_senales, tiempo_actual):
        if resultado_linea.valida:
            self.controlador.reiniciar()
            self._cambiar_estado(SEGUIR_LINEA, tiempo_actual, "línea recuperada")
            return self.controlador.calcular(resultado_linea)

        if tiempo_actual - self.tiempo_entrada_estado >= config.TIEMPO_MAX_PERDIDA:
            self._cambiar_estado(DETENIDO, tiempo_actual, "tiempo máximo de línea perdida agotado, se detiene")
            return self.controlador.detener()

        return self.controlador.girar_busqueda(self.signo_ultimo_error)

    def _en_detenido(self, resultado_linea, resultado_senales, tiempo_actual):
        return self.controlador.detener()
