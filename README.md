# touch-proximity-sensor

Works on Arduino Nano ESP32, ESP32-S3-DevKitC-1, or any board using the ESP32-S3 module.

## Serial Monitor Web UI

`tools/serial_webui.py` is a small web UI that reads the ESP32 serial stream from `src/usb-hub-node.cpp` and renders realtime bar charts per channel, scaled to the live min/max range (or optional manual limits).

Run:
```
python3 tools/serial_webui.py --port /dev/ttyACM0
```
