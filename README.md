# sidus-driver

Minimal Python driver for a Sidus Solutions SS250-series pan/tilt unit, talking the
documented serial protocol directly (no vendor GUI needed).

Status: reads and absolute moves (MML) confirmed working against real
hardware (2026-09-09, unit S241530Q, node address A on both axes, COM7,
9600 8N1). Soft-stop limits (MLF/MLB) are set and verified: pan ±45.00°,
tilt ±24.96°/-24.96°. MMF/MMB (continuous-velocity move) and raising the
baud rate have NOT been tested on real hardware yet — see "Open questions"
below. Written against
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

## Known hardware quirks

Found through live testing on the real unit (SS250 MK4, S241530Q), all now
handled by the driver:

1. **Verbose acknowledgement label lines.** Every response is preceded by a
   plain-text label line (e.g. `location\r\n#AMRL5412R\r\n` for an MRL read).
   Matches the manual's documented factory-default acknowledgement mode
   (`DAK`=0002, "verbose acknowledgement") — expected behavior, not a framing
   bug. Handled by `_read_response_frame` in `driver.py`, which skips lines
   not starting with the axis's header character.
2. **Same-axis command turnaround.** Two commands (read or write, any
   combination) sent back-to-back to the *same* axis fail 100% of the time
   at zero delay; any delay >= ~10ms succeeds 100% of the time (measured
   over 25+ trials). This is per-axis, not a shared bus pause — pan→tilt
   needs no delay even at 0.00s. Handled by `MIN_SAME_AXIS_INTERVAL_S`
   (30ms, budgeted above the ~10ms floor) in `driver.py`. This is likely
   also why the vendor GUI wasn't applying the safety limits — it probably
   issues writes back-to-back with no pause.
3. **MML's second response uses a widened data field.** Per the manual, MML
   (move to position) returns two responses: an ack, then a settled-position
   frame in MRL format. On real hardware that second frame uses a 6-digit
   zero-padded data field (e.g. `#AMRL005435R`), not the manual's documented
   4-digit width. The old fixed-offset parser silently mis-sliced this
   (no exception — the frame passed the length check but decoded to garbage,
   e.g. -434.75° for a real position of 38.24°). `parse_response()` is now
   variable-width: it peels the terminator off the end and treats everything
   between the command and terminator as the data field, whatever its width.

The unit's firmware (via `MRA` on the tilt axis) reports as **SS250 Mark
IV-AE, firmware 906000904 A1.2** — a materially different, alphanumeric
version scheme from the manual's own worked example (a Mark II unit,
firmware `6618`). That, plus these three undocumented quirks found in one
session, suggests we're on a firmware/hardware revision the manual wasn't
written against. Worth requesting a MK IV-AE-specific protocol addendum from
Sidus rather than continuing to reverse-engineer quirks one at a time.

## Open questions (flagged, not yet tested on real hardware)

- **Baud rate.** Raising `DBD` (currently 9600, supports up to 115200) might
  reduce or eliminate the same-axis turnaround delay if it's wire-turnaround
  dominated rather than USB-adapter-scheduling dominated — but changing live
  comms parameters on hardware at the end of an 85m tether risks losing
  communication if something doesn't match afterward. Needs explicit
  sign-off before testing.
- **MMF/MMB (continuous-velocity move).** Not yet tested — these only stop
  via an explicit `MST`, hitting a soft limit, or a 0000-speed command, and
  we haven't independently verified the soft limits actually arrest a
  continuous move (only absolute MML moves, which have a built-in target,
  have been tested). Also unconfirmed whether MMF/MMB's response has the
  same widened-field quirk as MML's second response.
- **Pan-axis `MRA` anomaly.** The tilt axis returns the full descriptive
  `MRA` block; the pan axis only ever returns a short ack line (serial
  number only), reproduced 3 times including on a freshly-opened, generously
  settled connection. Not yet explained — may indicate pan and tilt boards
  differ, or may be worth asking Sidus about directly.

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
