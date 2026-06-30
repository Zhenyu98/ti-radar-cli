"""DCA1000 raw ADC bin to per-frame range-Doppler radial velocity."""

from __future__ import annotations

import argparse
import csv
import os

import numpy as np

C = 299792458.0


def load_adc_cube(bin_path, n_adc, n_rx, n_tx):
    """Read DCA1000 raw bin -> adcCube (n_adc, total_loops, n_chan)."""
    raw = np.fromfile(bin_path, dtype=np.int16)
    n_chan = n_rx * n_tx
    quad = raw.size // 4
    raw = raw[:quad * 4].reshape(-1, 4)
    cplx = np.empty(quad * 2, dtype=np.complex64)
    cplx[0::2] = raw[:, 0] + 1j * raw[:, 2]
    cplx[1::2] = raw[:, 1] + 1j * raw[:, 3]
    per_loop = n_adc * n_chan
    total_loops = cplx.size // per_loop
    cplx = cplx[:total_loops * per_loop]
    lvds = cplx.reshape(total_loops, n_chan, n_adc)
    cube = np.transpose(lvds, (2, 0, 1))
    return cube, total_loops, n_chan


def range_doppler(frame_cube, win_range=True, win_dop=True):
    """Return noncoherently summed range-Doppler power spectrum."""
    n_adc, n_chirps, _n_rx = frame_cube.shape
    x = frame_cube.astype(np.complex64)
    if win_range:
        x = x * np.hanning(n_adc)[:, None, None]
    rng = np.fft.fft(x, axis=0)
    rng = rng - rng.mean(axis=1, keepdims=True)
    if win_dop:
        rng = rng * np.hanning(n_chirps)[None, :, None]
    dop = np.fft.fftshift(np.fft.fft(rng, axis=1), axes=1)
    rd = np.sum(np.abs(dop) ** 2, axis=2)
    return rd


def axes(n_adc, n_chirps, fs_ksps, slope_mhz_us, f0_ghz, idle_us, ramp_us, n_tx):
    fs = fs_ksps * 1e3
    slope = slope_mhz_us * 1e12
    rng_res = C / (2.0 * slope * (n_adc / fs))
    range_axis = np.arange(n_adc) * (C * fs / (2.0 * slope)) / n_adc
    lam = C / (f0_ghz * 1e9)
    tc_tx = n_tx * (idle_us + ramp_us) * 1e-6
    v_max = lam / (4.0 * tc_tx)
    vel_axis = np.linspace(-v_max, v_max, n_chirps, endpoint=False)
    return range_axis, rng_res, vel_axis, v_max, lam


def process(bin_path, n_adc=128, n_rx=4, n_tx=3, n_chirps=64, frame_period_ms=60.0,
            fs_ksps=10000.0, slope_mhz_us=29.982, f0_ghz=60.25, idle_us=200.0, ramp_us=60.0,
            rmin_m=0.5, rmax_m=8.0, zero_dop_guard=2):
    cube, total_loops, n_chan = load_adc_cube(bin_path, n_adc, n_rx, n_tx)
    n_frames = total_loops // n_chirps
    if n_frames < 1:
        raise ValueError("帧数 <1：total_loops=%d n_chirps=%d，检查 n_chirps/n_tx" % (total_loops, n_chirps))
    range_axis, rng_res, vel_axis, v_max, lam = axes(
        n_adc, n_chirps, fs_ksps, slope_mhz_us, f0_ghz, idle_us, ramp_us, n_tx)

    rgate = np.where((range_axis >= rmin_m) & (range_axis <= rmax_m))[0]
    dop_center = n_chirps // 2
    dop_mask = np.ones(n_chirps, dtype=bool)
    dop_mask[dop_center - zero_dop_guard: dop_center + zero_dop_guard + 1] = False

    rows = []
    rd_accum = np.zeros((len(rgate), n_chirps))
    for f in range(n_frames):
        loops = slice(f * n_chirps, (f + 1) * n_chirps)
        frame_cube = cube[:, loops, 0:n_rx]
        rd = range_doppler(frame_cube)
        rd_g = rd[rgate, :]
        rd_accum += rd_g
        masked = rd_g.copy()
        masked[:, ~dop_mask] = 0.0
        ri, di = np.unravel_index(np.argmax(masked), masked.shape)
        peak = masked[ri, di]
        noise = np.median(rd_g[:, dop_mask]) + 1e-9
        snr_db = 10.0 * np.log10(peak / noise)
        rows.append((f * frame_period_ms / 1000.0,
                     float(vel_axis[di]),
                     float(range_axis[rgate[ri]]),
                     float(snr_db)))
    info = dict(n_frames=n_frames, n_chan=n_chan, rng_res=rng_res, v_max=v_max,
                lam=lam, range_axis=range_axis, vel_axis=vel_axis, rgate=rgate,
                rd_accum=rd_accum)
    return rows, info


def write_csv(rows, out_csv):
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", "v_radial_mps", "range_m", "snr_db"])
        writer.writerows(["%.4f" % r[0], "%.4f" % r[1], "%.3f" % r[2], "%.1f" % r[3]] for r in rows)
    print("[radar] 写出 %s (%d 帧)" % (out_csv, len(rows)))


def plot(rows, info, out_png):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[radar] 无 matplotlib，跳过画图")
        return
    t = [r[0] for r in rows]
    v = [r[1] for r in rows]
    rng = [r[2] for r in rows]
    snr = [r[3] for r in rows]
    fig, ax = plt.subplots(3, 1, figsize=(7, 6.5), sharex=True)
    ax[0].plot(t, v, "-o", ms=3)
    ax[0].set_ylabel("v_radial (m/s)")
    ax[0].axhline(0, color="k", lw=0.5)
    ax[0].grid(alpha=0.3)
    ax[0].set_title("radar radial velocity  (v_max=±%.2f m/s)" % info["v_max"])
    ax[1].plot(t, rng, "-o", ms=3, color="tab:purple")
    ax[1].set_ylabel("range (m)")
    ax[1].grid(alpha=0.3)
    ax[2].plot(t, snr, "-o", ms=3, color="tab:gray")
    ax[2].set_ylabel("peak SNR (dB)")
    ax[2].set_xlabel("time (s)")
    ax[2].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    print("[radar] 图已存 %s" % out_png)


def main(argv=None):
    parser = argparse.ArgumentParser(description="DCA1000 raw -> 径向速度")
    parser.add_argument("--bin", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--n-adc", type=int, default=128)
    parser.add_argument("--n-rx", type=int, default=4)
    parser.add_argument("--n-tx", type=int, default=3)
    parser.add_argument("--n-chirps", type=int, default=64)
    parser.add_argument("--frame-period-ms", type=float, default=60.0)
    parser.add_argument("--rmin", type=float, default=0.5)
    parser.add_argument("--rmax", type=float, default=8.0)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args(argv)

    out_dir = args.out or os.path.dirname(os.path.abspath(args.bin))
    rows, info = process(args.bin, n_adc=args.n_adc, n_rx=args.n_rx, n_tx=args.n_tx,
                         n_chirps=args.n_chirps, frame_period_ms=args.frame_period_ms,
                         rmin_m=args.rmin, rmax_m=args.rmax)
    print("[radar] %d 帧  range_res=%.3fm  v_max=±%.2fm/s" % (info["n_frames"], info["rng_res"], info["v_max"]))
    out_csv = os.path.join(out_dir, "radar_doppler.csv")
    write_csv(rows, out_csv)
    if args.plot:
        plot(rows, info, os.path.join(out_dir, "radar_velocity.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
