"""Script de medición manual del mBot real (NO es unittest: necesita el
robot conectado por Bluetooth y a alguien mirándolo para frenarlo si se
sale de control).

Mide, antes de rediseñar control/controlador.py o control/estados.py,
el comportamiento real de comunicacion.salida_mbot.SalidaMBot para
saber contra qué límites físicos hay que diseñar:
- Cuántos comandos por segundo se logran enviar realmente.
- Cuánto bloquea cada llamada a enviar()/detener().
- Si el mismo comando repetido sostiene el movimiento o el robot se
  detiene entre pulsos (esto es lo más importante: si el firmware
  autodetiene el motor tras cada 'w'/'a'/'d', como parece indicar
  arduinoFinal.ino, un lazo de control continuo tendría que reenviar el
  mismo comando a una frecuencia mínima para que el robot no se pare
  solo entre correcciones).
- Cuánto avanza o gira el robot con un solo comando (para poder
  calibrar más adelante).

Cada función es independiente y se llama por separado desde el menú de
main(): así se puede parar entre pruebas, revisar que el robot quedó
bien, y no encadenar automáticamente varias mediciones sin supervisión.
Antes de cada prueba que mueve al robot, se pide confirmación explícita
y se explica qué va a hacer.
"""

import time

import config
from comunicacion.salida_mbot import SalidaMBot
from control.contratos import ComandoRobot

CANTIDAD_COMANDOS_FRECUENCIA = 20  # Cuántos comandos se envían para medir comandos/segundo reales.
DURACION_SOSTENIDO_S = 3.0  # Segundos que dura la prueba de "comando repetido sostenido".


def _confirmar(mensaje: str) -> bool:
    """Pide confirmación explícita antes de mover el robot.

    Recibe: mensaje (str, qué va a hacer el robot a continuación).
    Devuelve: True si el usuario escribió 's', False en cualquier otro caso.
    """
    respuesta = input(f"{mensaje}\n¿Continuar? [s/N]: ").strip().lower()
    return respuesta == "s"


def _parada_de_emergencia(salida: SalidaMBot) -> None:
    """Detiene el robot de inmediato. Se llama en cada 'finally'.

    Recibe: salida (SalidaMBot ya conectada).
    Devuelve: nada.
    """
    try:
        salida.detener()
    except Exception as error:
        print(f"[ADVERTENCIA] No se pudo detener el robot limpiamente: {error}")


def medir_comandos_por_segundo(salida: SalidaMBot) -> None:
    """Envía CANTIDAD_COMANDOS_FRECUENCIA comandos DETENER seguidos (sin
    mover al robot) y mide cuántos por segundo se logran enviar en la
    práctica, dado el bloqueo interno de Robot._enviar().

    Recibe: salida (SalidaMBot ya conectada).
    Devuelve: nada, imprime el resultado.
    """
    print(f"\n[Medir] Enviando {CANTIDAD_COMANDOS_FRECUENCIA} comandos DETENER seguidos (el robot no se mueve)...")
    comando_detener = ComandoRobot(izquierda=0, derecha=0, estado="DETENIDO", accion="DETENER")

    inicio = time.perf_counter()
    for _ in range(CANTIDAD_COMANDOS_FRECUENCIA):
        salida.enviar(comando_detener)
    duracion_total = time.perf_counter() - inicio

    comandos_por_segundo = CANTIDAD_COMANDOS_FRECUENCIA / duracion_total
    tiempo_promedio_por_llamada = duracion_total / CANTIDAD_COMANDOS_FRECUENCIA
    print(
        f"[Medir] {CANTIDAD_COMANDOS_FRECUENCIA} comandos en {duracion_total:.3f}s "
        f"-> {comandos_por_segundo:.2f} comandos/s reales "
        f"({tiempo_promedio_por_llamada * 1000:.1f} ms promedio por llamada)."
    )
    print(
        "[Medir] Compara esto con config.FRECUENCIA_ENVIO="
        f"{config.FRECUENCIA_ENVIO}Hz (periodo={1000 / config.FRECUENCIA_ENVIO:.1f}ms): "
        "si el promedio por llamada es mayor que ese periodo, SalidaMBot "
        "no puede seguirle el ritmo al lazo de control tal como está."
    )


def medir_tiempo_de_bloqueo(salida: SalidaMBot) -> None:
    """Mide, por separado, cuánto bloquea cada método (adelante, parar)
    en una sola llamada. Coloca al robot avanzando un instante y luego
    lo detiene: SÍ mueve al robot.

    Recibe: salida (SalidaMBot ya conectada).
    Devuelve: nada, imprime el resultado.
    """
    if not _confirmar("[Medir] El robot avanzará un solo pulso (adelante) y luego se detendrá."):
        print("[Medir] Cancelado.")
        return

    comando_avanzar = ComandoRobot(izquierda=60, derecha=60, estado="SEGUIR_LINEA", accion="AVANZAR")
    comando_detener = ComandoRobot(izquierda=0, derecha=0, estado="DETENIDO", accion="DETENER")

    inicio = time.perf_counter()
    salida.enviar(comando_avanzar)
    tiempo_adelante = time.perf_counter() - inicio

    inicio = time.perf_counter()
    salida.enviar(comando_detener)
    tiempo_parar = time.perf_counter() - inicio

    print(f"[Medir] enviar(AVANZAR) bloqueó {tiempo_adelante * 1000:.1f} ms.")
    print(f"[Medir] enviar(DETENER) bloqueó {tiempo_parar * 1000:.1f} ms.")


def medir_sostenimiento_de_movimiento(salida: SalidaMBot) -> None:
    """La medición más importante: reenvía el mismo comando AVANZAR
    durante DURACION_SOSTENIDO_S segundos y pide observación visual de
    si el robot se mueve de forma continua o se detiene entre pulsos.

    Recibe: salida (SalidaMBot ya conectada).
    Devuelve: nada, imprime instrucciones y el resultado reportado por
        quien observa al robot.
    """
    mensaje = (
        f"[Medir] El robot avanzará en pulsos repetidos durante "
        f"~{DURACION_SOSTENIDO_S:.0f}s. OBSERVA si se mueve de forma "
        "continua o si notas paradas/tirones entre cada pulso."
    )
    if not _confirmar(mensaje):
        print("[Medir] Cancelado.")
        return

    comando_avanzar = ComandoRobot(izquierda=60, derecha=60, estado="SEGUIR_LINEA", accion="AVANZAR")

    inicio = time.perf_counter()
    pulsos_enviados = 0
    while time.perf_counter() - inicio < DURACION_SOSTENIDO_S:
        salida.enviar(comando_avanzar)
        pulsos_enviados += 1

    print(f"[Medir] Se enviaron {pulsos_enviados} pulsos de AVANZAR en {DURACION_SOSTENIDO_S:.0f}s.")
    respuesta = input(
        "[Medir] ¿El robot se movió de forma CONTINUA (c) o se detuvo/tironeó ENTRE pulsos (e)? [c/e]: "
    ).strip().lower()
    if respuesta == "c":
        print("[Medir] Reportado: movimiento sostenido. El firmware no autodetiene entre pulsos a esta cadencia.")
    else:
        print(
            "[Medir] Reportado: el robot se detiene/tironea entre pulsos. "
            "Esto confirma que arduinoFinal.ino autodetiene el motor tras "
            "cada comando (delay + stopMotors), y que reenviar el mismo "
            "comando no basta para sostener el movimiento a esta cadencia."
        )


def medir_avance_y_giro_por_comando(salida: SalidaMBot) -> None:
    """Envía un único comando de avance y luego uno de giro, con pausas
    para que quien esté midiendo con una cinta métrica/transportador
    registre la distancia o el ángulo recorrido por ESE solo comando.

    Recibe: salida (SalidaMBot ya conectada).
    Devuelve: nada, solo guía la medición manual (la distancia/ángulo
        los anota quien ejecuta el script, no el script).
    """
    if not _confirmar(
        "[Medir] Marca la posición y orientación actual del robot en el "
        "piso (cinta/transportador). Al confirmar, se enviará UN solo "
        "comando de avance."
    ):
        print("[Medir] Cancelado.")
        return

    comando_avanzar = ComandoRobot(izquierda=60, derecha=60, estado="SEGUIR_LINEA", accion="AVANZAR")
    salida.enviar(comando_avanzar)
    input("[Medir] Anota cuánto avanzó el robot con ESE solo comando. Presiona Enter para continuar...")

    if not _confirmar(
        "[Medir] Marca de nuevo la orientación actual. Al confirmar, se "
        "enviará UN solo comando de giro (GIRAR_SOBRE_EJE)."
    ):
        print("[Medir] Cancelado.")
        return

    comando_girar = ComandoRobot(izquierda=35, derecha=-35, estado="LINEA_PERDIDA", accion="GIRAR_SOBRE_EJE")
    salida.enviar(comando_girar)
    input("[Medir] Anota cuántos grados giró el robot con ESE solo comando. Presiona Enter para continuar...")

    print(
        "[Medir] Recuerda: SalidaMBot.enviar(GIRAR_SOBRE_EJE) en realidad "
        "llama a Robot.derecha()/izquierda(), que en el firmware NO es un "
        "giro sobre el eje sino un giro de radio amplio (ver el comentario "
        "en comunicacion/salida_mbot.py). El ángulo medido aquí corresponde "
        "a ESE movimiento, no a un giro en el sitio real."
    )


def _menu() -> None:
    """Imprime las mediciones disponibles y corre la que el usuario elija.

    Recibe: nada. Devuelve: nada.
    """
    opciones = {
        "1": ("Comandos por segundo reales (no mueve al robot)", medir_comandos_por_segundo),
        "2": ("Tiempo de bloqueo por llamada (mueve al robot un instante)", medir_tiempo_de_bloqueo),
        "3": ("Sostenimiento del movimiento con comando repetido (mueve al robot varios segundos)", medir_sostenimiento_de_movimiento),
        "4": ("Avance y giro por un solo comando (mueve al robot, requiere medir a mano)", medir_avance_y_giro_por_comando),
    }

    if config.MAC_MBOT is None:
        print("[Medir] config.MAC_MBOT no está definida. Copia .env.example a .env y completa MAC_MBOT.")
        return

    salida = SalidaMBot()
    print(f"[Medir] Conectando a {config.MAC_MBOT}...")
    salida.conectar()

    try:
        while True:
            print("\n=== Mediciones disponibles ===")
            for clave, (descripcion, _) in opciones.items():
                print(f"  {clave}. {descripcion}")
            print("  q. Salir (detiene el robot)")

            eleccion = input("Elige una opción: ").strip().lower()
            if eleccion == "q":
                break
            if eleccion not in opciones:
                print("Opción no reconocida.")
                continue

            _, funcion = opciones[eleccion]
            try:
                funcion(salida)
            except KeyboardInterrupt:
                print("\n[Medir] Interrumpido por el usuario, deteniendo el robot.")
                break
            finally:
                _parada_de_emergencia(salida)
    finally:
        _parada_de_emergencia(salida)
        salida.cerrar()


if __name__ == "__main__":
    _menu()
