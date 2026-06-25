import json
import threading
import time
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_SETTINGS = {
    "targetColor": "#0066ff",
    "hueTolerance": 15,
    "saturationMin": 80,
    "valueMin": 70,
    "minContourArea": 400,
    "minColorDensity": 25,
}

LIMITS = {
    "hueTolerance": (0, 90),
    "saturationMin": (0, 255),
    "valueMin": (0, 255),
    "minContourArea": (1, 100000),
    "minColorDensity": (1, 100),
}


class ColorSettings:
    def __init__(self):
        self._lock = threading.Lock()
        self._settings = deepcopy(DEFAULT_SETTINGS)

    def get(self):
        with self._lock:
            return deepcopy(self._settings)

    def update(self, values):
        if not isinstance(values, dict):
            raise ValueError("Request body must be a JSON object")

        with self._lock:
            updated = deepcopy(self._settings)

            if "targetColor" in values:
                color = values["targetColor"]
                if (
                    not isinstance(color, str)
                    or len(color) != 7
                    or not color.startswith("#")
                ):
                    raise ValueError("targetColor must use the #RRGGBB format")
                try:
                    int(color[1:], 16)
                except ValueError as error:
                    raise ValueError(
                        "targetColor must use the #RRGGBB format"
                    ) from error
                updated["targetColor"] = color.lower()

            for name, (minimum, maximum) in LIMITS.items():
                if name not in values:
                    continue
                value = values[name]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name} must be a number")
                value = int(value)
                if not minimum <= value <= maximum:
                    raise ValueError(
                        f"{name} must be between {minimum} and {maximum}"
                    )
                updated[name] = value

            self._settings = updated
            return deepcopy(updated)


class VisionStatus:
    DISCONNECT_TIMEOUT = 3.0

    def __init__(self):
        self._lock = threading.Lock()
        self._last_seen = None
        self._details = {}

    def heartbeat(self, details):
        if not isinstance(details, dict):
            raise ValueError("Request body must be a JSON object")

        allowed_details = {
            key: details[key]
            for key in (
                "command",
                "targetDetected",
                "fps",
                "colorDensity",
                "candidateArea",
                "detectionState",
            )
            if key in details
        }
        with self._lock:
            self._last_seen = time.monotonic()
            self._details = allowed_details

    def get(self):
        with self._lock:
            if self._last_seen is None:
                return {
                    "visionConnected": False,
                    "lastSeenSeconds": None,
                }

            elapsed = time.monotonic() - self._last_seen
            return {
                "visionConnected": elapsed <= self.DISCONNECT_TIMEOUT,
                "lastSeenSeconds": round(elapsed, 1),
                **deepcopy(self._details),
            }


def _handler_factory(settings, vision_status, web_root):
    class ColorRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/settings":
                self._send_json(settings.get())
                return
            if path == "/api/status":
                self._send_json(vision_status.get())
                return
            super().do_GET()

        def do_POST(self):
            path = urlparse(self.path).path
            if path not in ("/api/settings", "/api/heartbeat"):
                self.send_error(404)
                return

            try:
                payload = self._read_json()
                if path == "/api/settings":
                    self._send_json(settings.update(payload))
                else:
                    vision_status.heartbeat(payload)
                    self._send_json(settings.get())
            except (json.JSONDecodeError, ValueError) as error:
                self._send_json({"error": str(error)}, status=400)

        def _read_json(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 4096:
                raise ValueError("Request body is too large")
            return json.loads(self.rfile.read(content_length) or b"{}")

        def log_message(self, message_format, *args):
            print(f"[web] {self.address_string()} - {message_format % args}")

        def _send_json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return ColorRequestHandler


def start_color_server(host="0.0.0.0", port=8000):
    settings = ColorSettings()
    vision_status = VisionStatus()
    web_root = Path(__file__).resolve().parent
    server = ThreadingHTTPServer(
        (host, port),
        _handler_factory(settings, vision_status, web_root),
    )
    thread = threading.Thread(
        target=server.serve_forever,
        name="color-control-server",
        daemon=True,
    )
    thread.start()
    return server, settings, vision_status


def run_color_server(host="0.0.0.0", port=8000):
    settings = ColorSettings()
    vision_status = VisionStatus()
    web_root = Path(__file__).resolve().parent
    server = ThreadingHTTPServer(
        (host, port),
        _handler_factory(settings, vision_status, web_root),
    )
    print(f"Spectra control panel: http://localhost:{port}")
    print("Press Ctrl+C to stop the web server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_color_server()
