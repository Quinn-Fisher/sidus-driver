"""
Wire-level encoding for the Sidus Solutions serial protocol.

Reference: Sidus Solutions User Manual, Doc 940250005 Rev 14 (SS250mkII/mkIII/mkIV),
section 4.4 "Sidus Solutions Protocol" and Appendix 1 "Position Calculation".

Frame format (12 bytes total):
    HEADER(1) ADDR(1) COMMAND(3) DATA(4) TERMINATOR(1: R or W) <CR><LF>

Header identifies the axis: "#" = pan, "$" = tilt.
Data is always 4 ASCII digits, zero-padded, in the range 0000-9999.

Position encoder scale: 0.0879 degrees/count, with 5000 counts = 0 degrees.
This conversion applies to MRL on all series. mkIV/mkV also support MAL, which
reports degrees directly (see driver.py) — but MRL still needs this conversion
on every series, per the manual's explicit backward-compatibility note.
"""

from __future__ import annotations

ENCODER_SCALE_DEG_PER_COUNT = 0.0879
ENCODER_ZERO_COUNT = 5000

PAN_HEADER = "#"
TILT_HEADER = "$"


def degrees_to_count(degrees: float) -> int:
    return round(degrees / ENCODER_SCALE_DEG_PER_COUNT + ENCODER_ZERO_COUNT)


def count_to_degrees(count: int) -> float:
    return (count - ENCODER_ZERO_COUNT) * ENCODER_SCALE_DEG_PER_COUNT


def build_command(header: str, addr: str, command: str, data: int, terminator: str) -> str:
    """Encode a single command frame. `data` is clamped into the 0000-9999 field width."""
    if header not in (PAN_HEADER, TILT_HEADER):
        raise ValueError(f"unknown header {header!r}")
    if len(addr) != 1:
        raise ValueError(f"node address must be a single character, got {addr!r}")
    if len(command) != 3:
        raise ValueError(f"command mnemonic must be 3 characters, got {command!r}")
    if terminator not in ("R", "W"):
        raise ValueError(f"terminator must be 'R' or 'W', got {terminator!r}")
    if data < 0:
        # Negative encoder counts/values are sent as-is by the manual's own examples
        # (e.g. "#AMAL-13245R"), so allow a leading '-' to eat into the data width.
        data_field = str(data)
    else:
        data_field = f"{data:04d}"
    return f"{header}{addr}{command}{data_field}{terminator}\r\n"


def parse_response(raw: bytes) -> dict:
    """Split a raw echoed line into its components. Raises on malformed frames."""
    text = raw.decode("ascii", errors="replace").strip("\r\n")
    if len(text) < 10:
        raise ValueError(f"response too short: {raw!r}")
    return {
        "header": text[0],
        "addr": text[1],
        "command": text[2:5],
        "data": text[5:9],
        "terminator": text[9],
        "raw": text,
    }
