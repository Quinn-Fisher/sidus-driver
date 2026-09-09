"""
Tests for degree/count conversion and frame encoding, checked against the
worked examples in the Sidus manual itself (Appendix 1 and section 4.4.2).
"""

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
