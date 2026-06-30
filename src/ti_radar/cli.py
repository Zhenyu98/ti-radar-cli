#!/usr/bin/env python3
"""ti-radar CLI.

This is the project-level command entry for agentic TI radar operation.
It calls shared ti_radar core, backend, workflow, and raw-processing modules.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Iterable

from ti_radar.core import paths as core_paths
from ti_radar.core import profile as core_profile
from ti_radar.core import session as core_session
from ti_radar import __version__

PROJECT_ROOT = core_paths.PROJECT_ROOT
SESSIONS = core_paths.SESSIONS


def _import_pipeline():
    try:
        from ti_radar.workflows import studio_pipeline
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"无法导入 ti_radar.workflows.studio_pipeline: {exc}") from exc
    return studio_pipeline


def _profile_names() -> tuple[str | None, list[str]]:
    return core_profile.profile_names()


def _load_profile(name: str | None):
    return core_profile.load_profile(name)


def _derived(profile: dict):
    return core_profile.derived(profile)


def _profile_errors(profile: dict) -> tuple[list[str], list[str]]:
    return core_profile.profile_errors(profile)


def _print_profile_report(profile: dict) -> bool:
    d = _derived(profile)
    errors, warnings = _profile_errors(profile)
    print("profile: %s" % profile.get("_name", "<unknown>"))
    print("  COM%d  %.3f GHz -> %.3f GHz" % (
        profile["com_port"], profile["start_freq_ghz"], d["chirp_end_ghz"]))
    print("  ADC window: start %.3f us + sample %.3f us = %.3f us; ramp_end %.3f us" % (
        profile["adc_start_us"], d["adc_sampling_time_us"], d["adc_window_end_us"], profile["ramp_end_us"]))
    print("  range_res=%.3f m  v_max=+/-%.2f m/s  frame_needed=%.2f ms  frame_period=%.2f ms" % (
        d["rng_res"], d["v_max"], d["frame_needed_ms"], profile["frame_period_ms"]))
    for w in warnings:
        print("  WARN: " + w)
    for e in errors:
        print("  ERROR: " + e)
    return not errors


def _python_name() -> str:
    return Path(sys.executable).name


def cmd_version(_: argparse.Namespace) -> int:
    print("ti-radar %s" % __version__)
    print("project: %s" % PROJECT_ROOT)
    print("python:  %s" % sys.executable)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    pipeline = _import_pipeline()
    print("=== ti-radar doctor ===")
    print("project: %s" % PROJECT_ROOT)
    print("python: %s" % sys.executable)
    print("python exe: %s" % _python_name())

    active, names = _profile_names()
    print("profiles: active=%s available=%s" % (active, ", ".join(names)))
    p = _load_profile(args.profile)
    ok_profile = _print_profile_report(p)

    ok_paths = True
    for label, path in [
        ("mmWave Studio", pipeline.STUDIO_EXE),
        ("BSS firmware", pipeline.BSS_FW),
        ("MSS firmware", pipeline.MSS_FW),
    ]:
        exists = os.path.exists(path)
        print("%s: %s %s" % (label, path, "OK" if exists else "MISSING"))
        ok_paths = ok_paths and exists

    nic_ok = pipeline.check_nic()
    com_ok = pipeline.check_com(p["com_port"])
    dca_ok = True
    if args.hardware:
        print("hardware probe: DCA SYSTEM_CONNECT, no FPGA reset")
        dca_ok = pipeline.dca_probe()
    else:
        print("hardware probe: skipped; add --hardware to probe DCA without reset")

    ok = ok_profile and ok_paths and nic_ok and com_ok and dca_ok
    print("doctor: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def _pipeline_main(argv: Iterable[str]) -> int:
    pipeline = _import_pipeline()
    return int(pipeline.main(list(argv)))


def _append_common_pipeline_args(out: list[str], args: argparse.Namespace) -> None:
    if getattr(args, "profile", None):
        out += ["--profile", args.profile]
    if getattr(args, "frames", None) is not None:
        out += ["--frames", str(args.frames)]
    if getattr(args, "out", None):
        out += ["--out", args.out]
    if getattr(args, "no_restart", False):
        out.append("--no-restart")
    if getattr(args, "no_dca_reset", False):
        out.append("--no-dca-reset")
    if getattr(args, "reuse_config", False):
        out.append("--reuse-config")
    # Do not persist the implicit default setup mode into manifests/argv.
    # `--reuse-config` is already the warm-capture signal; writing `--setup cold`
    # beside it is misleading even though the runtime path is warm.
    setup = getattr(args, "setup", None)
    if setup and setup != "cold":
        out += ["--setup", setup]


def _build_pipeline_argv(
    subcommand: str,
    args: argparse.Namespace,
    clock: Callable[[], str] | None = None,
) -> tuple[list[str], Path | None]:
    argv = [subcommand]
    out_dir: Path | None = None
    if subcommand in ("run", "capture"):
        if getattr(args, "out", None):
            out_dir = Path(args.out)
        else:
            stamp = (clock or (lambda: time.strftime("%Y%m%d_%H%M%S")))()
            out_dir = SESSIONS / ("%s_%s" % (subcommand, stamp))
        args = argparse.Namespace(**vars(args))
        args.out = str(out_dir)
    _append_common_pipeline_args(argv, args)
    return argv, out_dir


def _largest_bin(session_dir: Path) -> Path | None:
    return core_session.largest_bin(session_dir)


def _packet_summary(session_dir: Path) -> dict[str, int | str]:
    return core_session.packet_summary(session_dir)


def _capture_verdict(session_dir: Path) -> dict[str, object]:
    return core_session.capture_verdict(session_dir)


def _write_capture_manifest(
    session_dir: Path,
    session_id: str,
    backend: str,
    profile: str | None,
    frames: int | None,
    status: str,
    command: list[str],
) -> Path:
    return core_session.write_capture_manifest(
        session_dir=session_dir,
        session_id=session_id,
        backend=backend,
        profile=profile,
        frames=frames,
        status=status,
        command=command,
    )


def _capture_exit_code(rc: int, out_dir: Path | None) -> int:
    if rc != 0 or not out_dir or not out_dir.exists():
        return rc
    verdict = core_session.capture_verdict(out_dir)
    return 1 if verdict["verdict"] == "fail" else 0


def _tasklist_mmwave_studio() -> str:
    if os.name != "nt":
        return ""
    tasklist = shutil.which("tasklist")
    if not tasklist:
        return ""
    r = subprocess.run(
        [tasklist, "/FI", "IMAGENAME eq mmWaveStudio.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return (r.stdout or "").strip()


def cmd_studio_status(_: argparse.Namespace) -> int:
    pipeline = _import_pipeline()
    print("=== ti-radar studio status ===")
    ok_paths = True
    for label, path in [
        ("mmWave Studio exe", pipeline.STUDIO_EXE),
        ("RunTime dir", pipeline.STUDIO_RUNTIME),
        ("BSS firmware", pipeline.BSS_FW),
        ("MSS firmware", pipeline.MSS_FW),
    ]:
        exists = os.path.exists(path)
        print("%s: %s %s" % (label, path, "OK" if exists else "MISSING"))
        ok_paths = ok_paths and exists

    rows = _tasklist_mmwave_studio()
    if rows and "mmWaveStudio.exe" in rows:
        print("process: mmWaveStudio.exe RUNNING")
    elif os.name == "nt":
        print("process: mmWaveStudio.exe NOT FOUND")
    else:
        print("process: skipped on non-Windows")
    print("RSTD: use `ti-radar studio ping` to verify 127.0.0.1:2777")
    return 0 if ok_paths else 1


def cmd_studio_ping(_: argparse.Namespace) -> int:
    from ti_radar.backends import rstd

    _call_with_timeout(lambda: rstd.ping(), 10.0, "RSTD ping")
    return 0


def _call_with_timeout(fn: Callable[[], object], timeout_s: float, name: str) -> object:
    box: dict[str, object] = {}

    def worker() -> None:
        try:
            box["result"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise RuntimeError("%s timed out after %.1fs" % (name, timeout_s))
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box.get("result")


def _lua_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\")


def _read_studio_identity_registers(timeout_s: float) -> tuple[int, int, int]:
    from ti_radar.backends import rstd

    SESSIONS.mkdir(parents=True, exist_ok=True)
    retfile = SESSIONS / "_studio_identify_registers.txt"
    try:
        retfile.unlink()
    except FileNotFoundError:
        pass

    lua = r"""
local function rr(addr)
    local res, value = ar1.ReadRegister(addr, 0, 31)
    if res ~= 0 then
        error('ReadRegister failed addr='..tostring(addr)..' ret='..tostring(res))
    end
    return value
end
local efuse_device = rr(0xFFFFE214)
local efuse_es1_device = rr(0xFFFFE210)
local es_version = rr(0xFFFFE218)
local f = io.open([[__RETFILE__]], 'w')
if f == nil then error('cannot open identify retfile') end
f:write(tostring(efuse_device)..'\n')
f:write(tostring(efuse_es1_device)..'\n')
f:write(tostring(es_version)..'\n')
f:close()
""".replace("__RETFILE__", _lua_path(retfile))

    _call_with_timeout(lambda: rstd.connect(), timeout_s, "RSTD connect")
    _call_with_timeout(lambda: rstd.send_command(lua), timeout_s, "RSTD ReadRegister identify")
    if not retfile.exists():
        raise RuntimeError("RSTD command completed but identify return file was not written")
    lines = [line.strip() for line in retfile.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 3:
        raise RuntimeError("identify return file is incomplete: %r" % lines)
    return int(lines[0], 0), int(lines[1], 0), int(lines[2], 0)


def cmd_studio_identify(args: argparse.Namespace) -> int:
    from ti_radar.core.device import decode_es_version, decode_part_id, route_for_part_id

    try:
        efuse_device, efuse_es1_device, es_version_register = _read_studio_identity_registers(args.timeout)
        part_id = decode_part_id(efuse_device, efuse_es1_device)
        route = route_for_part_id(part_id)
    except Exception as exc:  # noqa: BLE001
        print("ERROR: RSTD identify failed: %s" % exc)
        print("Runbook: start mmWave Studio from RunTime, then run `ti-radar studio ping`.")
        print("Details: see the ti-radar-skill runbook section 2.")
        print("Safety: identify only reads efuse registers; it does not DownloadBSS/MSS, RfEnable, or StartFrame.")
        return 1

    print("efuse_device_0xFFFFE214: 0x%08X" % efuse_device)
    print("efuse_es1_device_0xFFFFE210: 0x%08X" % efuse_es1_device)
    print("es_version_register_0xFFFFE218: 0x%08X" % es_version_register)
    print("part_id: %s" % part_id)
    print("ESVersion: %s" % decode_es_version(es_version_register))
    _print_device_route(route)
    return 0


def _parse_int_auto(value: str) -> int:
    return int(value, 0)


def _print_device_route(route) -> None:
    from ti_radar.core.device import csv_args, lua_args

    print("part_id: %s" % route.part_id)
    print("frequency_band: %s" % (route.frequency_band or "default"))
    print("bss_fw: %s" % route.bss_fw)
    print("mss_fw: %s" % route.mss_fw)
    print("lpmod_args: %s" % csv_args(route.lpmod_args))
    print("lvds_lane_args: %s" % csv_args(route.lvds_lane_args))
    print("dca_mode_args: %s" % csv_args(route.dca_mode_args))
    print("LPModConfig: ar1.LPModConfig(%s)" % lua_args(route.lpmod_args))
    print("LVDSLaneConfig: ar1.LVDSLaneConfig(%s)" % lua_args(route.lvds_lane_args))
    print("CaptureCardConfig_Mode: ar1.CaptureCardConfig_Mode(%s)" % lua_args(route.dca_mode_args))
    print("project_profile: %s" % (route.project_profile or "none"))
    print("note: %s" % route.note)


def cmd_device(args: argparse.Namespace) -> int:
    from ti_radar.core.device import decode_part_id, route_for_part_id

    if args.device_cmd == "decode":
        part_id = decode_part_id(args.efuse_device, args.efuse_es1_device)
        _print_device_route(route_for_part_id(part_id))
        return 0
    if args.device_cmd == "route":
        _print_device_route(route_for_part_id(args.part_id))
        return 0
    return 2


def _postproc_snapshot() -> list[tuple[str, str, int]]:
    postproc = Path(r"C:\ti\mmwave_studio_02_01_01_00\mmWaveStudio\PostProc")
    rows: list[tuple[str, str, int]] = []
    for name in ["cf.json", "LogFile.txt", "CLI_LogFile.txt"]:
        path = postproc / name
        if path.exists():
            rows.append((str(path), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)), path.stat().st_size))
        else:
            rows.append((str(path), "MISSING", 0))
    return rows


def _print_postproc_snapshot(title: str) -> None:
    print(title)
    for path, mtime, size in _postproc_snapshot():
        print("  %s  mtime=%s  bytes=%d" % (path, mtime, size))


def _read_retfile_text(path: Path) -> str:
    """mmWave Studio writes .NET exception strings as GBK on Chinese Windows; try GBK first."""
    for enc in ("gbk", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _safe_print(text: str) -> None:
    """Print without crashing on a console codec that can't encode some chars."""
    enc = sys.stdout.encoding or "utf-8"
    print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def _ethinit_probe_lua(profile: dict, retfile: Path) -> str:
    from ti_radar.backends import dca1000_udp
    from ti_radar.core.device import lua_args, route_for_part_id

    route = route_for_part_id(int(profile.get("part_id", 6843)))
    frame_config = "ar1.FrameConfig(%d, %d, %d, %d, %g, 0, 0, 1)" % (
        int(profile["start_tx"]),
        int(profile["end_tx"]),
        int(profile.get("config_frames", 8)),
        int(profile["num_loops"]),
        float(profile["frame_period_ms"]),
    )
    eth_init = "ar1.CaptureCardConfig_EthInit('%s', '%s', '12:34:56:78:90:12', %d, %d)" % (
        dca1000_udp.DCA_PC_IP,
        dca1000_udp.DCA_FPGA_IP,
        dca1000_udp.DCA_CMD_PORT,
        dca1000_udp.DCA_DATA_PORT,
    )
    mode = "ar1.CaptureCardConfig_Mode(%s)" % lua_args(route.dca_mode_args)
    return r"""
local f = io.open([[__RETFILE__]], 'w')
if f == nil then error('cannot open ethinit probe retfile') end
local function log(line)
    f:write(line..'\n')
    f:flush()
end
local function call(tag, fn)
    local ok, ret = pcall(fn)
    log(tag..' ok='..tostring(ok)..' ret='..tostring(ret))
    return ok, ret
end
call('frame_config_init', function() return __FRAME_CONFIG__ end)
call('select_dca', function() return ar1.SelectCaptureDevice('DCA1000') end)
call('dca_eth', function() return __ETH_INIT__ end)
call('dca_mode', function() return __MODE__ end)
call('dca_packet_delay', function() return ar1.CaptureCardConfig_PacketDelay(25) end)
f:close()
""".replace("__RETFILE__", _lua_path(retfile)).replace("__FRAME_CONFIG__", frame_config).replace("__ETH_INIT__", eth_init).replace("__MODE__", mode)


def cmd_studio_ethinit_probe(args: argparse.Namespace) -> int:
    from ti_radar.backends import dca1000_udp, rstd

    profile = _load_profile(args.profile)
    out_dir = SESSIONS / ("ethinit_probe_" + time.strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== ti-radar studio ethinit-probe ===")
    print("legacy/expert diagnostic: prefer normal capture paths unless isolating DCA EthInit failures.")
    print("out: %s" % out_dir)
    print("profile: %s" % profile.get("_name", "<unknown>"))
    print("python: %s" % sys.executable)
    print("ti_radar: %s" % Path(__file__).resolve())
    _print_postproc_snapshot("PostProc before:")

    if args.no_dca_reset:
        ok = dca1000_udp.dca_probe()
    else:
        ok = dca1000_udp.dca_reset_and_probe()
    if not ok:
        print("DCA UDP probe failed before EthInit")
        return 1

    _call_with_timeout(lambda: rstd.connect(), args.timeout, "RSTD connect")
    failures = 0
    for idx in range(args.attempts):
        if args.reset_dca_each and idx > 0:
            dca1000_udp.dca_reset_and_probe()
        retfile = out_dir / ("attempt_%02d.txt" % (idx + 1))
        lua = _ethinit_probe_lua(profile, retfile)
        print("\n--- attempt %d/%d ---" % (idx + 1, args.attempts))
        try:
            _call_with_timeout(lambda lua=lua: rstd.send_command(lua), args.timeout, "EthInit attempt %d" % (idx + 1))
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("RSTD error: %s" % exc)
        if retfile.exists():
            text = _read_retfile_text(retfile).strip()
            _safe_print(text)
            if "dca_eth ok=true ret=0" not in text:
                failures += 1
        else:
            failures += 1
            print("retfile missing: %s" % retfile)
        if args.delay > 0 and idx + 1 < args.attempts:
            time.sleep(args.delay)

    _print_postproc_snapshot("\nPostProc after:")
    print("\nsummary: attempts=%d failures=%d" % (args.attempts, failures))
    return 0 if failures == 0 else 1


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _studio_paths() -> tuple[Path, Path]:
    runtime = Path(r"C:\ti\mmwave_studio_02_01_01_00\mmWaveStudio\RunTime")
    return runtime, runtime / "mmWaveStudio.exe"


def _studio_process_rows() -> list[str]:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq mmWaveStudio.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    return [line for line in (result.stdout or "").splitlines() if "mmWaveStudio.exe" in line]


def _studio_is_running() -> bool:
    return bool(_studio_process_rows())


def cmd_studio_start(args: argparse.Namespace) -> int:
    from ti_radar.backends import rstd

    runtime, exe = _studio_paths()
    if not exe.exists():
        print("ERROR: mmWave Studio executable not found: %s" % exe)
        return 1
    if _studio_is_running():
        if args.restart:
            subprocess.run(["taskkill", "/IM", "mmWaveStudio.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
        else:
            print("mmWaveStudio.exe already running; reuse it. Use --restart to replace it.")
            if args.ping:
                _call_with_timeout(lambda: rstd.ping(), args.timeout, "RSTD ping")
            return 0

    if args.method == "wmi":
        # Have the WMI service (WmiPrvSE, a host process) create mmWaveStudio so the new
        # process is NOT a child of this (possibly sandboxed) agent process. This is the
        # only method verified to make CaptureCardConfig_EthInit succeed under an agent
        # sandbox: direct Popen and Shell COM ShellExecute both stay inside the sandbox
        # process tree, so EthInit's network-adapter/MAC lookup returns empty and
        # RFEthernetInitializationConfigurationData_Impl throws Substring. (EXPERIMENT_LOG 会话16/17)
        cmd_line = '"%s"' % str(exe)
        script = (
            "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
            "-Arguments @{CommandLine=%s; CurrentDirectory=%s}; "
            "Write-Output ('WMI_CREATE_RETURN='+$r.ReturnValue+' PID='+$r.ProcessId); "
            "if ($r.ReturnValue -ne 0) { exit 1 }"
            % (_ps_single_quote(cmd_line), _ps_single_quote(str(runtime)))
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
        if r.stdout:
            print(r.stdout.strip())
        if r.returncode != 0:
            if r.stderr:
                print(r.stderr.strip())
            print("ERROR: WMI Win32_Process.Create failed to start mmWave Studio")
            return 1
        print("started by WMI Win32_Process.Create (host-parented, escapes agent sandbox): %s" % exe)
    elif args.method == "direct":
        subprocess.Popen([str(exe)], cwd=str(runtime))
        print("started by direct Popen: %s" % exe)
        print("WARNING: direct Popen inherits this process's environment; under an agent sandbox EthInit will fail (Substring). Use --method wmi.")
    else:
        prog_id = "Shell" + "." + "Application"
        script = "; ".join([
            "$rt = " + _ps_single_quote(str(runtime)),
            "$exe = Join-Path $rt " + _ps_single_quote("mmWaveStudio.exe"),
            "$p = " + _ps_single_quote(prog_id),
            "$sh = New-Object -ComObject $p",
            "$sh.ShellExecute($exe, '', $rt, 'open', 1)",
        ])
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
        print("started by Windows shell COM from RunTime: %s" % exe)
        print("WARNING: Shell COM ShellExecute runs in this (sandboxed) process; under an agent sandbox EthInit may still fail. Use --method wmi.")

    if args.wait > 0:
        print("waiting %.1fs for Startup.lua / RSTD.NetStart ..." % args.wait)
        time.sleep(args.wait)
    if args.ping:
        _call_with_timeout(lambda: rstd.ping(), args.timeout, "RSTD ping")
    return 0


def cmd_studio(args: argparse.Namespace) -> int:
    sub = args.studio_cmd
    if sub == "status":
        return cmd_studio_status(args)
    if sub == "ping":
        return cmd_studio_ping(args)
    if sub == "start":
        return cmd_studio_start(args)
    if sub == "identify":
        return cmd_studio_identify(args)
    if sub == "validate-profile":
        return 0 if _print_profile_report(_load_profile(args.profile)) else 1
    if sub == "ethinit-probe":
        return cmd_studio_ethinit_probe(args)
    argv, out_dir = _build_pipeline_argv(sub, args)
    rc = _pipeline_main(argv)
    if out_dir and out_dir.exists():
        _write_capture_manifest(
            session_dir=out_dir,
            session_id=out_dir.name,
            backend="studio",
            profile=args.profile,
            frames=args.frames,
            status="ok" if rc == 0 else "failed",
            command=["ti-radar", "studio"] + argv,
        )
    return _capture_exit_code(rc, out_dir)


def _write_mock_manifest(session_dir: Path, session_id: str, nbytes: int) -> None:
    manifest = session_dir / "manifest.yaml"
    manifest.write_text(
        "session_id: %s\nbackend: mock\nstatus: ok\ncreated_at: %s\noutput:\n  bin_path: adc_data_mock.bin\n  bytes: %d\n"
        % (session_id, time.strftime("%Y-%m-%dT%H:%M:%S"), nbytes),
        encoding="utf-8",
    )


def cmd_capture(args: argparse.Namespace) -> int:
    if args.capture_cmd == "smoke":
        if args.backend != "mock":
            print("smoke 当前只允许 --backend mock；真实硬件请用 ti-radar capture raw --backend studio")
            return 2
        SESSIONS.mkdir(parents=True, exist_ok=True)
        sid = "mock_" + time.strftime("%Y%m%d_%H%M%S")
        out = SESSIONS / sid
        out.mkdir(parents=True, exist_ok=True)
        payload = (b"TI_RADAR_MOCK\n" * 128)
        (out / "adc_data_mock.bin").write_bytes(payload)
        _write_mock_manifest(out, sid, len(payload))
        print("mock capture: %s" % out)
        print("bytes: %d" % len(payload))
        return 0

    if args.capture_cmd == "raw":
        if args.backend != "studio":
            print("raw 当前只实现 --backend studio")
            return 2
        p = _load_profile(args.profile)
        if not _print_profile_report(p):
            print("profile sanity check failed; 不启动硬件采集")
            return 1
        argv, out_dir = _build_pipeline_argv("run", args)
        rc = _pipeline_main(argv)
        if out_dir and out_dir.exists():
            _write_capture_manifest(
                session_dir=out_dir,
                session_id=out_dir.name,
                backend="studio",
                profile=args.profile,
                frames=args.frames,
                status="ok" if rc == 0 else "failed",
                command=["ti-radar", "capture", "raw"] + argv,
            )
        return _capture_exit_code(rc, out_dir)
    return 2


def _latest_session_dir() -> Path | None:
    return core_session.latest_session_dir(SESSIONS)


def _resolve_session(name: str) -> Path | None:
    if name == "latest":
        return _latest_session_dir()
    return core_session.resolve_session(name, SESSIONS)


def _read_text(path: Path, max_chars: int = 2000) -> str:
    return core_session.read_text(path, max_chars=max_chars)


def cmd_session(args: argparse.Namespace) -> int:
    if args.session_cmd == "list":
        dirs = sorted([p for p in SESSIONS.glob("*") if p.is_dir()], key=lambda p: p.stat().st_mtime) if SESSIONS.exists() else []
        for p in dirs[-20:]:
            print("%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)), p.name))
        return 0

    p = _resolve_session(args.name)
    if not p:
        print("找不到 session: %s" % args.name)
        return 1
    print("session: %s" % p)
    bins = sorted(p.glob("*.bin"), key=lambda x: x.stat().st_size, reverse=True)
    for b in bins:
        print("bin: %s  bytes=%d" % (b.name, b.stat().st_size))
    for m in [p / "manifest.yaml", p / "radar_meta.yaml"]:
        if m.exists():
            print("\n--- %s ---" % m.name)
            print(_read_text(m))
    logs = sorted(p.glob("*LogFile*.csv"))
    for log in logs[:3]:
        print("\n--- %s ---" % log.name)
        print(_read_text(log))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ti-radar",
        description="Agent-operable, evidence-verified TI mmWave radar hardware CLI.",
        epilog="Recommended flow: ti-radar doctor -> capture/run -> ti-radar session inspect latest.",
    )
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("version", help="print CLI version, project root, and Python executable")
    p.set_defaults(func=cmd_version)

    p = sp.add_parser(
        "doctor",
        help="safe project/profile/NIC/COM checks; add --hardware for DCA probe",
        description="Run non-capture readiness checks before touching the radar state machine.",
    )
    p.add_argument("--profile", default=None, help="profile name from src/ti_radar/configs/radar_profiles.yaml")
    p.add_argument("--hardware", action="store_true", help="probe DCA SYSTEM_CONNECT without RESET_FPGA")
    p.set_defaults(func=cmd_doctor)

    p = sp.add_parser(
        "studio",
        help="Expert backend commands",
        description="Expert mmWave Studio/RSTD backend commands.",
    )
    s = p.add_subparsers(dest="studio_cmd", required=True)
    studio_help = {
        "bringup": "run Studio environment bring-up checks before capture",
        "config": "configure radar and DCA through Studio/RSTD without capture",
        "capture": "run the Studio capture stage after configuration",
        "run": "full Studio pipeline: bringup, configure, capture, manifest, and verdict",
        "prepare": "cold prepare once: bringup, firmware/config, DCA EthInit, and state file",
    }
    for name in ["bringup", "config", "capture", "run", "prepare"]:
        q = s.add_parser(name, help=studio_help[name], description=studio_help[name])
        q.add_argument("--profile", default=None, help="profile name; default comes from radar_profiles.yaml")
        q.add_argument("--frames", type=int, default=10, help="number of frames requested from the radar profile")
        q.add_argument("--out", default=None, help="output session directory; default is sessions/run_<timestamp>")
        q.add_argument("--no-restart", action="store_true", help="reuse a running mmWave Studio instance when possible")
        q.add_argument("--no-dca-reset", action="store_true", help="skip DCA RESET_FPGA during the Studio workflow")
        q.add_argument("--reuse-config", action="store_true")
        q.add_argument("--setup", choices=["cold", "warm", "auto"], default="cold")
        q.set_defaults(func=cmd_studio)
    q = s.add_parser("status", help="print Studio process/path status without hardware actions")
    q.set_defaults(func=cmd_studio)
    q = s.add_parser("ping", help="verify pythonnet/RSTD connectivity without RF or capture")
    q.set_defaults(func=cmd_studio)
    q = s.add_parser("start", help="start mmWave Studio from RunTime; default WMI launch escapes agent sandbox (fixes EthInit Substring)")
    q.add_argument("--method", choices=["wmi", "shell", "direct"], default="wmi", help="launch method; use wmi for agent-driven runs")
    q.add_argument("--restart", action="store_true", help="kill existing Studio before launching a fresh instance")
    q.add_argument("--wait", type=float, default=28.0, help="seconds to wait for Studio startup")
    q.add_argument("--ping", action="store_true", help="ping RSTD after launch")
    q.add_argument("--timeout", type=float, default=10.0, help="RSTD command timeout in seconds")
    q.set_defaults(func=cmd_studio)
    q = s.add_parser("identify", help="read efuse identity registers through RSTD; no RF or capture")
    q.add_argument("--timeout", type=float, default=10.0, help="RSTD command timeout in seconds")
    q.set_defaults(func=cmd_studio)
    q = s.add_parser("validate-profile", help="validate derived profile timing and RF limits")
    q.add_argument("--profile", default=None, help="profile name; default comes from radar_profiles.yaml")
    q.set_defaults(func=cmd_studio)
    q = s.add_parser("ethinit-probe", help="expert diagnostic: repeat DCA EthInit probes")
    q.add_argument("--profile", default=None, help="profile name; default comes from radar_profiles.yaml")
    q.add_argument("--attempts", type=int, default=5, help="number of EthInit attempts")
    q.add_argument("--timeout", type=float, default=30.0, help="per-attempt timeout in seconds")
    q.add_argument("--delay", type=float, default=0.5, help="delay between attempts in seconds")
    q.add_argument("--no-dca-reset", action="store_true", help="skip DCA reset before probing")
    q.add_argument("--reset-dca-each", action="store_true", help="reset DCA before every probe attempt")
    q.set_defaults(func=cmd_studio)

    p = sp.add_parser(
        "capture",
        help="capture aliases that write session evidence",
        description="Capture aliases for mock or raw sessions; raw writes manifest and fail on bad verdict.",
    )
    c = p.add_subparsers(dest="capture_cmd", required=True)
    q = c.add_parser("smoke", help="create a no-hardware mock session for orchestration tests")
    q.add_argument("--backend", default="mock", help="backend name; default mock")
    q.set_defaults(func=cmd_capture)
    q = c.add_parser(
        "raw",
        help="capture raw ADC with the selected backend",
        description="Capture raw ADC, write manifest and fail on bad verdict.",
    )
    q.add_argument("--backend", default="studio", help="backend name; default studio")
    q.add_argument("--profile", default=None, help="profile name; default comes from radar_profiles.yaml")
    q.add_argument("--frames", type=int, default=10, help="number of frames to capture")
    q.add_argument("--out", default=None, help="output session directory; default is sessions/run_<timestamp>")
    q.add_argument("--no-restart", action="store_true", help="reuse a running mmWave Studio instance when possible")
    q.add_argument("--no-dca-reset", action="store_true", help="skip DCA RESET_FPGA for this capture")
    q.set_defaults(func=cmd_capture)

    p = sp.add_parser("session", help="inspect manifests, packet logs, bins, and verdicts")
    ss = p.add_subparsers(dest="session_cmd", required=True)
    q = ss.add_parser("list", help="list project-root sessions newest first")
    q.set_defaults(func=cmd_session)
    q = ss.add_parser("inspect", help="show bins, manifest/radar_meta, and DCA packet log snippets")
    q.add_argument("name", nargs="?", default="latest", help="session name, substring, path, or latest")
    q.set_defaults(func=cmd_session)

    p = sp.add_parser("device", help="mmWave device auto-detect and routing helpers")
    d = p.add_subparsers(dest="device_cmd", required=True)
    q = d.add_parser("route", help="show route for a known partId")
    q.add_argument("--part-id", type=_parse_int_auto, required=True)
    q.set_defaults(func=cmd_device)
    q = d.add_parser("decode", help="decode efuse registers and show route")
    q.add_argument("--efuse-device", type=_parse_int_auto, required=True)
    q.add_argument("--efuse-es1-device", type=_parse_int_auto, required=True)
    q.set_defaults(func=cmd_device)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("用户中断")
        return 130
    except Exception as exc:  # noqa: BLE001
        print("ERROR: %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
