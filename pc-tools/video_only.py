"""Minimal check: show the Pi camera (H.264 over LSL) on the PC. Video only.

No EEG, no Qt. Decoding runs on a background thread; the main thread only
displays the newest decoded frame, so the window stays responsive even if a
decode batch is briefly heavy.

Run (PC)::

    .venv-pc\\Scripts\\pip install pylsl numpy opencv-python av
    .venv-pc\\Scripts\\python pc_app\\video_only.py
    .venv-pc\\Scripts\\python pc_app\\video_only.py --name Perun32_Video
"""

import argparse
import sys
import threading
import time

import cv2

from h264_inlet import H264LslReceiver


class _DecodeThread(threading.Thread):
    """Pull + decode in the background; keep only the newest frame."""

    def __init__(self, rx):
        super().__init__(daemon=True)
        self._rx = rx
        self._lock = threading.Lock()
        self._img = None
        self._stop = threading.Event()
        self.count = 0

    def run(self):
        while not self._stop.is_set():
            frames = self._rx.poll(block_timeout=0.5)
            if not frames:
                continue
            img, _ts = frames[-1]
            with self._lock:
                self._img = img
                self.count += len(frames)

    def latest(self):
        with self._lock:
            return self._img, self.count

    def stop(self):
        self._stop.set()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Show the Pi camera LSL stream.")
    ap.add_argument("--name", default="Perun32_Video", help="LSL stream name.")
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="Seconds to wait for stream discovery.")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    rx = H264LslReceiver(args.name)
    print("Looking for LSL streams (%.0fs)..." % args.timeout, flush=True)
    streams = rx.resolve(timeout=args.timeout)

    if streams is not None:  # not connected -> diagnostics
        if not streams:
            print("\nNo LSL streams visible to this PC at all.")
            print("Network problem. Check: same WiFi; ping video-pi.local; "
                  "Windows Firewall; router AP/client isolation OFF.")
            sys.exit(2)
        print("\nStreams this PC can see:")
        for s in streams:
            print("  name=%-16r type=%-8r host=%r"
                  % (s.name(), s.type(), s.hostname()))
        print("\n'%s' is NOT in the list. Check -n on the Pi." % args.name)
        sys.exit(3)

    print("Connected to %r. Waiting for the first keyframe..." % args.name,
          flush=True)

    dec = _DecodeThread(rx)
    dec.start()

    win = "Pi camera (LSL H.264) - press Q to quit"
    got_first = False
    last_count = 0
    t0 = time.time()
    try:
        while True:
            img, count = dec.latest()
            if img is None:
                time.sleep(0.05)  # nothing decoded yet (pre-keyframe)
                continue
            if not got_first:
                print("  decoding OK: %dx%d. Showing video."
                      % (img.shape[1], img.shape[0]), flush=True)
                got_first = True

            cv2.imshow(win, img)

            now = time.time()
            if now - t0 >= 1.0:
                fps = (count - last_count) / (now - t0)
                cv2.setWindowTitle(
                    win, "Pi camera (LSL H.264)  ~%.0f fps decoded  (Q quits)"
                    % fps)
                last_count = count
                t0 = now

            # ~60 Hz UI cap; window stays responsive (decode is elsewhere).
            if cv2.waitKey(16) & 0xFF == ord("q"):
                break
    finally:
        dec.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
