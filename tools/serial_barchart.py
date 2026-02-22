#!/usr/bin/env python3
"""
Realtime bar chart for ESP32 touch stream.

Example:
  python3 tools/serial_barchart.py --port /dev/ttyUSB0 --mac A1B2C3D4E5F6 \
    --min 0,0,0,0 --max 4095,4095,4095,4095

Line format (from firmware):
  touch,<mac12>,<id3>,<seq>,<ms>,<n>,v1,v2,...,vn
"""

import argparse
import sys
from typing import List, Optional, Tuple

try:
    import serial  # type: ignore
except Exception:
    print("ERROR: pyserial not installed. Run: pip install pyserial", file=sys.stderr)
    raise

try:
    import matplotlib.pyplot as plt  # type: ignore
    from matplotlib.animation import FuncAnimation  # type: ignore
except Exception:
    print("ERROR: matplotlib not installed. Run: pip install matplotlib", file=sys.stderr)
    raise


def _normalize_mac(s: str) -> Optional[str]:
    if not s:
        return None
    hexchars = "".join([c for c in s if c in "0123456789abcdefABCDEF"])
    if len(hexchars) != 12:
        return None
    return hexchars.upper()


def _parse_limits(text: Optional[str]) -> Optional[List[float]]:
    if text is None:
        return None
    if text.strip() == "":
        return None
    parts = [p.strip() for p in text.split(",")]
    vals: List[float] = []
    for p in parts:
        if p == "":
            continue
        try:
            vals.append(float(p))
        except ValueError:
            raise ValueError(f"Invalid limit value: {p}")
    return vals if vals else None


def _expand_limits(vals: Optional[List[float]], n: int, default: float) -> List[float]:
    if not vals:
        return [default] * n
    if len(vals) >= n:
        return vals[:n]
    return vals + [vals[-1]] * (n - len(vals))


def _parse_line(line: str) -> Optional[Tuple[str, int, List[int]]]:
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
    vals: List[int] = []
    for p in parts[6:6 + n]:
        try:
            vals.append(int(p))
        except ValueError:
            return None
    return mac, n, vals


def main() -> int:
    ap = argparse.ArgumentParser(description="Realtime bar chart for ESP32 touch stream")
    ap.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0 or COM3")
    ap.add_argument("--baud", type=int, default=921600, help="Baud rate (default: 921600)")
    ap.add_argument("--mac", help="Target MAC (12 hex, with or without colons). If omitted, first seen.")
    ap.add_argument("--min", dest="vmin", help="Comma list of min values per channel")
    ap.add_argument("--max", dest="vmax", help="Comma list of max values per channel")
    ap.add_argument("--title", default="Touch Values", help="Chart title")
    ap.add_argument("--alpha", type=float, default=0.35, help="Bar smoothing alpha (0-1)")
    args = ap.parse_args()

    target_mac = _normalize_mac(args.mac) if args.mac else None
    if args.mac and not target_mac:
        print("ERROR: --mac must be 12 hex chars (colons ok)", file=sys.stderr)
        return 2

    vmin_list = _parse_limits(args.vmin)
    vmax_list = _parse_limits(args.vmax)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except Exception as exc:
        print(f"ERROR: failed to open serial port: {exc}", file=sys.stderr)
        return 2

    print("Reading serial... Press Ctrl+C to quit.")

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.canvas.manager.set_window_title("Touch Stream")

    bars = None
    last_vals: List[float] = []
    last_n = 0

    def update(_frame):
        nonlocal bars, last_vals, last_n, target_mac
        # Read multiple lines per frame
        for _ in range(50):
            try:
                raw = ser.readline()
            except Exception:
                break
            if not raw:
                break
            try:
                line = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue
            parsed = _parse_line(line)
            if not parsed:
                continue
            mac, n, vals = parsed
            if target_mac is None:
                target_mac = mac
                print(f"Auto-selected MAC: {target_mac}")
            if mac != target_mac:
                continue

            if n <= 0:
                continue

            vmin = _expand_limits(vmin_list, n, 0.0)
            vmax = _expand_limits(vmax_list, n, 1023.0)

            # Scale to 0-100
            scaled: List[float] = []
            for i in range(n):
                lo = vmin[i]
                hi = vmax[i]
                if hi <= lo:
                    pct = 0.0
                else:
                    pct = (vals[i] - lo) * 100.0 / (hi - lo)
                if pct < 0.0:
                    pct = 0.0
                elif pct > 100.0:
                    pct = 100.0
                scaled.append(pct)

            # Smooth updates for nicer motion
            if not last_vals or len(last_vals) != n:
                last_vals = scaled
            else:
                a = max(0.0, min(1.0, float(args.alpha)))
                last_vals = [a * s + (1.0 - a) * l for s, l in zip(scaled, last_vals)]

            if bars is None or n != last_n:
                ax.clear()
                ax.set_ylim(0, 100)
                ax.set_title(args.title)
                ax.set_xlabel("Channel")
                ax.set_ylabel("Percent")
                x = list(range(n))
                bars = ax.bar(x, last_vals, color="#2C7FB8")
                ax.set_xticks(x)
                ax.set_xticklabels([f"v{i}" for i in range(n)])
                last_n = n
            else:
                for b, v in zip(bars, last_vals):
                    b.set_height(v)
            break

        return bars

    _ = FuncAnimation(fig, update, interval=33, blit=False)
    try:
        plt.tight_layout()
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
