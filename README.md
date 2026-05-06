# touch-proximity-sensor

Works on Arduino Nano ESP32, ESP32-S3-DevKitC-1, or any board using the ESP32-S3 module.

## Serial Radar Web UI

`tools/serial_webui.py` is a small web UI that reads the ESP32 serial stream from `src/usb-hub-node.cpp` and renders available radar targets for connected sensor nodes. Each detected node shows distance, angle, speed, and an individual radar-like view.

Run:
```
python3 tools/serial_webui.py --port /dev/ttyACM0
```
