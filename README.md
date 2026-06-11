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

The page changes to `OpenCV connected` when it receives vision heartbeats.
Target color, HSV tolerances, and minimum contour area are applied while OpenCV
is running. Press `q` in an OpenCV window to stop the vision process; the page
changes back to `OpenCV disconnected` within three seconds.

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
2. Move forward when OpenCV sends `F` after finding the target color.
3. Rotate when OpenCV sends `L` because the target color is not visible.
4. Stop when `S` is received or no valid command arrives for one second.

Change `stopDistanceCm` in `arduino/arduino.ino` to adjust the stopping
distance. OpenCV sends commands in the framed format `<F>`, `<L>`, and `<S>`;
Arduino interprets them. The ESP32-CAM only forwards bytes between TCP and
serial, so adding or changing movement commands does not require changing the
camera sketch.

Rotation uses `180 PWM` and briefly starts at `230 PWM` to overcome static
friction. Adjust `rotateSpeed` and `rotateKickSpeed` if the chassis still turns
too slowly or aggressively.

## ESP32-CAM sketch

Open `esp32/CameraWebServer/CameraWebServer.ino` in Arduino IDE. Its required
headers, HTTP server source, camera page, and partition table are stored in the
same sketch folder so Arduino IDE can compile them together.
