# CLAUDE.md — Reglas del proyecto

Lee también `README.md`: contiene la arquitectura y el pipeline completo. Este archivo define las reglas que debes respetar siempre.

## Contexto
Proyecto universitario (Visión Artificial, Universidad de Caldas). Es el código de la laptop de un robot seguidor de línea que reconoce octágonos PARE (rojo) y SIGA (verde). El video llega desde un teléfono por WiFi/IP. La comunicación Bluetooth con el Arduino la hace otro integrante: aquí solo existe la interfaz `SalidaRobot`.

## Restricción principal: solo técnicas vistas en la materia
El equipo debe poder explicar cada etapa en un póster. **Solo puedes usar lo siguiente:**

**OpenCV permitido:**
- **Color:** `cvtColor` (GRAY, HSV, LAB, RGB)
- **Geometría:** `resize`, `rotate`
- **Suavizado:** `GaussianBlur`
- **Umbralización:** `threshold` (BINARY, BINARY_INV)
- **Segmentación por color:** `inRange`
- **Operaciones lógicas y aritméticas:** `bitwise_and`, `bitwise_or`, `bitwise_not`, `absdiff`, `add`, `subtract`
- **Morfología:** `erode`, `dilate`, `morphologyEx` (OPEN, CLOSE)
- **Bordes:** `Canny`
- **Contornos:** `findContours` (RETR_EXTERNAL), `contourArea`, `arcLength`, `approxPolyDP`, `boundingRect`, `moments` (para el centroide)
- **Dibujo, ventanas y trackbars:** `putText`, `rectangle`, `line`, `circle`, `drawContours`, `imshow`, `namedWindow`, `createTrackbar`, `getTrackbarPos`, `waitKey`
- **Captura:** `VideoCapture`, `imwrite`

**Otros permitidos:**
- **NumPy** para operaciones con matrices: slicing de ROI, sumas por columna, medias, `np.where`.
- **`sklearn.cluster.KMeans`** en su modalidad básica, como en el cuaderno de clase.

**PROHIBIDO (no usar aunque parezca mejor):**
- `HoughLines`, `HoughLinesP`, `HoughCircles`
- `CascadeClassifier` y el módulo `cv2.dnn`
- Cualquier red neuronal, modelo preentrenado o servicio de IA
- `adaptiveThreshold`, el flag `THRESH_OTSU`, `fitLine`, `minAreaRect`, `convexHull`, `matchShapes`: **no se usan salvo que el usuario lo autorice explícitamente**, porque no están en la lista del enunciado.
- Librerías de visión adicionales (scikit-image, etc.)

Si una tarea parece requerir algo fuera de esta lista, **detente y pregúntame** antes de implementarlo.

## Estilo de código (igual al del curso)
- Python 3.12, con **nombres de variables, funciones y comentarios en español** (p. ej. `detectar_linea`, `mascara_roja`, `umbral_bajo`).
- Funciones cortas, con docstring en español que explique **qué hace, qué recibe y qué devuelve**.
- En los módulos de visión, el docstring incluye una línea `Complejidad: O(...)` por fotograma (se usa en el póster).
- Sin sobre-ingeniería: nada de clases abstractas innecesarias, decoradores complejos ni patrones rebuscados. Debe poder explicarse en una exposición.
- **Ningún número mágico en el código:** todo parámetro ajustable vive en `config.py`, con un comentario que lo explique.
- Las funciones de visión son **puras**: reciben una imagen y parámetros y devuelven resultados. No abren ventanas ni leen trackbars; eso se hace solo en `main.py`, `calibrar.py` y `utils/visualizacion.py`.

## Forma de trabajar
- Implementa **solo la fase que te pido en el prompt**. No adelantes fases.
- No modifiques archivos de fases anteriores salvo que sea necesario; si lo haces, explica por qué.
- Al terminar cada fase:
  1. Resume qué archivos creaste o modificaste.
  2. Da el comando exacto para probarlo.
  3. Lista qué parámetros de `config.py` habrá que calibrar con los videos.
- Si no tienes un video para probar, crea una prueba mínima con una imagen sintética generada con NumPy (línea negra sobre fondo blanco, octágono rojo o verde dibujado con `fillPoly`).
- No instales paquetes fuera de `requirements.txt` sin preguntar.
