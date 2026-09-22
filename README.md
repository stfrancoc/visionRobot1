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
