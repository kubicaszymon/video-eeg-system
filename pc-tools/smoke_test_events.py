"""
smoke_test_events.py -- confirm the Perun32 'Events' channel reacts to the
Pico sync pulse BEFORE committing to a long recording.

Run on the PC while:
  - the EEG Pi is streaming 'Perun32' (autostarts), and
  - the Pico is wired to the Perun32 sync connector and powered on.

Expected: the Events value prints a CHANGE every ~5 seconds (each Pico pulse).
If you see nothing change, the trigger is not reaching RIN1 -- check wiring
(common GND!) before recording anything.

  PY=C:\\STUDIA\\NOWAMAGISTERKA\\pi_camera\\.venv-pc\\Scripts\\python.exe
  %PY% pc_examples\\smoke_test_events.py
"""
import pylsl

print("Resolving LSL streams...")
streams = pylsl.resolve_streams()                       # pylsl 2.x
perun = next((s for s in streams if s.name() == "Perun32"), None)
if perun is None:
    raise SystemExit("Perun32 stream not found. Is the EEG Pi running and on "
                     "the same WiFi subnet?")

inlet = pylsl.StreamInlet(perun, max_buflen=4)

# Read channel labels from metadata, locate 'Events'.
info = inlet.info()
n = info.channel_count()
ch = info.desc().child("channels").child("channel")
labels = []
for _ in range(n):
    labels.append(ch.child_value("label") or ch.child_value("name"))
    ch = ch.next_sibling()

if "Events" not in labels:
    raise SystemExit("No 'Events' channel found. Channels are:\n  %s" % labels)

ev = labels.index("Events")
print("Found 'Events' at index %d of %d channels." % (ev, n))
print("Watching... fire the Pico; expect a CHANGE every ~5 s. Ctrl-C to stop.\n")

last = None
while True:
    sample, ts = inlet.pull_sample(timeout=5.0)
    if sample is None:
        print("  (no samples for 5 s -- is the stream alive?)")
        continue
    val = sample[ev]
    if val != last:
        flag = "  <-- CHANGE" if last is not None else "  (initial)"
        print("t=%.3f   Events = %-6s%s" % (ts, val, flag))
        last = val
