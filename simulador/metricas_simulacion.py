"""Recolector de métricas para una corrida de la pista virtual.

Lo usan tanto simulador/visor.py (para mostrar el resumen final) como
simulador/calibrar_ganancias.py (para puntuar combinaciones de
ganancias), así que la recolección vive en un solo lugar.
"""

from dataclasses import dataclass, field

UMBRAL_OSCILACION = 0.05  # |error| mínimo (en ambos lados del cruce por cero) para contarlo como oscilación real y no como ruido de asentamiento.


@dataclass
class MetricasTramo:
    """Métricas acumuladas para un único tramo de la pista.

    nombre: etiqueta del tramo (Tramo.nombre).
    errores: lista de |error| válidos observados durante el tramo.
    tiempo: segundos simulados que duró el tramo.
    salidas_de_pista: número de veces que |error| > 1 durante el tramo.
    tiempo_fuera_de_pista: segundos acumulados con |error| > 1.
    cambios_de_signo: número de veces que el error cruzó por cero.
    esfuerzo: lista de |izquierda - derecha| por fotograma, para medir
        cuánto tuvo que corregir el controlador.
    """

    nombre: str
    errores: list = field(default_factory=list)
    tiempo: float = 0.0
    salidas_de_pista: int = 0
    tiempo_fuera_de_pista: float = 0.0
    cambios_de_signo: int = 0
    esfuerzo: list = field(default_factory=list)
    tiempo_detenido_forzado: float = 0.0


class RecolectorMetricas:
    """Acumula métricas globales y por tramo mientras corre la simulación.

    Se alimenta llamando a registrar_paso() una vez por fotograma
    simulado; al final, resumen() y resumen_por_tramo() devuelven los
    resultados agregados.
    """

    def __init__(self):
        self._tramos: dict[str, MetricasTramo] = {}
        self._orden_tramos: list[str] = []
        self._signo_error_anterior = 0
        self._magnitud_error_anterior = 0.0
        self._fuera_de_pista_anterior = False

    def _obtener_tramo(self, nombre: str) -> MetricasTramo:
        """Devuelve (creando si hace falta) las métricas del tramo.

        Recibe: nombre (str, Tramo.nombre).
        Devuelve: MetricasTramo correspondiente.
        Complejidad: O(1).
        """
        if nombre not in self._tramos:
            self._tramos[nombre] = MetricasTramo(nombre=nombre)
            self._orden_tramos.append(nombre)
        return self._tramos[nombre]

    def registrar_paso(
        self,
        nombre_tramo: str,
        error_valido: float | None,
        izquierda: int,
        derecha: int,
        dt: float,
        estado: str = "",
    ) -> None:
        """Registra un fotograma de simulación en las métricas.

        Recibe: nombre_tramo (str), error_valido (float o None si el
            fotograma llegó con valida=False), izquierda, derecha
            (velocidades del comando de este fotograma), dt (segundos) y
            estado (str opcional, estado de MaquinaEstados en este
            fotograma; si es "DETENIDO" se acumula como tiempo perdido
            de forma irrecuperable, distinto de solo "fuera de pista").
        Devuelve: nada.
        Complejidad: O(1).
        """
        tramo = self._obtener_tramo(nombre_tramo)
        tramo.tiempo += dt
        tramo.esfuerzo.append(abs(izquierda - derecha))

        if estado == "DETENIDO":
            tramo.tiempo_detenido_forzado += dt

        if error_valido is None:
            return

        tramo.errores.append(abs(error_valido))

        fuera_de_pista = abs(error_valido) > 1.0
        if fuera_de_pista:
            tramo.tiempo_fuera_de_pista += dt
            if not self._fuera_de_pista_anterior:
                tramo.salidas_de_pista += 1
        self._fuera_de_pista_anterior = fuera_de_pista

        signo_actual = 1 if error_valido > 0 else (-1 if error_valido < 0 else 0)
        magnitud_actual = abs(error_valido)
        cruce_real = (
            signo_actual != 0
            and self._signo_error_anterior != 0
            and signo_actual != self._signo_error_anterior
            and magnitud_actual >= UMBRAL_OSCILACION
            and self._magnitud_error_anterior >= UMBRAL_OSCILACION
        )
        if cruce_real:
            tramo.cambios_de_signo += 1
        if signo_actual != 0:
            self._signo_error_anterior = signo_actual
            self._magnitud_error_anterior = magnitud_actual

    def resumen_por_tramo(self) -> list[dict]:
        """Calcula el resumen de métricas de cada tramo, en el orden en
        que se visitaron por primera vez.

        Recibe: nada.
        Devuelve: lista de diccionarios con error_medio, error_max,
            salidas_de_pista, tiempo_fuera_de_pista, oscilacion (cambios
            de signo por segundo) y esfuerzo_medio, uno por tramo.
        Complejidad: O(n) sobre la cantidad de fotogramas acumulados.
        """
        resumen = []
        for nombre in self._orden_tramos:
            tramo = self._tramos[nombre]
            errores = tramo.errores
            resumen.append(
                {
                    "nombre": nombre,
                    "error_medio": sum(errores) / len(errores) if errores else 0.0,
                    "error_max": max(errores) if errores else 0.0,
                    "salidas_de_pista": tramo.salidas_de_pista,
                    "tiempo_fuera_de_pista": tramo.tiempo_fuera_de_pista,
                    "oscilacion": tramo.cambios_de_signo / tramo.tiempo if tramo.tiempo > 0 else 0.0,
                    "esfuerzo_medio": sum(tramo.esfuerzo) / len(tramo.esfuerzo) if tramo.esfuerzo else 0.0,
                    "tiempo": tramo.tiempo,
                    "tiempo_detenido_forzado": tramo.tiempo_detenido_forzado,
                }
            )
        return resumen

    def resumen_total(self) -> dict:
        """Calcula el resumen agregado de toda la corrida (todos los tramos).

        Recibe: nada.
        Devuelve: diccionario con las mismas claves que resumen_por_tramo(),
            calculadas sobre todos los fotogramas juntos.
        Complejidad: O(n) sobre la cantidad de fotogramas acumulados.
        """
        errores = []
        esfuerzo = []
        salidas_de_pista = 0
        tiempo_fuera_de_pista = 0.0
        cambios_de_signo = 0
        tiempo_total = 0.0
        tiempo_detenido_forzado = 0.0
        for tramo in self._tramos.values():
            errores.extend(tramo.errores)
            esfuerzo.extend(tramo.esfuerzo)
            salidas_de_pista += tramo.salidas_de_pista
            tiempo_fuera_de_pista += tramo.tiempo_fuera_de_pista
            cambios_de_signo += tramo.cambios_de_signo
            tiempo_total += tramo.tiempo
            tiempo_detenido_forzado += tramo.tiempo_detenido_forzado

        return {
            "nombre": "TOTAL",
            "error_medio": sum(errores) / len(errores) if errores else 0.0,
            "error_max": max(errores) if errores else 0.0,
            "salidas_de_pista": salidas_de_pista,
            "tiempo_fuera_de_pista": tiempo_fuera_de_pista,
            "oscilacion": cambios_de_signo / tiempo_total if tiempo_total > 0 else 0.0,
            "esfuerzo_medio": sum(esfuerzo) / len(esfuerzo) if esfuerzo else 0.0,
            "tiempo": tiempo_total,
            "tiempo_detenido_forzado": tiempo_detenido_forzado,
        }
