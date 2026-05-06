#!/usr/bin/env python3
"""
Web UI for ESP32 radar node stream.

Run:
  python3 tools/serial_webui.py --port /dev/ttyUSB0
Then open:
  http://localhost:8000

Line format (from firmware):
  <id3>,<ms>,<distance>,<angle>,<speed>,<detected>
"""

import argparse
import asyncio
import json
import threading
import site
import sys
from typing import Dict, Optional

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
  <title>Radar Nodes</title>
  <style>
    :root {
      --bg: #0b0f14;
      --panel: #111827;
      --accent: #2dd4bf;
      --accent-2: #38bdf8;
      --danger: #fb7185;
      --muted: #94a3b8;
      --line: #263244;
      --text: #e2e8f0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 16px;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      color: var(--text); background: var(--bg);
    }
    .wrap { max-width: 1180px; margin: 0 auto; }
    .title { font-size: 20px; font-weight: 600; margin-bottom: 12px; }
    .panel {
      background: var(--panel);
      border: 1px solid #1f2937;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .controls { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; align-items: end; }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
    select, input {
      width: 100%; padding: 8px 10px; border-radius: 8px;
      border: 1px solid #334155; background: #0f172a; color: #e2e8f0;
    }
    .status { font-size: 12px; color: var(--muted); }
    .node-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
    .node-card { background: #0f172a; border: 1px solid #243144; border-radius: 8px; padding: 12px; }
    .node-card.hidden { display: none; }
    .node-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 8px; }
    .node-id { font-weight: 700; font-variant-numeric: tabular-nums; }
    .node-age { color: var(--muted); font-size: 12px; white-space: nowrap; }
    .readings { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
    .reading { border: 1px solid #1f2c3d; border-radius: 8px; padding: 8px; min-width: 0; }
    .reading-label { color: var(--muted); font-size: 11px; margin-bottom: 2px; }
    .reading-value { font-size: 18px; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .radar { width: 100%; aspect-ratio: 1; display: block; background: #08111d; border: 1px solid #1f2c3d; border-radius: 8px; }
    .empty { color: var(--muted); text-align: center; padding: 36px 12px; }
    @media (max-width: 720px) {
      body { padding: 10px; }
      .controls, .readings { grid-template-columns: 1fr; }
      .node-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"title\">Radar Nodes</div>

    <div class=\"panel\">
      <div class=\"controls\">
        <div>
          <label for=\"nodeFilter\">Node view</label>
          <select id=\"nodeFilter\">
            <option value=\"all\">All nodes</option>
          </select>
        </div>
        <div>
          <label for=\"maxDistance\">Radar range (mm)</label>
          <input id=\"maxDistance\" type=\"number\" min=\"100\" step=\"100\" value=\"8000\" />
        </div>
        <div>
          <label>Serial status</label>
          <div class=\"status\" id=\"status\">Connecting...</div>
        </div>
      </div>
    </div>

    <div class=\"panel\">
      <div class=\"node-grid\" id=\"nodes\"></div>
      <div class=\"empty\" id=\"empty\">Waiting for detected radar targets...</div>
    </div>
  </div>

  <script>
    const statusEl = document.getElementById('status');
    const nodeFilterEl = document.getElementById('nodeFilter');
    const maxDistanceEl = document.getElementById('maxDistance');
    const nodesEl = document.getElementById('nodes');
    const emptyEl = document.getElementById('empty');

    let ws;
    const nodes = new Map();

    function fmt(value, suffix, digits = 1) {
      if (!Number.isFinite(value)) return '--';
      return `${value.toFixed(digits)} ${suffix}`;
    }

    function ensureNodeOption(id) {
      if (nodeFilterEl.querySelector(`option[value=\"${id}\"]`)) return;
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = `Node ${id}`;
      nodeFilterEl.appendChild(opt);
    }

    function makeNodeCard(id) {
      const card = document.createElement('div');
      card.className = 'node-card';
      card.dataset.node = id;
      card.innerHTML = `
        <div class=\"node-head\">
          <div class=\"node-id\">Node ${id}</div>
          <div class=\"node-age\">--</div>
        </div>
        <div class=\"readings\">
          <div class=\"reading\"><div class=\"reading-label\">Distance</div><div class=\"reading-value\" data-field=\"distance\">--</div></div>
          <div class=\"reading\"><div class=\"reading-label\">Angle</div><div class=\"reading-value\" data-field=\"angle\">--</div></div>
          <div class=\"reading\"><div class=\"reading-label\">Speed</div><div class=\"reading-value\" data-field=\"speed\">--</div></div>
        </div>
        <canvas class=\"radar\" width=\"480\" height=\"480\"></canvas>
      `;
      nodesEl.appendChild(card);
      return card;
    }

    function getNode(id) {
      let node = nodes.get(id);
      if (node) return node;
      const card = makeNodeCard(id);
      node = { id, card, canvas: card.querySelector('canvas'), lastSeen: 0, data: null };
      nodes.set(id, node);
      ensureNodeOption(id);
      return node;
    }

    function drawRadar(node) {
      const canvas = node.canvas;
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;
      const radius = Math.min(w, h) * 0.42;
      const maxDistance = Math.max(100, Number(maxDistanceEl.value) || 8000);
      const data = node.data;

      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#08111d';
      ctx.fillRect(0, 0, w, h);

      ctx.strokeStyle = '#263244';
      ctx.lineWidth = 1;
      for (let ring = 1; ring <= 4; ring++) {
        ctx.beginPath();
        ctx.arc(cx, cy, radius * ring / 4, 0, Math.PI * 2);
        ctx.stroke();
      }

      for (let deg = 0; deg < 360; deg += 45) {
        const a = deg * Math.PI / 180;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(a) * radius, cy - Math.sin(a) * radius);
        ctx.stroke();
        ctx.fillStyle = '#64748b';
        ctx.font = '12px ui-sans-serif, system-ui';
        ctx.textAlign = 'center';
        ctx.fillText(`${deg} deg`, cx + Math.cos(a) * (radius + 20), cy - Math.sin(a) * (radius + 20));
      }

      ctx.fillStyle = '#94a3b8';
      ctx.textAlign = 'right';
      ctx.fillText(`${Math.round(maxDistance)} mm`, w - 10, 18);

      if (!data) return;

      const clampedDistance = Math.max(0, Math.min(maxDistance, data.distance));
      const targetRadius = clampedDistance / maxDistance * radius;
      const angle = data.angle * Math.PI / 180;
      const x = cx + Math.cos(angle) * targetRadius;
      const y = cy - Math.sin(angle) * targetRadius;

      ctx.strokeStyle = 'rgba(45, 212, 191, 0.6)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(x, y);
      ctx.stroke();

      ctx.fillStyle = '#2dd4bf';
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, 13, 0, Math.PI * 2);
      ctx.stroke();
    }

    function applyFilter() {
      const selected = nodeFilterEl.value;
      let visible = 0;
      for (const node of nodes.values()) {
        const show = selected === 'all' || selected === node.id;
        node.card.classList.toggle('hidden', !show);
        if (show) visible++;
      }
      emptyEl.style.display = visible ? 'none' : 'block';
    }

    function updateNode(pkt) {
      if (!pkt.detected) return;
      const node = getNode(pkt.id);
      node.lastSeen = Date.now();
      node.data = pkt;

      node.card.querySelector('[data-field=\"distance\"]').textContent = fmt(pkt.distance, 'mm');
      node.card.querySelector('[data-field=\"angle\"]').textContent = fmt(pkt.angle, 'deg');
      node.card.querySelector('[data-field=\"speed\"]').textContent = fmt(pkt.speed, 'cm/s');
      drawRadar(node);
      applyFilter();
    }

    function connect() {
      ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onopen = () => { statusEl.textContent = 'Connected'; };
      ws.onclose = () => { statusEl.textContent = 'Disconnected (retrying)'; setTimeout(connect, 1000); };
      ws.onerror = () => { statusEl.textContent = 'Error'; };
      ws.onmessage = (ev) => {
        const pkt = JSON.parse(ev.data);
        if (pkt.error) {
          statusEl.textContent = pkt.error;
          return;
        }
        if (!pkt.id) return;
        updateNode(pkt);
      };
    }

    connect();

    nodeFilterEl.addEventListener('change', applyFilter);
    maxDistanceEl.addEventListener('input', () => {
      for (const node of nodes.values()) drawRadar(node);
    });

    setInterval(() => {
      const now = Date.now();
      for (const node of nodes.values()) {
        const age = Math.max(0, (now - node.lastSeen) / 1000);
        node.card.querySelector('.node-age').textContent = `${age.toFixed(1)} s ago`;
      }
    }, 250);
  </script>
</body>
</html>
"""


def _parse_line(line: str) -> Optional[Dict]:
    parts = line.strip().split(",")
    if len(parts) != 6:
        return None
    node_id = parts[0].strip().upper()
    if len(node_id) != 6:
        return None
    try:
        ms = int(parts[1])
        distance = float(parts[2])
        angle = float(parts[3])
        speed = float(parts[4])
    except ValueError:
        return None

    detected_text = parts[5].strip().lower()
    detected = detected_text in ("1", "true", "yes", "on")
    if not detected:
        return {"id": node_id, "detected": False}

    return {
        "id": node_id,
        "ms": ms,
        "distance": distance,
        "angle": angle,
        "speed": speed,
        "detected": detected,
    }


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
    ap = argparse.ArgumentParser(description="Web UI for ESP32 radar node stream")
    ap.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0 or COM3")
    ap.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
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
