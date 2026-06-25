# Spectra Architecture

## Scope

This document describes the current project architecture for the final robot
configuration. The active vision and control flow is the YOLO-based system in
`yolo/`. The older `opencv/` color-tracking folder is not part of the current
runtime architecture.

The YOLO runtime still uses the `cv2` Python package to read the ESP32-CAM
MJPEG stream and draw the local debug window. That is different from using the
old `opencv/` application flow.

## High-Level System

Spectra is a Wi-Fi controlled mobile robot that uses a laptop for object
detection and decision making, an ESP32-CAM for video streaming and wireless
serial bridging, and an Arduino Uno for low-level motor and sensor control.

```text
                 Wi-Fi HTTP/MJPEG                 TCP socket commands
Laptop YOLO  <--------------------  ESP32-CAM  <---------------------
detector/UI                         camera + bridge                    |
    |                                    |                              |
    | HTTP API / heartbeat              | UART 115200 baud             |
    v                                    v                              |
YOLO web panel                    Arduino Uno  ------------------------
localhost:8001                    motor + sensor controller
                                         |
                                         v
                              L298N motor driver
                                         |
                                         v
                           left/right DC motor groups
```

## Hardware Architecture

### Main Components

- Laptop: Runs YOLO object detection, the local web control panel, and the
  high-level movement decision loop.
- ESP32-CAM: Captures camera frames, streams MJPEG over Wi-Fi, and bridges TCP
  commands between the laptop and Arduino over UART.
- Arduino Uno: Parses framed commands, drives the L298N motor driver, reads
  the HC-SR04 ultrasonic distance sensor, and controls the RGB LED and buzzer.
- L298N motor driver: Drives the robot's DC motor channels using PWM from the
  Arduino.
- Two 2WD chassis units: Provide the mobile platform. In the current control
  model, motors are handled as left and right motor groups through the two
  L298N channels.
- HC-SR04 ultrasonic distance sensor: Provides the local obstacle stop layer.
- Common-anode RGB LED: Shows target/search status.
- Buzzer: Provides an audible obstacle alert.
- Power system: Two 3.7 V Li-ion cells for the motor/ESP power rail, a 9 V
  Duracell battery for the Arduino/sensor/status electronics, and an XL4016
  buck converter to provide regulated 5 V to the ESP32-CAM.

### Power Distribution

The robot uses separated power paths for noisy motor load and Arduino-side
logic/sensors.

```text
2 x 3.7 V Li-ion cells
        |
        +--> L298N motor supply input
        |
        +--> XL4016 buck converter --> regulated 5 V --> ESP32-CAM 5 V input

9 V Duracell battery
        |
        +--> Arduino Uno power input
              |
              +--> HC-SR04 VCC/GND
              +--> RGB LED common anode/channels
              +--> buzzer
              +--> L298N logic/control reference
```

All communication and control electronics must share a common ground:

- Arduino GND
- ESP32-CAM GND
- L298N GND
- Li-ion battery negative
- 9 V battery negative
- HC-SR04 GND

The XL4016 is used only to step the Li-ion rail down to 5 V for the ESP32-CAM.
The ESP32-CAM should receive regulated 5 V, not the raw Li-ion pack voltage.

If all four DC motors from the two 2WD chassis are installed, the architecture
assumes the motors on each side are grouped together and driven as one left
channel and one right channel by the L298N. The firmware does not control four
motors independently.

### Arduino Pin Map

The active Arduino pin assignments are defined in `arduino/arduino.ino`.

| Function | Arduino Pin |
| --- | --- |
| ESP32-CAM SoftwareSerial RX | `2` |
| ESP32-CAM SoftwareSerial TX | `3` |
| L298N ENA PWM | `9` |
| L298N IN1 | `7` |
| L298N IN2 | `8` |
| L298N ENB PWM | `6` |
| L298N IN3 | `5` |
| L298N IN4 | `4` |
| HC-SR04 TRIG | `10` |
| HC-SR04 ECHO | `11` |
| Buzzer | `12` |
| RGB LED green channel | `A0` |
| RGB LED red channel | `A1` |

The RGB LED is common-anode. The Arduino drives a color channel `LOW` to turn
that color on and `HIGH` to turn it off.

## Software Architecture

### Laptop: YOLO Detection and Control Loop

Main file: `yolo/detect.py`

Responsibilities:

- Loads the Ultralytics YOLO model. The default model path is `yolo11n.pt`.
- Opens the ESP32-CAM MJPEG stream with `cv2.VideoCapture`.
- Runs object detection on every frame.
- Selects the largest detected instance of the active COCO class.
- Computes the target center relative to the frame center.
- Converts detection state into movement commands.
- Sends movement and LED commands to the ESP32-CAM TCP bridge.
- Receives obstacle feedback from Arduino through the same TCP bridge.
- Sends heartbeat/status updates to the YOLO web server.
- Draws a local debug window with target boxes, center guides, command, FPS,
  confidence, and detection state.

Default runtime values:

| Setting | Default |
| --- | --- |
| ESP32-CAM IP | `10.42.0.221` |
| Command TCP port | `8888` |
| Camera stream URL | `http://<ESP_IP>:81/stream` |
| Web control URL | `http://127.0.0.1:8001` |
| Target class | `bottle` |
| Confidence threshold | `0.45` |
| Search turn duration | `0.35 s` |
| Search pause duration | `0.5 s` |
| Track turn duration | `0.08 s` |
| Track pause duration | `0.15 s` |
| Obstacle alert duration | `3.0 s` |
| Obstacle reverse duration | `1.0 s` |
| Obstacle search duration | `2.0 s` |

### `detect.py` Runtime Variables

The YOLO control loop keeps a larger set of runtime variables than the
high-level architecture alone shows. The most important variables are grouped
below so the control flow in `yolo/detect.py` is easier to understand and
defend during presentation or code review.

#### Runtime Inputs and Configuration

- `ESP_IP`, `ESP_PORT`, `STREAM_URL`: Define where the laptop reaches the
  ESP32-CAM command bridge and MJPEG stream.
- `MODEL_PATH`: YOLO model file path. Default is `yolo11n.pt`.
- `TARGET_CLASS`, `CONFIDENCE`: Startup defaults for the selected COCO class
  and detection confidence threshold.
- `WEB_CONTROL_URL`: Address of the local YOLO control panel backend.
- `SEND_INTERVAL`: Minimum resend interval for repeated commands.
- `SEARCH_TURN_SECONDS`, `SEARCH_PAUSE_SECONDS`: Search-cycle pulse timings.
- `TRACK_TURN_SECONDS`, `TRACK_PAUSE_SECONDS`: Centering turn/pause timings.
- `TARGET_REACQUIRE_HOLD_SECONDS`, `REACQUIRE_NUDGE_SECONDS`: Short-term memory
  timings used after the target is lost.
- `TURN_REVERSAL_CONFIRM_FRAMES`, `TURN_REVERSAL_STOP_SECONDS`: Protection
  against rapid left-right oscillation.
- `CENTER_CONFIRM_FRAMES`, `CENTER_CONFIRM_WINDOW`: Number of centered frames
  required before committing to forward motion.
- `CENTER_TOLERANCE_X_RATIO`, `CENTER_TOLERANCE_Y_RATIO`: Horizontal and
  vertical acceptance regions relative to frame size.
- `OBSTACLE_ALERT_SECONDS`, `OBSTACLE_REVERSE_SECONDS`,
  `OBSTACLE_SEARCH_SECONDS`: Recovery timings after Arduino distance-stop.

#### Threshold Mode Variables

The current detector also switches the Arduino between two obstacle threshold
modes by sending extra serial commands.

- `THRESHOLD_MODE_SEARCH_COMMAND = "Q"`: Requests the search obstacle mode.
- `THRESHOLD_MODE_MOTION_COMMAND = "W"`: Requests the motion obstacle mode.
- `SEARCH_STOP_THRESHOLD_CM`, `SEARCH_RESUME_THRESHOLD_CM`: Search-mode
  obstacle thresholds. These are tighter than motion mode.
- `MOTION_STOP_THRESHOLD_CM`, `MOTION_RESUME_THRESHOLD_CM`: Motion-mode
  thresholds used while approaching a target.
- `last_threshold_mode_command`: Last threshold-mode command sent to avoid
  redundant writes.
- `last_threshold_mode_send_time`: Last send time for threshold-mode updates.
- `last_search_threshold_mode`: Remembers which threshold profile Arduino was
  using when an obstacle feedback event arrived.

#### Vision and Frame State

- `cap`: OpenCV video reader connected to the ESP32-CAM stream.
- `fps`: Smoothed frame-rate estimate used for telemetry.
- `frame_id`: Incrementing frame counter for structured metrics logging.
- `target_class_id`: Numeric model class ID matching the currently selected
  COCO class.
- `active_target_class`, `active_confidence`: The live class and confidence
  currently in effect after web-panel updates are applied.
- `best_box`, `candidate_area`, `confidence_score`: The chosen detection box,
  its pixel area, and its confidence score for the current frame.
- `target_visible`: Whether a valid target was found in the current frame.
- `target_center_x`, `target_center_y`: Center of the chosen detection box.
- `center_error_x`, `center_error_y`: Horizontal and vertical offset from the
  image center. These are core tracking metrics.
- `memory_error_x`: Horizontal error of the last remembered target position
  when the target is temporarily lost.

#### Command and Output State

- `last_command`, `last_send_time`: Prevent command flooding and support
  periodic refresh.
- `last_led_command`, `last_led_send_time`: Same pattern for RGB LED status
  commands.
- `feedback_buffer`: Partial TCP feedback buffer used while parsing framed
  serial messages coming back through ESP32-CAM.
- `decision_source`: Labels whether the current command came from live
  detection, memory, search, or recovery logic.
- `detection_state`: Human-readable control state such as `TRACK LEFT`,
  `ADVANCING`, `SEARCH TURN`, or `OBSTACLE ALERT`.

#### Target Tracking Memory

- `last_target_box`: Most recent valid bounding box, used for visual memory.
- `last_target_center`: Most recent valid target center, used for reacquire
  nudges.
- `last_target_command`: Last target-driven motion command before the target
  disappeared.
- `last_target_seen_at`: Monotonic timestamp of the last valid target sighting.
- `approach_locked`: Allows the robot to keep moving forward briefly even if
  the target disappears at close range.
- `center_confirm_history`: Sliding window of recent centered/not-centered
  observations used before moving forward.

#### Search and Turn Control

- `search_phase`, `search_phase_started`: Alternate the robot between search
  turning and search pause.
- `active_turn_direction`: Tracks the turn direction currently being executed.
- `pending_turn_direction`, `pending_turn_frames`, `pending_turn_since`:
  Confirm a reversal before switching from left to right or vice versa.
- `track_phase`, `track_phase_started`, `track_phase_direction`: Alternate
  tracking turns and pauses while centering the target.
- `reacquire_nudge_direction`, `reacquire_nudge_until`: Short corrective nudge
  state used when the target has just been lost.

#### Obstacle Recovery State

- `arduino_obstacle_blocked`: Latest obstacle-blocked status reported from the
  Arduino.
- `obstacle_recovery_phase`: Current recovery sub-state, such as `ALERT` or
  `REVERSE`.
- `obstacle_alert_started`, `obstacle_reverse_started`: Timestamps for those
  recovery phases.
- `obstacle_search_until`: Prevents immediate target reacquisition after a
  recovery cycle and forces a short search period.
- `latest_distance_cm`, `latest_distance_monotonic_ns`: Most recent HC-SR04
  distance value and its arrival time, captured from Arduino telemetry.

#### Queue Mode State

- `active_control_mode`: Current operating mode, `single` or `queue`.
- `queue_targets`: Ordered COCO target list selected in queue mode.
- `queue_index`: Index of the currently active queued target.
- `queue_run_id`: Monotonic run identifier incremented whenever a new queue
  execution starts.
- `queue_finished`: Whether the active queue run has completed.
- `queue_target_seen`: Whether the current queued target has been seen at all.
- `queue_target_last_seen_at`: Last time the current queued target was visible.
- `queue_target_forward_started`: Whether the current queued target has
  produced at least one forward approach command. This is used before allowing
  queue advancement after obstacle recovery.

#### Logging and Telemetry State

- `DEBUG_LOG_PATH`: Plain-text debug log path.
- `METRICS_LOG_PATH`: Structured JSONL metrics log path.
- `last_logged_signature`: Deduplicates repeated debug lines so the plain-text
  log stays readable.
- `append_debug_log(...)`: Writes human-readable state transitions.
- `append_metrics_log(...)`: Writes structured event records used by
  `yolo/analyze_metrics.py`.

### Laptop: YOLO Web Server

Main file: `yolo/control_server.py`

The web server is a lightweight Python `ThreadingHTTPServer`, not FastAPI. It
serves the static frontend and exposes JSON endpoints for settings and status.

Default address:

```text
http://localhost:8001
```

API endpoints:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/settings` | `GET` | Read current YOLO settings |
| `/api/settings` | `POST` | Update target class, confidence, mode, or queue |
| `/api/status` | `GET` | Read latest detector heartbeat/status |
| `/api/classes` | `GET` | List supported COCO classes |
| `/api/heartbeat` | `POST` | Receive detector status and return current settings |

The server tracks the detector as connected if it receives a heartbeat within
the last 3 seconds.

### Laptop: YOLO Frontend

Main files:

- `yolo/web/index.html`
- `yolo/web/app.js`
- `yolo/web/styles.css`

The frontend is plain HTML, CSS, and vanilla JavaScript. It is not React.

User-facing features:

- Single-target mode.
- Queue mode for multiple COCO targets.
- COCO target class selection.
- Confidence threshold slider.
- Start/stop queue controls.
- Live detector connection state.
- Live command, target, queue progress, FPS, confidence, candidate area, and
  detection state.

### ESP32-CAM Firmware

Main files:

- `esp32/CameraWebServer/CameraWebServer.ino`
- `esp32/CameraWebServer/app_httpd.cpp`
- `esp32/CameraWebServer/board_config.h`
- `esp32/CameraWebServer/camera_pins.h`

Responsibilities:

- Initializes the AI Thinker ESP32-CAM board profile.
- Configures the camera for JPEG streaming.
- Connects to Wi-Fi.
- Starts the ESP camera HTTP server.
- Serves the MJPEG stream at `/stream` on the stream server port.
- Starts a raw TCP server on port `8888`.
- Forwards bytes from TCP to hardware serial.
- Forwards bytes from hardware serial back to TCP.

The ESP32-CAM is deliberately simple in the command path. It does not interpret
robot commands; it acts as a wireless bridge between the laptop and Arduino.

### Arduino Firmware

Main file: `arduino/arduino.ino`

Responsibilities:

- Receives framed serial commands from ESP32-CAM using `SoftwareSerial`.
- Parses movement commands and LED commands.
- Drives the L298N motor driver through PWM and direction pins.
- Reads HC-SR04 distance every 60 ms.
- Stops motion when an obstacle is detected at 20 cm or less.
- Resumes only after distance rises above 25 cm.
- Reports obstacle state back to the laptop as `<B1>` or `<B0>`.
- Sounds the buzzer for up to 3 seconds after obstacle stop activation.
- Stops the motors if no valid movement command arrives for 1 second.

Motor speeds:

| Motion | PWM |
| --- | --- |
| Forward | `120` |
| Reverse | `110` |
| Search turn | `150` |
| Track turn | `150` |

## Communication Architecture

### Video Stream

The ESP32-CAM provides an MJPEG stream:

```text
ESP32-CAM -> Wi-Fi -> Laptop
http://<ESP_IP>:81/stream
```

The laptop reads this stream in `yolo/detect.py` and runs YOLO inference on the
frames.

### Web Control

The browser talks only to the laptop web server:

```text
Browser <-> http://localhost:8001 <-> yolo/control_server.py
```

The detector process also talks to that same server through `yolo/web_client.py`
to send heartbeat/status data and receive updated settings.

### Command and Feedback Link

Movement commands use a raw TCP socket:

```text
Laptop yolo/detect.py -> TCP <ESP_IP>:8888 -> ESP32-CAM -> UART -> Arduino
```

Feedback uses the same bridge in reverse:

```text
Arduino -> UART -> ESP32-CAM -> TCP <ESP_IP>:8888 -> Laptop yolo/detect.py
```

UART baud rate between ESP32-CAM and Arduino is `115200`.

Arduino `SoftwareSerial` pins:

- Arduino pin `2`: receives from ESP32-CAM TX.
- Arduino pin `3`: transmits to ESP32-CAM RX.

Because Arduino Uno serial output is 5 V logic and ESP32-CAM RX is 3.3 V logic,
the Arduino TX to ESP32-CAM RX direction should pass through a level shifter or
voltage divider.

## Command Protocol

Commands are ASCII messages framed with angle brackets:

```text
<F>
<S>
<B1>
```

### Laptop to Arduino Commands

| Command | Meaning | Arduino action |
| --- | --- | --- |
| `<F>` | Forward | Drive both motor groups forward |
| `<B>` | Backward/recovery reverse | Drive both motor groups backward |
| `<L>` | Track left | Rotate left |
| `<R>` | Track right | Rotate right |
| `<T>` | Search turn | Rotate left for search |
| `<S>` | Stop | Stop both motor groups |
| `<G>` | Target found/status green | Turn RGB LED green |
| `<N>` | Searching/status red | Turn RGB LED red |

### Arduino to Laptop Feedback

| Feedback | Meaning |
| --- | --- |
| `<B1>` | Obstacle stop is active |
| `<B0>` | Obstacle stop is clear |

## Control Logic

### Single Target Mode

In single mode, the detector follows one selected COCO class.

1. The browser selects a target class and confidence threshold.
2. `yolo/control_server.py` stores the settings.
3. `yolo/detect.py` receives settings through heartbeat responses.
4. The detector finds the largest visible instance of the selected class.
5. The detector compares the target center with the frame center.
6. The detector sends `L`, `R`, `F`, `T`, or `S` depending on state.
7. Arduino executes the movement unless the ultrasonic stop layer blocks it.

### Queue Mode

Queue mode allows multiple target classes to be selected in order.

1. The user builds a queue in the web panel.
2. Starting the queue switches the control mode to `queue`.
3. The detector searches for the first queued class.
4. A queued target is considered completed only after it has produced at least
   one forward approach command and then the obstacle recovery cycle completes.
5. The detector advances to the next queued class.
6. When all queued targets are complete, the detector sends `S` and reports
   `QUEUE COMPLETE`.

### Search Behavior

When the selected target is not visible, the detector alternates between:

- `SEARCH TURN`: send `T`.
- `SEARCH PAUSE`: send `S`.

This gives the camera time to inspect the scene between turn pulses.

### Centering and Approach

When a target is visible:

- If the target is left of the center region, YOLO sends `L`.
- If the target is right of the center region, YOLO sends `R`.
- If the target is centered enough for enough recent frames, YOLO sends `F`.
- If the target is too low in the image and approach is not locked, YOLO sends
  `S` to avoid pushing forward blindly.
- Once approach is locked, the robot may continue forward briefly even if the
  object disappears from the camera because it is close to the lens.

### Obstacle Safety Layer

The Arduino is the final local safety layer for obstacles.

- If HC-SR04 distance is 20 cm or less, Arduino sets obstacle blocked state.
- While blocked, Arduino stops motor movement commands.
- Arduino reports `<B1>` to the laptop.
- Arduino clears blocked state only after distance rises above 25 cm.
- Arduino reports `<B0>` when clear.
- The buzzer sounds for up to 3 seconds after the obstacle stop starts.

The YOLO process reacts to `<B1>` by clearing target approach state, holding
stop during the alert phase, reversing with `<B>` after the alert duration, and
then forcing a short search period.

## Runtime Startup

Start the YOLO web panel:

```bash
source .venv/bin/activate
./yolo/start_web.sh
```

Open the panel:

```text
http://localhost:8001
```

Start the detector in a second terminal:

```bash
source .venv/bin/activate
python yolo/detect.py
```

Useful environment variables:

```bash
ESP_IP=10.42.0.221
ESP_PORT=8888
STREAM_URL=http://10.42.0.221:81/stream
YOLO_WEB_URL=http://127.0.0.1:8001
YOLO_MODEL=yolo11n.pt
YOLO_TARGET_CLASS=bottle
YOLO_CONFIDENCE=0.45
```

## Design Rationale

- The laptop performs YOLO inference because it has much more compute capacity
  than the ESP32-CAM or Arduino.
- The ESP32-CAM only streams video and bridges commands, keeping the embedded
  camera firmware simple.
- The Arduino owns motor timing and ultrasonic safety because those functions
  must continue even if the laptop vision loop slows down.
- The command protocol is intentionally small and framed as `<...>` messages so
  the Arduino parser can reject malformed serial data.
- The web panel is served locally from the laptop to make target selection and
  tuning possible during demonstrations without reflashing embedded firmware.

## Non-Active Code Paths

The `opencv/` folder and the root `web/` color-control panel are legacy
color-tracking components. They are useful as historical reference, but they
are not part of the current YOLO architecture described here.
