# Checklist de pruebas con el robot real

Guía corta para seguir EN ORDEN. No saltar pasos: cada uno depura una
capa antes de que la siguiente dependa de ella con el robot en
movimiento.

## 1. Conectar el teléfono y verificar la imagen

- Conectar el teléfono a la misma red que la laptop, anotar la URL del
  stream (p. ej. IP Webcam) y ponerla en `.env` como `CAMERA_URL`, o
  pasarla directo con `--url`.
- Verificar que llega imagen:
  ```
  python main.py --url http://<ip-telefono>:8080/video --salida nula --etapa vision --debug
  ```
- Medir la latencia real de captura: el mosaico y el CSV
  (`capturas/metricas_fotogramas.csv`, columna `latencia_captura_s`)
  ya la reportan. Con una fuente en vivo, esa latencia es cuánto
  tiempo pasó entre que el hilo lector recibió el fotograma y que se
  usó (ver `vision/captura.py:latencia_captura_s`) — si es alta y
  creciente, el WiFi no está entregando a tiempo.
- Confirmar la rotación: si la imagen se ve acostada, ajustar
  `ROTACION` en `config.py` (0/90/180/270).

## 2. Calibrar FILA_CHASIS y las ROI con la pista real

- Con el robot ya sobre la pista (quieto), correr:
  ```
  python calibrar.py --video videos/correctos/video1.mp4
  ```
  o, mejor, apuntando directo a la URL del teléfono si ya se verificó
  el paso 1 (calibrar.py también acepta `--video` con una URL, aunque
  el nombre del argumento diga video).
- Mover el trackbar `FILA_CHASIS x100` hasta que la línea roja quede
  justo antes de donde empieza el chasis/sensor ultrasónico (no las
  aletas: el sensor puede aparecer antes, ver el comentario en
  `config.py:FILA_CHASIS`).
- Ajustar `ROI_LINEA_INI/FIN` y `ROI_SENALES_INI/FIN` con la pista real
  a la vista, no solo con los videos de ensayo.
- Presionar `g` para guardar en `calibracion.json`. `config.py` lo
  carga automáticamente la próxima vez que se importe (no hace falta
  reiniciar nada más que el script que lo use).

## 3. Calibrar los HSV con las señales impresas

- Con las señales PARE/SIGA reales (impresas, no los cuadrados de los
  videos de ensayo) puestas frente a la cámara, en el mismo
  `calibrar.py`.
- Ajustar los trackbars de rojo (dos rangos: bajo y alto, porque el
  matiz rojo da la vuelta al 0) y de verde hasta que la máscara
  correspondiente marque solo la señal, no el fondo ni el chasis.
- Presionar `g` de nuevo para guardar (sobrescribe `calibracion.json`
  con los nuevos valores; los de ROI del paso 2 se conservan porque se
  guardan todos juntos).

## 4. Verificar el signo en modo "comandos" — LA MÁS IMPORTANTE

- Sin el robot conectado por Bluetooth todavía:
  ```
  python main.py --url http://<ip-telefono>:8080/video --salida consola --etapa comandos --debug
  ```
- Colocar la cámara/robot de forma que la línea quede claramente a la
  DERECHA del centro del cuadro: la consola y el mosaico deben mostrar
  `accion=GIRAR_DERECHA`.
- Colocarla con la línea a la IZQUIERDA: debe mostrar
  `accion=GIRAR_IZQUIERDA`.
- Si el signo está invertido (gira hacia el lado contrario a la
  línea), el robot se sale de la pista de inmediato en cuanto se
  prueba en modo completo. Ya se encontró y corrigió una vez un bug
  exactamente así en `control/controlador.py:_senal_giro` (los dos
  `return` estaban cambiados) — si algo vuelve a fallar aquí, revisar
  primero ese método y la convención documentada en
  `control/contratos.py:calcular_accion`.
- NO seguir al paso 5 hasta confirmar esto en ambos sentidos.

## 5. Medir cuántos comandos por segundo tolera el robot

Con el robot ya conectado por Bluetooth (`comunicacion/salida_mbot.py`):
```
python -m pruebas.medir_robot
```
Del menú, en este orden:
- `medir_comandos_por_segundo`: cuántos comandos/segundo acepta antes
  de saturarse.
- `medir_tiempo_de_bloqueo`: cuánto bloquea cada llamada a `enviar()`
  (se esperaba ~100ms por el `time.sleep(0.1)` de
  `comunicacion/robot_mbot.py`, pero hay que confirmarlo).
- `medir_sostenimiento_de_movimiento`: la más importante de las
  cuatro — si mandar el mismo comando repetido sostiene el movimiento
  o el robot pulsa y se detiene entre comandos (el firmware autodetiene
  cada pulso a los 100ms/30ms; esto dice si hay que reenviar más
  seguido que eso para que no se note el corte).

Cada medición pide confirmación explícita (`s`/N) antes de mover el
robot, y tiene parada de emergencia en el `finally`.

## 6. Medir avance y giro por comando

Del mismo menú de `pruebas/medir_robot.py`:
- `medir_avance_y_giro_por_comando`: cuánto avanza con un solo
  `adelante()`/`atras()` y cuánto gira con un solo
  `izquierda()`/`derecha()`.
- Estos números son los que hay que usar para ajustar
  `ZONA_CENTRADO`, `ZONA_FUERTE`, `GIROS_CONSECUTIVOS_ZONA_FUERTE`,
  `GIROS_POR_AVANCE_ZONA_LEVE`/`AVANCES_POR_GIRO_ZONA_LEVE` en
  `config.py` (todos marcados `CALIBRAR CON ROBOT`): si un solo giro
  desvía más de lo que el error típico necesita corregir, el robot
  va a sobre-corregir y zigzaguear.

## 7. Recién entonces: modo completo, a velocidad baja

```
python main.py --url http://<ip-telefono>:8080/video --salida mbot --etapa completo --debug
```
- El robot arranca DETENIDO: main.py no llama a `salida.enviar()` ni
  una sola vez hasta presionar `i` en la ventana. Confirmar en
  consola el mensaje `[main] --etapa completo con --salida mbot: el
  robot queda DETENIDO...` antes de acercarse al robot.
- Tener la mano cerca del robot (o de la fuente de alimentación) para
  poder detenerlo manualmente si algo sale mal.
- Presionar `q`/Esc en cualquier momento fuerza `salida.detener()` en
  el `finally` antes de cerrar.
