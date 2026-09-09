#!/usr/bin/env python3
"""
Print the current pan/tilt position. Read-only, no motion — safe to run any time.

Usage:
    python scripts/read_position.py /dev/ttyUSB0
"""

import argparse
import sys

sys.path.insert(0, "..")
from sidus_driver import SidusPanTilt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--pan-addr", default="A")
    parser.add_argument("--tilt-addr", default="A")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    unit = SidusPanTilt.open(args.port, pan_addr=args.pan_addr, tilt_addr=args.tilt_addr, baud=args.baud)
    pan_deg, tilt_deg = unit.read_position_degrees()
    print(f"pan:  {pan_deg:.2f} deg")
    print(f"tilt: {tilt_deg:.2f} deg")


if __name__ == "__main__":
    main()
