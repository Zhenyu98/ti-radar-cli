"""Session file inspection, DCA packet summaries, and capture verdicts."""

from __future__ import annotations

import glob
from pathlib import Path
import re
import time


def read_text(path: Path, max_chars: int = 2000) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=enc)[:max_chars]
        except UnicodeDecodeError:
            continue
    return ""


def largest_bin(session_dir: Path | str) -> Path | None:
    root = Path(session_dir)
    bins = [p for p in root.glob("*.bin") if p.is_file()]
    if not bins:
        return None
    return max(bins, key=lambda p: p.stat().st_size)


def packet_summary(session_dir: Path | str) -> dict[str, int | str]:
    root = Path(session_dir)
    logs = sorted(root.glob("*LogFile*.csv"))
    if not logs:
        return {}
    key_map = {
        "Number of received packets": "received_packets",
        "Out of sequence count": "out_of_sequence",
        "Number of zero filled packets": "zero_filled_packets",
        "Number of zero filled bytes": "zero_filled_bytes",
    }
    text = read_text(logs[0], max_chars=8000)
    summary: dict[str, int | str] = {"log_file": logs[0].name}
    for line in text.splitlines():
        for label, field in key_map.items():
            if label.lower() in line.lower():
                nums = re.findall(r"-?\d+", line)
                if nums:
                    summary[field] = int(nums[-1])
    return summary


def capture_verdict(session_dir: Path | str) -> dict[str, object]:
    root = Path(session_dir)
    bin_actual = largest_bin(root)
    nbytes = bin_actual.stat().st_size if bin_actual else 0
    packet = packet_summary(root)
    reasons: list[str] = []

    if not bin_actual:
        reasons.append("bin_actual missing")
    if nbytes <= 64:
        reasons.append("bytes <= 64")

    if not packet:
        reasons.append("DCA packet log missing")
    else:
        received = packet.get("received_packets")
        out_of_sequence = packet.get("out_of_sequence")
        zero_filled_packets = packet.get("zero_filled_packets")
        zero_filled_bytes = packet.get("zero_filled_bytes")

        if not isinstance(received, int) or received <= 0:
            reasons.append("received_packets <= 0")
        if isinstance(out_of_sequence, int) and out_of_sequence > 0:
            reasons.append("out_of_sequence > 0")
        if isinstance(zero_filled_packets, int) and zero_filled_packets > 0:
            reasons.append("zero_filled_packets > 0")
        if isinstance(zero_filled_bytes, int) and zero_filled_bytes > 0:
            reasons.append("zero_filled_bytes > 0")

    return {
        "verdict": "fail" if reasons else "pass",
        "failure_reasons": reasons,
        "bin_actual": bin_actual,
        "bytes": nbytes,
        "packet_log": packet,
    }


def write_capture_manifest(
    session_dir: Path | str,
    session_id: str,
    backend: str,
    profile: str | None,
    frames: int | None,
    status: str,
    command: list[str],
) -> Path:
    root = Path(session_dir)
    root.mkdir(parents=True, exist_ok=True)
    verdict_info = capture_verdict(root)
    bin_actual = verdict_info["bin_actual"]
    packet = verdict_info["packet_log"]
    failure_reasons = verdict_info["failure_reasons"]
    manifest = root / "manifest.yaml"

    lines = [
        "session_id: %s" % session_id,
        "backend: %s" % backend,
        "status: %s" % status,
        "verdict: %s" % verdict_info["verdict"],
        "created_at: %s" % time.strftime("%Y-%m-%dT%H:%M:%S"),
        "profile: %s" % (profile or "null"),
        "frames: %s" % (frames if frames is not None else "null"),
        "failure_reasons: []" if not failure_reasons else "failure_reasons:",
        "output:",
        "  bin_actual: %s" % (bin_actual.name if isinstance(bin_actual, Path) else "null"),
        "  bytes: %d" % verdict_info["bytes"],
        "packet_log:",
        "  log_file: %s" % packet.get("log_file", "null"),
        "  received_packets: %s" % packet.get("received_packets", "null"),
        "  out_of_sequence: %s" % packet.get("out_of_sequence", "null"),
        "  zero_filled_packets: %s" % packet.get("zero_filled_packets", "null"),
        "  zero_filled_bytes: %s" % packet.get("zero_filled_bytes", "null"),
        "command:",
    ]
    if failure_reasons:
        insert_at = lines.index("output:")
        for reason in reversed(failure_reasons):
            lines.insert(insert_at, "  - %s" % reason)
    lines.extend("  - %s" % item for item in command)
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def latest_session_dir(sessions_root: Path | str) -> Path | None:
    root = Path(sessions_root)
    if not root.exists():
        return None
    dirs = [Path(p) for p in glob.glob(str(root / "*")) if Path(p).is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def resolve_session(name: str, sessions_root: Path | str) -> Path | None:
    if name == "latest":
        return latest_session_dir(sessions_root)
    p = Path(name)
    if p.exists():
        return p
    p = Path(sessions_root) / name
    return p if p.exists() else None
