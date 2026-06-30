"""Radar profile loading, Lua generation, and validation."""

from __future__ import annotations

from pathlib import Path

from ti_radar.core.device import route_for_part_id

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by deployment environment
    yaml = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROFILES_YAML = PACKAGE_ROOT / "configs" / "radar_profiles.yaml"


def load_profile(name: str | None = None, profiles_yaml: str | Path = PROFILES_YAML) -> dict:
    if not yaml:
        raise RuntimeError("缺少 pyyaml 或 %s" % profiles_yaml)
    path = Path(profiles_yaml)
    if not path.exists():
        raise RuntimeError("缺少 pyyaml 或 %s" % path)
    with path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    profile_name = name or doc.get("active")
    prof = dict(doc["profiles"][profile_name])
    prof["_name"] = profile_name
    return prof


def profile_names(profiles_yaml: str | Path = PROFILES_YAML) -> tuple[str | None, list[str]]:
    if not yaml:
        return None, []
    path = Path(profiles_yaml)
    if not path.exists():
        return None, []
    with path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc.get("active"), sorted(doc.get("profiles", {}).keys())


def route_for_profile(p: dict, studio_root: str | None = None):
    if studio_root is None:
        return route_for_part_id(p.get("part_id", 6843))
    return route_for_part_id(p.get("part_id", 6843), studio_root)


def profile_config_lua(p: dict) -> str:
    """Build the mmWave Studio ProfileConfig call from a radar profile."""
    return ("ar1.ProfileConfig(0, %g, %g, %g, %g, 0, 0, 0, 0, 0, 0, %g, 0, %d, %d, 0, %d, %d)"
            % (p["start_freq_ghz"], p["idle_us"], p["adc_start_us"], p["ramp_end_us"],
               p["slope_mhz_us"], p["num_adc_samples"], p["sample_rate_ksps"],
               p["hpf2_hz"], p["rx_gain_db"]))


def derived(p: dict) -> dict:
    c = 299792458.0
    fs = p["sample_rate_ksps"] * 1e3
    fs_msps = p["sample_rate_ksps"] / 1000.0
    slope = p["slope_mhz_us"] * 1e12
    adc_sampling_time_us = p["num_adc_samples"] / fs_msps
    adc_window_end_us = p["adc_start_us"] + adc_sampling_time_us
    rng_res = c / (2 * slope * (p["num_adc_samples"] / fs))
    lam = c / (p["start_freq_ghz"] * 1e9)
    n_tx = p["end_tx"] - p["start_tx"] + 1
    tc_tx = n_tx * (p["idle_us"] + p["ramp_end_us"]) * 1e-6
    v_max = lam / (4 * tc_tx)
    frame_needed_ms = p["num_loops"] * n_tx * (p["idle_us"] + p["ramp_end_us"]) / 1000.0
    chirp_end_ghz = p["start_freq_ghz"] + p["slope_mhz_us"] * p["ramp_end_us"] / 1000.0
    adc_bw_ghz = p["slope_mhz_us"] * adc_sampling_time_us / 1000.0
    return dict(
        rng_res=rng_res,
        v_max=v_max,
        frame_needed_ms=frame_needed_ms,
        n_tx=n_tx,
        adc_sampling_time_us=adc_sampling_time_us,
        adc_window_end_us=adc_window_end_us,
        chirp_end_ghz=chirp_end_ghz,
        adc_bw_ghz=adc_bw_ghz,
    )


def profile_errors(p: dict) -> tuple[list[str], list[str]]:
    d = derived(p)
    errors: list[str] = []
    warnings: list[str] = []

    if p["ramp_end_us"] < d["adc_window_end_us"]:
        errors.append(
            "ADC 采样窗口放不下：ramp_end_us=%.3f < adc_start_us + samples/Fs = %.3f us"
            % (p["ramp_end_us"], d["adc_window_end_us"])
        )
    max_freq = float(p.get("max_freq_ghz", 64.0))
    min_freq = float(p.get("min_freq_ghz", 60.0))
    if d["chirp_end_ghz"] > max_freq:
        errors.append("chirp 终点频率越界：%.3f GHz > %.3f GHz" % (d["chirp_end_ghz"], max_freq))
    if p["start_freq_ghz"] < min_freq:
        warnings.append("start_freq_ghz=%.3f GHz 低于参考下界 %.3f GHz" % (p["start_freq_ghz"], min_freq))
    if p["frame_period_ms"] < d["frame_needed_ms"]:
        errors.append("帧周期太短：frame_period_ms=%.3f < 需要 %.3f ms" % (p["frame_period_ms"], d["frame_needed_ms"]))
    return errors, warnings
