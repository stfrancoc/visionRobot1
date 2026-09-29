# Checklist de pruebas con el robot real

Guía corta para seguir EN ORDEN. No saltar pasos: cada uno depura una
capa antes de que la siguiente dependa de ella con el robot en
movimiento.

## 0.1 Conectar el teléfono al PC (video por WiFi)

1. Instalar en el teléfono Android la app **IP Webcam** (la usada como
   referencia: nuestro código espera una URL tipo
   `http://IP:PUERTO/video`, que es el formato que esta app expone).
2. Conectar el teléfono a la **misma red WiFi** que el PC (no datos
   móviles, no una red de invitados que aísle dispositivos entre sí:
   si el PC no puede hacer ping a la IP del teléfono, tampoco va a
   poder leer el stream).
3. Antes de correr nuestro código: abrir la app, entrar a
   "Configuración de video" y bajar la resolución a la más baja que
   siga siendo legible para detectar la línea (p. ej. 640x480 o menor,
   no 1080p). Cada milisegundo de latencia cuenta contra el
   presupuesto de 80-90ms encontrado en la calibración del simulador;
   una resolución más alta solo agrega latencia de captura y
   preprocesamiento sin mejorar la detección (la ROI ya se reduce a
   `ANCHO_PROCESO` de todas formas).
4. Presionar "Iniciar servidor" en la app. La app muestra en pantalla
   una URL como `http://192.168.1.XX:8080`.
5. **Verificar el stream ANTES de tocar nuestro código**: abrir
   `http://<ip-mostrada>:8080/video` en un navegador del PC. Debe
   verse el video en vivo directamente en el navegador. Si no carga
   ahí, tampoco va a cargar en `FuenteVideo` — no perder tiempo
   depurando Python todavía.
6. Poner esa URL en el proyecto, de una de estas dos formas:
   - En `.env` (copiado de `.env.example` si no existe), variable
     `CAMERA_URL=http://<ip-telefono>:8080/video`.
   - O pasarla directo por línea de comandos con `--url
     http://<ip-telefono>:8080/video` (tiene prioridad sobre `.env`
     si se usa `--url` explícitamente).

## 0.2 Conectar el PC al robot (Bluetooth)

El procedimiento exacto de emparejado depende del sistema operativo
del PC:

- **Windows**: Configuración → Bluetooth y otros dispositivos →
  Agregar dispositivo → Bluetooth. Encender el mBot y ponerlo en modo
  de emparejamiento (según el firmware del docente, normalmente basta
  con encenderlo). Seleccionarlo en la lista y completar el
  emparejamiento (puede pedir un PIN; probar `0000` o `1234` si lo
  pide).
- **Linux**: `bluetoothctl` → `scan on` → anotar la MAC que aparece
  con el nombre del mBot → `pair <MAC>` → `trust <MAC>` → `scan off`.
- **macOS**: Preferencias del Sistema → Bluetooth → esperar a que
  aparezca el mBot en la lista → Conectar.

Una vez emparejado, obtener la dirección MAC del robot:
- Windows: en la lista de dispositivos Bluetooth, propiedades del
  mBot emparejado muestran la dirección.
- Linux: `bluetoothctl devices` lista `Device <MAC> <nombre>`.
- macOS: Preferencias del Sistema → Bluetooth, ⌥ (Option) + clic sobre
  el dispositivo muestra la dirección.

Poner esa MAC en `.env` (nunca hardcodeada en el código ni en
`config.py`, y nunca commiteada: `.env` está en `.gitignore`):
```
MAC_MBOT=<mac-del-robot>
```
`comunicacion/salida_mbot.py` la lee de `config.MAC_MBOT`.

**Antes de conectar por Bluetooth, confirmar que el robot está
encendido y con las baterías cargadas.** Con carga baja los motores
giran menos por pulso que con carga llena: si se calibra
`ZONA_FUERTE`/`GIROS_CONSECUTIVOS_ZONA_FUERTE` (paso 6 más abajo) con
batería baja, esos valores quedan mal calibrados para cuando el robot
tenga batería llena, y viceversa. Calibrar siempre con batería en un
estado similar al que tendrá durante la prueba real.

**Cómo reconocer un emparejamiento faltante o roto**: al llamar a
`SalidaMBot().conectar()` (lo hace `main.py` automáticamente con
`--salida mbot`), si el emparejamiento no está hecho o el robot está
apagado/fuera de rango, `Robot.conectar()` (en
`comunicacion/robot_mbot.py`) falla al conectar el socket — el
mensaje exacto de la excepción depende del sistema operativo (típicamente
un `OSError`/`ConnectionRefusedError`/`TimeoutError` de socket, con
"Conectando a `<mac>`..." impreso justo antes y sin el "Conexión
establecida" que sigue si funciona). Si en cambio el error es
`RuntimeError("El robot no está conectado")`, no es un problema de
emparejamiento: significa que se llamó a un comando (`adelante()`,
etc.) sin haber llamado antes a `conectar()` — revisar el orden de
llamadas, no el Bluetooth.

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

## Si algo falla

**1. No llega imagen / la ventana no muestra video**
- Primero: ¿el stream carga en el navegador (paso 0.1.5)? Si no,
  el problema es la app/WiFi, no nuestro código.
- ¿El teléfono sigue en la misma red? Algunas redes WiFi reasignan IP
  al reconectar; volver a mirar la IP que muestra IP Webcam y
  actualizar `.env`/`--url` si cambió.
- ¿Se cerró/bloqueó la pantalla del teléfono? Algunas apps de cámara
  IP dejan de transmitir con la pantalla apagada; revisar los ajustes
  de energía de la app.

**2. El robot no responde a los comandos (o `conectar()` falla)**
- ¿Está encendido y con luz de Bluetooth activa? Sin eso no hay nada
  que emparejar ni a qué conectarse.
- ¿El emparejamiento sigue vigente? Algunos sistemas operativos
  "olvidan" el emparejamiento si el dispositivo estuvo mucho tiempo
  sin conectarse; volver a emparejar desde cero (ver 0.2) si el error
  de conexión persiste.
- ¿Otro proceso tiene el puerto Bluetooth ocupado? Solo una conexión
  RFCOMM a la vez suele ser posible; cerrar cualquier otra app/consola
  que se haya conectado antes al mismo mBot (incluida una ejecución
  anterior de nuestro propio script que no haya cerrado bien: revisar
  que no quede un proceso Python colgado).

**3. El robot se mueve pero se sale de la pista de inmediato**
- Volver al paso 4 (verificación de signo en modo "comandos"): es
  exactamente el síntoma del bug de signo que ya se encontró una vez
  en `_senal_giro`. Confirmar que error negativo (línea a la
  izquierda) da `GIRAR_IZQUIERDA` y viceversa ANTES de seguir en modo
  completo.
- Si el signo ya está bien: revisar que `FILA_CHASIS`/las ROI (pasos 2
  y 3) se hayan calibrado con la pista real y no se estén usando los
  valores por defecto de los videos de ensayo (una pista con otra
  iluminación o encuadre puede hacer que la ROI capture parte del
  chasis o quede corta).
