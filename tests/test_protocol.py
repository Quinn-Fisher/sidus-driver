"""
Tests for degree/count conversion and frame encoding, checked against the
worked examples in the Sidus manual itself (Appendix 1 and section 4.4.2),
plus real-hardware response shapes seen on an SS250 MK4 unit (S241530Q)
that the manual's own examples don't cover.
"""

import pytest

from sidus_driver import protocol


def test_degrees_to_count_matches_manual_example():
    # Manual Appendix 1: "112 / 0.0879 + 5000 = 6274 counts"
    assert protocol.degrees_to_count(112) == 6274


def test_count_to_degrees_matches_manual_example():
    # Manual Appendix 1: "(4297 - 5000) x 0.0879 = -61.79 degrees"
    assert round(protocol.count_to_degrees(4297), 2) == -61.79


def test_zero_degrees_is_5000_counts():
    assert protocol.degrees_to_count(0) == 5000
    assert protocol.count_to_degrees(5000) == 0


def test_build_command_move_pan_to_112_degrees():
    # Manual: "The command to move a pan motor at address A to 112 degrees is thus: #AMML6274W"
    frame = protocol.build_command("#", "A", "MML", protocol.degrees_to_count(112), "W")
    assert frame == "#AMML6274W\r\n"


def test_build_command_read_location():
    # Manual example: "#AMRL0000R"
    frame = protocol.build_command("#", "A", "MRL", 0, "R")
    assert frame == "#AMRL0000R\r\n"


def test_parse_response_splits_fields():
    resp = protocol.parse_response(b"#AMRL6024R\r\n")
    assert resp == {
        "header": "#",
        "addr": "A",
        "command": "MRL",
        "data": "6024",
        "terminator": "R",
        "raw": "#AMRL6024R",
    }


def test_parse_response_handles_widened_data_field():
    # MML's second ("settled position") response on real hardware uses a
    # 6-digit zero-padded data field, not the manual's documented 4-digit
    # width. Captured on unit S241530Q: pan out/back and tilt out/back.
    for raw, expected_data, expected_degrees in [
        (b"#AMRL005435R\r\n", "005435", 38.24),
        (b"#AMRL005412R\r\n", "005412", 36.21),
        (b"$AMRL004904R\r\n", "004904", -8.44),
        (b"$AMRL004881R\r\n", "004881", -10.46),
    ]:
        resp = protocol.parse_response(raw)
        assert resp["data"] == expected_data
        assert resp["terminator"] == "R"
        assert round(protocol.count_to_degrees(int(resp["data"])), 2) == expected_degrees


def test_parse_response_handles_negative_value_field():
    # Manual's own MAL example: "#AMAL-13245R" (-132.45 degrees)
    resp = protocol.parse_response(b"#AMAL-13245R\r\n")
    assert resp["data"] == "-13245"
    assert resp["terminator"] == "R"


def test_parse_response_rejects_bad_terminator():
    with pytest.raises(ValueError, match="terminator"):
        protocol.parse_response(b"#AMRL6024X\r\n")


def test_parse_response_rejects_too_short():
    with pytest.raises(ValueError, match="too short"):
        protocol.parse_response(b"short\r\n")
