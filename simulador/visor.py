"""Visor de calibración: ventana OpenCV que corre la pista virtual y
permite ajustar KP, KD, KA, VEL_BASE y VEL_MIN en vivo con trackbars.

Esta es la única pieza de simulador/ que abre ventanas y lee trackbars,
igual que main.py y calibrar.py hacen para la visión real.
"""

import json
import time

import cv2
import numpy as np

import config
from control.estados import MaquinaEstados
from simulador.pista_virtual import ANCHO_PISTA, PistaVirtual, crear_pista_calibracion

ANCHO_VENTANA = 900  # Ancho en píxeles de la ventana del visor.
ALTO_VENTANA = 500  # Alto en píxeles de la ventana del visor.
MARGEN_VENTANA = 40  # Margen alrededor del área de dibujo de la pista.
ESCALA_TRACKBAR = 10  # Los trackbars de OpenCV solo dan enteros; se divide por esto para tener decimales.
DT_SIMULACION = 0.05  # Paso de tiempo fijo de cada iteración del visor (segundos).

RUTA_CALIBRACION = "calibracion_control.json"
NOMBRE_VENTANA = "Calibracion de control"


def _trackbar_a_config(nombre_trackbar: str) -> float:
    """Lee un trackbar y lo convierte al valor real del parámetro.

    Recibe: nombre_trackbar (str, debe existir en la ventana del visor).
    Devuelve: float, valor del trackbar dividido por ESCALA_TRACKBAR.
    Complejidad: O(1).
    """
    return cv2.getTrackbarPos(nombre_trackbar, NOMBRE_VENTANA) / ESCALA_TRACKBAR


def _crear_trackbars() -> None:
    """Crea la ventana del visor y sus trackbars, con los valores
    actuales de config.py como punto de partida.

    Recibe: nada. Devuelve: nada.
    Complejidad: O(1).
    """
    cv2.namedWindow(NOMBRE_VENTANA)
    cv2.createTrackbar("KP", NOMBRE_VENTANA, int(config.KP * ESCALA_TRACKBAR), 2000, lambda _: None)
    cv2.createTrackbar("KD", NOMBRE_VENTANA, int(config.KD * ESCALA_TRACKBAR), 2000, lambda _: None)
    cv2.createTrackbar("KA", NOMBRE_VENTANA, int(config.KA * ESCALA_TRACKBAR), 2000, lambda _: None)
    cv2.createTrackbar("VEL_BASE", NOMBRE_VENTANA, int(config.VEL_BASE * ESCALA_TRACKBAR), int(config.VEL_MAX * ESCALA_TRACKBAR), lambda _: None)
    cv2.createTrackbar("VEL_MIN", NOMBRE_VENTANA, int(config.VEL_MIN * ESCALA_TRACKBAR), int(config.VEL_MAX * ESCALA_TRACKBAR), lambda _: None)


def _aplicar_trackbars() -> None:
    """Copia los valores actuales de los trackbars a config.py, para que
    el controlador los use en el siguiente paso.

    Recibe: nada. Devuelve: nada.
    Complejidad: O(1).
    """
    config.KP = _trackbar_a_config("KP")
    config.KD = _trackbar_a_config("KD")
    config.KA = _trackbar_a_config("KA")
    config.VEL_BASE = _trackbar_a_config("VEL_BASE")
    config.VEL_MIN = _trackbar_a_config("VEL_MIN")


def _dibujar_pista(lienzo, pista: PistaVirtual, comando) -> None:
    """Dibuja la pista, el robot, el error y el estado en el lienzo.

    Recibe: lienzo (imagen de OpenCV donde dibujar), pista (PistaVirtual
        con la posición actual) y comando (ComandoRobot del paso actual).
    Devuelve: nada, dibuja sobre lienzo en el sitio.
    Complejidad: O(1).
    """
    lienzo[:] = (30, 30, 30)

    centro_x = ANCHO_VENTANA // 2
    y_pista = ALTO_VENTANA // 2
    medio_ancho_dibujo = ANCHO_VENTANA // 2 - MARGEN_VENTANA

    cv2.line(lienzo, (MARGEN_VENTANA, y_pista), (ANCHO_VENTANA - MARGEN_VENTANA, y_pista), (200, 200, 200), 2)
    cv2.line(
        lienzo,
        (MARGEN_VENTANA, y_pista - int(medio_ancho_dibujo)),
        (ANCHO_VENTANA - MARGEN_VENTANA, y_pista - int(medio_ancho_dibujo)),
        (80, 80, 80),
        1,
    )
    cv2.line(
        lienzo,
        (MARGEN_VENTANA, y_pista + int(medio_ancho_dibujo)),
        (ANCHO_VENTANA - MARGEN_VENTANA, y_pista + int(medio_ancho_dibujo)),
        (80, 80, 80),
        1,
    )

    posicion_normalizada = max(-1.5, min(1.5, pista.posicion_lateral / ANCHO_PISTA))
    y_robot = y_pista - int(posicion_normalizada * medio_ancho_dibujo)
    cv2.circle(lienzo, (centro_x, y_robot), 10, (0, 140, 255), -1)

    tramo = pista.tramo_actual()
    tipo_tramo = tramo.tipo if tramo is not None else "fin"

    textos = [
        f"tiempo={pista.distancia_total:.1f}  tramo={tipo_tramo}",
        f"estado={comando.estado}  accion={comando.accion}",
        f"izq={comando.izquierda}  der={comando.derecha}",
        f"pos_lateral={pista.posicion_lateral:.3f}",
        f"KP={config.KP:.2f} KD={config.KD:.2f} KA={config.KA:.2f} VEL_BASE={config.VEL_BASE:.0f} VEL_MIN={config.VEL_MIN:.0f}",
    ]
    for indice, texto in enumerate(textos):
        cv2.putText(lienzo, texto, (MARGEN_VENTANA, 30 + indice * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    cv2.rectangle(lienzo, (centro_x - 15, y_robot - 8), (centro_x + 15, y_robot + 8), (0, 140, 255), 1)


def _guardar_calibracion() -> None:
    """Guarda los valores actuales de control en calibracion_control.json.

    Recibe: nada. Devuelve: nada.
    Complejidad: O(1).
    """
    valores = {
        "KP": config.KP,
        "KD": config.KD,
        "KA": config.KA,
        "VEL_BASE": config.VEL_BASE,
        "VEL_MIN": config.VEL_MIN,
    }
    with open(RUTA_CALIBRACION, "w", encoding="utf-8") as archivo:
        json.dump(valores, archivo, indent=2)
    print(f"[Visor] Calibración guardada en {RUTA_CALIBRACION}: {valores}")


def _imprimir_metricas(errores: list[float], eventos_fuera: int, tiempo_total: float, estados: set[str]) -> None:
    """Imprime las métricas finales del recorrido.

    Recibe: errores (lista de |error| válidos por fotograma), eventos_fuera
        (veces que el robot se salió de la pista), tiempo_total (segundos
        simulados) y estados (conjunto de estados visitados).
    Devuelve: nada, solo imprime.
    Complejidad: O(n) sobre la cantidad de errores registrados.
    """
    error_medio = sum(errores) / len(errores) if errores else 0.0
    error_maximo = max(errores) if errores else 0.0
    print("\n[Visor] Métricas del recorrido:")
    print(f"  error medio absoluto: {error_medio:.4f}")
    print(f"  error máximo: {error_maximo:.4f}")
    print(f"  veces fuera de la pista: {eventos_fuera}")
    print(f"  tiempo total simulado: {tiempo_total:.2f} s")
    print(f"  estados recorridos: {sorted(estados)}")


def ejecutar_visor() -> None:
    """Corre el bucle principal del visor de calibración.

    Recibe: nada.
    Devuelve: nada. Sale cuando la pista termina o el usuario presiona 'q'.
    Complejidad: O(n) sobre la cantidad de pasos de simulación.
    """
    _crear_trackbars()

    pista = PistaVirtual(crear_pista_calibracion(), ruido=0.01, semilla=None)
    maquina = MaquinaEstados()
    lienzo = None

    errores_absolutos = []
    estados_visitados = set()
    tiempo_simulado = 0.0

    while not pista.terminado():
        _aplicar_trackbars()

        resultado_linea = pista.generar_resultado_linea()
        resultado_senales = pista.generar_resultado_senales()
        comando = maquina.actualizar(resultado_linea, resultado_senales, tiempo_simulado)
        pista.paso(comando.izquierda, comando.derecha, DT_SIMULACION)
        tiempo_simulado += DT_SIMULACION

        if resultado_linea.valida:
            errores_absolutos.append(abs(resultado_linea.error))
        estados_visitados.add(comando.estado)

        if lienzo is None:
            lienzo = np.zeros((ALTO_VENTANA, ANCHO_VENTANA, 3), dtype="uint8")
        _dibujar_pista(lienzo, pista, comando)
        cv2.imshow(NOMBRE_VENTANA, lienzo)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if tecla == ord("g"):
            _guardar_calibracion()

    _imprimir_metricas(errores_absolutos, pista.fuera_de_pista_eventos, tiempo_simulado, estados_visitados)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    ejecutar_visor()
