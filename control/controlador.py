"""Control por zonas para el seguimiento de línea.

Traduce un ResultadoLinea (error lateral y ángulo) en señales de rueda
para el robot. No conoce estados ni señales: solo hace control. La
máquina de estados (control/estados.py) decide cuándo llamarlo, cuándo
pedir una búsqueda y cuándo reiniciarlo.

El mBot real (ver comunicacion/robot_mbot.py) no acepta velocidades:
solo 5 comandos discretos sin parámetros, cada uno un pulso de duración
fija que el firmware autodetiene. No existe una magnitud de corrección
continua que multiplicar por el error (como haría un PD clásico); la
única "magnitud" disponible es CUÁNTOS comandos de giro consecutivos se
envían antes de volver a avanzar. Por eso el control se organiza en
zonas de error (ver ZONA_CENTRADO/ZONA_FUERTE en config.py), cada una
con su propia relación fija de giro/avance.
"""

import config
from control.contratos import ResultadoLinea

ZONA_CENTRADO = "CENTRADO"
ZONA_LEVE = "LEVE"
ZONA_FUERTE = "FUERTE"


class ControladorZonas:
    """Calcula señales de rueda a partir del error de línea, clasificando
    el error suavizado en zonas y alternando giro/avance según la zona.
    """

    def __init__(self):
        self.error_suavizado = 0.0
        self.zona_actual = ZONA_CENTRADO
        # Cuántos comandos lleva emitidos dentro del "plan" de la zona
        # actual (p. ej., en zona leve: 1 giro, luego 1 avance, luego
        # vuelve a contar desde 0 para el siguiente giro).
        self._comandos_en_plan = 0

    def calcular(self, resultado_linea: ResultadoLinea) -> tuple[int, int]:
        """Calcula la señal de rueda para este fotograma.

        Recibe: resultado_linea (ResultadoLinea con error en [-1, 1];
            se asume valida=True, ya se comprobó antes de llamar).
        Devuelve: (izquierda, derecha) en enteros. NO son velocidades
            reales (ver el módulo): son señales simbólicas de signo y
            diferencia para que control.contratos.calcular_accion()
            derive AVANZAR/GIRAR_IZQUIERDA/GIRAR_DERECHA. El signo del
            giro sigue la misma convención que el modelo anterior:
            error > 0 (línea a la derecha) -> izquierda > derecha, para
            que el chasis gire hacia la derecha.
        Complejidad: O(1).
        """
        self.error_suavizado = (
            config.ALFA_SUAVIZADO * resultado_linea.error
            + (1 - config.ALFA_SUAVIZADO) * self.error_suavizado
        )

        nueva_zona = self._clasificar_zona(self.error_suavizado)
        if nueva_zona != self.zona_actual:
            self.zona_actual = nueva_zona
            self._comandos_en_plan = 0

        debe_girar = self._decidir_giro()
        self._comandos_en_plan += 1

        if not debe_girar:
            return self._senal_avance()

        signo = 1 if self.error_suavizado > 0 else -1
        return self._senal_giro(signo)

    def _clasificar_zona(self, error_suavizado: float) -> str:
        """Clasifica el error suavizado en una zona, aplicando histéresis
        al salir de la zona actual hacia una menos severa.

        Recibe: error_suavizado (float).
        Devuelve: una de ZONA_CENTRADO, ZONA_LEVE, ZONA_FUERTE.
        Complejidad: O(1).
        """
        magnitud = abs(error_suavizado)

        # La histéresis solo se exige para SALIR de la zona actual hacia
        # una menos severa (fuerte->leve, leve->centrado): entrar a una
        # zona más severa usa el umbral normal, porque ahí no hay riesgo
        # de "parpadeo" (el error va en aumento, no oscilando alrededor
        # del umbral).
        if self.zona_actual == ZONA_FUERTE:
            if magnitud < config.ZONA_FUERTE - config.MARGEN_HISTERESIS_ZONA:
                return ZONA_LEVE if magnitud >= config.ZONA_CENTRADO else ZONA_CENTRADO
            return ZONA_FUERTE

        if self.zona_actual == ZONA_LEVE:
            if magnitud >= config.ZONA_FUERTE:
                return ZONA_FUERTE
            if magnitud < config.ZONA_CENTRADO - config.MARGEN_HISTERESIS_ZONA:
                return ZONA_CENTRADO
            return ZONA_LEVE

        # zona_actual == ZONA_CENTRADO
        if magnitud >= config.ZONA_FUERTE:
            return ZONA_FUERTE
        if magnitud >= config.ZONA_CENTRADO:
            return ZONA_LEVE
        return ZONA_CENTRADO

    def _decidir_giro(self) -> bool:
        """Decide si el comando de este fotograma debe ser un giro o un
        avance, según la relación giro/avance de la zona actual y
        cuántos comandos lleva el plan en curso.

        Recibe: nada (usa self.zona_actual y self._comandos_en_plan).
        Devuelve: bool, True si toca girar.
        Complejidad: O(1).
        """
        if self.zona_actual == ZONA_CENTRADO:
            return False

        if self.zona_actual == ZONA_FUERTE:
            # GIROS_CONSECUTIVOS_ZONA_FUERTE giros seguidos, luego un
            # avance intercalado: sin este tope, si el error quedara
            # "atascado" en zona fuerte (p. ej. una curva más cerrada
            # que lo que el giro de radio amplio puede corregir sin
            # avanzar nada), el robot giraría para siempre sin volver a
            # intentar avanzar y sin poder pasar curvas.
            longitud_ciclo = config.GIROS_CONSECUTIVOS_ZONA_FUERTE + 1
            posicion_en_ciclo = self._comandos_en_plan % longitud_ciclo
            return posicion_en_ciclo < config.GIROS_CONSECUTIVOS_ZONA_FUERTE

        # ZONA_LEVE: alterna GIROS_POR_AVANCE_ZONA_LEVE giros con
        # AVANCES_POR_GIRO_ZONA_LEVE avances, en ese orden.
        longitud_ciclo = config.GIROS_POR_AVANCE_ZONA_LEVE + config.AVANCES_POR_GIRO_ZONA_LEVE
        posicion_en_ciclo = self._comandos_en_plan % longitud_ciclo
        return posicion_en_ciclo < config.GIROS_POR_AVANCE_ZONA_LEVE

    def _senal_avance(self) -> tuple[int, int]:
        """Señal simbólica de avance recto (ambas ruedas iguales).

        Recibe: nada. Devuelve: (SENAL_AVANCE, SENAL_AVANCE).
        Complejidad: O(1).
        """
        return config.SENAL_AVANCE, config.SENAL_AVANCE

    def _senal_giro(self, signo: int) -> tuple[int, int]:
        """Señal simbólica de giro hacia un lado (una rueda en
        SENAL_GIRO, la otra en 0: mismo signo en ambas, nunca opuesto,
        porque el mBot no tiene giro sobre el eje).

        La convención real (ver control/contratos.py:calcular_accion y
        comunicacion/salida_mbot.py) es izquierda > derecha ->
        "GIRAR_IZQUIERDA" -> Robot.izquierda(): el chasis gira hacia
        el lado de la rueda con la señal MÁS ALTA, no hacia el lado de
        la rueda en 0. Por eso signo > 0 (girar a la derecha) debe
        producir derecha > izquierda, es decir (0, SENAL_GIRO).

        Recibe: signo (1 para girar hacia la derecha, -1 hacia la
            izquierda; misma convención que el resto del módulo).
        Devuelve: (izquierda, derecha) con diferencia SENAL_GIRO.
        Complejidad: O(1).
        """
        if signo > 0:
            return 0, config.SENAL_GIRO
        return config.SENAL_GIRO, 0

    def girar_busqueda(self, direccion: int) -> tuple[int, int]:
        """Señal de giro para buscar la línea perdida.

        Ya no existe un giro sobre el eje: la búsqueda usa la misma
        señal de giro de radio amplio que la corrección normal (ver
        _senal_giro), así que buscar la línea YA desplaza al robot
        hacia adelante mientras gira (ver control/estados.py para la
        documentación completa de esta implicación).

        Recibe: direccion (signo del último error válido: positivo si
            la línea estaba a la derecha del centro, negativo si estaba
            a la izquierda).
        Devuelve: (izquierda, derecha), mismo formato que _senal_giro.
        Complejidad: O(1).
        """
        signo = 1 if direccion >= 0 else -1
        return self._senal_giro(signo)

    def detener(self) -> tuple[int, int]:
        """Señal de parada para ambas ruedas.

        Recibe: nada. Devuelve: (0, 0).
        Complejidad: O(1).
        """
        return 0, 0

    def reiniciar(self) -> None:
        """Limpia el estado interno del controlador.

        Se debe llamar al salir de PARE o de una búsqueda, para que el
        plan de zona no arrastre comandos contados durante un estado
        distinto.

        Recibe: nada. Devuelve: nada.
        Complejidad: O(1).
        """
        self.error_suavizado = 0.0
        self.zona_actual = ZONA_CENTRADO
        self._comandos_en_plan = 0
