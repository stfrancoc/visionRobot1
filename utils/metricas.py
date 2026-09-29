"""Métricas del ciclo principal: FPS, latencia por etapa y registro de
eventos, con volcado a CSV en capturas/ para el póster.

No es un módulo de visión (no procesa imágenes), así que no lleva
`Complejidad: O(...)`: solo aritmética simple sobre unos pocos números
por fotograma.
"""

import csv
import os
import time

ETAPAS = ("captura", "preprocesamiento", "linea", "senales", "control")


class Cronometro:
    """Mide cuánto tarda cada etapa del ciclo y el total, en segundos.

    Se usa como: `with cronometro.medir("captura"): ...`. Guarda solo
    la última medición de cada etapa (no un historial), porque
    MetricasCiclo.registrar_fotograma() ya persiste lo que se necesita
    conservar entre fotogramas.
    """

    def __init__(self):
        self.duraciones = {etapa: 0.0 for etapa in ETAPAS}
        self._inicio_ciclo = None

    def iniciar_ciclo(self) -> None:
        """Marca el inicio del ciclo completo, para poder calcular la
        latencia total al terminar.

        Recibe: nada. Devuelve: nada.
        """
        self._inicio_ciclo = time.perf_counter()

    def medir(self, etapa: str):
        """Context manager que mide la duración de una etapa.

        Recibe: etapa (str, debe estar en ETAPAS).
        Devuelve: un context manager; al salir, guarda la duración en
            self.duraciones[etapa].
        """
        return _MedidorDeEtapa(self, etapa)

    def latencia_total_s(self) -> float:
        """Segundos transcurridos desde iniciar_ciclo().

        Recibe: nada. Devuelve: float. 0.0 si no se llamó iniciar_ciclo().
        """
        if self._inicio_ciclo is None:
            return 0.0
        return time.perf_counter() - self._inicio_ciclo


class _MedidorDeEtapa:
    """Context manager interno de Cronometro.medir(). No se usa directo."""

    def __init__(self, cronometro: Cronometro, etapa: str):
        self._cronometro = cronometro
        self._etapa = etapa

    def __enter__(self):
        self._inicio = time.perf_counter()
        return self

    def __exit__(self, tipo_excepcion, valor_excepcion, rastreo):
        self._cronometro.duraciones[self._etapa] = time.perf_counter() - self._inicio
        return False


class MetricasCiclo:
    """Acumula FPS, latencia por etapa y eventos (cambios de estado,
    señales confirmadas) durante la ejecución de main.py, y los guarda
    en un CSV al cerrar.

    Dos CSV distintos porque tienen una fila por concepto distinto
    (uno por fotograma, otro por evento discreto): mezclarlos en una
    sola tabla obligaría a dejar columnas vacías en la mayoría de filas.
    """

    def __init__(self, directorio_salida: str = "capturas"):
        self._directorio_salida = directorio_salida
        os.makedirs(directorio_salida, exist_ok=True)

        self._ruta_fotogramas = os.path.join(directorio_salida, "metricas_fotogramas.csv")
        self._ruta_eventos = os.path.join(directorio_salida, "metricas_eventos.csv")

        self._archivo_fotogramas = open(self._ruta_fotogramas, "w", newline="", encoding="utf-8")
        self._escritor_fotogramas = csv.writer(self._archivo_fotogramas)
        self._escritor_fotogramas.writerow(
            ["tiempo", "fps", "latencia_total_s"] + [f"latencia_{etapa}_s" for etapa in ETAPAS]
        )

        self._archivo_eventos = open(self._ruta_eventos, "w", newline="", encoding="utf-8")
        self._escritor_eventos = csv.writer(self._archivo_eventos)
        self._escritor_eventos.writerow(["tiempo", "tipo", "detalle"])

        self._tiempo_fotograma_anterior = None
        self.fps_actual = 0.0

    def registrar_fotograma(self, cronometro: Cronometro) -> None:
        """Calcula el FPS del fotograma actual (a partir del tiempo
        transcurrido desde el fotograma anterior) y escribe una fila
        en el CSV de fotogramas con FPS y todas las latencias medidas.

        Recibe: cronometro (Cronometro, ya con todas sus etapas
            medidas en este fotograma).
        Devuelve: nada.
        """
        ahora = time.monotonic()
        if self._tiempo_fotograma_anterior is not None:
            duracion = ahora - self._tiempo_fotograma_anterior
            if duracion > 0:
                self.fps_actual = 1.0 / duracion
        self._tiempo_fotograma_anterior = ahora

        fila = [ahora, self.fps_actual, cronometro.latencia_total_s()]
        fila += [cronometro.duraciones[etapa] for etapa in ETAPAS]
        self._escritor_fotogramas.writerow(fila)

    def registrar_evento(self, tipo: str, detalle: str) -> None:
        """Escribe una fila en el CSV de eventos: cambio de estado o
        señal confirmada.

        Recibe: tipo (str, p. ej. "cambio_estado" o "senal_confirmada"),
            detalle (str, texto libre con lo que ocurrió).
        Devuelve: nada.
        """
        self._escritor_eventos.writerow([time.monotonic(), tipo, detalle])

    def cerrar(self) -> None:
        """Cierra los archivos CSV. Debe llamarse siempre al terminar,
        incluso si main.py sale por una excepción (usar try/finally).

        Recibe: nada. Devuelve: nada.
        """
        self._archivo_fotogramas.close()
        self._archivo_eventos.close()
