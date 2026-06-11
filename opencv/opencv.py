import cv2
import colorsys
import numpy as np
import os
import socket
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from opencv.web_client import WebControlClient

# ESP32-CAM address. ESP_IP must not include "http://".
ESP_IP = os.environ.get("ESP_IP", "10.42.0.221")
ESP_PORT = int(os.environ.get("ESP_PORT", "8888"))
STREAM_URL = os.environ.get(
    "STREAM_URL",
    f"http://{ESP_IP}:81/stream",
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


sock = connect_to_esp()

print("Kameraya bağlanılıyor...")

cap = cv2.VideoCapture(STREAM_URL)

last_command = None
last_send_time = 0
SEND_INTERVAL = 0.1  # saniye
TARGET_CONFIRM_SECONDS = 0.5
TARGET_CONFIRM_LOSS_SECONDS = 0.5
APPROACH_BURST_SECONDS = 1.0
RECHECK_SECONDS = 0.5
CENTER_TOLERANCE_X_RATIO = 0.15
CENTER_TOLERANCE_Y_RATIO = 0.28
target_first_seen_time = None
target_last_seen_time = None
last_target_center = None
last_target_radius = 0
approach_until = 0.0
recheck_until = 0.0
last_frame_time = time.monotonic()
fps = 0.0


def hex_to_opencv_hsv(hex_color):
    red = int(hex_color[1:3], 16) / 255
    green = int(hex_color[3:5], 16) / 255
    blue = int(hex_color[5:7], 16) / 255
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    return round(hue * 179), round(saturation * 255), round(value * 255)


def hex_to_bgr(hex_color):
    red = int(hex_color[1:3], 16)
    green = int(hex_color[3:5], 16)
    blue = int(hex_color[5:7], 16)
    return blue, green, red


def create_color_mask(hsv_frame, settings):
    hue, _, _ = hex_to_opencv_hsv(settings["targetColor"])
    hue_tolerance = settings["hueTolerance"]
    saturation_min = settings["saturationMin"]
    value_min = settings["valueMin"]

    lower_hue = hue - hue_tolerance
    upper_hue = hue + hue_tolerance

    def in_range(hue_min, hue_max):
        lower = np.array([hue_min, saturation_min, value_min], dtype=np.uint8)
        upper = np.array([hue_max, 255, 255], dtype=np.uint8)
        return cv2.inRange(hsv_frame, lower, upper)

    if lower_hue < 0:
        return cv2.bitwise_or(
            in_range(0, upper_hue),
            in_range(180 + lower_hue, 179),
        )

    if upper_hue > 179:
        return cv2.bitwise_or(
            in_range(lower_hue, 179),
            in_range(0, upper_hue - 180),
        )

    return in_range(lower_hue, upper_hue)


web_control = WebControlClient()
web_control.start()
print("Web ayarlari: http://localhost:8000")

try:
    while True:
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

        settings = web_control.get_settings()
        overlay_color = hex_to_bgr(settings["targetColor"])
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = create_color_mask(hsv, settings)

        kernel = np.ones((3, 3), np.uint8)

        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(
            mask.copy(),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        target_visible = False
        low_density_candidate = False
        color_density = 0.0
        candidate_area = 0.0
        detection_state = "NO COLOR"
        frame_center_x = frame.shape[1] // 2
        frame_center_y = frame.shape[0] // 2
        target_center_x = None
        target_center_y = None

        if len(contours) > 0:
            c = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(c)
            candidate_area = area

            if area >= settings["minContourArea"]:
                x, y, width, height = cv2.boundingRect(c)
                candidate_mask = mask[y:y + height, x:x + width]
                color_density = (
                    cv2.countNonZero(candidate_mask) * 100.0
                    / (width * height)
                )

                if color_density >= settings["minColorDensity"]:
                    target_visible = True
                    detection_state = "VISIBLE"

                    (center_x, center_y), radius = cv2.minEnclosingCircle(c)
                    center = (int(center_x), int(center_y))
                    target_center_x = center[0]
                    target_center_y = center[1]
                    last_target_center = center
                    last_target_radius = int(radius)

                    # Black outline keeps the selected color visible on bright frames.
                    cv2.circle(
                        frame,
                        center,
                        int(radius),
                        (0, 0, 0),
                        5
                    )

                    cv2.circle(
                        frame,
                        center,
                        int(radius),
                        overlay_color,
                        2
                    )

                    cv2.circle(
                        frame,
                        center,
                        6,
                        (0, 0, 0),
                        -1
                    )

                    cv2.circle(
                        frame,
                        center,
                        4,
                        overlay_color,
                        -1
                    )

                    cv2.putText(
                        frame,
                        "HEDEF GORULDU",
                        (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 0, 0),
                        5
                    )

                    cv2.putText(
                        frame,
                        "HEDEF GORULDU",
                        (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        overlay_color,
                        2
                    )
                else:
                    low_density_candidate = True
                    detection_state = "DENSITY LOW"
            else:
                detection_state = "AREA LOW"

        now_monotonic = time.monotonic()
        if approach_until and now_monotonic >= approach_until:
            approach_until = 0.0
            recheck_until = now_monotonic + RECHECK_SECONDS

        if recheck_until and now_monotonic >= recheck_until:
            recheck_until = 0.0

        if recheck_until > now_monotonic:
            detection_state = "RECHECKING"
            command = 'S'
        elif target_visible:
            target_last_seen_time = now_monotonic
            if target_first_seen_time is None:
                target_first_seen_time = now_monotonic
                detection_state = "CONFIRMING"
                command = 'S'
            elif now_monotonic - target_first_seen_time < TARGET_CONFIRM_SECONDS:
                detection_state = "CONFIRMING"
                command = 'S'
            else:
                center_tolerance_x = int(frame.shape[1] * CENTER_TOLERANCE_X_RATIO)
                center_tolerance_y = int(frame.shape[0] * CENTER_TOLERANCE_Y_RATIO)
                center_error_x = target_center_x - frame_center_x
                center_error_y = target_center_y - frame_center_y
                centered_x = abs(center_error_x) <= center_tolerance_x
                centered_y = abs(center_error_y) <= center_tolerance_y

                if center_error_x < -center_tolerance_x:
                    detection_state = "TRACK LEFT"
                    command = 'L'
                elif center_error_x > center_tolerance_x:
                    detection_state = "TRACK RIGHT"
                    command = 'R'
                elif not centered_y and center_error_y > center_tolerance_y:
                    detection_state = "TOO CLOSE IN FRAME"
                    command = 'S'
                else:
                    detection_state = "ADVANCING" if centered_y else "APPROACHING"
                    if approach_until <= now_monotonic:
                        approach_until = now_monotonic + APPROACH_BURST_SECONDS
                        recheck_until = 0.0
                    command = 'F'
        else:
            advancing_on_memory = approach_until > now_monotonic
            if advancing_on_memory:
                detection_state = "ADVANCING MEMORY"
                command = 'F'
            else:
                approach_until = 0.0
            confirm_window_active = (
                target_first_seen_time is not None
                and target_last_seen_time is not None
                and now_monotonic - target_first_seen_time < (
                    TARGET_CONFIRM_SECONDS + TARGET_CONFIRM_LOSS_SECONDS
                )
                and now_monotonic - target_last_seen_time <= TARGET_CONFIRM_LOSS_SECONDS
                )

            if advancing_on_memory:
                pass
            elif confirm_window_active:
                detection_state = "CONFIRMING MEMORY"
                if last_target_center is not None:
                    cv2.circle(
                        frame,
                        last_target_center,
                        max(last_target_radius, 12),
                        overlay_color,
                        1
                )
                command = 'S'
            else:
                target_first_seen_time = None
                target_last_seen_time = None
                last_target_center = None
                last_target_radius = 0
                command = 'T'

        # Komutu ESP32'ye gönder
        current_time = time.time()

        if command != last_command or current_time - last_send_time >= SEND_INTERVAL:
            send_command(sock, command)
            last_command = command
            last_send_time = current_time

        web_control.update_status(
            command,
            target_visible,
            fps,
            color_density,
            candidate_area,
            detection_state,
        )

        cv2.putText(
            frame,
            (
                f"CMD: {command} TARGET: {settings['targetColor'].upper()} "
                f"{detection_state}"
            ),
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        cv2.putText(
            frame,
            (
                f"FPS: {fps:.1f}  DENSITY: {color_density:.1f}% "
                f"(MIN {settings['minColorDensity']}%)  "
                f"AREA: {candidate_area:.0f} (MIN {settings['minContourArea']})  "
                f"CX: {target_center_x if target_center_x is not None else '--'}  "
                f"CY: {target_center_y if target_center_y is not None else '--'}"
            ),
            (10, 105),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2
        )

        cv2.imshow("Robotun Gozu", frame)
        cv2.imshow("Hedef Renk Maskesi", mask)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            send_command(sock, 'S')
            break
finally:
    web_control.stop()
    cap.release()
    sock.close()
    cv2.destroyAllWindows()
