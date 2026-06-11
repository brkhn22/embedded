import json
import threading
from copy import deepcopy
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_SETTINGS = {
    "targetColor": "#0066ff",
    "hueTolerance": 20,
    "saturationTolerance": 175,
    "valueTolerance": 205,
    "minContourArea": 300,
}


class WebControlClient:
    def __init__(self, base_url="http://127.0.0.1:8000", interval=0.5):
        self._heartbeat_url = f"{base_url}/api/heartbeat"
        self._interval = interval
        self._lock = threading.Lock()
        self._settings = deepcopy(DEFAULT_SETTINGS)
        self._details = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="web-control-client",
            daemon=True,
        )

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=2)

    def get_settings(self):
        with self._lock:
            return deepcopy(self._settings)

    def update_status(self, command, target_detected):
        with self._lock:
            self._details = {
                "command": command,
                "targetDetected": target_detected,
            }

    def _run(self):
        while not self._stop_event.is_set():
            with self._lock:
                payload = deepcopy(self._details)

            request = Request(
                self._heartbeat_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=1) as response:
                    settings = json.load(response)
                with self._lock:
                    self._settings = settings
            except (URLError, TimeoutError, json.JSONDecodeError, OSError):
                pass

            self._stop_event.wait(self._interval)
