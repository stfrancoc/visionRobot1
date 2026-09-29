"""Captura de video: archivo, URL de red o cámara local.

Es la única fuente de fotogramas del pipeline. No procesa nada, solo
entrega fotogramas y su marca de tiempo; el resto de vision/ (por ahora
preprocesamiento.py) recibe lo que esta clase produce.

Con una fuente EN VIVO (URL o cámara), leer más lento que la fuente
entrega hace que los fotogramas se acumulen en el buffer de OpenCV y el
que finalmente se lee esté cada vez más retrasado respecto al momento
real: la latencia de percepción crecería sin límite. Por eso, para esas
dos fuentes, un hilo lee en segundo plano tan rápido como puede y solo
conserva el fotograma más reciente, descartando los viejos que nadie
llegó a consumir.

Con un ARCHIVO no hay ese problema (no está "sucediendo en vivo": se
puede leer tan rápido o lento como se quiera sin acumular retraso real),
así que se lee de forma secuencial y directa, sin hilo, para poder
pausar y avanzar fotograma a fotograma durante las pruebas.
"""

import threading
import time
from typing import Optional

import cv2
import numpy as np

import config

ROTACIONES_VALIDAS = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


class FuenteVideo:
    """Entrega fotogramas desde un archivo, una URL de red o una cámara
    local, con la misma interfaz sin importar el origen.
    """

    def __init__(self, origen, rotacion: int = None):
        """Abre la fuente de video.

        Recibe: origen (str con ruta de archivo o URL, o int con índice
            de cámara local) y rotacion (int en {0, 90, 180, 270};
            si es None usa config.ROTACION).
        Devuelve: nada.
        Complejidad: O(1).
        """
        if rotacion is None:
            rotacion = config.ROTACION
        if rotacion not in ROTACIONES_VALIDAS:
            raise ValueError(f"ROTACION debe ser uno de {sorted(ROTACIONES_VALIDAS)}, no {rotacion}")
        self._codigo_rotacion = ROTACIONES_VALIDAS[rotacion]

        self._es_archivo = isinstance(origen, str) and not origen.startswith(("http://", "https://"))
        self.captura = cv2.VideoCapture(origen)
        if not self.captura.isOpened():
            raise RuntimeError(f"No se pudo abrir la fuente de video: {origen}")

        self._pausado = False
        self._latencia_captura_s = 0.0

        if self._es_archivo:
            self._hilo = None
        else:
            self.captura.set(cv2.CAP_PROP_BUFFERSIZE, config.TAMANO_BUFFER_LECTOR)
            self._fotograma_mas_reciente: Optional[np.ndarray] = None
            self._marca_tiempo_mas_reciente = 0.0
            self._detener_hilo = False
            self._candado = threading.Lock()
            self._hilo = threading.Thread(target=self._leer_en_segundo_plano, daemon=True)
            self._hilo.start()

    def _leer_en_segundo_plano(self) -> None:
        """Bucle del hilo lector para fuentes en vivo: lee tan rápido
        como puede y sobrescribe el fotograma guardado, para que quien
        llame a leer() siempre obtenga el más reciente disponible.

        Recibe: nada. Devuelve: nada (corre hasta que se pide detener).
        Complejidad: O(1) por iteración.
        """
        while not self._detener_hilo:
            ok, fotograma = self.captura.read()
            if not ok:
                time.sleep(config.ESPERA_REINTENTO_LECTOR_MS / 1000.0)
                continue

            fotograma = self._aplicar_rotacion(fotograma)
            with self._candado:
                self._fotograma_mas_reciente = fotograma
                self._marca_tiempo_mas_reciente = time.monotonic()

    def _aplicar_rotacion(self, fotograma: np.ndarray) -> np.ndarray:
        """Aplica la rotación configurada a un fotograma.

        Recibe: fotograma (imagen de OpenCV).
        Devuelve: imagen rotada, o la misma si ROTACION=0.
        Complejidad: O(ancho × alto).
        """
        if self._codigo_rotacion is None:
            return fotograma
        return cv2.rotate(fotograma, self._codigo_rotacion)

    def leer(self) -> tuple[bool, Optional[np.ndarray], float]:
        """Entrega el fotograma disponible más reciente.

        Recibe: nada.
        Devuelve: (ok, fotograma, marca_de_tiempo). ok=False si no hay
            fotograma disponible todavía (fuente en vivo recién abierta)
            o si el archivo terminó. marca_de_tiempo es time.monotonic()
            de cuando se leyó (archivo) o se recibió (fuente en vivo).
        Complejidad: O(ancho × alto) para archivo (lee y rota en el
            momento); O(1) para fuente en vivo (el hilo ya lo dejó listo).
        """
        if self._es_archivo:
            return self._leer_de_archivo()
        return self._leer_de_buffer_compartido()

    def _leer_de_archivo(self) -> tuple[bool, Optional[np.ndarray], float]:
        """Lectura secuencial y directa para archivos: sin hilo, para
        que pausar()/avanzar_un_fotograma() controlen exactamente qué
        fotograma se procesa.

        Recibe: nada.
        Devuelve: (ok, fotograma, marca_de_tiempo).
        Complejidad: O(ancho × alto).
        """
        if self._pausado:
            return False, None, time.monotonic()

        inicio = time.perf_counter()
        ok, fotograma = self.captura.read()
        self._latencia_captura_s = time.perf_counter() - inicio

        if not ok:
            return False, None, time.monotonic()

        return True, self._aplicar_rotacion(fotograma), time.monotonic()

    def _leer_de_buffer_compartido(self) -> tuple[bool, Optional[np.ndarray], float]:
        """Lectura desde el fotograma que el hilo lector dejó listo,
        para fuentes en vivo (URL o cámara).

        Recibe: nada.
        Devuelve: (ok, fotograma, marca_de_tiempo). ok=False si el hilo
            todavía no entregó ningún fotograma.
        Complejidad: O(1).
        """
        with self._candado:
            if self._fotograma_mas_reciente is None:
                return False, None, time.monotonic()
            marca_tiempo = self._marca_tiempo_mas_reciente
            self._latencia_captura_s = time.monotonic() - marca_tiempo
            return True, self._fotograma_mas_reciente.copy(), marca_tiempo

    def latencia_captura_s(self) -> float:
        """Latencia de captura más reciente, en segundos.

        Para archivo: cuánto tardó cv2.read() en devolver el fotograma.
        Para fuente en vivo: cuánto tiempo pasó entre que el hilo
        lector recibió el fotograma y que leer() lo entregó (indica qué
        tan al día está el fotograma que se está usando).

        Recibe: nada.
        Devuelve: float, segundos. 0.0 si todavía no se ha leído nada.
        Complejidad: O(1).
        """
        return self._latencia_captura_s

    def pausar(self, pausado: bool) -> None:
        """Pausa o reanuda la lectura secuencial de un archivo.

        Solo tiene efecto sobre fuentes de archivo: una fuente en vivo
        no se puede "pausar" (la cámara o el stream siguen produciendo
        fotogramas de todas formas).

        Recibe: pausado (bool).
        Devuelve: nada.
        Complejidad: O(1).
        """
        self._pausado = pausado

    def avanzar_un_fotograma(self) -> tuple[bool, Optional[np.ndarray], float]:
        """Lee exactamente un fotograma de un archivo, sin importar si
        está pausado (para inspeccionar fotograma a fotograma).

        Recibe: nada.
        Devuelve: (ok, fotograma, marca_de_tiempo), igual que leer().
        Complejidad: O(ancho × alto).
        """
        if not self._es_archivo:
            raise RuntimeError("avanzar_un_fotograma() solo aplica a fuentes de archivo")

        estaba_pausado = self._pausado
        self._pausado = False
        resultado = self._leer_de_archivo()
        self._pausado = estaba_pausado
        return resultado

    def liberar(self) -> None:
        """Libera la fuente de video y detiene el hilo lector si existe.

        Recibe: nada. Devuelve: nada.
        Complejidad: O(1).
        """
        if self._hilo is not None:
            self._detener_hilo = True
            self._hilo.join(timeout=1.0)
        self.captura.release()
