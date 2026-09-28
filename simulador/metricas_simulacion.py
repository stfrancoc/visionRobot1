"""Recolector de métricas para una corrida de la pista virtual.

Lo usan tanto simulador/visor.py (para mostrar el resumen final) como
simulador/calibrar_ganancias.py (para puntuar combinaciones de
ganancias), así que la recolección vive en un solo lugar.

Calcular el error medio solo sobre los fotogramas donde valida=True
premia perder la línea (esos fotogramas simplemente no cuentan), así
que la métrica principal de salud del sistema es el porcentaje de
tiempo en cada estado de MaquinaEstados: si la mayor parte del tiempo
se va en LINEA_PERDIDA/DETENIDO, el "error medio en seguimiento normal"
puede verse bien y aun así el sistema estar fallando por completo.
"""

from dataclasses import dataclass, field

UMBRAL_OSCILACION = 0.05  # |error| mínimo (en ambos lados del cruce por cero) para contarlo como oscilación real y no como ruido de asentamiento.

# Estados de MaquinaEstados donde el robot está efectivamente siguiendo
# la línea (o parado a propósito por una señal, lo cual no es una
# falla): el resto (LINEA_PERDIDA, DETENIDO) cuenta como "fuera de
# seguimiento" para la métrica de desempeño global.
ESTADOS_EN_SEGUIMIENTO = frozenset({"SEGUIR_LINEA", "REANUDAR", "SIGA", "PARE"})

PESO_TIEMPO_FUERA_DE_SEGUIMIENTO = 2.0  # Penalización, en la puntuación global, por cada segundo fuera de ESTADOS_EN_SEGUIMIENTO (LINEA_PERDIDA/DETENIDO): el peor desenlace posible.


@dataclass
class MetricasTramo:
    """Métricas acumuladas para un único tramo de la pista.

    nombre: etiqueta del tramo (Tramo.nombre).
    errores: lista de |error| válidos observados durante el tramo,
        SOLO en fotogramas de seguimiento normal (ver ESTADOS_EN_SEGUIMIENTO).
    tiempo: segundos simulados que duró el tramo.
    salidas_de_pista: número de veces que |error| > 1 durante el tramo,
        en fotogramas de seguimiento normal.
    tiempo_fuera_de_pista: segundos acumulados con |error| > 1, en
        fotogramas de seguimiento normal.
    cambios_de_signo: número de veces que el error cruzó por cero.
    esfuerzo: lista de |izquierda - derecha| por fotograma, para medir
        cuánto tuvo que corregir el controlador.
    tiempo_por_estado: segundos acumulados en cada estado de MaquinaEstados.
    """

    nombre: str
    errores: list = field(default_factory=list)
    tiempo: float = 0.0
    salidas_de_pista: int = 0
    tiempo_fuera_de_pista: float = 0.0
    cambios_de_signo: int = 0
    esfuerzo: list = field(default_factory=list)
    tiempo_detenido_forzado: float = 0.0
    tiempo_por_estado: dict = field(default_factory=dict)


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
        estado: str,
    ) -> None:
        """Registra un fotograma de simulación en las métricas.

        Recibe: nombre_tramo (str), error_valido (float o None si el
            fotograma llegó con valida=False), izquierda, derecha
            (velocidades del comando de este fotograma), dt (segundos) y
            estado (str, estado de MaquinaEstados en este fotograma:
            siempre se acumula el tiempo en ese estado, y si es
            "DETENIDO" además cuenta como tiempo perdido de forma
            irrecuperable).
        Devuelve: nada.
        Complejidad: O(1).
        """
        tramo = self._obtener_tramo(nombre_tramo)
        tramo.tiempo += dt
        tramo.esfuerzo.append(abs(izquierda - derecha))
        tramo.tiempo_por_estado[estado] = tramo.tiempo_por_estado.get(estado, 0.0) + dt

        if estado == "DETENIDO":
            tramo.tiempo_detenido_forzado += dt

        # El error medio, las salidas de pista y su duración solo tienen
        # sentido en fotogramas de seguimiento normal: un fotograma
        # inválido durante LINEA_PERDIDA no es "sin error", es
        # directamente peor y ya queda capturado por tiempo_por_estado.
        if error_valido is None or estado not in ESTADOS_EN_SEGUIMIENTO:
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

    @staticmethod
    def _resumir(
        nombre: str,
        errores: list,
        esfuerzo: list,
        salidas_de_pista: int,
        tiempo_fuera_de_pista: float,
        cambios_de_signo: int,
        tiempo_total: float,
        tiempo_detenido_forzado: float,
        tiempo_por_estado: dict,
    ) -> dict:
        """Arma el diccionario de resumen a partir de los acumulados,
        usado tanto por tramo como para el total.

        Recibe: los acumulados de un tramo o de toda la corrida.
        Devuelve: dict con error_medio y error_max (solo sobre
            fotogramas de seguimiento normal), salidas_de_pista,
            tiempo_fuera_de_pista, oscilacion, esfuerzo_medio, tiempo,
            tiempo_detenido_forzado, tiempo_por_estado,
            porcentaje_tiempo_por_estado, porcentaje_en_seguimiento y
            puntuacion_global (error medio en seguimiento normal más
            una penalización fuerte por cada segundo fuera de
            seguimiento: así un barrido de ganancias no puede mejorar
            esta puntuación simplemente perdiendo la línea).
        Complejidad: O(k) sobre la cantidad de estados distintos.
        """
        tiempo_fuera_de_seguimiento = sum(
            segundos for estado, segundos in tiempo_por_estado.items() if estado not in ESTADOS_EN_SEGUIMIENTO
        )
        porcentaje_tiempo_por_estado = {
            estado: 100.0 * segundos / tiempo_total if tiempo_total > 0 else 0.0
            for estado, segundos in tiempo_por_estado.items()
        }
        porcentaje_en_seguimiento = 100.0 - sum(
            pct for estado, pct in porcentaje_tiempo_por_estado.items() if estado not in ESTADOS_EN_SEGUIMIENTO
        )
        error_medio = sum(errores) / len(errores) if errores else 0.0

        return {
            "nombre": nombre,
            "error_medio": error_medio,
            "error_max": max(errores) if errores else 0.0,
            "salidas_de_pista": salidas_de_pista,
            "tiempo_fuera_de_pista": tiempo_fuera_de_pista,
            "oscilacion": cambios_de_signo / tiempo_total if tiempo_total > 0 else 0.0,
            "esfuerzo_medio": sum(esfuerzo) / len(esfuerzo) if esfuerzo else 0.0,
            "tiempo": tiempo_total,
            "tiempo_detenido_forzado": tiempo_detenido_forzado,
            "tiempo_por_estado": dict(tiempo_por_estado),
            "porcentaje_tiempo_por_estado": porcentaje_tiempo_por_estado,
            "porcentaje_en_seguimiento": porcentaje_en_seguimiento,
            "puntuacion_global": error_medio + PESO_TIEMPO_FUERA_DE_SEGUIMIENTO * tiempo_fuera_de_seguimiento,
        }

    def resumen_por_tramo(self) -> list[dict]:
        """Calcula el resumen de métricas de cada tramo, en el orden en
        que se visitaron por primera vez.

        Recibe: nada.
        Devuelve: lista de diccionarios (ver _resumir), uno por tramo.
        Complejidad: O(n) sobre la cantidad de fotogramas acumulados.
        """
        return [
            self._resumir(
                nombre,
                tramo.errores,
                tramo.esfuerzo,
                tramo.salidas_de_pista,
                tramo.tiempo_fuera_de_pista,
                tramo.cambios_de_signo,
                tramo.tiempo,
                tramo.tiempo_detenido_forzado,
                tramo.tiempo_por_estado,
            )
            for nombre in self._orden_tramos
            for tramo in [self._tramos[nombre]]
        ]

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
        tiempo_por_estado: dict = {}
        for tramo in self._tramos.values():
            errores.extend(tramo.errores)
            esfuerzo.extend(tramo.esfuerzo)
            salidas_de_pista += tramo.salidas_de_pista
            tiempo_fuera_de_pista += tramo.tiempo_fuera_de_pista
            cambios_de_signo += tramo.cambios_de_signo
            tiempo_total += tramo.tiempo
            tiempo_detenido_forzado += tramo.tiempo_detenido_forzado
            for estado, segundos in tramo.tiempo_por_estado.items():
                tiempo_por_estado[estado] = tiempo_por_estado.get(estado, 0.0) + segundos

        return self._resumir(
            "TOTAL",
            errores,
            esfuerzo,
            salidas_de_pista,
            tiempo_fuera_de_pista,
            cambios_de_signo,
            tiempo_total,
            tiempo_detenido_forzado,
            tiempo_por_estado,
        )
