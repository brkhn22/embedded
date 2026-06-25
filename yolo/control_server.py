import json
import threading
import time
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from yolo.coco_classes import COCO_CLASSES


DEFAULT_SETTINGS = {
    "targetClass": "bottle",
    "confidence": 0.45,
    "controlMode": "single",
    "queueTargets": [],
    "queueActive": False,
    "queueRunId": 0,
}

LIMITS = {
    "confidence": (0.05, 0.95),
}


class YoloSettings:
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

            if "controlMode" in values:
                control_mode = values["controlMode"]
                if control_mode not in ("single", "queue"):
                    raise ValueError("controlMode must be single or queue")
                updated["controlMode"] = control_mode
                if control_mode == "single":
                    updated["queueActive"] = False

            if "targetClass" in values:
                target_class = values["targetClass"]
                if target_class not in COCO_CLASSES:
                    raise ValueError("targetClass must be a valid COCO class")
                updated["targetClass"] = target_class

            if "queueTargets" in values:
                queue_targets = values["queueTargets"]
                if not isinstance(queue_targets, list):
                    raise ValueError("queueTargets must be a list")
                if len(queue_targets) > len(COCO_CLASSES):
                    raise ValueError("queueTargets has too many items")

                cleaned_targets = []
                for target_class in queue_targets:
                    if target_class not in COCO_CLASSES:
                        raise ValueError("queueTargets must contain valid COCO classes")
                    if target_class not in cleaned_targets:
                        cleaned_targets.append(target_class)
                updated["queueTargets"] = cleaned_targets

            for name, (minimum, maximum) in LIMITS.items():
                if name not in values:
                    continue
                value = values[name]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name} must be a number")
                value = float(value)
                if not minimum <= value <= maximum:
                    raise ValueError(
                        f"{name} must be between {minimum} and {maximum}"
                    )
                updated[name] = round(value, 2)

            queue_action = values.get("queueAction")
            if queue_action is not None:
                if queue_action == "start":
                    if not updated["queueTargets"]:
                        raise ValueError("Select at least one queued object")
                    updated["controlMode"] = "queue"
                    updated["queueActive"] = True
                    updated["queueRunId"] += 1
                elif queue_action == "stop":
                    updated["queueActive"] = False
                else:
                    raise ValueError("queueAction must be start or stop")

            self._settings = updated
            return deepcopy(updated)

    def finish_queue(self, run_id):
        with self._lock:
            if run_id == self._settings["queueRunId"]:
                self._settings["queueActive"] = False
            return deepcopy(self._settings)


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
                "confidence",
                "candidateArea",
                "detectionState",
                "targetClass",
                "controlMode",
                "queueActive",
                "queueIndex",
                "queueTotal",
                "queueRunId",
                "queueFinished",
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
    class YoloRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            super().end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/settings":
                self._send_json(settings.get())
                return
            if path == "/api/status":
                self._send_json(vision_status.get())
                return
            if path == "/api/classes":
                self._send_json({"classes": COCO_CLASSES})
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
                    if payload.get("queueFinished"):
                        settings.finish_queue(payload.get("queueRunId"))
                    self._send_json(settings.get())
            except (json.JSONDecodeError, ValueError) as error:
                self._send_json({"error": str(error)}, status=400)

        def _read_json(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 4096:
                raise ValueError("Request body is too large")
            return json.loads(self.rfile.read(content_length) or b"{}")

        def log_message(self, message_format, *args):
            print(f"[yolo-web] {self.address_string()} - {message_format % args}")

        def _send_json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return YoloRequestHandler


def run_yolo_server(host="0.0.0.0", port=8001):
    settings = YoloSettings()
    vision_status = VisionStatus()
    web_root = Path(__file__).resolve().parent / "web"
    server = ThreadingHTTPServer(
        (host, port),
        _handler_factory(settings, vision_status, web_root),
    )
    print(f"Spectra YOLO panel: http://localhost:{port}")
    print("Press Ctrl+C to stop the web server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_yolo_server()
