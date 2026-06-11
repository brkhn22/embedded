import cv2
import numpy as np
import socket
import time

# ESP32-CAM stream
STREAM_URL = "http://192.168.137.90:81/stream"

# ESP32 socket
ESP_IP = "192.168.137.90"
ESP_PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((ESP_IP, ESP_PORT))

print("Kameraya bağlanılıyor...")

cap = cv2.VideoCapture(STREAM_URL)

# Mavi nesne algılama için minimum alan
MIN_CONTOUR_AREA = 300

last_command = None
last_send_time = 0
SEND_INTERVAL = 0.1  # saniye

while True:
    ret, frame = cap.read()

    if not ret:
        print("Kameradan goruntu alinamadi!")
        break

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Mavi renk aralığı
    lower_blue = np.array([90, 80, 50])
    upper_blue = np.array([130, 255, 255])

    mask = cv2.inRange(hsv, lower_blue, upper_blue)

    kernel = np.ones((3, 3), np.uint8)

    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(
        mask.copy(),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    command = 'L'  # Başta ve mavi yokken kendi etrafında dönerek ara

    if len(contours) > 0:
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)

        if area >= MIN_CONTOUR_AREA:
            command = 'F'  # Mavi görüldü, ileri git

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
                "MAVI GORULDU",
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

    cv2.putText(
        frame,
        f"CMD: {command}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.imshow("Robotun Gozu", frame)
    cv2.imshow("Mavi Maske", mask)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        sock.send('S'.encode())
        break

cap.release()
sock.close()
cv2.destroyAllWindows()