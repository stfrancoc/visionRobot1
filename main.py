"""Punto de entrada del pipeline completo: captura -> preprocesamiento
-> detección de línea -> detección de señales -> máquina de estados ->
salida.

Uso:
    python main.py --video videos/correctos/video1.mp4 --salida nula
    python main.py --url http://192.168.1.10:8080/video --salida consola
    python main.py --camara 0 --salida mbot

--etapa controla hasta dónde llega el pipeline en cada fotograma, para
poder probar con el robot real por partes en vez de depurar todo junto
con el robot en movimiento (ver capturas/checklist_pruebas.md):
    - "vision" (default): solo captura+preprocesamiento+línea+señales.
      NUNCA se llama a la máquina de estados ni a salida.enviar(): sirve
      para calibrar HSV/umbral sobre la pista real sin que el robot se
      mueva ni pueda moverse.
    - "comandos": además corre la máquina de estados y MUESTRA en el
      mosaico y la consola qué comando se emitiría, pero tampoco llama
      a salida.enviar(): sirve para verificar el signo del error y la
      acción resultante ANTES de que el robot se mueva.
    - "completo": el pipeline entero, incluida la llamada real a
      salida.enviar(). Con --salida mbot, el robot arranca DETENIDO y
      no se envía ningún comando de movimiento hasta presionar 'i'
      (ver _esperar_inicio()): evita que el robot salga disparado en
      cuanto se ejecuta el script.

Teclas: 'q' o Esc salir, espacio pausar/reanudar (solo con --video),
'n' avanzar un fotograma en pausa (solo con --video), 's' guardar el
mosaico actual en capturas/, 'i' iniciar el envío de comandos (solo
--etapa completo, ver arriba).

Este archivo (y calibrar.py, utils/visualizacion.py) es el único lugar
del proyecto donde vision/ se combina con dibujo, ventanas y decisiones
de integración: las funciones de vision/ siguen siendo puras.
"""

import argparse
import time

import cv2

import config
from comunicacion.salida import SalidaConsola, SalidaNula
from control.contratos import ComandoRobot, ResultadoLinea
from control.estados import MaquinaEstados
from utils.metricas import Cronometro, MetricasCiclo
from utils.visualizacion import construir_mosaico
from vision.captura import FuenteVideo
from vision.linea import EstadoLinea, analizar_franjas, detectar_linea
from vision.preprocesamiento import preprocesar, recortar_zonas
from vision.senales import ConfirmadorSenales, detectar_senales

NOMBRE_VENTANA = "Robot seguidor de linea"


def _franja_intersecta_senal(fila_inicio_franja, fila_fin_franja, columna_franja, resultado_senales, desplazamiento_y_linea):
    """Decide si una franja de línea cae dentro del boundingRect de
    alguna señal detectada este fotograma (confirmada o no).

    Recibe: fila_inicio_franja, fila_fin_franja (píxeles de la franja
        DENTRO de la ROI de línea), columna_franja (columna, en la ROI
        de línea, del centro de línea detectado en esa franja: solo
        importa si intersecta en X, no toda la franja horizontal),
        resultado_senales (ResultadoSenales de este fotograma, con
        candidatos ya en coordenadas del fotograma completo) y
        desplazamiento_y_linea (fila del fotograma completo donde
        empieza la ROI de línea, para comparar en el mismo sistema de
        coordenadas que candidato["bounding_rect"]).
    Devuelve: bool.
    Complejidad: O(candidatos), un puñado de señales por fotograma.
    """
    fila_inicio_absoluta = fila_inicio_franja + desplazamiento_y_linea
    fila_fin_absoluta = fila_fin_franja + desplazamiento_y_linea

    for candidato in resultado_senales.candidatos:
        x, y, ancho, alto = candidato["bounding_rect"]
        solapa_en_y = fila_inicio_absoluta < y + alto and fila_fin_absoluta > y
        solapa_en_x = x <= columna_franja <= x + ancho
        if solapa_en_y and solapa_en_x:
            return True
    return False


def corregir_linea_tapada_por_senal(resultado_linea, mascara_linea_img, resultado_senales, desplazamiento_y_linea, cfg=config):
    """Invalida las franjas de línea contaminadas por una señal antes
    de que la máquina de estados vea el resultado.

    Corrección de integración documentada como pendiente en
    vision/senales.py: cuando una señal (PARE o SIGA, incluso sin
    confirmar todavía) está delante del robot, lo que
    vision/linea.py detecta bajo su boundingRect no es la línea real
    sino el borde oscuro de la señal. vision/linea.py no puede
    corregir esto porque no sabe nada de señales (ni debe: sigue
    siendo un módulo puro de línea); aquí sí se conoce el
    boundingRect de la señal detectada en el mismo fotograma, así que
    se descartan esas franjas y se recalcula error/ángulo/confianza
    con las que queden.

    Si no queda ninguna franja válida tras el descarte, se conserva el
    último resultado_linea conocido (con valida=True) en vez de
    dejarlo caer a valida=False: si la máquina de estados viera
    valida=False entraría en LINEA_PERDIDA y el robot empezaría a
    girar buscando, pero aquí no se perdió la pista, sino que la señal
    la está tapando por completo; seguir con el último error conocido
    (que la máquina de estados ya venía usando) es más seguro que
    iniciar una búsqueda que además desplaza al robot (ver
    control/controlador.py:girar_busqueda).

    Recibe: resultado_linea (ResultadoLinea de detectar_linea()),
        mascara_linea_img (máscara devuelta por detectar_linea(), para
        recalcular los centros de franja), resultado_senales
        (ResultadoSenales del mismo fotograma), desplazamiento_y_linea
        (fila del fotograma completo donde empieza la ROI de línea) y
        cfg (módulo config o compatible).
    Devuelve: ResultadoLinea corregido.
    Complejidad: O(alto × ancho) de la ROI de línea (repite el trabajo
        de analizar_franjas(), ya barato frente al resto del ciclo).
    """
    if not resultado_senales.candidatos:
        return resultado_linea

    alto_roi, ancho_roi = mascara_linea_img.shape
    limites_franja = [round(alto_roi * i / cfg.N_FRANJAS) for i in range(cfg.N_FRANJAS + 1)]
    centros = analizar_franjas(mascara_linea_img, resultado_linea.error, cfg)

    centros_validos = []
    for indice, centro_col in enumerate(centros):
        if centro_col is None:
            continue
        fila_inicio = limites_franja[indice]
        fila_fin = limites_franja[indice + 1]
        if _franja_intersecta_senal(fila_inicio, fila_fin, centro_col, resultado_senales, desplazamiento_y_linea):
            continue
        centros_validos.append((indice, centro_col))

    confianza = len(centros_validos)
    if confianza < cfg.FRANJAS_MINIMAS_VALIDAS:
        # Ninguna franja utilizable: probablemente la señal tapa toda
        # (o casi toda) la línea visible. Se mantiene el último
        # resultado conocido en vez de invalidar, por la razón
        # explicada en el docstring.
        return ResultadoLinea(
            error=resultado_linea.error,
            angulo=resultado_linea.angulo,
            confianza=resultado_linea.confianza,
            valida=True,
        )

    ancho = ancho_roi
    centro_cuadro = ancho / 2
    indice_cercana, centro_cercana = centros_validos[-1]
    indice_lejana, centro_lejana = centros_validos[0]

    error = max(-1.0, min(1.0, (centro_cercana - centro_cuadro) / centro_cuadro))
    if indice_lejana == indice_cercana:
        angulo = 0.0
    else:
        angulo = max(-1.0, min(1.0, (centro_lejana - centro_cercana) / centro_cuadro))

    return ResultadoLinea(error=error, angulo=angulo, confianza=confianza, valida=True)


def _crear_fuente_video(argumentos) -> FuenteVideo:
    """Construye la FuenteVideo según los argumentos de línea de comandos.

    Recibe: argumentos (Namespace de argparse, con video/url/camara).
    Devuelve: FuenteVideo.
    """
    if argumentos.video is not None:
        return FuenteVideo(argumentos.video)
    if argumentos.url is not None:
        return FuenteVideo(argumentos.url)
    return FuenteVideo(argumentos.camara)


def _crear_salida(nombre_salida: str):
    """Construye la implementación de SalidaRobot pedida por --salida.

    Recibe: nombre_salida (str, "consola", "nula" o "mbot").
    Devuelve: instancia de SalidaRobot. Para "mbot", ya conectada.
    """
    if nombre_salida == "consola":
        return SalidaConsola()
    if nombre_salida == "nula":
        return SalidaNula()
    if nombre_salida == "mbot":
        # Import diferido: comunicacion.salida_mbot solo se necesita
        # (y solo debería fallar si falta pybluez/el robot) cuando de
        # verdad se pide --salida mbot.
        from comunicacion.salida_mbot import SalidaMBot
        salida = SalidaMBot()
        salida.conectar()
        return salida
    raise ValueError(f"--salida debe ser consola, nula o mbot, no {nombre_salida!r}")


def ejecutar(argumentos) -> None:
    """Corre el ciclo principal del robot hasta que la fuente termine o
    el usuario salga.

    Recibe: argumentos (Namespace de argparse, ver construir_parser()).
    Devuelve: nada.
    Complejidad: O(n) sobre la cantidad de fotogramas procesados.
    """
    fuente = _crear_fuente_video(argumentos)
    salida = _crear_salida(argumentos.salida)
    metricas = MetricasCiclo()

    estado_linea = EstadoLinea()
    confirmador_senales = ConfirmadorSenales()
    maquina = MaquinaEstados()

    # SalidaMBot bloquea ~100ms por llamada (ver
    # comunicacion/salida_mbot.py): FRECUENCIA_ENVIO limita cuántas
    # veces por segundo se llama a salida.enviar(), para que ese
    # bloqueo no determine la velocidad del ciclo de visión completo
    # (que puede seguir corriendo mucho más rápido). Con --salida
    # consola/nula el bloqueo no existe, pero se respeta la misma
    # frecuencia para medir en condiciones parecidas a las reales.
    periodo_minimo_envio = 1.0 / config.FRECUENCIA_ENVIO
    tiempo_ultimo_envio = 0.0

    if argumentos.debug:
        cv2.namedWindow(NOMBRE_VENTANA)

    # --etapa completo con una salida que de verdad mueve el robot: se
    # arranca DETENIDO y no se llama a salida.enviar() ni una vez hasta
    # que el usuario presione 'i' explícitamente (ver el bucle
    # principal). Con vision/comandos nunca se llama a enviar(), así
    # que este flag no aplica (se deja en True para no bloquear nada).
    envio_habilitado = argumentos.etapa != "completo" or argumentos.salida != "mbot"
    if not envio_habilitado:
        print(
            "[main] --etapa completo con --salida mbot: el robot queda DETENIDO. "
            "Presiona 'i' en la ventana para empezar a enviar comandos."
        )

    contador_capturas = 0
    eventos_registrados = 0
    tiempo_inicio = time.monotonic()
    ultimo_mosaico = None

    def _procesar_fotograma(fotograma, cronometro):
        nonlocal tiempo_ultimo_envio, eventos_registrados, ultimo_mosaico

        with cronometro.medir("preprocesamiento"):
            preprocesado = preprocesar(fotograma, config)
            roi_linea, roi_senales, fila_inicio_linea, fila_inicio_senales = recortar_zonas(preprocesado, config)

        with cronometro.medir("linea"):
            resultado_linea, mascara_linea_img = detectar_linea(roi_linea, estado_linea, config)

        with cronometro.medir("senales"):
            resultado_senales = detectar_senales(roi_senales, fila_inicio_senales, confirmador_senales, config)

        resultado_linea = corregir_linea_tapada_por_senal(
            resultado_linea, mascara_linea_img, resultado_senales, fila_inicio_linea, config
        )

        if argumentos.etapa == "vision":
            # Ni máquina de estados ni salida: solo la detección, para
            # calibrar HSV/umbral sobre la pista real sin que el robot
            # pueda moverse.
            comando = ComandoRobot(estado="(sin control, --etapa vision)")
        else:
            tiempo_actual = time.monotonic() - tiempo_inicio
            with cronometro.medir("control"):
                comando = maquina.actualizar(resultado_linea, resultado_senales, tiempo_actual)

            eventos_nuevos = maquina.obtener_eventos()[eventos_registrados:]
            eventos_registrados += len(eventos_nuevos)
            for _, estado_anterior, estado_nuevo, motivo in eventos_nuevos:
                metricas.registrar_evento("cambio_estado", f"{estado_anterior}->{estado_nuevo}: {motivo}")

            if argumentos.etapa == "comandos":
                # Se calcula el comando y se muestra, pero nunca se
                # envía: sirve para verificar signo/acción antes de
                # que el robot se mueva.
                print(
                    f"[main] (sin enviar) estado={comando.estado} accion={comando.accion} "
                    f"izq={comando.izquierda} der={comando.derecha} error={resultado_linea.error:+.2f}"
                )
            else:  # "completo"
                ahora = time.monotonic()
                if envio_habilitado and ahora - tiempo_ultimo_envio >= periodo_minimo_envio:
                    salida.enviar(comando)
                    tiempo_ultimo_envio = ahora

        metricas.registrar_fotograma(cronometro)

        alto = preprocesado.shape[0]
        fila_chasis_px = round(alto * config.FILA_CHASIS)
        fila_fin_linea = round(fila_chasis_px * config.ROI_LINEA_FIN)
        fila_fin_senales = round(fila_chasis_px * config.ROI_SENALES_FIN)
        ultimo_mosaico = construir_mosaico(
            preprocesado, resultado_linea, resultado_senales, mascara_linea_img, comando,
            fila_chasis_px, fila_inicio_linea, fila_fin_linea, fila_inicio_senales, fila_fin_senales,
            metricas.fps_actual, cronometro.latencia_total_s(), config,
        )

        if argumentos.debug:
            cv2.imshow(NOMBRE_VENTANA, ultimo_mosaico)

    def _leer_y_procesar(funcion_lectura):
        """Lee un fotograma con funcion_lectura, midiendo su duración
        como etapa "captura", y si hay fotograma lo procesa completo.

        Recibe: funcion_lectura (callable sin argumentos que devuelve
            (ok, fotograma, marca_de_tiempo), p. ej. fuente.leer o
            fuente.avanzar_un_fotograma).
        Devuelve: bool, el "ok" de funcion_lectura.
        """
        cronometro = Cronometro()
        cronometro.iniciar_ciclo()
        with cronometro.medir("captura"):
            ok, fotograma, _ = funcion_lectura()
        if ok:
            _procesar_fotograma(fotograma, cronometro)
        return ok

    def _procesar_tecla_inicio(tecla):
        """Si la tecla es 'i' y el envío todavía no está habilitado,
        lo habilita e informa por consola.

        Recibe: tecla (int, código de cv2.waitKey).
        Devuelve: nada.
        """
        nonlocal envio_habilitado
        if tecla == ord("i") and not envio_habilitado:
            envio_habilitado = True
            print("[main] envío de comandos HABILITADO: el robot empezará a moverse.")

    try:
        while True:
            ok = _leer_y_procesar(fuente.leer)
            if not ok:
                if argumentos.video is None:
                    continue  # fuente en vivo momentáneamente sin fotograma nuevo
                break

            tecla = cv2.waitKey(1) & 0xFF if argumentos.debug else 0xFF
            if tecla in (ord("q"), 27):
                break
            _procesar_tecla_inicio(tecla)
            if tecla == ord("s") and ultimo_mosaico is not None:
                contador_capturas += 1
                ruta = f"capturas/main_captura_{contador_capturas}.png"
                cv2.imwrite(ruta, ultimo_mosaico)
                print(f"[main] mosaico guardado en {ruta}")
            if tecla == ord(" ") and argumentos.video is not None:
                fuente.pausar(True)
                while True:
                    tecla_pausa = cv2.waitKey(0) & 0xFF
                    if tecla_pausa == ord(" "):
                        fuente.pausar(False)
                        break
                    if tecla_pausa in (ord("q"), 27):
                        return
                    _procesar_tecla_inicio(tecla_pausa)
                    if tecla_pausa == ord("s") and ultimo_mosaico is not None:
                        contador_capturas += 1
                        ruta = f"capturas/main_captura_{contador_capturas}.png"
                        cv2.imwrite(ruta, ultimo_mosaico)
                        print(f"[main] mosaico guardado en {ruta}")
                    if tecla_pausa == ord("n"):
                        _leer_y_procesar(fuente.avanzar_un_fotograma)
    finally:
        salida.detener()
        salida.cerrar()
        fuente.liberar()
        metricas.cerrar()
        if argumentos.debug:
            cv2.destroyAllWindows()


def construir_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de línea de comandos.

    Recibe: nada. Devuelve: argparse.ArgumentParser.
    """
    parser = argparse.ArgumentParser(description="Pipeline completo del robot seguidor de línea.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--video", help="Ruta a un archivo de video, p. ej. videos/correctos/video1.mp4")
    origen.add_argument("--url", help="URL de stream de video (p. ej. la cámara IP del teléfono)")
    origen.add_argument("--camara", type=int, help="Índice de cámara local (0, 1, ...)")
    parser.add_argument("--debug", action="store_true", help="Muestra el mosaico de depuración en una ventana")
    parser.add_argument(
        "--salida", choices=["consola", "nula", "mbot"], default="consola",
        help="Implementación de SalidaRobot a usar (default: consola)",
    )
    parser.add_argument(
        "--etapa", choices=["vision", "comandos", "completo"], default="vision",
        help=(
            "Hasta dónde llega el pipeline (default: vision, la más segura). "
            "vision: solo detección, nunca mueve el robot. comandos: calcula y "
            "muestra el comando pero no lo envía. completo: lo envía de verdad "
            "(con --salida mbot, requiere presionar 'i' para empezar)."
        ),
    )
    return parser


if __name__ == "__main__":
    argumentos = construir_parser().parse_args()
    ejecutar(argumentos)
