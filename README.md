# touch-proximity-sensor

Reads distance/angle/speed from one or more RD-03D mmWave radar sensor
nodes over ESP-NOW, aggregates them on a USB-connected hub node, and
displays live target data through a serial web UI or a small onboard TFT.
Works on Arduino Nano ESP32, ESP32-S3-DevKitC-1, or any ESP32-S3-module
board.

## Hardware

Two firmware roles, selected at compile time in `src/main.cpp`
(`#define SENSOR_NODE` or `#define HUB_NODE`):

- **Sensor node** — an ESP32-S3 board + RD-03D radar module (UART,
  RX=GPIO1, TX=GPIO2 per `src/sensor-node.cpp`). Reads the radar and
  broadcasts `{ms, mac id, distance, angle, speed, detected}` packets over
  ESP-NOW to the hub.
- **Hub node** — an ESP32-S3 board connected to a PC over USB. Receives
  ESP-NOW packets from all sensor nodes in range and forwards them over
  serial (`src/usb-hub-node.cpp`).
- Optional onboard display: `code/esp32-s3-tft-display`-style TFT output
  (see `PCB/esp32-s3 touch.fzz` / `esp32-s3 touch-v2.fzz` for board
  revisions with a TFT).
- Custom PCBs (Fritzing, `PCB/`): `arduino-nano-touch.fzz`,
  `esp32-s3 touch.fzz`, `esp32-s3 touch-v2.fzz` — check these for the
  actual sensor/board wiring, since no separate wiring diagram is
  documented in this README.

## Firmware

`src/main.cpp` picks a role via `#define`:

```cpp
#define HUB_NODE 1
//#define SENSOR_NODE 1
```

Flip the active `#define` (and comment out the other) before building for
a sensor node vs. the hub.

### Build & flash

```bash
pio run
pio run -t upload
```

## Host-side tool

`tools/serial_webui.py` — a small web UI that reads the hub's serial stream
and renders each connected sensor node's radar view (distance, angle, speed):

```bash
python3 tools/serial_webui.py --port /dev/ttyACM0
```

`tools/serial_barchart.py` provides a simpler terminal bar-chart view of the
same data.

## Known limitations

- No consolidated wiring diagram — pin assignments live split across
  `src/sensor-node.cpp` and the Fritzing `.fzz` PCB files.
- No documented range/accuracy figures for the RD-03D in this multi-node
  setup, or guidance on how many sensor nodes one hub can reliably track.
