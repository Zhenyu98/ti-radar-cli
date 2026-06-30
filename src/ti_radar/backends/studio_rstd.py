"""mmWave Studio + RSTD backend for ti-radar."""

from __future__ import annotations

from dataclasses import dataclass
import glob
import os
import subprocess
import threading
import time

from ti_radar.backends.base import CaptureBackend
from ti_radar.backends import dca1000_udp
from ti_radar.backends import rstd
from ti_radar.core import profile as core_profile
from ti_radar.core.device import lua_args, route_for_part_id

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MMW_DIR = os.path.join(PACKAGE_ROOT, "mmw")
STUDIO = r"C:\ti\mmwave_studio_02_01_01_00"
SCRIPTS_DIR = os.path.join(STUDIO, "mmWaveStudio", "Scripts")
FW = os.path.join(STUDIO, "rf_eval_firmware")
DCA_FPGA_IP = dca1000_udp.DCA_FPGA_IP
DCA_PC_IP = dca1000_udp.DCA_PC_IP
DCA_CMD_PORT = dca1000_udp.DCA_CMD_PORT
DCA_DATA_PORT = dca1000_udp.DCA_DATA_PORT


@dataclass(frozen=True)
class StudioStep:
    name: str
    expr: str
    checked: bool
    timeout_s: int


def lua_path(path: str) -> str:
    return path.replace("\\", "\\\\")


def checked_lua(expr: str) -> str:
    """Wrap an ar1 call so nonzero returns become Lua errors."""
    return ("local ret = %s; "
            "WriteToLog('ti_radar ret='..tostring(ret)..'\\n', ret == 0 and 'green' or 'red'); "
            "if ret ~= 0 then error('ti_radar step failed ret='..tostring(ret)) end" % expr)


def config_step_plan(
    profile: dict,
    studio_root: str = STUDIO,
    com: int | None = None,
    part_id: int | None = None,
    sleep_name: str = "sleep",
) -> list[StudioStep]:
    p = dict(profile)
    com_port = int(com if com is not None else p["com_port"])
    route_part_id = int(part_id if part_id is not None else p.get("part_id", 6843))
    route = route_for_part_id(route_part_id, studio_root)
    prof = core_profile.profile_config_lua(p)

    steps = [
        StudioStep("full_reset", "ar1.FullReset()", False, 20),
        StudioStep("sop", "ar1.SOPControl(2)", False, 10),
        StudioStep("connect_com", "ar1.Connect(%d, 115200, 1000)" % com_port, True, 20),
        StudioStep("read_efuse_214", "ar1.ReadRegister(0xFFFFE214, 0, 31)", False, 10),
        StudioStep("read_efuse_210", "ar1.ReadRegister(0xFFFFE210, 0, 31)", False, 10),
        StudioStep("read_esver_218", "ar1.ReadRegister(0xFFFFE218, 0, 31)", False, 10),
    ]
    if route.frequency_band:
        steps.append(
            StudioStep(
                "band_%s" % route.frequency_band.lower(),
                "ar1.frequencyBandSelection('%s')" % route.frequency_band,
                False,
                10,
            )
        )
    steps += [
        StudioStep("download_bss", "ar1.DownloadBSSFw('%s')" % lua_path(route.bss_fw), True, 90),
        StudioStep("download_mss", "ar1.DownloadMSSFw('%s')" % lua_path(route.mss_fw), True, 90),
        StudioStep("power_on", "ar1.PowerOn(1, 1000, 0, 0)", True, 30),
        StudioStep("rf_enable", "ar1.RfEnable()", True, 30),
        StudioStep("chan_adc", "ar1.ChanNAdcConfig(1, 1, 1, 1, 1, 1, 1, 2, 2, 0)", True, 20),
        StudioStep("lpmod", "ar1.LPModConfig(%s)" % lua_args(route.lpmod_args), True, 20),
        StudioStep("rf_init", "ar1.RfInit()", True, 60),
        StudioStep(sleep_name, "RSTD.Sleep(1000)", False, 5),
        StudioStep("data_path", "ar1.DataPathConfig(1, 1, 0)", True, 20),
        StudioStep("lvds_clk", "ar1.LvdsClkConfig(1, 1)", True, 20),
        StudioStep("lvds_lane", "ar1.LVDSLaneConfig(%s)" % lua_args(route.lvds_lane_args), True, 20),
        StudioStep("profile", prof, True, 20),
        StudioStep("chirp0", "ar1.ChirpConfig(0, 0, 0, 0, 0, 0, 0, 1, 0, 0)", True, 20),
        StudioStep("chirp2", "ar1.ChirpConfig(2, 2, 0, 0, 0, 0, 0, 0, 1, 0)", True, 20),
        StudioStep("chirp1", "ar1.ChirpConfig(1, 1, 0, 0, 0, 0, 0, 0, 0, 1)", True, 20),
        # FrameConfig must run before SelectCaptureDevice/CaptureCardConfig_EthInit:
        # mmWave Studio's RFEthernetInitializationConfigurationData_Impl() reads the
        # frame/data config when building the DCA Ethernet config, and crashes with
        # System.ArgumentOutOfRangeException (String.Substring) when no FrameConfig
        # has primed it. This matches DCAconnect.lua order (Chirp -> FrameConfig ->
        # SelectCaptureDevice -> EthInit). The real frame count is re-issued by the
        # capture step right before StartRecord/StartFrame.
        StudioStep(
            "frame_config_init",
            "ar1.FrameConfig(%d, %d, %d, %d, %g, 0, 0, 1)"
            % (int(p["start_tx"]), int(p["end_tx"]), int(p.get("config_frames", 8)),
               int(p["num_loops"]), float(p["frame_period_ms"])),
            True,
            20,
        ),
        StudioStep("select_dca", "ar1.SelectCaptureDevice('DCA1000')", True, 20),
        StudioStep(
            "dca_eth",
            "ar1.CaptureCardConfig_EthInit('%s', '%s', '12:34:56:78:90:12', %d, %d)"
            % (DCA_PC_IP, DCA_FPGA_IP, DCA_CMD_PORT, DCA_DATA_PORT),
            True,
            30,
        ),
        StudioStep("dca_mode", "ar1.CaptureCardConfig_Mode(%s)" % lua_args(route.dca_mode_args), True, 20),
        StudioStep("dca_packet_delay", "ar1.CaptureCardConfig_PacketDelay(25)", True, 20),
    ]
    return steps


def pipeline_config_steps(profile: dict) -> list[tuple[str, str, bool, int]]:
    return [(step.name, step.expr, step.checked, step.timeout_s) for step in config_step_plan(profile)]


def rstd_config_steps(com: int, part_id: int | None = None, profile: dict | None = None) -> list[tuple[str, str, int]]:
    p = dict(profile or core_profile.load_profile("default_6843"))
    plan = config_step_plan(p, com=com, part_id=part_id, sleep_name="sleep_after_rf_init")
    return [
        (step.name, checked_lua(step.expr) if step.checked else step.expr, step.timeout_s)
        for step in plan
    ]


def pipeline_capture_steps(
    profile: dict,
    n_frames: int,
    bin_path: str,
    include_frame_config: bool = True,
) -> list[tuple[str, str, bool, int]]:
    steps: list[tuple[str, str, bool, int]] = []
    if include_frame_config:
        steps.append(
            (
                "frame_config",
                "ar1.FrameConfig(%d, %d, %d, %d, %g, 0, 0, 1)"
                % (profile["start_tx"], profile["end_tx"], n_frames, profile["num_loops"], profile["frame_period_ms"]),
                True,
                20,
            )
        )
    steps += [
        ("start_record", "ar1.CaptureCardConfig_StartRecord('%s', 1)" % lua_path(bin_path), True, 20),
        ("sleep", "RSTD.Sleep(1000)", False, 5),
        ("start_frame", "ar1.StartFrame()", True, 40),
    ]
    return steps


def rstd_capture_steps(
    start_tx: int,
    end_tx: int,
    n_frames: int,
    n_chirps: int,
    frame_period_ms: float,
    bin_path: str,
    include_frame_config: bool = True,
) -> list[tuple[str, str, int]]:
    steps: list[tuple[str, str, bool, int]] = []
    if include_frame_config:
        steps.append(
            (
                "frame_config",
                "ar1.FrameConfig(%d, %d, %d, %d, %.6g, 0, 0, 1)"
                % (start_tx, end_tx, n_frames, n_chirps, frame_period_ms),
                True,
                20,
            )
        )
    steps += [
        ("start_record", "ar1.CaptureCardConfig_StartRecord('%s', 1)" % lua_path(bin_path), True, 20),
        ("sleep", "RSTD.Sleep(1000)", False, 5),
        ("start_frame", "ar1.StartFrame()", True, 40),
    ]
    return [(name, checked_lua(expr) if checked else expr, timeout) for name, expr, checked, timeout in steps]


# MATLAB fallback templates remain unchanged from the validated legacy backend.
CONFIG_LUA = r"""
ar1.FullReset()
ar1.SOPControl(2)
ar1.Connect(__COM__, 115200, 1000)
ar1.ReadRegister(0xFFFFE214, 0, 31)
ar1.ReadRegister(0xFFFFE210, 0, 31)
ar1.frequencyBandSelection("60G")
ar1.ReadRegister(0xFFFFE218, 0, 31)
info = debug.getinfo(1, 'S')
fp = string.gsub(info.source, "@", "")
fp = string.gsub(fp, "ti_radar_config.lua", "")
fw = fp.."..\\..\\rf_eval_firmware"
ar1.DownloadBSSFw(fw.."\\radarss\\xwr68xx_radarss.bin")
ar1.DownloadMSSFw(fw.."\\masterss\\xwr68xx_masterss.bin")
ar1.PowerOn(1, 1000, 0, 0)
ar1.RfEnable()
ar1.ChanNAdcConfig(1, 1, 1, 1, 1, 1, 1, 2, 2, 0)
ar1.LPModConfig(0, 0)
ar1.RfInit()
RSTD.Sleep(1000)
ar1.DataPathConfig(1, 1, 0)
ar1.LvdsClkConfig(1, 1)
ar1.LVDSLaneConfig(0, 1, 1, 0, 0, 1, 0, 0)
ar1.ProfileConfig(0, 60.25, 200, 6, 60, 0, 0, 0, 0, 0, 0, 29.982, 0, 128, 10000, 0, 131072, 30)
ar1.ChirpConfig(0, 0, 0, 0, 0, 0, 0, 1, 0, 0)
ar1.ChirpConfig(2, 2, 0, 0, 0, 0, 0, 0, 1, 0)
ar1.ChirpConfig(1, 1, 0, 0, 0, 0, 0, 0, 0, 1)
ar1.SelectCaptureDevice("DCA1000")
ar1.CaptureCardConfig_EthInit("192.168.33.30", "192.168.33.180", "12:34:56:78:90:12", 4096, 4098)
ar1.CaptureCardConfig_Mode(1, 2, 1, 2, 3, 30)
ar1.CaptureCardConfig_PacketDelay(25)
WriteToLog("ti_radar: config done\n", "green")
"""

CAPTURE_LUA = r"""
ar1.FrameConfig(__STX__, __ETX__, __NFRAMES__, __NCHIRPS__, __FP__, 0, 0, 1)
adc_data_path = "__BIN__"
ar1.CaptureCardConfig_StartRecord(adc_data_path, 1)
RSTD.Sleep(1000)
ar1.StartFrame()
WriteToLog("ti_radar: StartFrame issued\n", "green")
"""


def load_profile_arg(profile: str | dict | None) -> dict:
    if profile is None:
        return core_profile.load_profile("default_6843")
    if isinstance(profile, str):
        return core_profile.load_profile(profile)
    return dict(profile)


class StudioRstdBackend(CaptureBackend):
    name = "mmwstudio"

    def __init__(self, com_port=3, part_id=None, n_frames=125, n_chirps=64, frame_period_ms=60,
                 start_tx=0, end_tx=2, driver="rstd", matlab="matlab", matlab_timeout=300,
                 profile=None):
        self.profile = load_profile_arg(profile)
        self.com_port = int(com_port if com_port is not None else self.profile.get("com_port", 3))
        self.part_id = int(part_id if part_id is not None else self.profile.get("part_id", 6843))
        self.n_frames = int(n_frames)
        self.n_chirps = int(n_chirps)
        self.frame_period_ms = float(frame_period_ms)
        self.start_tx = int(start_tx)
        self.end_tx = int(end_tx)
        self.driver = driver
        self.matlab = matlab
        self.matlab_timeout = matlab_timeout
        self._configured = False
        self._cur = None
        os.makedirs(MMW_DIR, exist_ok=True)

    def _rstd_step(self, name, lua, timeout_s):
        box = {}

        def worker():
            try:
                box["status"] = rstd.send_command(lua)
            except Exception as exc:  # noqa: BLE001
                box["err"] = exc
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout_s)
        if t.is_alive():
            raise RuntimeError("RSTD 步骤 %s 超时 %ss（可能 mmWaveStudio 弹窗卡住）" % (name, timeout_s))
        if "err" in box:
            raise RuntimeError("RSTD 步骤 %s 失败: %r" % (name, box["err"]))
        return box.get("status")

    def _rstd_config(self):
        rstd.connect()
        for name, lua, timeout_s in rstd_config_steps(self.com_port, part_id=self.part_id, profile=self.profile):
            print("[mmwstudio] config %s ..." % name, flush=True)
            self._rstd_step(name, lua, timeout_s)
        print("[mmwstudio] 雷达配置完成（rstd）")

    def _rstd_capture(self, bin_path):
        for name, lua, timeout_s in rstd_capture_steps(
            self.start_tx,
            self.end_tx,
            self.n_frames,
            self.n_chirps,
            self.frame_period_ms,
            bin_path,
            include_frame_config=False,
        ):
            print("[mmwstudio] capture %s ..." % name, flush=True)
            self._rstd_step(name, lua, timeout_s)

    def _write_config_lua(self):
        path = os.path.join(SCRIPTS_DIR, "ti_radar_config.lua")
        with open(path, "w") as f:
            f.write(CONFIG_LUA.replace("__COM__", str(self.com_port)))
        return path

    def _write_capture_lua(self, bin_path):
        s = (CAPTURE_LUA
             .replace("__STX__", str(self.start_tx)).replace("__ETX__", str(self.end_tx))
             .replace("__NFRAMES__", str(self.n_frames)).replace("__NCHIRPS__", str(self.n_chirps))
             .replace("__FP__", str(self.frame_period_ms)).replace("__BIN__", lua_path(bin_path)))
        path = os.path.join(SCRIPTS_DIR, "ti_radar_capture.lua")
        with open(path, "w") as f:
            f.write(s)
        return path

    def _matlab(self, lua_paths):
        luas = ", ".join("'%s'" % p for p in lua_paths)
        stmt = "addpath('%s'); rstd_dofile(%s)" % (MMW_DIR, luas)
        r = subprocess.run([self.matlab, "-batch", stmt],
                           capture_output=True, text=True, timeout=self.matlab_timeout)
        if r.stdout:
            print(r.stdout.rstrip())
        if r.returncode != 0 or "RSTD_DOFILE_OK" not in (r.stdout or ""):
            raise RuntimeError("MATLAB/RSTD 失败 (rc=%d)\n%s\n%s" % (r.returncode, r.stdout, r.stderr))

    def prepare(self):
        exp = self.n_frames * self.frame_period_ms / 1000.0
        print("[mmwstudio] driver=%s  COM%d  %d frames @ %.0fms ≈ %.1fs/采集"
              % (self.driver, self.com_port, self.n_frames, self.frame_period_ms, exp))
        self.profile["config_frames"] = self.n_frames
        if self.driver == "rstd":
            self._rstd_config()
            self._configured = True

    def start(self, session_id, label, out_dir):
        bin_path = os.path.join(out_dir, "adc_data.bin")
        exp_dur = self.n_frames * self.frame_period_ms / 1000.0
        print("[mmwstudio] 触发采集，预计 %.1fs …" % exp_dur)
        t0 = time.time_ns()
        if self.driver == "rstd":
            if not self._configured:
                self.profile["config_frames"] = self.n_frames
                self._rstd_config()
                self._configured = True
            self._rstd_capture(bin_path)
        else:
            self._matlab([self._write_config_lua(), self._write_capture_lua(bin_path)])
        self._cur = {"out_dir": out_dir, "bin_path": bin_path,
                     "t_radar_start_ns": t0, "exp_dur": exp_dur}
        return {"bin_path": bin_path, "t_radar_start_ns": t0}

    def stop(self):
        cur = self._cur or {}
        out_dir = cur.get("out_dir")
        exp = cur.get("exp_dur", 5.0)
        binf, last, stable = None, -1, 0
        deadline = time.time() + exp + 12.0
        while time.time() < deadline:
            bins = [b for b in glob.glob(os.path.join(out_dir or ".", "*.bin"))
                    if os.path.getsize(b) > 64]
            if bins:
                binf = max(bins, key=os.path.getsize)
                sz = os.path.getsize(binf)
                stable = stable + 1 if sz == last and sz > 0 else 0
                last = sz
                if stable >= 3:
                    break
            time.sleep(0.5)
        t1 = time.time_ns()
        nbytes = os.path.getsize(binf) if binf else 0
        print("[mmwstudio] 采集落盘: %s (%d bytes)" % (binf, nbytes))
        self._cur = None
        return {"t_radar_stop_ns": t1, "bytes": nbytes, "bin_actual": binf,
                "dur_s": (t1 - cur.get("t_radar_start_ns", t1)) / 1e9}

    def close(self):
        pass
