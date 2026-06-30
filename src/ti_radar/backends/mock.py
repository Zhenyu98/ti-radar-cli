"""Mock capture backend for local PC/Pi orchestration tests."""

from __future__ import annotations

import os
import time

from ti_radar.backends.base import CaptureBackend


class MockBackend(CaptureBackend):
    name = "mock"

    def __init__(self, synthetic_doppler=False, frame_period_ms=50.0):
        self.synthetic_doppler = synthetic_doppler
        self.frame_period_ms = float(frame_period_ms)
        self._cur = None

    def prepare(self):
        print("[mock] backend ready (no hardware).")

    def start(self, session_id, label, out_dir):
        bin_path = os.path.join(out_dir, "adc_data.bin")
        with open(bin_path, "wb") as f:
            f.write(b"MOCK_ADC\x00")
        t0 = time.time_ns()
        self._cur = {
            "bin_path": bin_path,
            "out_dir": out_dir,
            "t_radar_start_ns": t0,
            "t0_mono": time.monotonic_ns(),
            "session_id": session_id,
        }
        print("[mock] START %s -> %s" % (session_id, bin_path))
        return {"bin_path": bin_path, "t_radar_start_ns": t0}

    def stop(self):
        if self._cur is None:
            return {"t_radar_stop_ns": time.time_ns(), "bytes": 0}
        dur_s = (time.monotonic_ns() - self._cur["t0_mono"]) / 1e9
        t1 = time.time_ns()
        nbytes = os.path.getsize(self._cur["bin_path"])
        if self.synthetic_doppler:
            self._write_synth_doppler(self._cur["out_dir"], dur_s)
        print("[mock] STOP  dur=%.2fs bytes=%d" % (dur_s, nbytes))
        info = {"t_radar_stop_ns": t1, "bytes": nbytes, "dur_s": dur_s}
        self._cur = None
        return info

    def _write_synth_doppler(self, out_dir, dur_s):
        dt = self.frame_period_ms / 1000.0
        n = max(int(dur_s / dt), 1)
        path = os.path.join(out_dir, "radar_doppler.csv")
        with open(path, "w") as f:
            f.write("t_s,v_radial_mps\n")
            for k in range(n):
                t = k * dt
                frac = t / max(dur_s, 1e-9)
                v = (1.4 * frac) if frac < 0.5 else (1.4 * (1 - frac))
                f.write("%.4f,%.4f\n" % (t, v))
        print("[mock] wrote synthetic doppler: %s (%d rows)" % (path, n))

