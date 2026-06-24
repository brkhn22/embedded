import json
import threading
from copy import deepcopy
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_SETTINGS = {
    "targetClass": "bottle",
    "confidence": 0.45,
    "controlMode": "single",
    "queueTargets": [],
    "queueActive": False,
    "queueRunId": 0,
}


class WebControlClient:
    def __init__(self, base_url="http://127.0.0.1:8001", interval=0.5):
        self._heartbeat_url = f"{base_url}/api/heartbeat"
        self._interval = interval
        self._lock = threading.Lock()
        self._settings = deepcopy(DEFAULT_SETTINGS)
        self._details = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="yolo-web-control-client",
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

    def update_status(
        self,
        command,
        target_detected,
        fps=0,
        confidence=0,
        candidate_area=0,
        detection_state="NO TARGET",
        target_class="bottle",
        control_mode="single",
        queue_active=False,
        queue_index=0,
        queue_total=0,
        queue_run_id=0,
        queue_finished=False,
    ):
        with self._lock:
            self._details = {
                "command": command,
                "targetDetected": target_detected,
                "fps": round(fps, 1),
                "confidence": round(confidence, 2),
                "candidateArea": round(candidate_area),
                "detectionState": detection_state,
                "targetClass": target_class,
                "controlMode": control_mode,
                "queueActive": queue_active,
                "queueIndex": queue_index,
                "queueTotal": queue_total,
                "queueRunId": queue_run_id,
                "queueFinished": queue_finished,
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
                    self._settings = {
                        **DEFAULT_SETTINGS,
                        **settings,
                    }
            except (URLError, TimeoutError, json.JSONDecodeError, OSError):
                pass

            self._stop_event.wait(self._interval)
