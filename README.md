# sidus-driver

Minimal Python driver for a Sidus Solutions SS250-series pan/tilt unit, talking the
documented serial protocol directly (no vendor GUI needed).

Status: exploratory / not yet run against real hardware. Written against
Sidus Solutions User Manual Doc 940250005 Rev 14 (covers SS250mkII/mkIII/mkIV),
included in this repo at
[`docs/sidus_user_manual_940250005-02.pdf`](docs/sidus_user_manual_940250005-02.pdf)
— the serial command protocol is documented in section 4.4.

Confirmed via the Sidus order (S241530Q): our unit is an **SS250 PT 24VDC,
MK4**, RS485, aluminum housing, 3km depth rating, with factory hard stops of
Pan ±170° / Tilt ±90°. So this driver's protocol assumptions are the right
ones — no mkV ambiguity. Connector chain: unit has an 8-pin Subconn MCBH-8M;
an 85m cable runs from an 8-pin Subconn (wet end, at the unit) to a DB-9 (dry
end, topside) — a standard serial connector, so a plain USB-to-serial (DB-9)
adapter should be enough to connect a computer.

First real step with the hardware should still be running
`scripts/read_position.py` and checking it gets a sane response, since the
protocol has only been checked against the manual's own worked examples, not
the physical unit yet.

## What's here

- `sidus_driver/protocol.py` — wire-level frame encoding and the
  degree/encoder-count conversion (`count = degrees / 0.0879 + 5000`, per the
  manual's Appendix 1). Has unit tests checked against the manual's own worked
  examples — no hardware needed to run these.
- `sidus_driver/driver.py` — a thin `SidusAxis` / `SidusPanTilt` wrapper over
  `pyserial` implementing: read position (`MRL`), move to absolute position
  (`MML`+`MSP`), stop (`MST`), read/set soft-stop limits (`MLF`/`MLB`), and
  read temperature (`TMP`).
- `scripts/read_position.py` — read-only, prints current pan/tilt degrees.
  Safe to run any time.
- `scripts/set_safety_limits.py` — sets the pan/tilt soft-stop limits over
  serial (the Sidus GUI wasn't applying these reliably). Prints current
  position first so you have a record before changing anything.

## Setup

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Before touching real hardware

1. Confirm the node address(es) for pan and tilt — check the power-up
   startup message on the serial port, or send an `MRA` (Motor Report All)
   command. Don't assume "A" for both; the driver defaults to "A" but this
   needs to be confirmed against the actual unit.
2. Confirm baud rate — factory default per the manual is 9600 8N1, but this
   may have been changed.
3. Run `read_position.py` first. It's read-only and will confirm whether the
   protocol from the mkII/mkIII/mkIV manual actually applies to our unit.

## Setting the pan/tilt safety limits

Cable slack limits how far the unit can safely pan/tilt without straining the
cable. Current known-safe limits: pan ±45°, tilt ±25° — these are *soft*
stops we set in software (`MLF`/`MLB`), well inside the unit's factory
*hard* stops (mechanical, Pan ±170° / Tilt ±90°). The hard stops exist as a
backup in case the soft stops aren't set or fail; they're not a substitute
for setting the soft limits correctly.

```
# stop the toolkit / anything else talking to the sonar rig first
python scripts/set_safety_limits.py /dev/ttyUSB0 --pan-limit 45 --tilt-limit 25
```

This prints the current position before writing anything, sets the `MLF`/`MLB`
soft-stop registers, then reads them back to confirm. It never commands a
move — only writes the limit registers.

## Not yet implemented

- Continuous-velocity moves (`MMF`/`MMB`) — present in the protocol, not yet
  wrapped in the driver.
- Homing (`MHF`/`MHB`) — only relevant for mkII/mkIII (incremental encoder);
  mkIV/mkV use absolute encoders and don't need it, per the manual's
  Appendix 4.
- Anything related to actually deciding *when* to move the gimbal based on
  detection output — this repo is just the hardware control layer, not the
  active-perception logic.
