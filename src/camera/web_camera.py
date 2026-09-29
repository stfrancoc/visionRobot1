"""Servidor Flask que recibe fotogramas JPEG enviados por un navegador móvil."""

import socket
import threading
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, render_template_string, request
from werkzeug.serving import make_server


PHONE_CAMERA_PAGE = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#101b1d">
  <title>Cámara del robot</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; background: #101b1d; color: #edf4ee; }
    body { max-width: 640px; margin: 0 auto; padding: 20px; }
    h1 { font-size: 1.35rem; margin: 0 0 18px; }
    video { display: block; width: 100%; max-height: 68vh; object-fit: cover; background: #263638; border-radius: 8px; }
    .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 14px 0; }
    button, select { min-height: 46px; border: 1px solid #718488; border-radius: 6px; padding: 8px 12px; font: inherit; color: inherit; background: #263638; }
    button:first-child { background: #b5e36a; color: #162014; border-color: #b5e36a; font-weight: 700; }
    button:disabled { opacity: .5; }
    #status { min-height: 1.5em; color: #b5e36a; }
    #status.error { color: #ff9d8c; }
  </style>
</head>
<body>
  <h1>Cámara del robot</h1>
  <video id="preview" autoplay playsinline muted></video>
  <div class="controls">
    <select id="facing" aria-label="Cámara">
      <option value="environment">Cámara trasera</option>
      <option value="user">Cámara frontal</option>
    </select>
    <button id="start">Iniciar cámara</button>
    <button id="stop" disabled>Detener</button>
  </div>
  <p id="status" role="status">Conecta este teléfono y el PC a la misma red Wi-Fi.</p>
  <script>
    const video = document.querySelector('#preview');
    const statusText = document.querySelector('#status');
    const startButton = document.querySelector('#start');
    const stopButton = document.querySelector('#stop');
    const canvas = document.createElement('canvas');
    let mediaStream = null;
    let running = false;
    let sending = false;

    function status(message, error = false) {
      statusText.textContent = message;
      statusText.classList.toggle('error', error);
    }

    async function sendFrame() {
      if (!running) return;
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && !sending) {
        sending = true;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
        try {
          const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.72));
          if (!blob) throw new Error('No se pudo codificar el fotograma');
          const response = await fetch('/frame', {
            method: 'POST',
            headers: { 'Content-Type': 'image/jpeg' },
            body: blob,
            cache: 'no-store'
          });
          if (!response.ok) throw new Error(`Servidor: ${response.status}`);
          status('Cámara activa · enviando video al PC');
        } catch (error) {
          status(`Error enviando video: ${error.message}`, true);
        } finally {
          sending = false;
        }
      }
      if (running) window.setTimeout(sendFrame, 100);
    }

    startButton.addEventListener('click', async () => {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        status('El navegador requiere HTTPS confiable para habilitar la cámara. Configura un certificado para la IP del PC.', true);
        return;
      }
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: document.querySelector('#facing').value }, width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false
        });
        video.srcObject = mediaStream;
        await video.play();
        running = true;
        startButton.disabled = true;
        stopButton.disabled = false;
        sendFrame();
      } catch (error) {
        status(`No se pudo iniciar la cámara: ${error.message}`, true);
      }
    });

    stopButton.addEventListener('click', () => {
      running = false;
      if (mediaStream) mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
      video.srcObject = null;
      startButton.disabled = false;
      stopButton.disabled = true;
      status('Cámara detenida');
    });

    if (!window.isSecureContext) {
      status('Esta dirección HTTP no permite acceso a la cámara. Abre el sitio mediante HTTPS con certificado confiable.', true);
    }
  </script>
</body>
</html>
"""


def local_ip_addresses():
    addresses = set()
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        addresses.update(
            result[4][0]
            for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            if not result[4][0].startswith("127.")
        )
    except OSError:
        pass
    return sorted(addresses)


class BrowserCameraServer:
    """API de cámara con interfaz compatible con el bucle del pipeline."""

    def __init__(self, host="0.0.0.0", port=5000, tls_cert=None, tls_key=None, max_upload_bytes=2_000_000):
        self.host = host
        self.port = int(port)
        self.tls_cert = Path(tls_cert) if tls_cert else None
        self.tls_key = Path(tls_key) if tls_key else None
        self.max_upload_bytes = max_upload_bytes
        self.app = Flask(__name__)
        self.app.config["MAX_CONTENT_LENGTH"] = max_upload_bytes
        self._frame_condition = threading.Condition()
        self._latest_frame = None
        self._frame_id = 0
        self._last_read_id = 0
        self._server = None
        self._thread = None
        self._register_routes()

    def _register_routes(self):
        @self.app.get("/")
        def camera_page():
            return render_template_string(PHONE_CAMERA_PAGE)

        @self.app.post("/frame")
        def receive_frame():
            payload = request.get_data(cache=False)
            if not payload or len(payload) > self.max_upload_bytes:
                return jsonify(error="Fotograma vacío o demasiado grande"), 413
            frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return jsonify(error="El cuerpo debe ser una imagen JPEG válida"), 400
            with self._frame_condition:
                self._latest_frame = frame
                self._frame_id += 1
                self._frame_condition.notify_all()
            return jsonify(ok=True, frame_id=self._frame_id), 202

        @self.app.get("/health")
        def health():
            with self._frame_condition:
                return jsonify(ready=self._frame_id > 0, frame_id=self._frame_id)

    @property
    def secure(self):
        return self.tls_cert is not None and self.tls_key is not None

    def start(self):
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("Configura ambos PHONE_CAMERA_TLS_CERT y PHONE_CAMERA_TLS_KEY para usar HTTPS")
        ssl_context = None
        if self.secure:
            if not self.tls_cert.is_file() or not self.tls_key.is_file():
                raise FileNotFoundError("No se encuentran el certificado TLS o su clave privada")
            ssl_context = (str(self.tls_cert), str(self.tls_key))
        self._server = make_server(self.host, self.port, self.app, threaded=True, ssl_context=ssl_context)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, name="phone-camera-http", daemon=True)
        self._thread.start()
        scheme = "https" if self.secure else "http"
        print("[PhoneCamera] Servidor listo:")
        for address in local_ip_addresses():
            print(f"  {scheme}://{address}:{self.port}")
        if not self.secure:
            print("[PhoneCamera] AVISO: HTTP no permite getUserMedia desde la IP del PC; configura un certificado HTTPS confiable en el celular.")
        else:
            print("[PhoneCamera] HTTPS habilitado; el certificado debe ser confiable y cubrir la IP mostrada.")
        return True

    def read_frame(self):
        """Entrega cada frame nuevo una sola vez y omite frames atrasados."""
        with self._frame_condition:
            if self._frame_id <= self._last_read_id:
                return None
            self._last_read_id = self._frame_id
            return self._latest_frame.copy()

    def close(self):
        if self._server is not None:
            self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        with self._frame_condition:
            self._latest_frame = None
            self._frame_id = 0
            self._last_read_id = 0