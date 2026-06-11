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
YOLO_WEB_URL=http://127.0.0.1:8001
```

## Behavior

- `T`: search turn when no target is visible
- `S`: brief stop when a target first appears
- `L` / `R`: steer left or right to center the target
- `F`: move forward in `1.0s` bursts
- `0.5s` re-check pause after each forward burst

The script follows the largest detected instance of the selected YOLO class.
