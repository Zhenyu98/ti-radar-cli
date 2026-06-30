"""Local non-hardware checks for the public ti-radar-cli package."""

from __future__ import annotations

import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ti_radar import cli  # noqa: E402
from ti_radar.backends import base as backend_base  # noqa: E402
from ti_radar.backends import mock as backend_mock  # noqa: E402
from ti_radar.core import device, profile, session  # noqa: E402


def parser_help(argv: list[str]) -> str:
    parser = cli.build_parser()
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            parser.parse_args(argv)
        except SystemExit as exc:
            assert exc.code == 0
    return buf.getvalue()


def test_top_level_help_is_slim() -> None:
    text = parser_help(["--help"])
    for expected in ["version", "doctor", "studio", "capture", "session", "device"]:
        assert expected in text
    assert "Expert backend commands" in text
    for hidden in ["bringup", "ethinit-probe", "validate-profile", "StartFrame", "backend internals"]:
        assert hidden not in text


def test_studio_help_keeps_expert_commands() -> None:
    text = parser_help(["studio", "--help"])
    for expected in [
        "status",
        "ping",
        "start",
        "identify",
        "validate-profile",
        "bringup",
        "config",
        "capture",
        "run",
        "ethinit-probe",
    ]:
        assert expected in text


def test_capture_raw_help_options() -> None:
    text = parser_help(["capture", "raw", "--help"])
    for expected in ["--backend", "--profile", "--frames"]:
        assert expected in text


def test_default_profile_and_device_route() -> None:
    prof = profile.load_profile("default_6843")
    errors, warnings = profile.profile_errors(prof)
    route = device.route_for_part_id(6843)
    assert errors == []
    assert warnings == []
    assert route.part_id == 6843
    assert route.frequency_band == "60G"
    assert profile.profile_config_lua(prof).startswith("ar1.ProfileConfig(")


def test_capture_verdict_pass_and_fail() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "adc_data_Raw_0.bin").write_bytes(b"x" * 256)
        (root / "adc_data_Raw_LogFile.csv").write_text(
            "Number of received packets,10\n"
            "Out of sequence count,0\n"
            "Number of zero filled packets,0\n"
            "Number of zero filled bytes,0\n",
            encoding="utf-8",
        )
        assert session.capture_verdict(root)["verdict"] == "pass"

        (root / "adc_data_Raw_LogFile.csv").write_text(
            "Number of received packets,10\n"
            "Out of sequence count,0\n"
            "Number of zero filled packets,0\n"
            "Number of zero filled bytes,4\n",
            encoding="utf-8",
        )
        verdict = session.capture_verdict(root)
        assert verdict["verdict"] == "fail"
        assert "zero_filled_bytes > 0" in verdict["failure_reasons"]


def test_mock_backend_factory() -> None:
    backend = backend_base.get_backend("mock", {"synthetic_doppler": True})
    assert isinstance(backend, backend_mock.MockBackend)
    assert backend.synthetic_doppler is True


def main() -> None:
    for test in [
        test_top_level_help_is_slim,
        test_studio_help_keeps_expert_commands,
        test_capture_raw_help_options,
        test_default_profile_and_device_route,
        test_capture_verdict_pass_and_fail,
        test_mock_backend_factory,
    ]:
        test()
    print("TI_RADAR_CLI_PUBLIC_TESTS OK")


if __name__ == "__main__":
    main()
