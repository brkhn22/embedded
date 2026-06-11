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

The page changes to `OpenCV connected` when it receives vision heartbeats.
Target color, HSV tolerances, and minimum contour area are applied while OpenCV
is running. Press `q` in an OpenCV window to stop the vision process; the page
changes back to `OpenCV disconnected` within three seconds.

The server listens on all local interfaces. Another device on the same network
can use `http://<computer-ip>:8000`.

Activate the environment again with `source .venv/bin/activate` whenever you
open a new terminal. Do not use `sudo pip` or `--break-system-packages`.
