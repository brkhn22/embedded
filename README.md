# Megatron embedded

## Dynamic target color

The standalone local control page changes the color that the robotic car
follows and reports whether the OpenCV vision process is connected.

1. Create and activate a project-local Python environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

2. Start the web control panel:

   ```bash
   ./web/start.sh
   ```

3. Open [http://localhost:8000](http://localhost:8000). The page works without
   OpenCV and shows `OpenCV disconnected` until the vision process starts.

4. In a second terminal, start the vision process:

   ```bash
   source .venv/bin/activate
   python opencv/opencv.py
   ```

   The default ESP32 address is `10.42.0.221`. To use another address:

   ```bash
   ESP_IP=192.168.1.50 python opencv/opencv.py
   ```

   `ESP_IP` must contain only the IP address, without `http://`.

5. For object detection in a separate folder, use the YOLO flow:

   ```bash
   source .venv/bin/activate
   python -m pip install -r yolo/requirements.txt
   python yolo/detect.py
   ```

   This path leaves the existing `opencv/` color tracker untouched.

The page changes to `OpenCV connected` when it receives vision heartbeats.
Target color, HSV thresholds, and steering behavior are applied while OpenCV is
running. Press `q` in an OpenCV window to stop the vision process; the page
changes back to `OpenCV disconnected` within three seconds.

`Minimum color density` controls how much of a detected object's bounding box
must contain the selected color before OpenCV sends `F`. The camera window and
web connection card show live FPS, measured color density, candidate area, and
the detection state:

- `VISIBLE`: all thresholds passed; OpenCV sends `F`.
- `CONFIRMING`: the car has stopped after first seeing the target.
- `CONFIRMING MEMORY`: the last valid target position is being held briefly.
- `TRACK LEFT` / `TRACK RIGHT`: the target is visible but off-center.
- `CENTERED`: the target is centered, so OpenCV sends `F`.
- `AREA LOW`: lower `Minimum object area` if the target is genuinely visible.
- `DENSITY LOW`: lower `Minimum color density` or tune the HSV minimums.
- `NO COLOR`: the selected hue is not present in the mask.

The selected hex color defines the HSV hue center only. `Minimum saturation`
and `Minimum brightness` are lower camera thresholds; saturation and brightness
have no upper limit. This makes detection less sensitive to lighting changes.

The server listens on all local interfaces. Another device on the same network
can use `http://<computer-ip>:8000`.

Activate the environment again with `source .venv/bin/activate` whenever you
open a new terminal. Do not use `sudo pip` or `--break-system-packages`.

## Arduino movement and HC-SR04

Connect the HC-SR04 to the Arduino:

- `VCC` to `5V`
- `GND` to `GND`
- `TRIG` to pin `10`
- `ECHO` to pin `11`

The movement priority is:

1. Stop when the HC-SR04 reads `20 cm` or less. Movement resumes only after
   the measured distance exceeds `25 cm`, preventing sensor noise from rapidly
   toggling the motors.
2. Rotate with `T` when the target color is not visible, even if the ultrasonic
   threshold is already passed.
3. Stop briefly with `S` when the target color is first detected so the camera
   can settle.
4. Steer with `L` or `R` to center the visible target horizontally in the image.
5. Move forward with `F` in `1.0` second bursts when the target is centered
   horizontally and reasonably centered vertically.
6. Stop if the HC-SR04 threshold is passed while steering toward or moving
   toward the target.
7. Stop when `S` is received or no valid command arrives for one second.

Change `stopDistanceCm` in `arduino/arduino.ino` to adjust the stopping
distance. OpenCV sends framed commands such as `<T>`, `<L>`, `<R>`, `<F>`, and
`<S>`; Arduino interprets them. The ESP32-CAM only forwards bytes between TCP
and serial, so adding or changing movement commands does not require changing
the camera sketch.

Search rotation uses `150 PWM`, target-tracking turns use `130 PWM`, and both
get a short `180 PWM` kick to overcome static friction. When a target first
becomes visible, OpenCV stops for `0.5` seconds, keeps the last valid target
position for another `0.5` seconds if needed, then steers left/right until the
target is centered and moves in `1.0` second forward bursts separated by `0.5`
second re-check pauses. Adjust `searchTurnSpeed`, `trackTurnSpeed`,
`turnKickSpeed`, `TARGET_CONFIRM_SECONDS`, `TARGET_CONFIRM_LOSS_SECONDS`,
`APPROACH_BURST_SECONDS`, `RECHECK_SECONDS`, `CENTER_TOLERANCE_X_RATIO`, or
`CENTER_TOLERANCE_Y_RATIO` if needed.

The ESP32-CAM and Arduino serial bridge uses `9600 baud`, which is reliable for
Arduino `SoftwareSerial`. Upload both sketches after changing this baud rate.

## ESP32-CAM sketch

Open `esp32/CameraWebServer/CameraWebServer.ino` in Arduino IDE. Its required
headers, HTTP server source, camera page, and partition table are stored in the
same sketch folder so Arduino IDE can compile them together.
