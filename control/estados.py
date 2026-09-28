"""Máquina de estados del robot seguidor de línea.

Combina las salidas de visión (ResultadoLinea, ResultadoSenales) con el
ControladorPD para decidir, en cada fotograma, qué ComandoRobot enviar.
Implementa los estados y transiciones de la sección 3.4 del README:
SEGUIR_LINEA, PARE, REANUDAR, SIGA y LINEA_PERDIDA. Se agrega un estado
adicional DETENIDO, al que se llega solo si LINEA_PERDIDA agota
TIEMPO_MAX_PERDIDA: mantiene las ruedas en cero y no se abandona solo,
porque "detenerse y reportarlo" debe ser un estado final visible y no
una vuelta silenciosa a SEGUIR_LINEA.

El tiempo siempre llega como parámetro (tiempo_actual); esta clase nunca
llama a time.time(), para poder probarla con secuencias simuladas.
"""

import config
from control.contratos import ComandoRobot, ResultadoLinea, ResultadoSenales, calcular_accion
from control.controlador import ControladorPD

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
        self.controlador = ControladorPD()
        self.estado = SEGUIR_LINEA
        self.signo_ultimo_error = 1
        self.tiempo_entrada_estado = 0.0
        self.tiempo_anterior = None
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
        Devuelve: ComandoRobot con las velocidades, el estado y la
            acción derivada.
        Complejidad: O(1).
        """
        dt = 0.0 if self.tiempo_anterior is None else tiempo_actual - self.tiempo_anterior
        self.tiempo_anterior = tiempo_actual

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

        izquierda, derecha = manejador(resultado_linea, resultado_senales, tiempo_actual, dt)

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

    def _en_seguir_linea(self, resultado_linea, resultado_senales, tiempo_actual, dt):
        if resultado_senales.senal == "PARE" and resultado_senales.en_disparo:
            self._cambiar_estado(PARE, tiempo_actual, "PARE confirmado en disparo")
            return self.controlador.detener()

        if resultado_senales.senal == "SIGA" and resultado_senales.en_disparo:
            self._cambiar_estado(SIGA, tiempo_actual, "SIGA confirmado en disparo")
            return self.controlador.calcular(resultado_linea, dt)

        if not resultado_linea.valida:
            self._cambiar_estado(LINEA_PERDIDA, tiempo_actual, "línea inválida")
            return self.controlador.girar_en_sitio(self.signo_ultimo_error)

        return self.controlador.calcular(resultado_linea, dt)

    def _en_pare(self, resultado_linea, resultado_senales, tiempo_actual, dt):
        if tiempo_actual - self.tiempo_entrada_estado >= config.TIEMPO_PARE:
            self.controlador.reiniciar()
            self._cambiar_estado(REANUDAR, tiempo_actual, "tiempo de PARE cumplido")
            return self.controlador.calcular(resultado_linea, dt)

        return self.controlador.detener()

    def _en_reanudar(self, resultado_linea, resultado_senales, tiempo_actual, dt):
        rojo_ausente = resultado_senales.senal != "PARE"
        tiempo_agotado = tiempo_actual - self.tiempo_entrada_estado >= config.TIEMPO_ENFRIAMIENTO

        if rojo_ausente or tiempo_agotado:
            motivo = "rojo fuera de cuadro" if rojo_ausente else "tiempo de enfriamiento cumplido"
            self._cambiar_estado(SEGUIR_LINEA, tiempo_actual, motivo)

        if not resultado_linea.valida:
            self._cambiar_estado(LINEA_PERDIDA, tiempo_actual, "línea inválida en REANUDAR")
            return self.controlador.girar_en_sitio(self.signo_ultimo_error)

        return self.controlador.calcular(resultado_linea, dt)

    def _en_siga(self, resultado_linea, resultado_senales, tiempo_actual, dt):
        self._cambiar_estado(SEGUIR_LINEA, tiempo_actual, "evento SIGA registrado")
        return self.controlador.calcular(resultado_linea, dt)

    def _en_linea_perdida(self, resultado_linea, resultado_senales, tiempo_actual, dt):
        if resultado_linea.valida:
            self.controlador.reiniciar()
            self._cambiar_estado(SEGUIR_LINEA, tiempo_actual, "línea recuperada")
            return self.controlador.calcular(resultado_linea, dt)

        if tiempo_actual - self.tiempo_entrada_estado >= config.TIEMPO_MAX_PERDIDA:
            self._cambiar_estado(DETENIDO, tiempo_actual, "tiempo máximo de línea perdida agotado, se detiene")
            return self.controlador.detener()

        return self.controlador.girar_en_sitio(self.signo_ultimo_error)

    def _en_detenido(self, resultado_linea, resultado_senales, tiempo_actual, dt):
        return self.controlador.detener()
