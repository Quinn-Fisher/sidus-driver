"""
Minimal driver for a Sidus SS250-series pan/tilt over RS232/RS485.

This wraps the command set documented in Sidus Solutions User Manual
Doc 940250005 Rev 14, section 4.4.2 ("Command Mnemonics for SS250mkII and
SS250mkIII series"). Confirmed via the Sidus order (S241530Q) that our unit
is an SS250 MK4, RS485 — the right series for this manual, no mkV ambiguity.
This has not yet been run against the physical unit, though.

Node addresses (the single ASCII character identifying pan vs. tilt on the
wire) are NOT hardcoded — the factory default is "A" for both axes on
some units, but ours may differ. Confirm via the power-up message or the
MRA command before assuming an address.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import serial

from . import protocol

DEFAULT_BAUD = 9600  # manual's factory default; confirm against your unit
RESPONSE_TIMEOUT_S = 1.0
MAX_JUNK_LINES = 5

# Same-axis turnaround delay. Measured on real hardware (SS250 MK4, unit
# S241530Q): back-to-back commands to the SAME axis (read or write, any
# combination) fail 100% of the time at 0.00s and succeed 100% of the time
# at every tested delay from 0.01s up. Commands to DIFFERENT axes (pan then
# tilt) need no delay at all, even at 0.00s — this is per-axis, not a
# global bus pause. The floor looked like a binary threshold rather than a
# gradual falloff, suggesting a write-ordering/scheduling race in the
# USB-serial adapter path rather than RS485 wire settle time. Budgeting
# 30ms for jitter margin above the ~10ms measured floor.
MIN_SAME_AXIS_INTERVAL_S = 0.03

# IMPORTANT: this is NOT just a wall-clock budget. Measured on real hardware
# that reading+parsing a previous response naturally takes ~60-80ms (longer
# than MIN_SAME_AXIS_INTERVAL_S), so a naive "only sleep if elapsed time is
# short" check computes a negative/zero remainder and skips sleep() entirely
# -- and that FAILS 3/3, even though *more* wall-clock time had already
# passed than the budget calls for. An explicit time.sleep(0.005) call
# landing in that exact same measured gap SUCCEEDS 3/3. Same duration,
# different outcome -- the only difference is whether an actual blocking
# sleep() call executed. This points to something like the USB-RS485
# adapter coalescing two write() calls into one burst (confusing its
# auto TX/RX direction switching) when nothing forces a real yield between
# them -- elapsed wall-clock time doesn't model this at all. So: always
# call time.sleep() with a real nonzero duration before a same-axis command,
# never skip it based on a computed "should already be fine" remainder.
MIN_ABSOLUTE_SLEEP_S = 0.01


class SidusAxis:
    """One axis (pan or tilt) on a shared serial connection."""

    def __init__(self, conn: serial.Serial, header: str, addr: str):
        self._conn = conn
        self._header = header
        self._addr = addr
        self._last_send_time: float | None = None

    def _send(self, command: str, data: int, terminator: str, expected_responses: int = 1) -> list[dict]:
        self._wait_for_same_axis_turnaround()
        frame = protocol.build_command(self._header, self._addr, command, data, terminator)
        self._conn.write(frame.encode("ascii"))
        self._last_send_time = time.monotonic()
        return [self._read_response_frame(frame) for _ in range(expected_responses)]

    def _wait_for_same_axis_turnaround(self) -> None:
        if self._last_send_time is None:
            return
        remaining = MIN_SAME_AXIS_INTERVAL_S - (time.monotonic() - self._last_send_time)
        # Always sleep a real nonzero amount -- see MIN_ABSOLUTE_SLEEP_S comment above.
        # Do NOT skip this even when `remaining` is already <= 0.
        time.sleep(max(remaining, MIN_ABSOLUTE_SLEEP_S))

    def _read_response_frame(self, sent_frame: str) -> dict:
        """Read lines until one starts with this axis's header, skipping any
        human-readable label lines the unit sends first.

        Observed on real SS250 MK4 hardware: MRL reads come back as e.g.
        b"location\\r\\n#AMRL5412R\\r\\n" — a plain-text label line ahead of the
        documented 12-byte frame. This matches the manual's own examples for
        the factory-default acknowledgement mode (DAK=0002, "verbose
        acknowledgement", section 4.4.2), which show a label line before the
        real response frame (e.g. "device baud" before "$ADBD0096R"). So this
        is very likely documented behavior, not a framing artifact — but
        skipping non-matching lines is safe either way.
        """
        for _ in range(MAX_JUNK_LINES):
            line = self._conn.readline()
            if not line:
                raise TimeoutError(f"no response to {sent_frame.strip()!r}")
            if line[:1] == self._header.encode("ascii"):
                return protocol.parse_response(line)
        raise TimeoutError(
            f"no line starting with {self._header!r} after skipping {MAX_JUNK_LINES} lines "
            f"(sent {sent_frame.strip()!r})"
        )

    # --- position -------------------------------------------------------

    def read_location_degrees(self) -> float:
        """MRL — read current position. Needs the encoder-count conversion on ALL series."""
        resp = self._send("MRL", 0, "R")[0]
        return protocol.count_to_degrees(int(resp["data"]))

    def move_to_degrees(self, degrees: float, speed_deg_per_sec: float) -> float:
        """Set speed (MSP) then move to an absolute position (MML). Returns settled position."""
        self.set_speed(speed_deg_per_sec)
        count = protocol.degrees_to_count(degrees)
        responses = self._send("MML", count, "W", expected_responses=2)
        return protocol.count_to_degrees(int(responses[-1]["data"]))

    def set_speed(self, speed_deg_per_sec: float) -> None:
        """MSP — allowable range is 0.5 to 20.0 deg/sec (data field 0050-2000)."""
        data = round(speed_deg_per_sec * 100)
        self._send("MSP", data, "W")

    def stop(self) -> dict:
        """MST — stop with brakes on. Returns the stop-reason data field (see manual for codes)."""
        return self._send("MST", 0, "W", expected_responses=1)[0]

    # --- safety limits ----------------------------------------------------

    def set_limit_forward_degrees(self, degrees: float) -> None:
        """MLF — soft stop in the clockwise direction."""
        self._send("MLF", protocol.degrees_to_count(degrees), "W")

    def set_limit_backward_degrees(self, degrees: float) -> None:
        """MLB — soft stop in the counter-clockwise direction."""
        self._send("MLB", protocol.degrees_to_count(degrees), "W")

    def read_limit_forward_degrees(self) -> float:
        resp = self._send("MLF", 0, "R")[0]
        return protocol.count_to_degrees(int(resp["data"]))

    def read_limit_backward_degrees(self) -> float:
        resp = self._send("MLB", 0, "R")[0]
        return protocol.count_to_degrees(int(resp["data"]))

    # --- diagnostics ------------------------------------------------------

    def read_temperature_c(self) -> int:
        resp = self._send("TMP", 0, "R")[0]
        return int(resp["data"])


@dataclass
class SidusPanTilt:
    pan: SidusAxis
    tilt: SidusAxis

    @classmethod
    def open(
        cls,
        port: str,
        pan_addr: str = "A",
        tilt_addr: str = "A",
        baud: int = DEFAULT_BAUD,
    ) -> "SidusPanTilt":
        conn = serial.Serial(port, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=RESPONSE_TIMEOUT_S)
        # Manual: startup message appears within 1s of power-up, response time ~150us after.
        time.sleep(1.0)
        conn.reset_input_buffer()
        return cls(
            pan=SidusAxis(conn, protocol.PAN_HEADER, pan_addr),
            tilt=SidusAxis(conn, protocol.TILT_HEADER, tilt_addr),
        )

    def read_position_degrees(self) -> tuple[float, float]:
        return self.pan.read_location_degrees(), self.tilt.read_location_degrees()
