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


class SidusAxis:
    """One axis (pan or tilt) on a shared serial connection."""

    def __init__(self, conn: serial.Serial, header: str, addr: str):
        self._conn = conn
        self._header = header
        self._addr = addr

    def _send(self, command: str, data: int, terminator: str, expected_responses: int = 1) -> list[dict]:
        frame = protocol.build_command(self._header, self._addr, command, data, terminator)
        self._conn.write(frame.encode("ascii"))
        responses = []
        for _ in range(expected_responses):
            line = self._conn.readline()
            if not line:
                raise TimeoutError(f"no response to {frame.strip()!r}")
            responses.append(protocol.parse_response(line))
        return responses

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
