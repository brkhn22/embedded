import os
import socket
import sys
import time
from collections import deque
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from ultralytics import YOLO
except ModuleNotFoundError as error:
    raise SystemExit(
        "ultralytics kurulmamış. "
        "`source .venv/bin/activate && python3 -m pip install -r yolo/requirements.txt` "
        "komutunu çalıştırın.",
    ) from error

from yolo.web_client import DEFAULT_SETTINGS, WebControlClient


ESP_IP = os.environ.get("ESP_IP", "10.42.0.221")
ESP_PORT = int(os.environ.get("ESP_PORT", "8888"))
STREAM_URL = os.environ.get(
    "STREAM_URL",
    f"http://{ESP_IP}:81/stream",
)
MODEL_PATH = os.environ.get("YOLO_MODEL", "yolo11n.pt")
TARGET_CLASS = os.environ.get("YOLO_TARGET_CLASS", "bottle")
CONFIDENCE = float(os.environ.get("YOLO_CONFIDENCE", "0.45"))
WEB_CONTROL_URL = os.environ.get("YOLO_WEB_URL", "http://127.0.0.1:8001")
DEBUG_LOG_PATH = Path(
    os.environ.get("YOLO_DEBUG_LOG", str(PROJECT_ROOT / "yolo" / "detect_debug.log"))
)

SEND_INTERVAL = 0.1
SEARCH_TURN_SECONDS = float(os.environ.get("YOLO_SEARCH_TURN_SECONDS", "0.35"))
SEARCH_PAUSE_SECONDS = float(os.environ.get("YOLO_SEARCH_PAUSE_SECONDS", "0.5"))
TRACK_TURN_SECONDS = float(os.environ.get("YOLO_TRACK_TURN_SECONDS", "0.08"))
TRACK_PAUSE_SECONDS = float(os.environ.get("YOLO_TRACK_PAUSE_SECONDS", "0.15"))
TARGET_REACQUIRE_HOLD_SECONDS = float(
    os.environ.get("YOLO_TARGET_REACQUIRE_HOLD_SECONDS", "0.45")
)
REACQUIRE_NUDGE_SECONDS = float(
    os.environ.get("YOLO_REACQUIRE_NUDGE_SECONDS", "0.08")
)
TURN_REVERSAL_CONFIRM_FRAMES = int(
    os.environ.get("YOLO_TURN_REVERSAL_CONFIRM_FRAMES", "3")
)
TURN_REVERSAL_STOP_SECONDS = float(
    os.environ.get("YOLO_TURN_REVERSAL_STOP_SECONDS", "0.15")
)
CENTER_CONFIRM_FRAMES = int(os.environ.get("YOLO_CENTER_CONFIRM_FRAMES", "3"))
CENTER_CONFIRM_WINDOW = int(os.environ.get("YOLO_CENTER_CONFIRM_WINDOW", "5"))
CENTER_TOLERANCE_X_RATIO = float(
    os.environ.get("YOLO_CENTER_TOLERANCE_X_RATIO", "0.18")
)
CENTER_TOLERANCE_Y_RATIO = float(
    os.environ.get("YOLO_CENTER_TOLERANCE_Y_RATIO", "0.18")
)
OBSTACLE_ALERT_SECONDS = float(
    os.environ.get("YOLO_OBSTACLE_ALERT_SECONDS", "3.0")
)
OBSTACLE_REVERSE_SECONDS = float(
    os.environ.get("YOLO_OBSTACLE_REVERSE_SECONDS", "1.0")
)
OBSTACLE_SEARCH_SECONDS = float(
    os.environ.get("YOLO_OBSTACLE_SEARCH_SECONDS", "2.0")
)
def connect_to_esp():
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            print(f"ESP32 komut baglantisi: {ESP_IP}:{ESP_PORT}")
            sock.connect((ESP_IP, ESP_PORT))
            sock.settimeout(None)
            print("ESP32 komut baglantisi kuruldu.")
            return sock
        except (socket.gaierror, TimeoutError, OSError) as error:
            sock.close()
            print(f"ESP32 baglantisi basarisiz: {error}")
            print("2 saniye sonra tekrar denenecek. Cikmak icin Ctrl+C.")
            time.sleep(2)


def send_command(sock, command):
    sock.sendall(f"<{command}>".encode("ascii"))


def receive_feedback(sock, buffer):
    while True:
        try:
            chunk = sock.recv(1024, socket.MSG_DONTWAIT)
        except BlockingIOError:
            break

        if not chunk:
            raise ConnectionError("ESP32 komut baglantisi kapandi.")
        buffer += chunk.decode("ascii", errors="ignore")

    messages = []
    while "<" in buffer and ">" in buffer:
        start = buffer.find("<")
        end = buffer.find(">", start + 1)
        if end == -1:
            buffer = buffer[start:]
            break
        messages.append(buffer[start + 1 : end])
        buffer = buffer[end + 1 :]

    if len(buffer) > 128:
        buffer = buffer[-128:]

    return messages, buffer


def load_model():
    print(f"YOLO model yukleniyor: {MODEL_PATH}")
    return YOLO(MODEL_PATH)


def draw_box(frame, box, label, color):
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 0), 4)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(
        frame,
        label,
        (x1, max(25, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 0, 0),
        4,
    )
    cv2.putText(
        frame,
        label,
        (x1, max(25, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
    )


def append_debug_log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} {message}\n")


model = load_model()
sock = connect_to_esp()
cap = cv2.VideoCapture(STREAM_URL)
web_control = WebControlClient(
    base_url=WEB_CONTROL_URL,
    interval=0.5,
)
web_control.start()

last_command = None
last_send_time = 0
feedback_buffer = ""
arduino_obstacle_blocked = False
last_target_box = None
last_target_center = None
last_target_command = None
search_phase = None
search_phase_started = None
active_turn_direction = None
pending_turn_direction = None
pending_turn_frames = 0
pending_turn_since = None
track_phase = None
track_phase_started = None
track_phase_direction = None
reacquire_nudge_direction = None
reacquire_nudge_until = 0.0
center_confirm_history = deque(maxlen=CENTER_CONFIRM_WINDOW)
approach_locked = False
last_target_seen_at = None
obstacle_recovery_phase = None
obstacle_alert_started = None
obstacle_reverse_started = None
obstacle_search_until = 0.0
last_frame_time = time.monotonic()
fps = 0.0
target_class_id = None
active_target_class = TARGET_CLASS
active_confidence = CONFIDENCE
active_control_mode = "single"
queue_targets = []
queue_index = 0
queue_run_id = 0
queue_finished = False
queue_target_seen = False
queue_target_last_seen_at = None
queue_target_forward_started = False
last_logged_signature = None

print(f"YOLO hedef sinifi: {TARGET_CLASS}")
append_debug_log("detect.py started")

try:
    while True:
        live_settings = {
            **DEFAULT_SETTINGS,
            "targetClass": TARGET_CLASS,
            "confidence": CONFIDENCE,
            **web_control.get_settings(),
        }
        requested_control_mode = live_settings["controlMode"]
        requested_queue_targets = list(live_settings["queueTargets"])
        requested_queue_active = bool(live_settings["queueActive"])
        requested_queue_run_id = int(live_settings["queueRunId"])
        active_control_mode = requested_control_mode

        if requested_control_mode == "queue" and requested_queue_active:
            if requested_queue_run_id != queue_run_id or not queue_targets:
                queue_targets = requested_queue_targets
                queue_index = 0
                queue_run_id = requested_queue_run_id
                queue_finished = False
                queue_target_seen = False
                queue_target_last_seen_at = None
                queue_target_forward_started = False
                target_class_id = None
                last_target_box = None
                last_target_center = None
                last_target_command = None
                search_phase = None
                search_phase_started = None
                active_turn_direction = None
                pending_turn_direction = None
                pending_turn_frames = 0
                pending_turn_since = None
                track_phase = None
                track_phase_started = None
                track_phase_direction = None
                reacquire_nudge_direction = None
                reacquire_nudge_until = 0.0
                center_confirm_history.clear()
                approach_locked = False
                last_target_seen_at = None
                obstacle_recovery_phase = None
                obstacle_alert_started = None
                obstacle_reverse_started = None
                obstacle_search_until = 0.0
                last_command = None
                print(
                    "YOLO kuyruk basladi: "
                    + ", ".join(queue_targets)
                )

            requested_target_class = (
                queue_targets[queue_index]
                if queue_index < len(queue_targets)
                else live_settings["targetClass"]
            )
        else:
            if requested_control_mode == "single":
                queue_finished = False
                queue_target_seen = False
                queue_target_last_seen_at = None
                queue_target_forward_started = False
            elif requested_queue_targets != queue_targets:
                queue_finished = False
                queue_target_seen = False
                queue_target_last_seen_at = None
                queue_target_forward_started = False
            queue_targets = requested_queue_targets
            queue_index = 0
            queue_run_id = requested_queue_run_id
            requested_target_class = live_settings["targetClass"]

        requested_confidence = float(live_settings["confidence"])
        if requested_target_class != active_target_class:
            active_target_class = requested_target_class
            target_class_id = None
            last_target_box = None
            last_target_center = None
            last_target_command = None
            search_phase = None
            search_phase_started = None
            active_turn_direction = None
            pending_turn_direction = None
            pending_turn_frames = 0
            pending_turn_since = None
            track_phase = None
            track_phase_started = None
            track_phase_direction = None
            reacquire_nudge_direction = None
            reacquire_nudge_until = 0.0
            center_confirm_history.clear()
            approach_locked = False
            last_target_seen_at = None
            obstacle_recovery_phase = None
            obstacle_alert_started = None
            obstacle_reverse_started = None
            obstacle_search_until = 0.0
            queue_target_seen = False
            queue_target_last_seen_at = None
            queue_target_forward_started = False
            last_command = None
            print(f"YOLO hedef sinifi degisti: {active_target_class}")
        active_confidence = requested_confidence

        feedback_messages, feedback_buffer = receive_feedback(
            sock,
            feedback_buffer,
        )
        for feedback_message in feedback_messages:
            if feedback_message == "B1":
                if not arduino_obstacle_blocked:
                    print("Arduino mesafe engeli: motorlar durduruldu.")
                arduino_obstacle_blocked = True
                if obstacle_recovery_phase is None:
                    obstacle_recovery_phase = "ALERT"
                    obstacle_alert_started = time.monotonic()
                    obstacle_reverse_started = None
                approach_locked = False
                center_confirm_history.clear()
                last_target_command = None
                last_target_seen_at = None
                reacquire_nudge_direction = None
                reacquire_nudge_until = 0.0
            elif feedback_message == "B0":
                if arduino_obstacle_blocked:
                    print("Arduino mesafe engeli temizlendi.")
                arduino_obstacle_blocked = False

        ret, frame = cap.read()
        if not ret:
            print("Kameradan goruntu alinamadi!")
            break

        frame_time = time.monotonic()
        frame_duration = frame_time - last_frame_time
        last_frame_time = frame_time
        if frame_duration > 0:
            current_fps = 1.0 / frame_duration
            fps = current_fps if fps == 0 else fps * 0.9 + current_fps * 0.1

        frame_height, frame_width = frame.shape[:2]
        frame_center_x = frame_width // 2
        frame_center_y = frame_height // 2

        result = model.predict(
            source=frame,
            conf=active_confidence,
            verbose=False,
        )[0]

        names = result.names
        if target_class_id is None:
            for class_id, name in names.items():
                if name == active_target_class:
                    target_class_id = class_id
                    break
            if target_class_id is None:
                raise RuntimeError(
                    f"Model sinif listesinde '{active_target_class}' bulunamadi."
                )

        target_visible = False
        detection_state = "NO TARGET"
        candidate_area = 0.0
        target_center_x = None
        target_center_y = None
        center_error_x = None
        center_error_y = None
        memory_error_x = None
        confidence_score = 0.0
        best_box = None
        decision_source = "SEARCH"

        best_candidate = None
        for xyxy, confidence, class_id in zip(
            result.boxes.xyxy.tolist(),
            result.boxes.conf.tolist(),
            result.boxes.cls.tolist(),
        ):
            if int(class_id) != target_class_id:
                continue
            x1, y1, x2, y2 = [int(value) for value in xyxy]
            area = max(0, x2 - x1) * max(0, y2 - y1)
            if best_candidate is None or area > best_candidate["area"]:
                best_candidate = {
                    "box": (x1, y1, x2, y2),
                    "area": area,
                    "confidence": confidence,
                }

        if best_candidate is not None:
            target_visible = True
            best_box = best_candidate["box"]
            candidate_area = best_candidate["area"]
            confidence_score = best_candidate["confidence"]
            x1, y1, x2, y2 = best_box
            target_center_x = (x1 + x2) // 2
            target_center_y = (y1 + y2) // 2
            last_target_box = best_box
            last_target_center = (target_center_x, target_center_y)
            detection_state = "VISIBLE"
            draw_box(
                frame,
                best_box,
                f"{active_target_class} {confidence_score:.2f}",
                (0, 200, 255),
            )
            cv2.circle(frame, last_target_center, 5, (0, 200, 255), -1)

        now_monotonic = time.monotonic()
        forcing_obstacle_search = now_monotonic < obstacle_search_until
        if target_visible and forcing_obstacle_search:
            target_visible = False
            target_center_x = None
            target_center_y = None
            center_error_x = None
            center_error_y = None
            last_target_box = None
            last_target_center = None
            last_target_seen_at = None

        if target_visible:
            decision_source = "LIVE"
            last_target_seen_at = now_monotonic
            if active_control_mode == "queue":
                queue_target_seen = True
                queue_target_last_seen_at = now_monotonic
            reacquire_nudge_direction = None
            reacquire_nudge_until = 0.0
            search_phase = None
            search_phase_started = None

            center_tolerance_x = int(frame_width * CENTER_TOLERANCE_X_RATIO)
            center_tolerance_y = int(frame_height * CENTER_TOLERANCE_Y_RATIO)
            center_error_x = target_center_x - frame_center_x
            center_error_y = target_center_y - frame_center_y
            centered_x = abs(center_error_x) <= center_tolerance_x
            centered_y = abs(center_error_y) <= center_tolerance_y

            if center_error_x < -center_tolerance_x:
                center_confirm_history.append(False)
                detection_state = "TRACK LEFT"
                desired_command = "L"
            elif center_error_x > center_tolerance_x:
                center_confirm_history.append(False)
                detection_state = "TRACK RIGHT"
                desired_command = "R"
            elif (
                not approach_locked
                and not centered_y
                and center_error_y > center_tolerance_y
            ):
                center_confirm_history.append(False)
                detection_state = "TOO CLOSE IN FRAME"
                desired_command = "S"
            else:
                center_confirm_history.append(True)
                center_hits = sum(center_confirm_history)
                if approach_locked or center_hits >= CENTER_CONFIRM_FRAMES:
                    detection_state = (
                        "ADVANCING" if centered_y else "APPROACHING"
                    )
                    desired_command = "F"
                    approach_locked = True
                else:
                    detection_state = (
                        f"CENTER CONFIRM {center_hits}/"
                        f"{CENTER_CONFIRM_WINDOW}"
                    )
                    desired_command = "S"

            if desired_command in ("L", "R", "S") and not detection_state.startswith(
                "CENTER CONFIRM"
            ):
                approach_locked = False

            reversing_turn = (
                desired_command in ("L", "R")
                and active_turn_direction in ("L", "R")
                and desired_command != active_turn_direction
            )
            if reversing_turn:
                if pending_turn_direction == desired_command:
                    pending_turn_frames += 1
                else:
                    pending_turn_direction = desired_command
                    pending_turn_frames = 1
                    pending_turn_since = now_monotonic

                reversal_stop_elapsed = (
                    pending_turn_since is not None
                    and now_monotonic - pending_turn_since
                    >= TURN_REVERSAL_STOP_SECONDS
                )
                reversal_confirmed = (
                    pending_turn_frames >= TURN_REVERSAL_CONFIRM_FRAMES
                    and reversal_stop_elapsed
                )
                if reversal_confirmed:
                    command = desired_command
                    pending_turn_direction = None
                    pending_turn_frames = 0
                    pending_turn_since = None
                else:
                    detection_state = (
                        f"REVERSAL WAIT {pending_turn_frames}/"
                        f"{TURN_REVERSAL_CONFIRM_FRAMES}"
                    )
                    command = "S"
            else:
                command = desired_command
                pending_turn_direction = None
                pending_turn_frames = 0
                pending_turn_since = None

            if command in ("L", "R"):
                if (
                    track_phase is None
                    or track_phase_started is None
                    or track_phase_direction != command
                ):
                    track_phase = "TURN"
                    track_phase_started = now_monotonic
                    track_phase_direction = command

                track_phase_duration = now_monotonic - track_phase_started
                if (
                    track_phase == "TURN"
                    and track_phase_duration >= TRACK_TURN_SECONDS
                ):
                    track_phase = "PAUSE"
                    track_phase_started = now_monotonic
                elif (
                    track_phase == "PAUSE"
                    and track_phase_duration >= TRACK_PAUSE_SECONDS
                ):
                    track_phase = "TURN"
                    track_phase_started = now_monotonic

                if track_phase == "PAUSE":
                    detection_state = f"TRACK PAUSE {track_phase_direction}"
                    command = "S"
            else:
                track_phase = None
                track_phase_started = None
                track_phase_direction = None

            last_target_command = command
            if active_control_mode == "queue" and command == "F":
                queue_target_forward_started = True
        else:
            pending_turn_direction = None
            pending_turn_frames = 0
            pending_turn_since = None
            track_phase = None
            track_phase_started = None
            track_phase_direction = None
            center_confirm_history.append(False)

            if approach_locked:
                search_phase = None
                search_phase_started = None
                detection_state = "APPROACH LOCK"
                if last_target_box is not None:
                    draw_box(
                        frame,
                        last_target_box,
                        f"{active_target_class} memory",
                        (120, 120, 255),
                    )
                command = "F"
                last_target_command = command
            else:
                recently_saw_target = (
                    last_target_seen_at is not None
                    and now_monotonic - last_target_seen_at
                    < TARGET_REACQUIRE_HOLD_SECONDS
                )

                if recently_saw_target:
                    decision_source = "MEMORY"
                    search_phase = None
                    search_phase_started = None
                    center_tolerance_x = int(frame_width * CENTER_TOLERANCE_X_RATIO)
                    if last_target_center is not None:
                        memory_error_x = last_target_center[0] - frame_center_x

                    if (
                        reacquire_nudge_direction is None
                        and memory_error_x is not None
                        and abs(memory_error_x) > center_tolerance_x
                    ):
                        reacquire_nudge_direction = (
                            "L" if memory_error_x < 0 else "R"
                        )
                        reacquire_nudge_until = (
                            now_monotonic + REACQUIRE_NUDGE_SECONDS
                        )

                    if (
                        reacquire_nudge_direction in ("L", "R")
                        and now_monotonic < reacquire_nudge_until
                    ):
                        detection_state = (
                            f"REACQUIRE NUDGE {reacquire_nudge_direction}"
                        )
                        command = reacquire_nudge_direction
                    else:
                        detection_state = "REACQUIRE HOLD"
                        command = "S"
                else:
                    decision_source = (
                        "RECOVERY_SEARCH" if forcing_obstacle_search else "SEARCH"
                    )
                    start_search_with_pause = last_target_command in ("L", "R", "S")
                    last_target_box = None
                    last_target_center = None
                    last_target_command = None
                    reacquire_nudge_direction = None
                    reacquire_nudge_until = 0.0
                    center_confirm_history.clear()

                    if search_phase is None or search_phase_started is None:
                        search_phase = "PAUSE" if start_search_with_pause else "TURN"
                        search_phase_started = now_monotonic

                    phase_duration = now_monotonic - search_phase_started
                    if (
                        search_phase == "TURN"
                        and phase_duration >= SEARCH_TURN_SECONDS
                    ):
                        search_phase = "PAUSE"
                        search_phase_started = now_monotonic
                    elif (
                        search_phase == "PAUSE"
                        and phase_duration >= SEARCH_PAUSE_SECONDS
                    ):
                        search_phase = "TURN"
                        search_phase_started = now_monotonic

                    if search_phase == "TURN":
                        detection_state = (
                            "RECOVERY SEARCH TURN"
                            if forcing_obstacle_search
                            else "SEARCH TURN"
                        )
                        command = "T"
                    else:
                        detection_state = (
                            "RECOVERY SEARCH PAUSE"
                            if forcing_obstacle_search
                            else "SEARCH PAUSE"
                        )
                        command = "S"

        if obstacle_recovery_phase is not None:
            approach_locked = False
            center_confirm_history.clear()
            last_target_command = None
            last_target_seen_at = None
            reacquire_nudge_direction = None
            reacquire_nudge_until = 0.0
            pending_turn_direction = None
            pending_turn_frames = 0
            pending_turn_since = None
            track_phase = None
            track_phase_started = None
            track_phase_direction = None
            search_phase = None
            search_phase_started = None

            if (
                obstacle_recovery_phase == "ALERT"
                and obstacle_alert_started is not None
                and now_monotonic - obstacle_alert_started >= OBSTACLE_ALERT_SECONDS
            ):
                obstacle_recovery_phase = "REVERSE"
                obstacle_reverse_started = now_monotonic

            if obstacle_recovery_phase == "REVERSE":
                reverse_elapsed = (
                    now_monotonic - obstacle_reverse_started
                    if obstacle_reverse_started is not None
                    else 0.0
                )
                if reverse_elapsed < OBSTACLE_REVERSE_SECONDS:
                    detection_state = "OBSTACLE REVERSE"
                    command = "B"
                else:
                    obstacle_recovery_phase = None
                    obstacle_alert_started = None
                    obstacle_reverse_started = None
                    arduino_obstacle_blocked = False
                    queue_target_completed = queue_target_forward_started
                    if (
                        active_control_mode == "queue"
                        and requested_queue_active
                        and queue_index < len(queue_targets)
                        and queue_target_completed
                    ):
                        queue_index += 1
                        if queue_index >= len(queue_targets):
                            queue_finished = True
                            queue_target_seen = False
                            queue_target_last_seen_at = None
                            queue_target_forward_started = False
                            detection_state = "QUEUE COMPLETE"
                            command = "S"
                            search_phase = None
                            search_phase_started = None
                            print("YOLO kuyruk tamamlandi.")
                        else:
                            active_target_class = queue_targets[queue_index]
                            queue_target_seen = False
                            queue_target_last_seen_at = None
                            queue_target_forward_started = False
                            target_class_id = None
                            last_target_box = None
                            last_target_center = None
                            center_confirm_history.clear()
                            obstacle_search_until = (
                                now_monotonic + OBSTACLE_SEARCH_SECONDS
                            )
                            detection_state = "QUEUE NEXT TARGET"
                            command = "S"
                            search_phase = "TURN"
                            search_phase_started = now_monotonic
                            print(
                                "YOLO kuyruk siradaki hedef: "
                                f"{active_target_class}"
                            )
                    elif active_control_mode == "queue" and requested_queue_active:
                        obstacle_search_until = now_monotonic + OBSTACLE_SEARCH_SECONDS
                        detection_state = "QUEUE TARGET NOT CONFIRMED"
                        command = "S"
                        search_phase = "TURN"
                        search_phase_started = now_monotonic
                    else:
                        obstacle_search_until = now_monotonic + OBSTACLE_SEARCH_SECONDS
                        detection_state = "OBSTACLE RECOVERY DONE"
                        command = "S"
                        search_phase = "TURN"
                        search_phase_started = now_monotonic
            else:
                detection_state = "OBSTACLE ALERT"
                command = "S"

        queue_running = (
            active_control_mode == "queue"
            and requested_queue_active
            and not queue_finished
            and bool(queue_targets)
            and queue_index < len(queue_targets)
        )
        if active_control_mode == "queue" and not queue_running:
            approach_locked = False
            center_confirm_history.clear()
            last_target_command = None
            last_target_seen_at = None
            reacquire_nudge_direction = None
            reacquire_nudge_until = 0.0
            pending_turn_direction = None
            pending_turn_frames = 0
            pending_turn_since = None
            track_phase = None
            track_phase_started = None
            track_phase_direction = None
            search_phase = None
            search_phase_started = None
            target_visible = False
            confidence_score = 0.0
            candidate_area = 0.0
            command = "S"
            if queue_finished:
                detection_state = "QUEUE COMPLETE"
            elif queue_targets:
                detection_state = "QUEUE READY"
            else:
                detection_state = "QUEUE EMPTY"

        if command == "L":
            active_turn_direction = "L"
        elif command == "R":
            active_turn_direction = "R"
        elif command == "T":
            # Arduino implements T with the same motor direction as L.
            active_turn_direction = "L"
        elif command == "F":
            active_turn_direction = None
        elif command == "B":
            active_turn_direction = None
        elif (
            detection_state not in ("SEARCH PAUSE",)
            and not detection_state.startswith("REVERSAL WAIT")
            and not detection_state.startswith("TRACK PAUSE")
        ):
            active_turn_direction = None

        current_time = time.time()
        if command != last_command or current_time - last_send_time >= SEND_INTERVAL:
            send_command(sock, command)
            last_command = command
            last_send_time = current_time

        log_signature = (
            command,
            detection_state,
            decision_source,
            target_visible,
            target_center_x,
            target_center_y,
            center_error_x,
            center_error_y,
            memory_error_x,
            approach_locked,
            last_target_command,
            arduino_obstacle_blocked,
            obstacle_recovery_phase,
            obstacle_search_until,
            active_control_mode,
            queue_index,
            len(queue_targets),
            queue_run_id,
            queue_finished,
        )
        should_log = (
            log_signature != last_logged_signature
            and (
                command in ("L", "R", "F", "S", "B")
                or detection_state.startswith("TRACK ")
                or detection_state.startswith("REACQUIRE ")
                or detection_state.startswith("REVERSAL WAIT")
                or detection_state.startswith("OBSTACLE ")
                or detection_state.startswith("QUEUE ")
                or detection_state in (
                    "ADVANCING",
                    "APPROACHING",
                    "APPROACH LOCK",
                    "ARDUINO DISTANCE STOP",
                )
            )
        )
        if should_log:
            append_debug_log(
                " ".join(
                    [
                        f"cmd={command}",
                        f"state={detection_state}",
                        f"src={decision_source}",
                        f"visible={int(target_visible)}",
                        f"cx={target_center_x if target_center_x is not None else '--'}",
                        f"cy={target_center_y if target_center_y is not None else '--'}",
                        f"ex={center_error_x if center_error_x is not None else '--'}",
                        f"ey={center_error_y if center_error_y is not None else '--'}",
                        f"mex={memory_error_x if memory_error_x is not None else '--'}",
                        f"lock={int(approach_locked)}",
                        f"last={last_target_command if last_target_command is not None else '--'}",
                        f"blocked={int(arduino_obstacle_blocked)}",
                        f"recovery={obstacle_recovery_phase if obstacle_recovery_phase is not None else '--'}",
                        f"mode={active_control_mode}",
                        f"queue={queue_index}/{len(queue_targets)}",
                        f"run={queue_run_id}",
                        f"finished={int(queue_finished)}",
                    ]
                )
            )
            last_logged_signature = log_signature

        web_control.update_status(
            command=command,
            target_detected=target_visible,
            fps=fps,
            confidence=confidence_score,
            candidate_area=candidate_area,
            detection_state=detection_state,
            target_class=active_target_class,
            control_mode=active_control_mode,
            queue_active=queue_running,
            queue_index=queue_index,
            queue_total=len(queue_targets),
            queue_run_id=queue_run_id,
            queue_finished=queue_finished,
        )

        cv2.putText(
            frame,
            f"CMD: {command} TARGET: {active_target_class.upper()} {detection_state}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            frame,
            (
                f"FPS: {fps:.1f} CONF: {confidence_score:.2f}/{active_confidence:.2f} "
                f"AREA: {candidate_area:.0f} "
                f"CX: {target_center_x if target_center_x is not None else '--'} "
                f"CY: {target_center_y if target_center_y is not None else '--'}"
            ),
            (10, 65),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            (
                f"SRC: {decision_source} "
                f"EX: {center_error_x if center_error_x is not None else '--'} "
                f"EY: {center_error_y if center_error_y is not None else '--'} "
                f"MEX: {memory_error_x if memory_error_x is not None else '--'} "
                f"LOCK: {'1' if approach_locked else '0'} "
                f"LAST: {last_target_command if last_target_command is not None else '--'}"
            ),
            (10, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 220, 120),
            2,
        )

        cv2.line(
            frame,
            (frame_center_x, 0),
            (frame_center_x, frame_height),
            (255, 255, 255),
            1,
        )
        center_tolerance_x = int(frame_width * CENTER_TOLERANCE_X_RATIO)
        cv2.line(
            frame,
            (frame_center_x - center_tolerance_x, 0),
            (frame_center_x - center_tolerance_x, frame_height),
            (255, 180, 0),
            1,
        )
        cv2.line(
            frame,
            (frame_center_x + center_tolerance_x, 0),
            (frame_center_x + center_tolerance_x, frame_height),
            (255, 180, 0),
            1,
        )
        cv2.line(
            frame,
            (0, frame_center_y),
            (frame_width, frame_center_y),
            (255, 255, 255),
            1,
        )

        cv2.imshow("YOLO Robot Gozu", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            send_command(sock, "S")
            break
finally:
    cap.release()
    sock.close()
    web_control.stop()
    cv2.destroyAllWindows()
