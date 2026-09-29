# Reporte de calibración — control de movimiento

Rama `feature/control-movimiento`. Resume el trabajo de calibración con
`simulador/pista_virtual.py` y `simulador/calibrar_ganancias.py`: qué se
encontró, qué se corrigió, por qué se agregó el estado `REALINEANDO`, y
qué queda pendiente de calibrar con video real antes de confiar en estos
números.

## 1. Umbral de latencia: requisito de diseño, no un detalle de ajuste

Con las ganancias finales (KP=10, KD=15, KA=15) y todo lo demás igual
(zona muerta, inercia de motor, ruido de detección), se barrió la
latencia total del lazo cerrado (percepción + actuación) mantenendo la
misma proporción 80/20 entre ambos tramos:

| Latencia total | % tiempo en seguimiento normal | error medio |
|---|---|---|
| 0–90 ms | 94.8% (estable) | 0.070 |
| 100–120 ms | 67.9% | 0.804 |
| 150 ms | 58.1% | 0.774 |

La transición es abrupta, no gradual: el sistema es estable en un rango
amplio (0 a ~90ms) y se degrada bruscamente al cruzar los 100ms. Esto
**no es un problema de sintonía de ganancias** — se probaron 364
combinaciones de KP/KD/KA en cada punto de latencia y el patrón se
repite para todas. Es una propiedad del lazo cerrado: por encima de ese
umbral, la información con la que el control decide ya está demasiado
desactualizada respecto al estado real del robot, y cualquier
corrección basada en ella llega tarde.

**Por qué es un requisito de diseño para el pipeline de visión:** la
latencia total observada en el robot real (captura de la cámara del
teléfono + transmisión WiFi + todo el procesamiento de
`vision/detectar_linea.py` + transmisión Bluetooth + tiempo de reacción
del firmware) debe medirse y mantenerse por debajo de ~90-100ms. Si el
pipeline real la excede, **ninguna ganancia de control puede
compensarlo**: hay que atacar la latencia directamente (bajar la
resolución de captura, simplificar el preprocesamiento, subir
`FRECUENCIA_ENVIO`, etc.), no seguir ajustando KP/KD/KA.

## 2. Bugs encontrados y corregidos, con su impacto en el robot real

### 2.1. Término derivativo espurio con dt=0

**El bug:** `control/controlador.py` calculaba
`delta_error = (error_actual - error_anterior) / dt`. En la primera
llamada tras crear `ControladorPD()` (arranque del programa) o tras
`reiniciar()` (al salir de `PARE`, ver `control/estados.py`), no hay un
`dt` real todavía, y dividir por un `dt` casi nulo amplifica cualquier
error, incluso pequeño, por un factor de hasta 1000×.

**Impacto en el robot real:** en el primer arranque del programa, o
**inmediatamente después de cada parada en un octágono PARE**, el
primer error de línea detectado (por más pequeño que fuera) se habría
multiplicado enormemente, saturando ambas ruedas a velocidad máxima en
direcciones opuestas durante un instante. En la simulación ideal (sin
ruido) nunca se manifestaba porque el primer error era exactamente 0;
con ruido de detección sí, porque el primer error casi nunca es
exactamente cero.

**Fix:** si `dt` no supera un umbral mínimo (`DT_MINIMO`), se omite el
término derivativo en vez de inventar una tasa de cambio a partir de un
`dt` artificial.

### 2.2. Zona muerta binaria encadenaba salidas de pista

**El bug:** el modelo original de motor anulaba a 0 cualquier velocidad
ordenada por debajo de un umbral (zona muerta), de forma binaria. Si el
control pedía, por ejemplo, 5 en una rueda y 77 en la otra, la rueda de
5 se anulaba a 0 mientras la otra seguía a 77: una diferencia de rueda
enorme que el control **nunca ordenó**, suficiente para sacar al robot
de la pista y reiniciar el ciclo indefinidamente.

**Impacto en el robot real:** cualquier corrección fina (diferencias de
velocidad pequeñas, típicas de curvas suaves o de ajustes cerca del
centro de la línea) se habría convertido en un giro brusco no
intencionado en cuanto una de las dos ruedas cayera justo por debajo
del punto de arranque del motor.

**Fix:** en vez de anular de golpe, se comprime linealmente el rango
`[ZONA_MUERTA, VEL_MAX]` a `[0, VEL_MAX]`: la velocidad real crece de
forma continua desde 0 apenas se supera el umbral, en vez de saltar de
0 al valor pedido.

### 2.3. Latencia duplicada (300ms medidos donde se esperaban 150ms)

**El bug:** el retardo de percepción (cámara+WiFi+visión) y el de
actuación (Bluetooth+firmware) son dos tramos **consecutivos** del
mismo lazo, cuyos tiempos deben sumarse. El simulador aplicaba el
parámetro `LATENCIA_MS` completo a cada uno por separado, duplicando el
retardo real del lazo cerrado (150ms configurados, 300ms medidos con un
experimento de escalón). Además, dentro de la cola de comandos había un
bug de un paso adicional: se encolaba el comando nuevo antes de leer el
más viejo, así que con `maxlen=1` la lectura devolvía lo recién
insertado, colapsando un paso de retardo a cero.

**Impacto en el robot real:** ninguno directo (es un bug del
simulador, no del control), pero **sí afectó qué ganancias parecían
funcionar durante la calibración**: con el doble de latencia real de la
esperada, el barrido de ganancias eligió valores más bajos y
conservadores de lo necesario, y el sistema parecía mucho menos estable
de lo que sería con la latencia real del robot.

**Fix:** se dividió en `LATENCIA_PERCEPCION_MS` (120) y
`LATENCIA_ACTUACION_MS` (30), cada uno con su propia cola en
`simulador/pista_virtual.py`, y se corrigió el orden de lectura/encolado
en la cola de comandos. Verificado con un experimento de escalón: 150ms
configurados = 150ms medidos.

### 2.4. Traslación espuria durante el giro en sitio

**El bug:** al buscar la línea perdida girando sobre su propio eje
(ruedas a velocidades iguales y opuestas), el modelo cinemático seguía
aplicando el término de traslación lateral
(`posicion_lateral -= GANANCIA_POSICION * orientacion * velocidad_avance * dt`)
sin excluirlo explícitamente durante el giro puro. Aunque la velocidad
de avance neta debería ser ~0 en ese caso, residuos del comando
anterior (inercia del motor, redondeo) bastaban para que la posición
lateral siguiera desplazándose varias unidades por segundo mientras el
robot giraba — llegando a medirse posiciones de hasta 21.67 (en una
escala donde 1.0 ya es "fuera de la pista").

**Impacto en el robot real:** ninguno directo (un robot real que gira
sobre su eje físicamente no se traslada, así que este bug solo existía
en el modelo del simulador), pero distorsionaba por completo la
calibración: hacía parecer que el punto de reingreso tras una búsqueda
estaba mucho más lejos del centro de lo que estaría en la realidad,
sesgando el barrido de ganancias hacia un escenario irreal.

**Fix:** mientras el robot está girando en sitio (`girando_en_sitio`),
la posición lateral se deja congelada explícitamente; solo cambia la
orientación (rumbo).

## 3. El estado REALINEANDO

Al corregir el bug 2.4 se hizo evidente el problema de diseño de fondo:
la máquina de estados pasaba de `LINEA_PERDIDA` a `SEGUIR_LINEA` en
cuanto la línea volvía a ser visible, **sin exigir que el chasis
estuviera alineado**. Un robot que recupera la línea girando sobre su
eje normalmente lo hace con el chasis todavía torcido (a menudo con un
ángulo cercano al límite del campo de visión); retomar el seguimiento
normal de inmediato significa avanzar a velocidad casi normal estando
girado, lo que en uno o dos fotogramas vuelve a sacar la línea del
cuadro — un ciclo de pérdida-recuperación-pérdida que ninguna ganancia
de KP/KD/KA podía evitar, porque el problema no era de sintonía sino de
que el control avanzaba en un momento en el que no debía.

**Esto es defendible en el robot físico, no un parche para el
simulador:** es exactamente el comportamiento esperado de cualquier
seguidor de línea real que recupera la trayectoria — seguir girando
sobre el eje hasta quedar alineado, y solo entonces retomar el avance.
Es además uno de los criterios que se evalúa en la recuperación de
trayectoria.

Se agregó `REALINEANDO` como estado intermedio entre `LINEA_PERDIDA` y
`SEGUIR_LINEA` (`control/estados.py`): al recuperar la línea, el robot
gira **sin avanzar** (`ControladorPD.realinear()`) corrigiendo el
ángulo del chasis (no la posición lateral, que girar en el sitio no
puede corregir) hasta que el ángulo se mantenga por debajo de
`ERROR_REALINEADO` durante `FOTOGRAMAS_REALINEADO_CONSECUTIVOS`
fotogramas seguidos. Solo entonces se reinicia el controlador PD y se
pasa a `SEGUIR_LINEA`. Si se agota `TIEMPO_MAX_REALINEANDO` sin lograr
alinearse, o si la línea se pierde de nuevo durante la realineación,
se vuelve a `LINEA_PERDIDA`.

**Efecto medido:** en el escenario de calibración con latencia de
150ms, el porcentaje de tiempo en seguimiento normal subió de ~26% a
58-80% (según el criterio con que se elijan las ganancias), y en
latencia baja (≤90ms) el sistema alcanza 94.8% de tiempo en seguimiento
con error medio de 0.07 — validando que el estado es correcto y
necesario.

## 4. Limitaciones conocidas del simulador

- **El error de reingreso tras `LINEA_PERDIDA` no es representativo.**
  El simulador modela la pérdida de línea como un corte binario (visible
  o no) basado en un umbral de distancia lateral (`ANCHO_PISTA`) sin
  relación verificada con centímetros reales ni con el ancho de la ROI
  de la cámara. En la realidad, la pérdida de línea es gradual: la
  franja lejana de la ROI deja de ver la línea antes que la cercana, la
  confianza baja progresivamente, y solo cuando ninguna franja la ve se
  marca inválido. Con el modelo binario actual, el robot puede alejarse
  mucho más de la línea (en términos relativos) de lo que ocurriría en
  la realidad antes de que se declare "perdida", así que el error con
  el que se reingresa tras una búsqueda está sobreestimado. Esto es la
  causa de que, incluso con `REALINEANDO`, el porcentaje de tiempo en
  seguimiento normal con latencia de 150ms no llegue al 90%: el error
  de posición residual al salir de `REALINEANDO` (que girar en el sitio
  no puede corregir) sigue siendo mayor de lo que sería con un modelo
  de reingreso gradual y a pocos centímetros del borde real de la ROI.
- La escala completa de `simulador/pista_virtual.py` (`ANCHO_PISTA` y
  las ganancias cinemáticas `GANANCIA_ORIENTACION`, `GANANCIA_POSICION`,
  `GANANCIA_CURVATURA`) es arbitraria, no está anclada a unidades
  físicas. Cambiar esto (idealmente a centímetros reales, con el ancho
  de la ROI medido de los videos) resolvería el punto anterior.
- Zona muerta, inercia del motor y ruido de detección son estimaciones
  razonables pero no medidas: todos estos parámetros están marcados
  `CALIBRAR CON VIDEO` en `config.py`.
- El barrido de ganancias corrió sobre una sola pista sintética y (para
  la mayoría de las corridas) una sola semilla de ruido; no se
  promedió sistemáticamente sobre múltiples semillas en esta última
  ronda, a diferencia de una calibración anterior donde eso sí cambió
  cuál combinación resultaba más robusta.

## 5. Ganancias finales y su elección

Con el estado `REALINEANDO` en su lugar, el barrido final (364
combinaciones de KP/KD/KA sobre el simulador realista, latencia total
150ms) no elige la combinación de mayor porcentaje de tiempo en
seguimiento, sino la más conservadora — menor cantidad de salidas de
pista y menor oscilación — precisamente porque el error de reingreso
está sobreestimado (ver sección 4) y no es confiable optimizar
agresivamente contra él:

```
KP = 10.0
KD = 15.0
KA = 15.0
```

Quedan marcadas como provisionales en `config.py` y deberán
recalibrarse en cuanto haya video real y, sobre todo, en cuanto el
modelo de reingreso del simulador esté anclado a distancias físicas
verificadas.
