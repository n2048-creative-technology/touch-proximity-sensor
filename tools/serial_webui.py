#!/usr/bin/env python3
"""
Web UI for ESP32 touch stream.

Run:
  python3 tools/serial_webui.py --port /dev/ttyUSB0
Then open:
  http://localhost:8000

Line format (from firmware):
  touch,<mac12>,<id3>,<seq>,<ms>,<n>,v1,v2,...,vn
"""

import argparse
import asyncio
import json
import threading
import site
import sys
from typing import Dict, List, Optional

# Ensure user site-packages are visible (common on systems with locked site-packages)
if site.ENABLE_USER_SITE:
    try:
        site.addsitedir(site.getusersitepackages())
    except Exception:
        pass

try:
    import serial  # type: ignore
except Exception:
    raise SystemExit(
        "ERROR: pyserial not installed for this Python.\n"
        f"Python: {sys.executable}\n"
        "Try: python3 -m pip install --user pyserial"
    )

try:
    from aiohttp import web, WSMsgType  # type: ignore
except Exception:
    raise SystemExit(
        "ERROR: aiohttp not installed for this Python.\n"
        f"Python: {sys.executable}\n"
        "Try: python3 -m pip install --user aiohttp"
    )


HTML_PAGE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Touch Stream</title>
  <style>
    :root {
      --bg: #0b0f14;
      --panel: #111827;
      --accent: #2dd4bf;
      --muted: #94a3b8;
      --bar: #2c7fb8;
      --bar-bg: #1f2937;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 16px;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      color: #e2e8f0; background: var(--bg);
    }
    .wrap { max-width: 980px; margin: 0 auto; }
    .title { font-size: 20px; font-weight: 600; margin-bottom: 12px; }
    .panel {
      background: var(--panel);
      border: 1px solid #1f2937;
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
    input {
      width: 100%; padding: 8px 10px; border-radius: 8px;
      border: 1px solid #334155; background: #0f172a; color: #e2e8f0;
    }
    .status { font-size: 12px; color: var(--muted); }
    .bars { display: grid; gap: 8px; }
    .bar-row { display: grid; grid-template-columns: 60px 1fr 80px; gap: 8px; align-items: center; }
    .bar-label { font-size: 12px; color: var(--muted); }
    .bar-track { height: 18px; background: var(--bar-bg); border-radius: 9px; overflow: hidden; }
    .bar-fill { height: 100%; width: 0%; background: var(--bar); transition: width 0.08s linear; }
    .bar-val { font-variant-numeric: tabular-nums; text-align: right; font-size: 12px; color: #cbd5f5; }
    @media (max-width: 720px) {
      .row { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 44px 1fr 64px; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"title\">Touch Stream</div>

    <div class=\"panel\">
      <div class=\"row\">
        <div>
          <label for=\"mac\">MAC filter</label>
          <select id=\"mac\"></select>
        </div>
        <div>
          <label for=\"min\">Min values (comma list)</label>
          <input id=\"min\" placeholder=\"0,0,0,0\" />
        </div>
        <div>
          <label for=\"max\">Max values (comma list)</label>
          <input id=\"max\" placeholder=\"4095,4095,4095,4095\" />
        </div>
        <div>
          <label>Status</label>
          <div class=\"status\" id=\"status\">Connecting...</div>
        </div>
      </div>
    </div>

    <div class=\"panel\">
      <div class=\"bars\" id=\"bars\"></div>
    </div>
  </div>

  <script>
    const statusEl = document.getElementById('status');
    const macEl = document.getElementById('mac');
    const minEl = document.getElementById('min');
    const maxEl = document.getElementById('max');
    const barsEl = document.getElementById('bars');

    let ws;
    let autoMac = null;
    let knownMacs = new Set();
    let obsMin = [];
    let obsMax = [];

    function normMac(s) {
      const hex = (s || '').replace(/[^0-9a-fA-F]/g, '');
      return hex.length === 12 ? hex.toUpperCase() : null;
    }

    function loadSelectedMac() {
      const saved = localStorage.getItem('selectedMac');
      return saved && normMac(saved) ? saved : null;
    }

    function saveSelectedMac(mac) {
      if (mac) localStorage.setItem('selectedMac', mac);
    }

    function ensureMacOption(mac) {
      if (knownMacs.has(mac)) return;
      knownMacs.add(mac);
      const opt = document.createElement('option');
      opt.value = mac;
      opt.textContent = mac;
      macEl.appendChild(opt);
    }

    function parseList(s) {
      if (!s) return [];
      return s.split(',').map(v => v.trim()).filter(v => v !== '').map(Number);
    }

    function expandList(list, n, defVal) {
      if (!list || list.length === 0) return Array(n).fill(defVal);
      if (list.length >= n) return list.slice(0, n);
      const out = list.slice();
      while (out.length < n) out.push(out[out.length - 1]);
      return out;
    }

    function ensureBars(n) {
      if (barsEl.children.length === n) return;
      barsEl.innerHTML = '';
      for (let i = 0; i < n; i++) {
        const row = document.createElement('div');
        row.className = 'bar-row';

        const label = document.createElement('div');
        label.className = 'bar-label';
        label.textContent = `v${i}`;

        const track = document.createElement('div');
        track.className = 'bar-track';
        const fill = document.createElement('div');
        fill.className = 'bar-fill';
        track.appendChild(fill);

        const val = document.createElement('div');
        val.className = 'bar-val';
        val.textContent = '0%';

        row.appendChild(label);
        row.appendChild(track);
        row.appendChild(val);
        barsEl.appendChild(row);
      }
    }

    function updateBars(vals) {
      const n = vals.length;
      ensureBars(n);

      if (obsMin.length !== n) obsMin = Array(n).fill(Infinity);
      if (obsMax.length !== n) obsMax = Array(n).fill(-Infinity);

      for (let i = 0; i < n; i++) {
        if (vals[i] < obsMin[i]) obsMin[i] = vals[i];
        if (vals[i] > obsMax[i]) obsMax[i] = vals[i];
      }

      const vminManual = parseList(minEl.value);
      const vmaxManual = parseList(maxEl.value);
      const vmin = vminManual.length ? expandList(vminManual, n, 0) : obsMin.slice();
      const vmax = vmaxManual.length ? expandList(vmaxManual, n, 1023) : obsMax.slice();

      for (let i = 0; i < n; i++) {
        const lo = vmin[i];
        const hi = vmax[i];
        let pct = 0;
        if (hi > lo) pct = (vals[i] - lo) * 100 / (hi - lo);
        pct = Math.max(0, Math.min(100, pct));

        const row = barsEl.children[i];
        const fill = row.children[1].children[0];
        const val = row.children[2];
        fill.style.width = pct.toFixed(1) + '%';
        val.textContent = `${vals[i]}  (${pct.toFixed(1)}%)`;
      }
    }

    function connect() {
      ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onopen = () => { statusEl.textContent = 'Connected'; };
      ws.onclose = () => { statusEl.textContent = 'Disconnected (retrying)'; setTimeout(connect, 1000); };
      ws.onerror = () => { statusEl.textContent = 'Error'; };
      ws.onmessage = (ev) => {
        const pkt = JSON.parse(ev.data);
        const mac = pkt.mac;
        if (!mac) return;

        ensureMacOption(mac);
        if (!autoMac) autoMac = mac;

        const saved = loadSelectedMac();
        if (saved && macEl.value !== saved) {
          macEl.value = saved;
        } else if (!macEl.value) {
          macEl.value = autoMac;
        }

        const target = macEl.value || autoMac;
        if (target && mac !== target) return;

        updateBars(pkt.values || []);
      };
    }

    connect();

    macEl.addEventListener('change', () => {
      saveSelectedMac(macEl.value);
    });
  </script>
</body>
</html>
"""


def _parse_line(line: str) -> Optional[Dict]:
    if not line.startswith("touch,"):
        return None
    parts = line.strip().split(",")
    if len(parts) < 7:
        return None
    mac = parts[1].upper()
    try:
        n = int(parts[5])
    except ValueError:
        return None
    values: List[int] = []
    for p in parts[6:6 + n]:
        try:
            values.append(int(p))
        except ValueError:
            return None
    return {"mac": mac, "n": n, "values": values}


class SerialReader(threading.Thread):
    def __init__(self, port: str, baud: int, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        super().__init__(daemon=True)
        self._port = port
        self._baud = baud
        self._loop = loop
        self._queue = queue
        self._stop = threading.Event()

    def run(self) -> None:
        try:
            ser = serial.Serial(self._port, self._baud, timeout=0.1)
        except Exception as exc:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, {"error": str(exc)})
            return

        try:
            while not self._stop.is_set():
                raw = ser.readline()
                if not raw:
                    continue
                try:
                    line = raw.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                pkt = _parse_line(line)
                if pkt:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, pkt)
        finally:
            ser.close()

    def stop(self) -> None:
        self._stop.set()


async def index(_request: web.Request) -> web.Response:
    return web.Response(text=HTML_PAGE, content_type="text/html")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    request.app["clients"].add(ws)

    async for msg in ws:
        if msg.type == WSMsgType.ERROR:
            break

    request.app["clients"].discard(ws)
    return ws


async def broadcaster(app: web.Application) -> None:
    queue: asyncio.Queue = app["queue"]
    clients = app["clients"]
    while True:
        pkt = await queue.get()
        if "error" in pkt:
            payload = json.dumps({"error": pkt["error"]})
        else:
            payload = json.dumps(pkt)
        dead = []
        for ws in clients:
            if ws.closed:
                dead.append(ws)
                continue
            await ws.send_str(payload)
        for ws in dead:
            clients.discard(ws)


async def on_startup(app: web.Application) -> None:
    loop = asyncio.get_running_loop()
    app["queue"] = asyncio.Queue()
    app["clients"] = set()
    app["reader"] = SerialReader(app["port"], app["baud"], loop, app["queue"])
    app["reader"].start()
    app["broadcast_task"] = asyncio.create_task(broadcaster(app))


async def on_cleanup(app: web.Application) -> None:
    app["reader"].stop()
    app["broadcast_task"].cancel()


def main() -> int:
    ap = argparse.ArgumentParser(description="Web UI for ESP32 touch stream")
    ap.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0 or COM3")
    ap.add_argument("--baud", type=int, default=921600, help="Baud rate (default: 921600)")
    ap.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    ap.add_argument("--http", type=int, default=8000, help="HTTP port (default: 8000)")
    args = ap.parse_args()

    app = web.Application()
    app["port"] = args.port
    app["baud"] = args.baud
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    web.run_app(app, host=args.host, port=args.http)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
