# Robot Vision

Pipeline de visión clásica para un robot móvil seguidor de línea. No usa redes neuronales, Deep Learning ni modelos preentrenados. La segmentación se basa en OpenCV, HSV, morfología, geometría de contornos y K-Means clásico K=2 para recalibrar el umbral de la línea.

## Instalación en Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Configura `CAMERA_URL` en `.env`. Acepta una URL de cámara IP, un índice local (`0`) o se puede indicar un vídeo local directamente en `--source`.

### Cámara del celular desde el navegador

Inicia el servidor y el pipeline con:

```powershell
python -m src.main --phone-camera
```

El terminal imprimirá la IP y el puerto para abrir desde el celular, conectado a la misma Wi-Fi. En la página pulsa **Iniciar cámara** y permite el acceso. Los JPEG se envían por POST a `/frame`; se conserva el frame más reciente y el pipeline descarta imágenes atrasadas.

Los navegadores solo habilitan `getUserMedia` en orígenes seguros. Por eso `http://<IP-del-PC>:5000` permite comprobar que el servidor responde, pero no permite usar la cámara del celular. Para habilitarla, genera un certificado para la IP local estable del PC con una CA confiable, por ejemplo con [mkcert](https://github.com/FiloSottile/mkcert):

```powershell
mkcert -install
mkcert -cert-file phone-camera-cert.pem -key-file phone-camera-key.pem 192.168.1.20 localhost 127.0.0.1
```

Instala también la CA raíz de mkcert en el teléfono y márcala como confiable para el navegador/sistema. Luego configura en `.env` `PHONE_CAMERA_TLS_CERT=phone-camera-cert.pem` y `PHONE_CAMERA_TLS_KEY=phone-camera-key.pem`, reinicia el comando y abre la dirección `https://` impresa. Sustituye `192.168.1.20` por la IP real del PC. También permite el puerto configurado en el firewall de Windows para la red privada.

Para el robot, configura `BLUETOOTH_MAC` con la MAC real del mBot y verifica que esté emparejado con Windows. `ROBOT_EXECUTOR_PATH` es opcional; por defecto apunta a la carpeta `robotEjecutor/practica-vision-artificial-robotica/master_pc` hermana de este proyecto.

## Ejecución

```powershell
python -m src.main
python -m src.main --source .\videos\ensayo.mp4
python -m src.main --source 0
python -m src.main --phone-camera
python -m src.main --phone-camera --robot
python -m src.main --robot --source http://192.168.1.10:8080/video
python -m src.main --robot --bluetooth-mac 00:1B:10:21:2C:1B --source http://192.168.1.10:8080/video
```

La ventana muestra la imagen, la máscara de línea, la máscara de señales y la vista anotada. Pulsa `q` o `Esc` para salir. `c` abre el calibrador; ajusta HSV/umbral y pulsa `s` para escribir `calibration.json`.

Para calibrar antes de iniciar el seguimiento:

```powershell
python -m src.main --calibrate --source .\videos\ensayo.mp4
```

## Pipeline

La captura corre en un hilo y conserva el fotograma más reciente. El preprocesado orienta y escala a 280 px, aplica un Gaussiano leve, elimina el tercio inferior y extrae ROI separadas. El seguidor calcula error/confianza por cuatro franjas y un ángulo de anticipación; K-Means K=2 recalibra periódicamente el umbral. La detección PARE/SIGA filtra máscaras HSV por morfología, área, polígono de 7-9 vértices, extensión y circularidad, y confirma detecciones en 3 de 5 frames al cruzar el disparador.

El controlador genera velocidades diferenciales lógicas acotadas a 0-255 y gestiona `SEGUIR_LÍNEA`, `PARE`, `REANUDAR`, `SIGA` y `LÍNEA_PERDIDA`. Con `--robot`, `src/control/bluetooth_executor.py` carga directamente el `Robot.py` de `ROBOT_EXECUTOR_PATH`, abre RFCOMM y llama a sus métodos `adelante()`, `atras()`, `izquierda()`, `derecha()` y `parar()` en un hilo independiente. El envío periódico permite mantener el movimiento aunque el firmware pare los motores al terminar cada pulso; detenerse o cerrar el programa envía `x`.

**Límite del protocolo del executor:** los comandos Bluetooth solo son `w/s/a/d/x`. El firmware actual fija velocidad 150, mueve adelante/atrás 100 ms o gira 30 ms y luego detiene motores. No acepta PWM ni los valores `left/right`; el adaptador reduce cada par a avance, giro, retroceso o parada y aproxima la intensidad con el intervalo entre pulsos. Por tanto, la dirección es funcional pero la velocidad diferencial no se conserva continuamente. Para control proporcional de verdad habría que ampliar el protocolo y firmware con un comando de velocidad por motor; el firmware no se modifica aquí.

Asegura el robot sobre un soporte durante las primeras pruebas. El inicio completo es opt-in mediante `--robot`; sin esa opción solo corre la visión y no establece Bluetooth.

Todos los parámetros operativos están en `.env.example`; los rangos HSV calibrados se guardan aparte en JSON.
