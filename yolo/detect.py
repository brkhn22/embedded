import os
import socket
import sys
import time
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

SEND_INTERVAL = 0.1
TARGET_CONFIRM_SECONDS = 0.4
TARGET_CONFIRM_LOSS_SECONDS = 0.4
APPROACH_BURST_SECONDS = 1.0
RECHECK_SECONDS = 0.5
CENTER_TOLERANCE_X_RATIO = 0.16
CENTER_TOLERANCE_Y_RATIO = 0.28


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
target_first_seen_time = None
target_last_seen_time = None
last_target_box = None
last_target_center = None
approach_until = 0.0
recheck_until = 0.0
last_frame_time = time.monotonic()
fps = 0.0
target_class_id = None
active_target_class = TARGET_CLASS
active_confidence = CONFIDENCE

print(f"YOLO hedef sinifi: {TARGET_CLASS}")

try:
    while True:
        live_settings = {
            **DEFAULT_SETTINGS,
            "targetClass": TARGET_CLASS,
            "confidence": CONFIDENCE,
            **web_control.get_settings(),
        }
        requested_target_class = live_settings["targetClass"]
        requested_confidence = float(live_settings["confidence"])
        if requested_target_class != active_target_class:
            active_target_class = requested_target_class
            target_class_id = None
            target_first_seen_time = None
            target_last_seen_time = None
            last_target_box = None
            last_target_center = None
            approach_until = 0.0
            recheck_until = 0.0
            last_command = None
            print(f"YOLO hedef sinifi degisti: {active_target_class}")
        active_confidence = requested_confidence

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
        confidence_score = 0.0
        best_box = None

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
        if approach_until and now_monotonic >= approach_until:
            approach_until = 0.0
            recheck_until = now_monotonic + RECHECK_SECONDS

        if recheck_until and now_monotonic >= recheck_until:
            recheck_until = 0.0

        if recheck_until > now_monotonic:
            detection_state = "RECHECKING"
            command = "S"
        elif target_visible:
            target_last_seen_time = now_monotonic
            if target_first_seen_time is None:
                target_first_seen_time = now_monotonic
                detection_state = "CONFIRMING"
                command = "S"
            elif now_monotonic - target_first_seen_time < TARGET_CONFIRM_SECONDS:
                detection_state = "CONFIRMING"
                command = "S"
            else:
                center_tolerance_x = int(frame_width * CENTER_TOLERANCE_X_RATIO)
                center_tolerance_y = int(frame_height * CENTER_TOLERANCE_Y_RATIO)
                center_error_x = target_center_x - frame_center_x
                center_error_y = target_center_y - frame_center_y
                centered_x = abs(center_error_x) <= center_tolerance_x
                centered_y = abs(center_error_y) <= center_tolerance_y

                if center_error_x < -center_tolerance_x:
                    detection_state = "TRACK LEFT"
                    command = "L"
                elif center_error_x > center_tolerance_x:
                    detection_state = "TRACK RIGHT"
                    command = "R"
                elif not centered_y and center_error_y > center_tolerance_y:
                    detection_state = "TOO CLOSE IN FRAME"
                    command = "S"
                else:
                    detection_state = "ADVANCING" if centered_y else "APPROACHING"
                    if approach_until <= now_monotonic:
                        approach_until = now_monotonic + APPROACH_BURST_SECONDS
                        recheck_until = 0.0
                    command = "F"
        else:
            advancing_on_memory = approach_until > now_monotonic
            if advancing_on_memory:
                detection_state = "ADVANCING MEMORY"
                command = "F"
            else:
                approach_until = 0.0

            confirm_window_active = (
                target_first_seen_time is not None
                and target_last_seen_time is not None
                and now_monotonic - target_first_seen_time
                < (TARGET_CONFIRM_SECONDS + TARGET_CONFIRM_LOSS_SECONDS)
                and now_monotonic - target_last_seen_time
                <= TARGET_CONFIRM_LOSS_SECONDS
            )

            if advancing_on_memory:
                pass
            elif confirm_window_active:
                detection_state = "CONFIRMING MEMORY"
                if last_target_box is not None:
                    draw_box(
                        frame,
                        last_target_box,
                        f"{active_target_class} memory",
                        (120, 120, 255),
                    )
                command = "S"
            else:
                target_first_seen_time = None
                target_last_seen_time = None
                last_target_box = None
                last_target_center = None
                command = "T"

        current_time = time.time()
        if command != last_command or current_time - last_send_time >= SEND_INTERVAL:
            send_command(sock, command)
            last_command = command
            last_send_time = current_time

        web_control.update_status(
            command=command,
            target_detected=target_visible,
            fps=fps,
            confidence=confidence_score,
            candidate_area=candidate_area,
            detection_state=detection_state,
            target_class=active_target_class,
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

        cv2.line(
            frame,
            (frame_center_x, 0),
            (frame_center_x, frame_height),
            (255, 255, 255),
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
