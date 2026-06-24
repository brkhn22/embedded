# YOLO object detection

This folder runs a separate object-detection control loop without modifying the
existing `opencv/` color-tracking flow.

## Setup

Use the existing virtual environment, then install the YOLO dependency:

```bash
source .venv/bin/activate
python -m pip install -r yolo/requirements.txt
```

## Run

Default target class is `bottle`:

```bash
source .venv/bin/activate
python yolo/detect.py
```

## Web panel

Object selection now has its own local panel, separate from the color panel:

```bash
./yolo/start_web.sh
```

Then open:

```text
http://localhost:8001
```

From this panel you can:

- choose any COCO object class
- change YOLO confidence threshold
- see whether the YOLO detector is connected
- see live command / FPS / detection state

Optional environment variables:

```bash
ESP_IP=10.42.0.221
YOLO_MODEL=yolo11n.pt
YOLO_TARGET_CLASS=bottle
YOLO_CONFIDENCE=0.45
YOLO_SEARCH_TURN_SECONDS=0.5
YOLO_SEARCH_PAUSE_SECONDS=0.25
YOLO_TRACK_TURN_SECONDS=0.12
YOLO_TRACK_PAUSE_SECONDS=0.15
YOLO_TURN_REVERSAL_CONFIRM_FRAMES=3
YOLO_TURN_REVERSAL_STOP_SECONDS=0.15
YOLO_CENTER_CONFIRM_FRAMES=3
YOLO_CENTER_CONFIRM_WINDOW=5
YOLO_CENTER_TOLERANCE_X_RATIO=0.12
YOLO_CENTER_TOLERANCE_Y_RATIO=0.16
YOLO_OBSTACLE_ALERT_SECONDS=3.0
YOLO_OBSTACLE_REVERSE_SECONDS=1.0
YOLO_OBSTACLE_SEARCH_SECONDS=2.0
YOLO_WEB_URL=http://127.0.0.1:8001
```

## Behavior

- `T`: turn for `0.5s` while searching
- `S`: stop when the target is too close in the frame
- `B`: reverse after a completed distance-stop alert
- `L` / `R`: use short turn pulses to center the target
- `F`: move forward while the target remains in the approach region
- after a centered target is confirmed, lock into `F` even if the target
  disappears because it is close to the camera
- the Arduino ultrasonic threshold remains responsible for stopping the motors
- Arduino reports `<B1>` when the distance stop activates and `<B0>` when it
  clears; YOLO resets its center/approach state, holds `S` for
  `YOLO_OBSTACLE_ALERT_SECONDS`, reverses for `YOLO_OBSTACLE_REVERSE_SECONDS`,
  then forces the search cycle for `YOLO_OBSTACLE_SEARCH_SECONDS`

Bidirectional feedback requires the Arduino software-serial TX pin (`3`) to be
connected through a 5V-to-3.3V level shifter or voltage divider to the
ESP32-CAM UART RX pin, in addition to the existing ESP32 TX to Arduino RX
connection and common ground.
- do not preserve `L`, `R`, or `S` after losing the target
- without an active approach lock, alternate between a `0.5s` search turn
  and a `0.25s` stopped inspection period
- configure the search cycle with `YOLO_SEARCH_TURN_SECONDS` and
  `YOLO_SEARCH_PAUSE_SECONDS`
- while centering, alternate between a `0.12s` turn and a `0.15s` stopped
  inspection period
- require the target to be inside the horizontal center region in at least
  `3` of the latest `5` frames before moving forward
- the default horizontal center region is the middle `24%` of the image and
  is shown between two blue boundary lines
- release the approach lock only when a visible target requires `L` or `R`;
  visual closeness does not override the ultrasonic stop
- before reversing turn direction, stop for at least `0.15s` and require the
  new direction for `3` consecutive frames

The script follows the largest detected instance of the selected YOLO class.
