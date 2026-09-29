# Robot Vision - Cerebro de visión para robot seguidor de línea

Este proyecto define una base modular para un sistema de visión artificial clásico en Python para un robot móvil autónomo.

## Objetivo inicial

- Capturar video desde un celular conectado por Wi‑Fi.
- Probar una etapa de segmentación con K‑Means por cuadro.
- Dejar una arquitectura lista para integrar:
  - seguimiento de línea,
  - detección de señales PARE/SIGA,
  - control del robot.

## Estructura

- `src/camera/`: captura y gestión del flujo de video.
- `src/processing/`: módulos de segmentación, detección y análisis.
- `src/utils/`: utilidades auxiliares.
- `src/config.py`: configuración centralizada desde `.env`.

## Instalación

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
```

## Ejecución

```bash
python src/main.py
```

## Configuración de la cámara

Ajusta la URL de la cámara en `.env`.

Ejemplos compatibles:

- IP Webcam: `http://192.168.1.10:8080/video`
- MJPEG stream: `http://192.168.1.10:8080/videofeed` o similar

## Nota de arquitectura

El módulo de K‑Means es un prototipo de prueba de concepto. Más adelante será reemplazado o combinado con HSV + morfología para detectar la línea y las señales.

# Reto 1 · Cerebro de un robot seguidor de línea

**Visión Artificial – Universidad de Caldas**
Módulo de la laptop: recibe el video de la cámara del teléfono, detecta la línea y las señales PARE/SIGA, decide el movimiento y entrega los comandos al módulo de comunicación (a cargo de otro integrante del equipo).

> Restricción del reto: **sin redes neuronales, sin deep learning, sin modelos entrenados, sin cascadas Haar, sin servicios de IA externos.** Solo técnicas vistas en la materia (ver sección *Técnicas permitidas*).

---

## 1. Arquitectura del sistema

```
Teléfono (cámara)  --WiFi/IP-->  Laptop (este proyecto)  --Bluetooth-->  Arduino (motores)
                                   │
                                   ├─ Captura (hilo, último fotograma)
                                   ├─ Preprocesamiento (resize, rotación, blur, recorte del chasis)
                                   ├─ Rama LÍNEA   → error de posición + ángulo
                                   ├─ Rama SEÑALES → PARE / SIGA / nada (+ distancia por posición en y)
                                   ├─ Máquina de estados
                                   ├─ Controlador PD → velocidad izquierda / derecha
                                   └─ Salida (interfaz para el módulo Bluetooth del compañero)
```

La laptop **no** implementa el protocolo Bluetooth. Solo entrega comandos a través de una interfaz (`comunicacion/salida.py`) que el compañero conecta con su implementación.

## 2. Condiciones observadas en los videos de ensayo

Estas observaciones guían los parámetros por defecto:

- **Video vertical.** La cámara del teléfono va montada sobre el robot y mira hacia adelante y abajo.
- **El chasis del robot ocupa aproximadamente el 35–40 % inferior del cuadro.** Se ven el chasis cian, el sensor ultrasónico y baterías verdes y naranjas. **Esa zona se descarta siempre**, porque las baterías verdes generarían falsos "SIGA".
- **La línea es gris oscuro o negra**, sobre un piso blanco o gris claro. Hay sombras del robot y del entorno, y la línea se ve en perspectiva (se estrecha a lo lejos).
- **Las señales están en el piso, sobre la línea.** Hay una franja negra transversal debajo de cada una. Se ven achatadas por la perspectiva.
- **Las señales definitivas son octágonos rojo y verde** con texto blanco ("PARE" / "SIGA") y borde oscuro.
- **Hay desenfoque de movimiento** en varios fotogramas.

## 3. Pipeline de visión

### 3.1 Preprocesamiento
1. Rotación si el stream llega girado (`cv2.rotate`).
2. Redimensionado a un ancho fijo (≈ 240–320 px) para garantizar el tiempo real.
3. Filtro gaussiano leve.
4. **Recorte del chasis:** se descarta todo lo que esté por debajo de la fila `FILA_CHASIS`.

### 3.2 Detección de la línea (franjas horizontales)
1. La ROI de la línea es la zona justo encima del chasis. Se divide en `N_FRANJAS` franjas horizontales.
2. Máscara de "oscuridad": escala de grises → umbral inverso → apertura y cierre.
   - El umbral se **recalibra periódicamente con K-Means (K=2)** sobre una submuestra de píxeles de la ROI. Los dos centroides corresponden a "línea" y "piso", y el umbral es su punto medio.
3. En cada franja se calcula la **proyección por columnas** (suma de píxeles blancos por columna) y se buscan los tramos continuos.
   - **Selección voraz:** se elige el tramo más cercano a la posición anterior de la línea.
   - Se **descartan los tramos demasiado anchos** (franja transversal de las señales o cruces).
4. Salidas del módulo:
   - `error`: desplazamiento normalizado de la franja cercana respecto al centro, en [-1, 1].
   - `angulo`: diferencia entre el centro de la franja lejana y el de la cercana.
   - `confianza`: número de franjas válidas.

### 3.3 Detección de señales
1. Conversión a HSV. Máscaras de color:
   - **Rojo:** dos rangos, porque el matiz da la vuelta (0–10 y 170–179).
   - **Verde:** H ≈ 55–85. **No se amplía más allá de 85**, para no confundirlo con el cian del chasis (≈ 90–95).
2. Apertura y cierre. El cierre también tapa los huecos que dejan las letras blancas.
3. Contornos externos (`RETR_EXTERNAL`). Los filtros se aplican en cascada:
   - Área mínima.
   - `approxPolyDP` con **7 a 9 vértices** (tolerancia a la perspectiva y al desenfoque).
   - **Extensión** = área del contorno / área del `boundingRect`. En un octágono regular vale ≈ 0.83, y **no cambia al achatarse por perspectiva**, a diferencia de la relación de aspecto.
   - Circularidad 4πA/P² como filtro auxiliar, con rango amplio.
4. **Confirmación temporal:** una señal solo se acepta si se detecta en `N` de los últimos `M` fotogramas.
5. **Distancia por posición:** como la señal está en el piso, cuanto más abajo aparece su centroide, más cerca está. El robot actúa cuando el centroide cruza la **línea de disparo** `Y_DISPARO`.

### 3.4 Máquina de estados

| Estado | Comportamiento | Transición |
|---|---|---|
| `SEGUIR_LINEA` | Control PD sobre la línea | Rojo confirmado bajo `Y_DISPARO` → `PARE`; línea perdida → `LINEA_PERDIDA` |
| `PARE` | Motores detenidos durante `TIEMPO_PARE` segundos | Fin del tiempo → `REANUDAR` |
| `REANUDAR` | Sigue la línea **ignorando el rojo** | El rojo sale del cuadro o pasa `TIEMPO_ENFRIAMIENTO` → `SEGUIR_LINEA` |
| `SIGA` | Registra la señal y continúa | Inmediato → `SEGUIR_LINEA` |
| `LINEA_PERDIDA` | Gira hacia el lado del último error conocido | Línea recuperada → `SEGUIR_LINEA`; tiempo límite → detenerse |

### 3.5 Control
- Control **PD**: `giro = KP·error + KD·Δerror + KA·angulo`, con el error suavizado mediante una media exponencial.
- La velocidad base se reduce cuando |error| o |ángulo| son grandes (curvas).
- Salida diferencial: `izq = v + giro`, `der = v − giro`, recortadas a `[-VEL_MAX, VEL_MAX]`.

## 4. Contrato con el módulo de comunicación

La laptop entrega comandos mediante esta interfaz (`comunicacion/salida.py`):

```python
class SalidaRobot:
    def enviar(self, izquierda: int, derecha: int, estado: str) -> None: ...
    def detener(self) -> None: ...
    def cerrar(self) -> None: ...
```

- `izquierda` y `derecha` son enteros en `[-VEL_MAX, VEL_MAX]`; el signo indica el sentido de giro de cada rueda.
- `enviar` se llama a una frecuencia fija (`FRECUENCIA_ENVIO`, por defecto 15 Hz).
- Hay dos implementaciones incluidas: `SalidaConsola` (imprime los comandos) y `SalidaNula` (no hace nada). El compañero agrega `SalidaBluetooth` con el mismo método.
- Se recomienda que el Arduino tenga un *watchdog*: si no recibe comandos en ~400 ms, detiene los motores.
- `SalidaMBot` (en `comunicacion/salida_mbot.py`) envuelve la clase `Robot` que entrega el docente para el firmware Bluetooth del mBot (repositorio [`practica-vision-artificial-robotica`](https://github.com/stfrancoc/practica-vision-artificial-robotica), carpeta `master_pc/Robot.py`). Ese código no es un fork ni se reorganizó este repositorio hacia su estructura: es solo la referencia del firmware/protocolo Bluetooth, usada como implementación de `SalidaRobot`.
  - `comunicacion/robot_mbot.py` es una **copia sin modificar** de `Robot.py`, tomada el 2026-09-28. Se copió (en vez de importarse desde el repositorio clonado del docente) porque ese repositorio se clona solo como referencia local y no está versionado en este proyecto (ver `.gitignore`).

## 4.1 Modelo real de comandos del mBot (según `Robot.py` y `arduinoFinal.ino`)

El robot del docente **no acepta velocidades ni magnitudes**: son 5 comandos discretos sin parámetros (`adelante`, `atras`, `izquierda`, `derecha`, `parar`), y cada uno es un **pulso de duración fija que se autodetiene** en el firmware (100 ms para avance/retroceso, 30 ms para los giros) — no hay control de velocidad desde Python. Además, `izquierda()`/`derecha()` mueven **ambos motores en el mismo sentido**: son giros de radio amplio, no giros sobre el propio eje. `control/controlador.py` y `control/estados.py` están adaptados a este modelo (control por zonas de error en vez de una magnitud continua de corrección); ver los comentarios `CALIBRAR CON ROBOT` en `config.py` para los parámetros que solo se pueden fijar con el robot físico conectado.

## 5. Estructura del proyecto

```
reto-seguidor-linea/
├── README.md
├── CLAUDE.md                 # reglas para Claude Code
├── requirements.txt
├── config.py                 # TODOS los parámetros ajustables
├── main.py                   # punto de entrada
├── calibrar.py               # herramienta de calibración con trackbars
├── vision/
│   ├── captura.py            # fuente de video (archivo / URL / cámara) con hilo
│   ├── preprocesamiento.py
│   ├── umbral_kmeans.py
│   ├── linea.py
│   └── senales.py
├── control/
│   ├── controlador.py        # PD
│   └── estados.py            # máquina de estados
├── comunicacion/
│   └── salida.py             # interfaz + SalidaConsola + SalidaNula
├── utils/
│   ├── visualizacion.py      # mosaico de depuración
│   └── metricas.py           # FPS, latencia, registro de eventos
├── videos/                   # videos de ensayo (no se suben al repositorio)
└── capturas/                 # imágenes exportadas para el póster
```

## 6. Instalación

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Dependencias: `opencv-python`, `numpy` y `scikit-learn` (K-Means, igual que en el cuaderno de clase).

## 7. Uso

```bash
# Con un video de ensayo (modo desarrollo)
python main.py --video videos/ensayo1.mp4 --debug

# Con el stream del teléfono (p. ej. app IP Webcam)
python main.py --url http://192.168.1.50:8080/video --debug

# Con una cámara local
python main.py --camara 0

# Herramienta de calibración
python calibrar.py --video videos/ensayo1.mp4
```

Teclas en modo `--debug`:

| Tecla | Acción |
|---|---|
| `q` / `Esc` | Salir |
| `Espacio` | Pausar / reanudar |
| `d` | Avanzar un fotograma (en pausa) |
| `s` | Guardar el mosaico actual en `capturas/` |

## 8. Técnicas permitidas (según el enunciado)

Operaciones lógicas y aritméticas · espacios de color RGB/HSV/CIELab · ROI · redimensionado y rotación · umbralización · segmentación por color · K-Means básico · erosión, dilatación, apertura y cierre · suavizado · Canny · contornos · formas geométricas simples · área, perímetro, centroide (momentos), aproximación poligonal y relación de aspecto.

**No se usan:** Hough, cascadas Haar, el módulo `cv2.dnn`, modelos entrenados ni ninguna función que detecte automáticamente la línea o las señales.

## 9. Relación con Análisis y Diseño de Algoritmos

- **Complejidad por fotograma:** cada etapa es O(W·H) y K-Means es O(n·k·i). Esto justifica el redimensionado, la ROI y ejecutar K-Means solo cada `PERIODO_KMEANS` fotogramas y sobre una submuestra.
- **Estrategia voraz:** en cada franja se elige el tramo más cercano a la posición anterior de la línea.
- **Máquina de estados finitos:** formaliza las decisiones del robot.

## 10. Criterios de la competencia que atiende cada módulo

| Criterio | Módulo |
|---|---|
| Tiempo total | Control PD con anticipación y velocidad adaptativa |
| Cumplimiento de PARE | `senales.py` + línea de disparo + estado `PARE` |
| Cumplimiento de SIGA | `senales.py` + estado `SIGA` |
| Descarrilamientos | Franjas + descarte de tramos anchos + selección voraz |
| Recuperación de la trayectoria | Estado `LINEA_PERDIDA` con memoria del último error |
