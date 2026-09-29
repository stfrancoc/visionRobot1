# simulador/

Simulador cinemático de la pista y el robot, usado para calibrar el
control antes de tener acceso al robot físico.

**Nota importante:** este simulador modela **velocidades continuas por
rueda** (un PD clásico), no el modelo real del mBot del docente, que solo
acepta 5 comandos discretos sin parámetros (adelante/atras/izquierda/
derecha/parar), cada uno un pulso de duración fija que el firmware
autodetiene. El control real (`control/controlador.py`,
`control/estados.py`) se migró a un control por zonas de error sobre ese
modelo de pulsos, y ya no corre sobre este simulador.

Este código se conserva congelado porque ya cumplió su función: los
hallazgos que produjo (bugs del modelo cinemático, el umbral de latencia
del lazo cerrado, el estado REALINEANDO y por qué hizo falta) están
documentados en `capturas/reporte_calibracion.md` y siguen siendo
relevantes para entender por qué el control quedó como quedó. No se
actualizará para modelar pulsos discretos: no es el entregable de esta
rama.
