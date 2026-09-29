"""Configuración centralizada del proyecto.

Aquí viven todos los parámetros ajustables para que ningún módulo tenga
números mágicos.

Si existen `calibracion_control.json` y/o `calibracion.json` en la raíz
del proyecto, sus valores tienen prioridad sobre los de este archivo:
- calibracion_control.json lo genera simulador/visor.py (tecla 'g').
- calibracion.json lo genera calibrar.py (tecla 'g'), con los
  parámetros de visión (ROI, umbral de línea, rangos HSV de señales).
Se cargan en ese orden; si una misma clave estuviera en ambos archivos
(no debería pasar, cubren secciones distintas), gana calibracion.json
por cargarse después.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

RUTA_CALIBRACION_CONTROL = os.path.join(os.path.dirname(__file__), "calibracion_control.json")
RUTA_CALIBRACION_VISION = os.path.join(os.path.dirname(__file__), "calibracion.json")

# ==========================================================================
# VISIÓN — CAPTURA (vision/captura.py)
# ==========================================================================

# Origen de video por defecto para main.py/scripts de prueba: ruta de
# archivo, URL de stream del teléfono (p. ej. IP Webcam) o índice de
# cámara local (0, 1, ...). FuenteVideo acepta cualquiera de los tres;
# esto solo fija con cuál arrancar si no se indica otro por argumento.
# CALIBRAR CON VIDEO/ROBOT: la URL real depende de la red del teléfono
# en el momento de la prueba.
FUENTE_VIDEO_URL = os.getenv("CAMERA_URL", "http://192.168.1.10:8080/video")

# Cuántos fotogramas "viejos" puede acumular como máximo el buffer
# interno de OpenCV antes de que el hilo lector los descarte: con una
# fuente en vivo (URL o cámara), leer más lento que la fuente produce
# genera fotogramas cada vez más retrasados si no se descartan
# activamente. Se conserva solo el más reciente en todo momento.
TAMANO_BUFFER_LECTOR = 1

# Cuántos milisegundos espera el hilo lector antes de reintentar si la
# fuente en vivo no entrega un fotograma nuevo (URL caída, cámara
# ocupada). Evita que el hilo consuma CPU en un bucle apretado inútil.
ESPERA_REINTENTO_LECTOR_MS = 20

# Rotación aplicada al fotograma justo después de leerlo, ANTES de
# cualquier otro procesamiento: el teléfono puede guardar el video en
# vertical pero algunos backends de video reproducen el contenido
# "acostado" (la orientación queda solo como metadato, no rotada en los
# píxeles). Valores válidos: 0 (sin rotación), 90, 180, 270 (grados en
# sentido horario). CALIBRAR CON VIDEO: depende del teléfono y del
# backend de video de cada máquina, se verifica con
# pruebas/probar_captura_preprocesamiento.py o main.py --etapa vision.
#
# Cambiado a 90 tras montar el teléfono en el nuevo soporte vertical
# (más estable que el soporte horizontal anterior): con DroidCam el
# stream llega acostado. Si con 90 la imagen queda al revés (girada
# hacia el lado contrario), cambiar a 270.
ROTACION = 90

ANCHO_PROCESO = 480  # Ancho (px) al que se redimensiona el fotograma para el resto del pipeline, manteniendo la proporción original. Bajarlo acelera todo el procesamiento; subirlo da más detalle a costa de latencia.

KERNEL_GAUSSIANO = 5  # Tamaño (impar) del kernel de GaussianBlur para atenuar ruido antes de segmentar. CALIBRAR CON VIDEO.

# Fila (en el fotograma YA redimensionado a ANCHO_PROCESO, medida desde
# arriba) a partir de la cual empieza a verse el chasis del propio
# robot: el teléfono va montado sobre el mBot mirando adelante y abajo,
# así que el tercio inferior del cuadro es chasis y baterías, no piso.
# Las baterías (verdes) son un falso positivo directo para la
# detección de SIGA (también verde) si no se descartan primero. Todo lo
# que esté en fila >= FILA_CHASIS se recorta y nunca llega a las ROI de
# línea ni de señales.
#
# Nota sobre la escena real (confirmada viendo videos/correctos/ y
# videos/fallos/): la pista es una superficie blanca con una línea
# negra ancha vista de frente, NO un piso en perspectiva que se
# estreche a lo lejos como se asumió al principio. La línea es visible
# y útil en casi toda la altura del cuadro hasta donde la tapan el
# chasis y, ANTES que las aletas, el sensor ultrasónico: sus dos aros
# plateados reflejan la luz de forma desigual y generan sombras/brillos
# que la máscara línea/piso puede confundir con línea (se observó esto
# directamente: con FILA_CHASIS=0.6 aparecían dos manchas oscuras
# falsas en las esquinas de la franja más cercana al robot, una de las
# cuales llegó a "ganarle" a la línea real en la selección por
# cercanía). Por eso el límite se fija ANTES del sensor, no solo antes
# de las aletas. CALIBRAR CON VIDEO: depende de dónde quede montado el
# teléfono en cada robot; medido aquí sobre video4.mp4 fotograma 407,
# el sensor empieza a aparecer alrededor de 0.55-0.56.
FILA_CHASIS = 0.53  # Fracción de la altura del fotograma (en [0, 1]), no píxeles absolutos: así no depende de ANCHO_PROCESO/la resolución original.

# La ROI de línea y la ROI de señales son dos recortes verticales
# distintos del mismo fotograma ya sin el chasis, expresados como
# fracciones de la altura disponible (entre 0 arriba y FILA_CHASIS
# abajo), no en píxeles, por la misma razón que FILA_CHASIS. Se
# solapan a propósito en la franja donde suelen aparecer las señales
# (que están cerca de la línea, no lejos de ella en esta escena): cada
# módulo busca algo distinto ahí, no hay conflicto en que ambas ROI
# cubran esa zona. CALIBRAR CON VIDEO.
ROI_LINEA_INICIO = 0.0  # Fracción de la altura disponible donde empieza la ROI de línea: la línea es útil en casi toda la altura, no solo cerca del chasis (a diferencia de un piso en perspectiva).
ROI_LINEA_FIN = 1.0  # Fracción de la altura disponible donde termina la ROI de línea (coincide con FILA_CHASIS: es el límite inferior utilizable).
ROI_SENALES_INICIO = 0.0  # Fracción de la altura disponible donde empieza la ROI de señales.
ROI_SENALES_FIN = 0.6  # Fracción de la altura disponible donde termina la ROI de señales: las señales aparecen cerca de la línea, más abajo de lo asumido originalmente.

# ==========================================================================
# VISIÓN — UMBRAL ADAPTATIVO (vision/umbral_kmeans.py)
# ==========================================================================

TAMANO_MUESTRA_KMEANS = 500  # Cuántos píxeles de la ROI se muestrean al azar para ajustar K-Means: no hace falta usar todos los píxeles para separar grupos de gris bien distintos.

# En cuántos grupos de nivel de gris divide K-Means los píxeles de la
# ROI. Es 3, no 2, porque la escena real tiene TRES poblaciones: pista
# blanca (~220), línea negra (~35) y la madera del borde de la mesa que
# rodea la pista (~100-150). Con K=2, en cuanto la madera ocupa
# suficiente área, K-Means la agrupa con la línea: medido sobre las
# grabaciones test1-test4, el umbral saltaba de ~118 a ~163 y la
# máscara de línea pasaba de ~15% a ~46% de píxeles blancos, con el
# robot siguiendo el borde de la pista en vez de la línea hasta
# salirse. Con 3 grupos el umbral se toma entre el centroide más
# oscuro (línea) y el intermedio (madera), dejando fuera a ambas.
# CALIBRAR CON VIDEO: si la pista se monta sobre una superficie de un
# solo tono (sin borde de madera visible), 2 vuelve a ser suficiente.
KMEANS_GRUPOS = 3

# Cuántas veces corre K-Means con centroides iniciales distintos, se
# queda con el mejor. Es el parámetro que más determina el costo de
# calcular_umbral(): medido sobre videos/correctos/ completos, cada
# corrida de K-Means (incluso con TAMANO_MUESTRA_KMEANS ya bajo) tarda
# ~7-10ms por inicialización (el overhead fijo de sklearn por llamada,
# no el ajuste en sí: bajar la muestra de 500 a 80 casi no cambia el
# tiempo). n_init=5 daba picos de latencia de vision/linea.py de hasta
# ~55ms, que superaban el umbral de latencia total encontrado en la
# calibración del simulador. n_init=1 bajaba el pico a ~14ms pero en
# un fotograma de video1.mp4 (línea casi saliendo del cuadro, poca
# separación línea/piso) dio un umbral 53 unidades distinto al de
# n_init=5 — un caso raro pero real de mala inicialización. n_init=2
# es el punto intermedio: conserva una segunda inicialización como
# red de seguridad contra ese caso, y baja el pico a ~40ms. CALIBRAR
# CON VIDEO si el umbral sale inestable entre fotogramas parecidos.
KMEANS_N_INIT = 2
KMEANS_SEMILLA = 42  # Semilla fija: mismo fotograma da siempre el mismo umbral (reproducible para depurar).

# Si los dos centroides de K-Means quedan más cerca que esto (en la
# escala de gris 0-255), no hay separación clara línea/piso en este
# fotograma (p. ej. la línea salió del cuadro, o el ruido domina la
# ROI): calcular_umbral() devuelve None y quien llama conserva el
# umbral anterior en vez de adoptar uno sin significado.
DIFERENCIA_MINIMA_CENTROIDES = 30  # CALIBRAR CON VIDEO.

# Cada cuántos fotogramas se recalcula el umbral con K-Means, en vez de
# reutilizar el último válido: K-Means sobre una muestra no es gratis
# (ver KMEANS_N_INIT arriba), y la iluminación no cambia de un
# fotograma al siguiente lo bastante rápido como para necesitar
# recalcularlo cada vez. Subido de 10 a 30 (a ~20 fps, cada ~1.5s en
# vez de cada ~0.5s): con 10, el pico de K-Means aparecía 1 de cada 10
# fotogramas y dominaba la latencia p95 del ciclo completo (~23ms);
# con 30 aparece 3 veces menos seguido sin que se haya observado
# ningún caso, en los videos disponibles, donde la iluminación
# cambiara lo bastante en 1.5s como para necesitar un umbral más
# reciente. CALIBRAR CON VIDEO/ROBOT: si la pista real tiene sombras
# que se muevan más rápido que esto (p. ej. por luz solar directa),
# bajar de nuevo.
PERIODO_KMEANS = 30

# ==========================================================================
# VISIÓN — DETECCIÓN DE LÍNEA (vision/linea.py)
# ==========================================================================

# En cuántas franjas horizontales se divide la ROI de línea para
# estimar su trayectoria. Más franjas dan una estimación más fina del
# ángulo, pero cada franja tiene menos alto y por lo tanto más ruido en
# su propia proyección por columnas.
N_FRANJAS = 6  # CALIBRAR CON VIDEO.

# Tamaño del kernel para las operaciones morfológicas (apertura y
# cierre) que limpian la máscara binaria línea/piso: la apertura quita
# puntos sueltos de ruido, el cierre rellena huecos pequeños dentro de
# la línea (p. ej. por un reflejo).
KERNEL_MORFOLOGICO = 5  # CALIBRAR CON VIDEO.

# Al analizar cada franja, se descartan los tramos continuos de
# columnas con línea que sean más angostos que ANCHO_MIN_PX (ruido
# suelto, no la línea real) o cuyo ÁREA (no su ancho de bounding box)
# supere ANCHO_EQUIVALENTE_MAX_PX × altura_de_la_franja.
#
# Se filtra por ÁREA y no por ancho de bbox a propósito: una línea
# inclinada dentro de una franja proyecta un bounding box mucho más
# ancho que su grosor real (un tramo de 70px de grosor inclinado ~45°
# proyecta cerca de 140px de ancho), pero su ÁREA no cambia con la
# inclinación — es geometría normal, no ruido, y un filtro por ancho de
# bbox la descartaba por error (bug encontrado con video1.mp4: la
# línea real, inclinada, medía 139px de bbox y se descartaba, dejando
# como único candidato un reflejo de 24px). El área normalizada por la
# altura de franja ("ancho equivalente") sí distingue bien ambos casos:
# medido sobre videos/correctos/ completos (video1, video2, video4;
# ~9300 tramos), la línea real da un ancho equivalente con p50=64,
# p90=86, p95=106, p99=190px; una franja transversal de señal, al
# llenar por completo su bounding box, da un ancho equivalente igual a
# su ancho real (~480px con la ROI completa) — muy por encima de
# cualquier línea real inclinada. CALIBRAR CON VIDEO si la línea real
# es de otro grosor.
ANCHO_EQUIVALENTE_MAX_PX = 200  # Cubre hasta ~p99.3 de lo medido; los casos más extremos de la cola quedan atrapados por UMBRAL_CONTINUIDAD_PX en vez de por este filtro.
ANCHO_MIN_PX = 8  # Un tramo más angosto que esto se descarta (ruido, no la línea).

# Cuando una franja tiene varios tramos válidos a la vez (línea real +
# ruido angosto, p. ej. un reflejo del sensor ultrasónico o del borde
# de la ROI), se descartan los que sean más angostos (por ancho
# equivalente, ver arriba) que este factor multiplicado por el tramo
# MÁS ANCHO de esa misma franja, antes de elegir por cercanía a la
# franja anterior. Sin esto, un tramo de ruido puede "ganarle" a la
# línea real si por casualidad queda más cerca de una referencia que ya
# venía desviada. CALIBRAR CON VIDEO.
PROPORCION_MINIMA_ANCHO_CANDIDATO = 0.5

# Continuidad entre franjas: si el centro elegido en una franja se
# aleja de la franja vecina ya confirmada más que este umbral (en
# píxeles), se descarta esa franja (queda None) EN VEZ de aceptarla, y
# su centro no se usa como referencia para la franja siguiente ni para
# el próximo fotograma (evita que un engancho a ruido se autoconfirme:
# si se usara igual como referencia, el error se propaga porque cada
# fotograma parte del resultado del anterior). Medido sobre los mismos
# tramos válidos de arriba: el salto entre franjas consecutivas reales
# tiene p50=28px, p95=79px, p97=82px, y salta a p99=343px — ese salto
# grande es la firma de un engancho a ruido, no de una curva real.
# CALIBRAR CON VIDEO.
UMBRAL_CONTINUIDAD_PX = 120

# Cuántas franjas válidas (con un tramo de línea aceptado) hacen falta,
# de las N_FRANJAS totales, para considerar el fotograma válido en su
# conjunto. Con muy pocas franjas válidas la estimación de ángulo/error
# es poco confiable.
FRANJAS_MINIMAS_VALIDAS = 2  # CALIBRAR CON VIDEO.

# ==========================================================================
# VISIÓN — DETECCIÓN DE SEÑALES (vision/senales.py)
# ==========================================================================
#
# Los videos de ensayo (videos/correctos/, videos/fallos/) NO traen las
# señales definitivas: tienen cuadrados rosados y verdes de pruebas
# anteriores del equipo, que no sirven para calibrar ni color ni forma
# (el rosado y el rojo de la señal real son colores de matiz distinto,
# y un cuadrado no es un octágono). Las señales reales son octágonos
# rojo y verde con texto PARE/SIGA en blanco y borde oscuro (ver imagen
# de referencia). Todos los valores de esta sección se calibraron con
# esa imagen y con octágonos sintéticos, NUNCA con los cuadrados de los
# videos. CALIBRAR CON VIDEO REAL cuando existan señales definitivas.

# Rango de matiz (H, en la escala 0-179 de OpenCV) para el rojo de la
# señal PARE. El rojo cruza el 0 en la rueda de color, así que se cubren
# dos rangos (0-10 y 170-179) y se unen con bitwise_or.
ROJO_H_BAJO_1 = 0  # CALIBRAR CON VIDEO REAL.
ROJO_H_ALTO_1 = 10  # CALIBRAR CON VIDEO REAL.
ROJO_H_BAJO_2 = 170  # CALIBRAR CON VIDEO REAL.
ROJO_H_ALTO_2 = 179  # CALIBRAR CON VIDEO REAL.
ROJO_S_MIN = 80  # Saturación mínima: descarta rosados/grises pálidos que compartan matiz con el rojo pero no su intensidad de color. CALIBRAR CON VIDEO REAL.
ROJO_V_MIN = 50  # Valor (brillo) mínimo: descarta rojos casi negros por sombra. CALIBRAR CON VIDEO REAL.

# Rango de matiz para el verde de la señal SIGA. Se limita a 55-85
# (sin llegar a 85 de sobra) para no invadir el cian: el chasis/carcasa
# del mBot en varios videos tiene tonos azul-cian que si se incluyeran
# generarían falsos positivos de SIGA.
VERDE_H_BAJO = 55  # CALIBRAR CON VIDEO REAL.
VERDE_H_ALTO = 85  # CALIBRAR CON VIDEO REAL. No subir de 85: ahí empieza el cian del chasis.
VERDE_S_MIN = 80  # CALIBRAR CON VIDEO REAL.
VERDE_V_MIN = 50  # CALIBRAR CON VIDEO REAL.

KERNEL_MORFOLOGICO_SENALES = 5  # Tamaño del kernel de apertura/cierre para las máscaras de color: la apertura quita ruido suelto, el cierre tapa los huecos que dejan las letras blancas de PARE/SIGA dentro del octágono. CALIBRAR CON VIDEO REAL.

# Filtro en cascada de buscar_octagonos(): un contorno debe pasar TODOS
# estos umbrales para considerarse candidato a octágono. Se aplican en
# cascada (el más barato de calcular primero) para no gastar approxPolyDP
# ni momentos en contornos que ya se sabe que no sirven.
AREA_MINIMA_SENAL_PX = 200  # Contornos más pequeños que esto son ruido de la máscara, no una señal a distancia útil. CALIBRAR CON VIDEO REAL.

# Número de vértices que approxPolyDP debe encontrar en el contorno.
# Las señales definitivas son OCTÁGONOS rojo (PARE) y verde (SIGA) con
# texto blanco y borde oscuro: medidos sobre la imagen de referencia
# (capturas/_ref_senales.png) dan exactamente 8 vértices. El rango
# 6-9 tolera la degradación en video real: a distancia, con desenfoque
# de movimiento o parcialmente tapado, approxPolyDP puede colapsar un
# par de lados (6-7) o añadir uno espurio (9).
VERTICES_SENAL_MIN = 6
VERTICES_SENAL_MAX = 9

# Extensión: área del contorno sobre área de su boundingRect. Un
# octágono regular tiene extensión teórica 0.828 (pierde las cuatro
# esquinas frente al cuadrado que lo circunscribe); medido sobre la
# imagen de referencia da 0.824-0.826, clavado en el valor teórico.
# El rango 0.79-0.92 deja fuera al círculo por abajo y al
# cuadrado/rectángulo lleno (1.0) por arriba. El mínimo está ajustado
# a propósito justo encima de 0.785, la extensión de un círculo: es el
# ÚNICO discriminante fiable contra un círculo del color de una señal,
# porque approxPolyDP le da también 8 vértices y su circularidad
# (0.907) se solapa con la del octágono (0.948). Medido con formas
# sintéticas: círculo 0.785, octágono 0.809-0.826.
EXTENSION_SENAL_MIN = 0.79  # CALIBRAR CON VIDEO REAL.
EXTENSION_SENAL_MAX = 0.92  # CALIBRAR CON VIDEO REAL.

# Relación de aspecto (ancho/alto del boundingRect). Un octágono
# regular visto de frente da 1.0 (medido en la referencia: 1.000-1.002).
# El rango 0.65-1.55 tolera el escorzo cuando la cámara mira la señal
# en ángulo y el recorte parcial por el borde del cuadro, y sigue
# descartando con holgura la franja transversal sobre la que van
# montadas las señales (aspecto de 6 a 16 medido en los videos).
ASPECTO_SENAL_MIN = 0.65  # CALIBRAR CON VIDEO REAL.
ASPECTO_SENAL_MAX = 1.55  # CALIBRAR CON VIDEO REAL.

# Circularidad 4πA/P² (1.0 = círculo perfecto). Un octágono regular da
# ~0.906 teórico; medido en la referencia: 0.910-0.912. Un cuadrado da
# 0.785 y un círculo ~1.0. El rango 0.82-0.97 deja fuera al cuadrado
# por abajo, y por arriba no llega a 1.0 para que un círculo del color
# de una señal no pase. La franja transversal y el ruido, con
# perímetro largo y poca área, caen muy por debajo de 0.82.
CIRCULARIDAD_SENAL_MIN = 0.82  # CALIBRAR CON VIDEO REAL.
CIRCULARIDAD_SENAL_MAX = 0.97  # CALIBRAR CON VIDEO REAL.

# ConfirmadorSenales: una señal solo se reporta como confirmada si
# aparece en al menos CONFIRMAR_N de los últimos CONFIRMAR_M fotogramas
# por color. Evita que un solo fotograma con ruido (o una detección
# real pero fugaz de un cuadrado de prueba con el color equivocado)
# dispare una acción del robot.
CONFIRMAR_M = 5  # CALIBRAR CON VIDEO REAL.
CONFIRMAR_N = 3  # CALIBRAR CON VIDEO REAL.

# Fracción de la altura de la ROI de señales (0 arriba, 1 en
# FILA_CHASIS) a partir de la cual se considera que la señal está lo
# bastante cerca para actuar (en_disparo=True): el centroide de la
# señal debe estar en fila >= Y_DISPARO * altura_roi_senales.
Y_DISPARO = 0.7  # CALIBRAR CON VIDEO REAL.

# ==========================================================================
# CONTROL POR ZONAS
# ==========================================================================
#
# El mBot del docente (ver comunicacion/robot_mbot.py) no acepta
# velocidades: solo 5 comandos discretos sin parámetros (adelante,
# atras, izquierda, derecha, parar), cada uno un pulso de duración fija
# que el firmware autodetiene (100ms avance/retroceso, 30ms giros). No
# hay forma de pedirle "gira un poco más fuerte": la única "magnitud"
# de corrección disponible es CUÁNTOS comandos de giro consecutivos se
# envían antes de volver a avanzar. Por eso el control ya no es un PD
# continuo (KP/KD/KA no tienen sentido sin una magnitud que multiplicar):
# es un control por zonas de error, con una relación giro/avance fija
# por zona.
#
# Tres zonas según |error| (normalizado en [-1, 1], igual que siempre):
# CENTRADO (avanzar sin girar), LEVE (alternar giro/avance) y FUERTE
# (girar varios comandos seguidos sin avanzar). Dos umbrales separan las
# tres franjas:
# |error| < ZONA_CENTRADO              -> centrado
# ZONA_CENTRADO <= |error| < ZONA_FUERTE -> leve
# |error| >= ZONA_FUERTE               -> fuerte
# CALIBRAR CON ROBOT: son estimaciones razonables, deberán ajustarse
# viendo cuánto se desvía el mBot entre correcciones reales.
ZONA_CENTRADO = 0.15  # |error| por debajo de este umbral: centrado, se avanza sin girar.
# |error| por encima de este umbral: desviación fuerte, se giran varios
# comandos seguidos sin avanzar. Entre ZONA_CENTRADO y este valor es la
# zona leve (alterna giro/avance).
# Bajado de 0.5 a 0.38: con 0.5 la línea tenía que estar a media
# anchura del cuadro del centro antes de que el control reaccionara en
# serio, y en una curva cerrada para entonces el robot ya venía
# demasiado abierto para recuperarla. Entrando antes en zona fuerte la
# corrección empieza mientras la curva todavía se puede tomar.
# CALIBRAR CON ROBOT.
ZONA_FUERTE = 0.38

# Histéresis entre zonas: al SALIR de una zona hacia una menos severa
# (p. ej. de FUERTE a LEVE) se exige que |error| baje un margen extra
# por debajo del umbral de entrada, no que apenas lo cruce. Sin esto,
# ruido de detección que oscila justo alrededor de un umbral haría que
# el control alterne de zona (y por lo tanto de plan de giro/avance) en
# cada fotograma. El suavizado exponencial (ALFA_SUAVIZADO) ya atenúa
# el ruido de alta frecuencia; esta histéresis es una segunda defensa
# específica para la frontera entre zonas, que es donde el suavizado
# solo no basta si el error suavizado se queda oscilando justo ahí.
# CALIBRAR CON ROBOT.
MARGEN_HISTERESIS_ZONA = 0.05

GIROS_POR_AVANCE_ZONA_LEVE = 1  # Cuántos comandos de giro se envían antes de volver a avanzar, en zona leve.
AVANCES_POR_GIRO_ZONA_LEVE = 1  # Cuántos comandos de avance se envían antes de volver a girar, en zona leve (relación 1:1 por defecto).
# Cuántos comandos de giro seguidos se envían en zona fuerte antes de
# intercalar un avance.
#
# OJO al contar comandos en vez de tiempo: un pulso de avance dura
# 100ms y uno de giro 30ms, así que un ciclo de 3 giros + 1 avance
# deja al robot 90ms girando contra 100ms avanzando — pasaba MÁS
# tiempo avanzando que girando justo en la zona pensada para corregir
# fuerte, y por eso se pasaba de largo en las curvas cerradas. Con 5
# el reparto queda en 150ms girando contra 100ms avanzando (60%
# girando), que es lo que se espera de esta zona.
# CALIBRAR CON ROBOT: subir a 7 (68% girando) si aún se abre en las
# curvas cerradas; bajar si empieza a sobre-corregir y zigzaguear.
GIROS_CONSECUTIVOS_ZONA_FUERTE = 5

ALFA_SUAVIZADO = 0.4  # Peso del error nuevo en la media exponencial (0-1). Más alto = menos suavizado.

# ComandoRobot.izquierda/derecha ya no son velocidades reales (el mBot
# no las acepta, y el firmware mueve ambos motores del mismo lado a la
# misma magnitud fija tanto para avanzar como para girar: ver
# moveForward/turnLeft/turnRight en arduinoFinal.ino). Aquí son valores
# SIMBÓLICOS que existen solo para que calcular_accion()
# (control/contratos.py, sin cambios) derive la acción discreta
# correcta a partir del signo y la diferencia entre ambos:
# - (SENAL_AVANCE, SENAL_AVANCE) -> diferencia 0 -> AVANZAR.
# - (SENAL_GIRO, 0) -> diferencia = SENAL_GIRO >= DIF_GIRO, mismo signo
#   (ninguno es negativo) -> GIRAR_IZQUIERDA.
# - (0, SENAL_GIRO) -> misma lógica -> GIRAR_DERECHA.
# SalidaMBot solo mira comando.accion (y, para GIRAR_SOBRE_EJE si
# llegara a producirse, el signo de comando.izquierda) para decidir
# qué método de Robot llamar: nunca usa estos números como velocidad.
VEL_MAX = 100  # Límite simbólico de ComandoRobot.izquierda/derecha, heredado del modelo anterior; ya no corresponde a una velocidad real del mBot.
SENAL_AVANCE = 60
SENAL_GIRO = 35

DIF_GIRO = 8  # Diferencia mínima entre ruedas (unidades simbólicas de signo, no de velocidad real) para que calcular_accion() lo reconozca como giro y no como avance recto.

# ==========================================================================
# SALIDA / COMUNICACIÓN
# ==========================================================================

# Frecuencia máxima (Hz) a la que se envía un ComandoRobot al robot.
#
# ES EL ÚNICO CONTROL DE VELOCIDAD QUE EXISTE. El firmware no acepta
# magnitudes: cada comando es un pulso de duración fija que se
# autodetiene (100ms avanzando, 30ms girando). La velocidad efectiva
# del robot es entonces el ciclo de trabajo = duración del pulso /
# periodo de envío. Ni SENAL_AVANCE ni SENAL_GIRO influyen: son
# símbolos para calcular_accion(), no velocidades.
#
# A 15 Hz (periodo 66.7ms) el pulso de avance de 100ms NUNCA alcanza a
# expirar antes del siguiente: el robot avanzaba de forma continua a
# velocidad máxima, sin poder tomar las curvas. A 8 Hz (periodo 125ms)
# quedan 25ms de pausa entre pulsos de avance, ~80% de ciclo de
# trabajo, y el robot avanza más despacio dando tiempo a que la
# corrección de rumbo surta efecto antes de seguir adelante.
#
# CALIBRAR CON ROBOT: si aún va rápido para las curvas, bajar a 6 Hz
# (66ms de pausa, ~60% de ciclo) o 5 Hz (100ms, 50%). Si se vuelve
# demasiado lento o entrecortado, subir hacia 10 Hz (avance continuo
# justo en el límite, sin pausa). Ojo: bajar esta frecuencia también
# espacia los comandos de GIRO, que ya tienen pausa a cualquier valor
# por debajo de 33 Hz; si el problema pasa a ser que gira poco, la
# palanca es GIROS_CONSECUTIVOS_ZONA_FUERTE, no esta.
FRECUENCIA_ENVIO = 8

# Dirección Bluetooth del mBot físico, leída de un .env local (nunca
# hardcodeada ni versionada: cada integrante prueba con su propio robot).
# Ver .env.example para el nombre de la variable.
MAC_MBOT = os.getenv("MAC_MBOT")

# ==========================================================================
# MÁQUINA DE ESTADOS
# ==========================================================================

TIEMPO_PARE = 3.0  # Segundos que el robot permanece detenido en el estado PARE.
TIEMPO_ENFRIAMIENTO = 4.0  # Segundos máximos en REANUDAR ignorando el rojo, incluso si no sale del cuadro.

# Segundos máximos buscando la línea en LINEA_PERDIDA antes de
# detenerse y reportar. No existe un giro sobre el eje (ver
# control/controlador.py:girar_busqueda): buscar ya desplaza al robot
# hacia adelante mientras gira, así que este tiempo también acota
# cuánto puede alejarse buscando antes de rendirse.
TIEMPO_MAX_PERDIDA = 5.0

# ==========================================================================
# SIMULACIÓN (simulador/pista_virtual.py) — no afecta al robot real, solo
# a qué tan exigente es la pista virtual para calibrar el control.
# ==========================================================================

# La latencia total del lazo cerrado (150ms estimados) se reparte en dos
# tramos físicamente distintos, cada uno con su propia cola en
# pista_virtual.py: percepción (captura por WiFi + procesamiento de
# visión, hasta tener un ResultadoLinea) y actuación (Bluetooth +
# firmware, hasta que el comando mueve las ruedas). Aplicar el total a
# cada cola por separado duplicaría el retardo real a 300ms.
#
# CALIBRAR CON VIDEO: son estimaciones. El barrido de latencia (ver
# capturas/reporte_calibracion.md) muestra que el sistema es estable
# hasta ~80ms totales y se degrada abruptamente a partir de ~100ms, así
# que medir la latencia real del pipeline (WiFi + procesamiento +
# Bluetooth) es un requisito de diseño, no solo un ajuste fino: si el
# pipeline real excede ese umbral, ninguna ganancia de control lo
# compensa y hay que reducir la latencia misma (menor resolución,
# menos preprocesamiento, FRECUENCIA_ENVIO más alta).
LATENCIA_PERCEPCION_MS = 120  # Retardo entre que la cámara captura el fotograma y la visión entrega un ResultadoLinea.
LATENCIA_ACTUACION_MS = 30  # Retardo entre que se emite un ComandoRobot y las ruedas realmente lo ejecutan (Bluetooth + firmware).

PASO_SIMULACION_MS = 50  # Paso de tiempo de la simulación, equivalente a unos 20 fotogramas por segundo.

ZONA_MUERTA = 18  # CALIBRAR CON VIDEO (medir en el robot real con una rampa de PWM). Velocidad de rueda por debajo de la cual el motor real no arranca (PWM insuficiente).

TAU_MOTOR = 0.05  # CALIBRAR CON VIDEO. Constante de tiempo (s) del filtro de primer orden que modela la inercia de cada motor.

RUIDO_ERROR = 0.03  # CALIBRAR CON VIDEO. Desviación estándar del ruido gaussiano sumado al error de línea entregado al control.
RUIDO_ANGULO = 0.05  # CALIBRAR CON VIDEO. Desviación estándar del ruido gaussiano sumado al ángulo estimado.
PROB_FRANJA_PERDIDA = 0.05  # CALIBRAR CON VIDEO. Probabilidad de que un fotograma llegue con confianza reducida (una franja menos detectada).
PROB_LINEA_INVALIDA = 0.02  # CALIBRAR CON VIDEO. Probabilidad de que un fotograma llegue con valida=False aunque el robot esté sobre la línea (desenfoque, sombras, franja de una señal).

SEMILLA_SIMULACION = 42  # Semilla fija del generador aleatorio, para que las corridas de calibración sean reproducibles.


def _cargar_calibracion_desde(ruta: str) -> None:
    """Sobrescribe constantes del módulo con valores calibrados desde
    un archivo JSON, si existe.

    Recibe: ruta (str, ruta absoluta a un archivo JSON con pares
        clave/valor; solo se aplican las claves que ya existen como
        variable de este módulo, para no crear parámetros nuevos por
        error de tipeo en el JSON).
    Devuelve: nada, modifica las variables del módulo en su lugar.
    Complejidad: O(1), el archivo tiene un puñado de claves.
    """
    if not os.path.exists(ruta):
        return
    with open(ruta, "r", encoding="utf-8") as archivo:
        valores = json.load(archivo)
    globals().update({clave: valores[clave] for clave in valores if clave in globals()})


def _cargar_calibracion():
    """Aplica, en orden, calibracion_control.json y calibracion.json
    sobre las constantes por defecto de este módulo.

    Recibe: nada. Devuelve: nada.
    Complejidad: O(1).
    """
    _cargar_calibracion_desde(RUTA_CALIBRACION_CONTROL)
    _cargar_calibracion_desde(RUTA_CALIBRACION_VISION)


_cargar_calibracion()
