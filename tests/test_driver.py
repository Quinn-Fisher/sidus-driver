"""
Tests for SidusAxis response parsing, using a fake serial connection.

Covers the real-hardware behavior found on an actual SS250 MK4 unit: every
response is preceded by a plain-text label line (e.g. b"location\\r\\n")
before the documented 12-byte frame. See driver.py's _read_response_frame
docstring for why (factory-default verbose acknowledgement mode).
"""

import time
from unittest.mock import patch

import pytest

from sidus_driver import protocol
from sidus_driver.driver import MIN_ABSOLUTE_SLEEP_S, MIN_SAME_AXIS_INTERVAL_S, SidusAxis


class FakeSerial:
    """Minimal stand-in for serial.Serial: write() records, readline() replays."""

    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""


class RepeatingFakeSerial:
    """Like FakeSerial, but replays the same line forever (for pacing tests)."""

    def __init__(self, line: bytes):
        self._line = line
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def readline(self) -> bytes:
        return self._line


def test_read_location_skips_leading_label_line():
    # Real hardware response for a pan MRL read, confirmed 2026-09-09 on unit S241530Q.
    conn = FakeSerial([b"location\r\n", b"#AMRL5412R\r\n"])
    axis = SidusAxis(conn, protocol.PAN_HEADER, "A")

    degrees = axis.read_location_degrees()

    assert degrees == pytest.approx(36.21, abs=0.01)
    assert conn.written == [b"#AMRL0000R\r\n"]


def test_read_location_tilt_skips_leading_label_line():
    # Real hardware response for a tilt MRL read, confirmed 2026-09-09 on unit S241530Q.
    conn = FakeSerial([b"location\r\n", b"$AMRL4881R\r\n"])
    axis = SidusAxis(conn, protocol.TILT_HEADER, "A")

    degrees = axis.read_location_degrees()

    assert degrees == pytest.approx(-10.46, abs=0.01)


def test_read_location_works_without_a_label_line_too():
    # Backward-compat: don't assume a label line is always present.
    conn = FakeSerial([b"#AMRL5000R\r\n"])
    axis = SidusAxis(conn, protocol.PAN_HEADER, "A")

    assert axis.read_location_degrees() == 0.0


def test_gives_up_after_too_many_non_matching_lines():
    conn = FakeSerial([b"location\r\n"] * 10)
    axis = SidusAxis(conn, protocol.PAN_HEADER, "A")

    with pytest.raises(TimeoutError):
        axis.read_location_degrees()


def test_same_axis_back_to_back_commands_are_paced():
    # Real hardware (unit S241530Q): back-to-back commands to the SAME axis
    # fail 100% of the time with zero delay, succeed 100% of the time at any
    # nonzero delay >= ~10ms. We budget MIN_SAME_AXIS_INTERVAL_S (30ms).
    conn = RepeatingFakeSerial(b"#AMRL5000R\r\n")
    axis = SidusAxis(conn, protocol.PAN_HEADER, "A")
    axis.read_location_degrees()  # first call: nothing to wait on yet

    start = time.monotonic()
    axis.read_location_degrees()
    elapsed = time.monotonic() - start

    assert elapsed >= MIN_SAME_AXIS_INTERVAL_S - 0.005  # small tolerance for scheduling jitter


def test_same_axis_sleep_is_never_skipped_even_if_elapsed_time_looks_sufficient():
    # Regression: the first version of this pacing fix computed
    # `remaining = budget - elapsed` and skipped time.sleep() entirely
    # whenever `remaining <= 0`. On real hardware, reading+parsing a
    # response naturally takes ~60-80ms (already more than the 30ms
    # budget), so `remaining` was already negative before the NEXT
    # same-axis command -- and skipping the sleep in that case failed
    # 100% of the time on the real unit, even though MORE wall-clock time
    # had passed than the budget called for. An explicit, real sleep()
    # call is required regardless of measured elapsed time -- this is not
    # a wall-clock-based mechanism (see driver.py's MIN_ABSOLUTE_SLEEP_S
    # comment). So: assert sleep() is actually called with a nonzero
    # duration even when we simulate a large already-elapsed gap.
    conn = RepeatingFakeSerial(b"#AMRL5000R\r\n")
    axis = SidusAxis(conn, protocol.PAN_HEADER, "A")
    axis.read_location_degrees()
    # Simulate that a lot of wall-clock time has already passed since the
    # last send (e.g. slow response parsing) -- the exact scenario that
    # broke on real hardware.
    axis._last_send_time = time.monotonic() - 1.0

    with patch("sidus_driver.driver.time.sleep") as mock_sleep:
        axis.read_location_degrees()

    mock_sleep.assert_called_once()
    (slept_seconds,), _ = mock_sleep.call_args
    assert slept_seconds >= MIN_ABSOLUTE_SLEEP_S


def test_different_axes_do_not_wait_on_each_other():
    # Real hardware: pan->tilt (or tilt->pan) succeeds reliably even at zero
    # delay — the turnaround requirement is per-axis, not a shared bus pause.
    pan = SidusAxis(RepeatingFakeSerial(b"#AMRL5000R\r\n"), protocol.PAN_HEADER, "A")
    tilt = SidusAxis(RepeatingFakeSerial(b"$AMRL5000R\r\n"), protocol.TILT_HEADER, "A")
    pan.read_location_degrees()

    start = time.monotonic()
    tilt.read_location_degrees()
    elapsed = time.monotonic() - start

    assert elapsed < MIN_SAME_AXIS_INTERVAL_S / 2
