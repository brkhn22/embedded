import cv2
import colorsys
import numpy as np
import socket
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from opencv.web_client import WebControlClient

# ESP32-CAM stream
STREAM_URL = "http://192.168.137.90:81/stream"

# ESP32 socket
ESP_IP = "192.168.137.90"
ESP_PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((ESP_IP, ESP_PORT))

print("Kameraya bağlanılıyor...")

cap = cv2.VideoCapture(STREAM_URL)

last_command = None
last_send_time = 0
SEND_INTERVAL = 0.1  # saniye


def hex_to_opencv_hsv(hex_color):
    red = int(hex_color[1:3], 16) / 255
    green = int(hex_color[3:5], 16) / 255
    blue = int(hex_color[5:7], 16) / 255
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    return round(hue * 179), round(saturation * 255), round(value * 255)


def create_color_mask(hsv_frame, settings):
    hue, saturation, value = hex_to_opencv_hsv(settings["targetColor"])
    hue_tolerance = settings["hueTolerance"]
    saturation_min = max(0, saturation - settings["saturationTolerance"])
    saturation_max = min(255, saturation + settings["saturationTolerance"])
    value_min = max(0, value - settings["valueTolerance"])
    value_max = min(255, value + settings["valueTolerance"])

    lower_hue = hue - hue_tolerance
    upper_hue = hue + hue_tolerance

    def in_range(hue_min, hue_max):
        lower = np.array([hue_min, saturation_min, value_min], dtype=np.uint8)
        upper = np.array([hue_max, saturation_max, value_max], dtype=np.uint8)
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

        settings = web_control.get_settings()
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

        command = 'L'  # Hedef yokken kendi etrafında dönerek ara
        target_detected = False

        if len(contours) > 0:
            c = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(c)

            if area >= settings["minContourArea"]:
                command = 'F'  # Hedef görüldü, ileri git
                target_detected = True

                (x, y), radius = cv2.minEnclosingCircle(c)

                cv2.circle(
                    frame,
                    (int(x), int(y)),
                    int(radius),
                    (255, 255, 0),
                    2
                )

                cv2.circle(
                    frame,
                    (int(x), int(y)),
                    5,
                    (255, 0, 0),
                    -1
                )

                cv2.putText(
                    frame,
                    "HEDEF GORULDU",
                    (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (255, 0, 0),
                    2
                )

        # Komutu ESP32'ye gönder
        current_time = time.time()

        if command != last_command or current_time - last_send_time >= SEND_INTERVAL:
            sock.send(command.encode())
            last_command = command
            last_send_time = current_time

        web_control.update_status(command, target_detected)

        cv2.putText(
            frame,
            f"CMD: {command} TARGET: {settings['targetColor'].upper()}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        cv2.imshow("Robotun Gozu", frame)
        cv2.imshow("Hedef Renk Maskesi", mask)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            sock.send('S'.encode())
            break
finally:
    web_control.stop()
    cap.release()
    sock.close()
    cv2.destroyAllWindows()
