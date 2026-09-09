#!/usr/bin/env python3
"""
Set pan/tilt soft-stop limits via serial, since the Sidus GUI wasn't applying them.

This is READ-ONLY with respect to motion — it never commands a move. It only
writes the MLF/MLB soft-stop registers, and it prints the current position
before doing anything so you have a record to restore to by hand if needed.

Recommended procedure (per the "system maintenance" plan):
    1. Stop the toolkit / anything else that might be talking to the sonar rig.
    2. Run this script. It prints current pan/tilt position BEFORE touching
       anything — write those numbers down.
    3. It then sets the soft limits and reads them back to confirm.
    4. Restart the toolkit.

Usage:
    python scripts/set_safety_limits.py /dev/ttyUSB0 --pan-limit 45 --tilt-limit 25
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
    parser.add_argument("--pan-limit", type=float, default=45.0, help="+/- degrees, pan soft stop")
    parser.add_argument("--tilt-limit", type=float, default=25.0, help="+/- degrees, tilt soft stop")
    parser.add_argument("--dry-run", action="store_true", help="only read/print, don't write limits")
    args = parser.parse_args()

    unit = SidusPanTilt.open(args.port, pan_addr=args.pan_addr, tilt_addr=args.tilt_addr, baud=args.baud)

    pan_deg, tilt_deg = unit.read_position_degrees()
    print(f"CURRENT POSITION — write this down before proceeding:")
    print(f"  pan:  {pan_deg:.2f} deg")
    print(f"  tilt: {tilt_deg:.2f} deg")

    if args.dry_run:
        print("\n--dry-run set, not writing limits.")
        return

    print(f"\nSetting pan limits to +/-{args.pan_limit} deg, tilt limits to +/-{args.tilt_limit} deg...")
    unit.pan.set_limit_forward_degrees(args.pan_limit)
    unit.pan.set_limit_backward_degrees(-args.pan_limit)
    unit.tilt.set_limit_forward_degrees(args.tilt_limit)
    unit.tilt.set_limit_backward_degrees(-args.tilt_limit)

    print("Reading back limits to confirm:")
    print(f"  pan  forward/backward: {unit.pan.read_limit_forward_degrees():.2f} / {unit.pan.read_limit_backward_degrees():.2f} deg")
    print(f"  tilt forward/backward: {unit.tilt.read_limit_forward_degrees():.2f} / {unit.tilt.read_limit_backward_degrees():.2f} deg")


if __name__ == "__main__":
    main()
