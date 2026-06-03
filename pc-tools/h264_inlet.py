"""Shared H.264-over-LSL decode helpers (PC side).

The Pi sends one **H.264 access unit per LSL sample** on a 2-channel
``cf_string`` stream:

  * channel 0: the access-unit bytes, base64-encoded (Annex-B, SPS/PPS
    repeated before every keyframe so any keyframe is a valid entry point);
  * channel 1: ``"1"`` if this sample is a keyframe (IDR), else ``"0"``.

The LSL timestamp of each sample is the camera **sensor capture time on the
LSL clock** — this is what keeps EEG↔video sync exact.

Two classes:

  * ``H264Decoder``  — pure decoder. Feed (bytes, keyframe, ts) in order;
    get back (BGR frame, ts). Used by the live receiver *and* by the
    offline XDF sync check, so there is one decode path, not three.
  * ``H264LslReceiver`` — wraps an LSL inlet: pulls, drains backlog, and if
    it has fallen too far behind it jumps to the most recent keyframe and
    resets the decoder (bounded live latency, self-healing after a WiFi
    blip). Recording (LabRecorder) is unaffected — it stores the raw
    samples and they decode exactly offline.

The Pi encodes **baseline profile (no B-frames)**, so decode order ==
display order == input order. That makes the timestamp mapping a plain FIFO
(k-th decoded frame ↔ k-th fed packet) and keeps it exact for the sync test.
"""

import base64
import collections

import av
import pylsl


class H264Decoder:
    def __init__(self):
        self._reset()

    def _reset(self):
        self._cc = av.CodecContext.create("h264", "r")
        # SINGLE-THREADED on purpose. thread_type="AUTO" enables ffmpeg
        # frame-threading, which emits decoded frames in CLUMPS (feed N
        # packets, get 0 back, then N at once). Consumers that show only the
        # newest frame per poll then drop N-1 of every clump -> ~30 fps
        # decoded collapses to ~2-3 fps displayed. Decode is ~1.7 ms/frame
        # (measured, video_pipeline_probe Phase B) so threading is
        # unnecessary; single-thread = one packet in -> one frame out
        # immediately, no clump, no added latency, and an exact 1:1
        # packet->frame FIFO (better for the offline sync mapping too).
        self._cc.thread_type = "NONE"
        self._cc.thread_count = 1
        self._ts = collections.deque()
        self._started = False  # have we seen the first keyframe yet?

    def reset(self):
        self._reset()

    def feed(self, data, keyframe, ts):
        """Feed one access unit. Returns a list of (bgr_ndarray, ts)."""
        if not self._started:
            if not keyframe:
                return []  # can't start a decoder mid-GOP
            self._started = True
        self._ts.append(ts)
        out = []
        try:
            for frame in self._cc.decode(av.Packet(data)):
                fts = self._ts.popleft() if self._ts else ts
                out.append((frame.to_ndarray(format="bgr24"), fts))
        except Exception:
            # corrupt/incomplete stream (e.g. after dropped samples) —
            # drop the decoder; the next keyframe re-establishes it.
            self._reset()
        return out

    def flush(self):
        """Drain decoder buffers at end-of-stream (offline use)."""
        out = []
        try:
            for frame in self._cc.decode(None):
                fts = self._ts.popleft() if self._ts else None
                out.append((frame.to_ndarray(format="bgr24"), fts))
        except Exception:
            pass
        return out


class H264LslReceiver:
    """Resolve the video LSL stream and yield freshly decoded frames."""

    def __init__(self, name, max_behind=15):
        self.name = name
        # if more than this many samples are queued we are "behind": jump
        # forward to the latest keyframe and decode only from there (don't
        # decode-then-discard). ~max_behind/fps seconds of live latency, so
        # ~0.5 s at 30 fps. Small = low latency + self-healing; the offline
        # XDF path is unaffected (it uses H264Decoder directly, in order).
        self.max_behind = max_behind
        self._inlet = None
        self._dec = H264Decoder()
        self.info = None

    def resolve(self, timeout=5.0):
        """Return None on success, else the list of visible streams (for
        diagnostics by the caller)."""
        streams = pylsl.resolve_streams(wait_time=timeout)
        match = [s for s in streams if s.name() == self.name]
        if not match:
            return streams
        self._inlet = pylsl.StreamInlet(match[0], max_buflen=1)
        self.info = self._inlet.info()
        return None

    @property
    def connected(self):
        return self._inlet is not None

    def time_correction(self, timeout=0.0):
        """LSL clock offset to add to this stream's sample timestamps to map
        them onto the local clock. None if not connected / not yet known."""
        if self._inlet is None:
            return None
        try:
            return self._inlet.time_correction(timeout)
        except Exception:
            return None

    def reset(self):
        """Drop the decoder state (use after a reconnect; the next keyframe
        re-establishes decoding)."""
        self._dec.reset()

    def poll(self, block_timeout=1.0):
        """Pull + decode. Returns list of (bgr_ndarray, ts), newest last.
        Empty list means nothing arrived this call."""
        if self._inlet is None:
            return []
        samples, timestamps = self._inlet.pull_chunk(
            timeout=block_timeout, max_samples=256)
        if not samples:
            return []
        while True:  # drain backlog so we decode what's actually current
            more, mts = self._inlet.pull_chunk(timeout=0.0, max_samples=512)
            if not more:
                break
            samples += more
            timestamps += mts

        if len(samples) > self.max_behind:
            # behind: skip to the last keyframe and restart the decoder.
            ki = None
            for i in range(len(samples) - 1, -1, -1):
                if samples[i][1] == "1":
                    ki = i
                    break
            if ki is not None:
                samples = samples[ki:]
                timestamps = timestamps[ki:]
                self._dec.reset()

        out = []
        for (smp, ts) in zip(samples, timestamps):
            data = base64.b64decode(smp[0])
            keyframe = smp[1] == "1"
            out.extend(self._dec.feed(data, keyframe, ts))
        return out
