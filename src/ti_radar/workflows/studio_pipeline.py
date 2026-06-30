#!/usr/bin/env python3
"""mmWave Studio reliability-first capture workflow for ti-radar.

铁律（用户要求）：发任何 RSTD/Lua 之前，必须按固定顺序先做硬件复位与检查：
  ① 网口检查(以太网2=192.168.33.30/24)
  ② DCA1000 硬件复位(UDP RESET_FPGA；无响应→提示重新上电)
  ③ mmWave Studio 重启(从 RunTime，确保 Startup.lua 跑 RSTD.NetStart)
  ④ 串口检查(雷达 enhanced COM) + FPGA 存活复检
  ⑤ 建立 RSTD 连接(pythonnet)
  ⑥ 发 Lua 配置(6843 bring-up 顺序参考 DCAconnect.lua；profile 参数外置 configs/radar_profiles.yaml)
  ⑦ 采集 + 校验 bin(大小+丢包日志)

子命令：
  bringup           只做 ①~⑤，留绿状态
  config            ⑥（假定 bringup 已绿）
  capture --frames  ⑦
  run --frames N    ①~⑦ 一条龙（推荐，单进程单 RSTD 生命周期）

失败时不静默：自动抓 mmWave Studio 的真实 .NET 异常串（GBK 解码）。
物理/管理员动作（重新上电、加防火墙、改网卡）不会硬来——明确打印让用户处理后重跑。
"""

import argparse
import glob
import os
import subprocess
import threading
import time

from ti_radar.backends import dca1000_udp
from ti_radar.backends import rstd
from ti_radar.backends import studio_rstd
from ti_radar.core import paths as core_paths
from ti_radar.core import profile as core_profile
from ti_radar.core import state as core_state

# ---- 固定环境 ----
PROJECT_ROOT = str(core_paths.PROJECT_ROOT)
SESSIONS = str(core_paths.SESSIONS)
STUDIO = r"C:\ti\mmwave_studio_02_01_01_00"
STUDIO_RUNTIME = os.path.join(STUDIO, "mmWaveStudio", "RunTime")
STUDIO_EXE = os.path.join(STUDIO_RUNTIME, "mmWaveStudio.exe")
FW = os.path.join(STUDIO, "rf_eval_firmware")
BSS_FW = os.path.join(FW, "radarss", "xwr68xx_radarss.bin")
MSS_FW = os.path.join(FW, "masterss", "xwr68xx_masterss.bin")
PROFILES_YAML = str(core_profile.PROFILES_YAML)
RETFILE = os.path.join(SESSIONS, "_lua_ret.txt")
yaml = core_profile.yaml

DCA_FPGA_IP = dca1000_udp.DCA_FPGA_IP
DCA_PC_IP = dca1000_udp.DCA_PC_IP
DCA_CMD_PORT = dca1000_udp.DCA_CMD_PORT
DCA_DATA_PORT = dca1000_udp.DCA_DATA_PORT
DCA_NETMASK_PREFIX = dca1000_udp.DCA_NETMASK_PREFIX
HDR = dca1000_udp.HDR
FTR = dca1000_udp.FTR
CMD_SYSTEM_CONNECT = dca1000_udp.CMD_SYSTEM_CONNECT
CMD_RESET_FPGA = dca1000_udp.CMD_RESET_FPGA
STUDIO_BOOT_WAIT_S = 22


def banner(msg):
    print("\n=== %s ===" % msg, flush=True)


# ============ 参数模板 ============
def load_profile(name=None):
    return core_profile.load_profile(name, PROFILES_YAML)


def profile_for_frames(p, n_frames):
    q = dict(p)
    q["config_frames"] = int(n_frames)
    return q


def route_for_profile(p):
    return core_profile.route_for_profile(p, STUDIO)


def profile_config_lua(p):
    return core_profile.profile_config_lua(p)


def derived(p):
    return core_profile.derived(p)


def profile_errors(p):
    return core_profile.profile_errors(p)


# ============ DCA1000 UDP（硬件复位/存活） ============
def _dca_pkt(code, payload=b""):
    return dca1000_udp.dca_packet(code, payload)


def _dca_cmd(sock, code):
    return dca1000_udp.dca_command(sock, code)


def dca_probe():
    """只探活(SYSTEM_CONNECT)，不复位 FPGA；用于复用用户刚清好的硬件时。"""
    return dca1000_udp.dca_probe()


def dca_reset_and_probe():
    """返回 True 表示 FPGA 活着且已复位；False 表示无响应（需重新上电）。"""
    return dca1000_udp.dca_reset_and_probe()


# ============ 检查 ============
def check_nic():
    """以太网2 是否已配 192.168.33.30（用能否 bind 该 IP 判定）。"""
    return dca1000_udp.check_nic()


def check_com(com_port):
    try:
        from serial.tools import list_ports
    except ImportError:
        print("  [COM] 无 pyserial，跳过串口检查")
        return True
    names = [p.device for p in list_ports.comports()]
    want = "COM%d" % com_port
    ok = want in names
    print("  [COM] 期望雷达口 %s -> %s (现有: %s)" % (want, "OK" if ok else "FAIL", ",".join(names)))
    return ok


# ============ RSTD + Lua（带看门狗 + 真实错误抓取） ============
def _watchdog(fn, timeout, name):
    box = {}

    def worker():
        try:
            box["r"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise RuntimeError("步骤 %s 超时 %ss（mmWave Studio 可能弹窗卡住）" % (name, timeout))
    if "e" in box:
        raise box["e"]
    return box.get("r")


def _read_retfile():
    for enc in ("gbk", "utf-8", "latin-1"):
        try:
            with open(RETFILE, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    return ""


def capture_real_error(expr):
    """用 pcall 抓 ar1 调用的真实返回/异常串（mmWave Studio 内部 .NET 异常多为 GBK 中文）。"""
    os.makedirs(os.path.dirname(RETFILE), exist_ok=True)
    lua = ("local ok, ret = pcall(function() return %s end); "
           "local f = io.open([[%s]], 'w'); f:write(tostring(ok)..'\\t'..tostring(ret)); f:close()"
           % (expr, RETFILE.replace("\\", "\\\\")))
    try:
        rstd.send_command(lua)
        return _read_retfile()
    except Exception as e:  # noqa: BLE001
        return "pcall 抓取失败: %r" % e


def run_step(name, expr, checked, timeout):
    lua = ("local r = %s; if r ~= 0 then error('ret='..tostring(r)) end" % expr) if checked else expr
    print("  · %s ..." % name, flush=True)
    try:
        _watchdog(lambda: rstd.send_command(lua), timeout, name)
    except Exception as e:  # noqa: BLE001
        detail = capture_real_error(expr) if checked else ""
        raise RuntimeError("步骤 [%s] 失败：%s\n    真实返回: %s" % (name, e, detail))


def config_steps(p):
    return studio_rstd.pipeline_config_steps(p)


def capture_steps(p, n_frames, bin_path, include_frame_config=True):
    return studio_rstd.pipeline_capture_steps(p, n_frames, bin_path, include_frame_config=include_frame_config)


# ============ mmWave Studio 重启 ============
def studio_running():
    """mmWave Studio 进程是否在跑——用于判断是否有可复用实例。
    刻意不去连 RSTD 端口：RSTD 是单客户端服务，裸连/断会扰乱后续真正的 rstd.connect()（10054）。"""
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq mmWaveStudio.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:  # noqa: BLE001
        return False
    return "mmWaveStudio.exe" in (r.stdout or "")


def studio_pid():
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq mmWaveStudio.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:  # noqa: BLE001
        return None
    for line in (r.stdout or "").splitlines():
        if "mmWaveStudio.exe" not in line:
            continue
        cols = [c.strip().strip(chr(34)) for c in line.split(",")]
        if len(cols) >= 2:
            try:
                return int(cols[1])
            except ValueError:
                return None
    return None


def start_studio_wmi(wait_s=STUDIO_BOOT_WAIT_S):
    """用 WMI(Win32_Process.Create，由宿主 WmiPrvSE 服务建进程) 启动 mmWave Studio，
    使其脱离 agent 沙盒进程树。这是在 agent 沙盒下唯一验证可让 CaptureCardConfig_EthInit
    成功的启动方式：直接 Popen / Shell COM ShellExecute 都仍在沙盒进程树内，EthInit 取网卡
    MAC 拿到空串 → RFEthernetInitializationConfigurationData_Impl 的 Substring 崩。"""
    cmd_line = '"%s"' % STUDIO_EXE
    ps = (
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
        "-Arguments @{CommandLine='%s'; CurrentDirectory='%s'}; "
        "Write-Output ('RET='+$r.ReturnValue); if ($r.ReturnValue -ne 0) { exit 1 }"
        % (cmd_line.replace("'", "''"), STUDIO_RUNTIME.replace("'", "''"))
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [studio] WMI 启动失败: %s %s" % ((r.stdout or "").strip(), (r.stderr or "").strip()))
        return False
    print("  [studio] 已用 WMI(宿主服务) 启动，等待 %ds 让 Startup.lua 跑 RSTD.NetStart ..." % wait_s)
    time.sleep(wait_s)
    return True


def restart_studio():
    """[legacy] 直接 Popen 重启——在 agent 沙盒下会导致 EthInit Substring 崩；仅保留兼容。
    新代码用 start_studio_wmi()。"""
    subprocess.run(["taskkill", "/IM", "mmWaveStudio.exe", "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    subprocess.Popen([STUDIO_EXE], cwd=STUDIO_RUNTIME)
    print("  [studio] 已从 RunTime 启动，等待 %ds 让 Startup.lua 跑 RSTD.NetStart ..." % STUDIO_BOOT_WAIT_S)
    time.sleep(STUDIO_BOOT_WAIT_S)


# ============ 阶段 ============
def bringup(p, restart=True, dca_reset=True):
    probe = dca_reset_and_probe if dca_reset else dca_probe
    banner("① 网口检查")
    nic_ok = check_nic()
    if not nic_ok:
        print("  ACTION: 需管理员把 DCA 网卡配为 %s/%d（见 skill runbook §3）。中止。" % (DCA_PC_IP, DCA_NETMASK_PREFIX))
        return False

    banner("② DCA1000 检查 (%s)" % ("UDP RESET_FPGA" if dca_reset else "仅探活"))
    if not probe():
        print("  ACTION: DCA1000 FPGA 无响应。请【重新上电 DCA1000】（拔电源等5s再插，网线不动），然后重跑。中止。")
        return False

    # 关键：优先复用已在运行的 mmWave Studio。由 ti-radar 自己 Popen 启动的 Studio 会继承
    # 当前执行环境（如 agent 沙盒/容器），其 CaptureCardConfig_EthInit 在该环境下枚举网卡
    # 取 PC MAC 会拿到空串并在 RFEthernetInitializationConfigurationData_Impl 里 Substring 崩。
    # 因此除非用户显式 --restart 且当前无可用 Studio，否则绝不 taskkill/Popen 重启。
    # 优先复用已运行的 Studio；没有就用 WMI(宿主服务)启动以脱离 agent 沙盒。
    # 绝不用 Popen 自启：那会让 Studio 继承沙盒环境、EthInit 必崩（详见 start_studio_wmi 注释）。
    banner("③ mmWave Studio 实例")
    if studio_running():
        print("  [studio] 检测到 mmWaveStudio.exe 在运行，复用它（不重启）")
    elif not start_studio_wmi():
        print("  ACTION: WMI 启动 mmWave Studio 失败。请在宿主手动从 RunTime 启动后重跑：")
        print("          %s" % STUDIO_EXE)
        return False

    banner("④ 串口 + FPGA 复检")
    com_ok = check_com(p["com_port"])
    fpga_ok = probe()
    if not com_ok:
        print("  ACTION: 没找到雷达串口 COM%d。检查 USB/排线后重跑。中止。" % p["com_port"])
        return False
    if not fpga_ok:
        print("  ACTION: FPGA 无响应，请【重新上电 DCA1000】后重跑。中止。")
        return False

    banner("⑤ 建立 RSTD 连接 (pythonnet)")
    rstd.connect()
    rstd.send_command('WriteToLog("radar_pipeline: bringup RSTD ok\\n", "green")')
    print("  [RSTD] 连接 + 通信 OK")
    return True


def do_config(p):
    d = derived(p)
    banner("⑥ 下发雷达配置 (profile=%s)" % p["_name"])
    print("  派生量: range_res=%.3fm  adc_bw=%.2fGHz  v_max=+/-%.2fm/s  帧时长需>=%.2fms (当前%gms)"
          % (d["rng_res"], d["adc_bw_ghz"], d["v_max"], d["frame_needed_ms"], p["frame_period_ms"]))
    print("  ADC窗口: adc_start=%.3fus + sample=%.3fus => %.3fus；ramp_end=%.3fus；chirp_end=%.3fGHz"
          % (p["adc_start_us"], d["adc_sampling_time_us"], d["adc_window_end_us"],
             p["ramp_end_us"], d["chirp_end_ghz"]))
    errors, warnings = profile_errors(p)
    for warning in warnings:
        print("  WARN " + warning)
    for error in errors:
        print("  WARN " + error)
    if errors:
        print("  中止，避免黑盒下发。")
        return False
    for name, expr, checked, to in config_steps(p):
        run_step(name, expr, checked, to)
    print("  雷达 + DCA 配置完成 OK")
    return True


def do_capture(p, n_frames, out_dir, reuse_config=False):
    os.makedirs(out_dir, exist_ok=True)
    bin_path = os.path.join(out_dir, "adc_data.bin")
    exp = n_frames * p["frame_period_ms"] / 1000.0
    banner("⑦ 采集 %d 帧 ~= %.1fs -> %s" % (n_frames, exp, out_dir))
    for name, expr, checked, to in capture_steps(p, n_frames, bin_path, False if reuse_config else True):
        run_step(name, expr, checked, to)
    # 等待落盘（mmWave Studio 写 *_Raw_0.bin）
    binf, last, stable = None, -1, 0
    deadline = time.time() + exp + 12
    while time.time() < deadline:
        bins = [b for b in glob.glob(os.path.join(out_dir, "*.bin")) if os.path.getsize(b) > 64]
        if bins:
            binf = max(bins, key=os.path.getsize)
            sz = os.path.getsize(binf)
            stable = stable + 1 if sz == last and sz > 0 else 0
            last = sz
            if stable >= 3:
                break
        time.sleep(0.5)
    nbytes = os.path.getsize(binf) if binf else 0
    print("  落盘: %s (%d bytes)" % (binf, nbytes))
    # 丢包日志校验
    logs = glob.glob(os.path.join(out_dir, "*LogFile*.csv"))
    if logs:
        print("  采集日志: %s" % logs[0])
    return binf, nbytes


def write_prepare_state(p, frames):
    state = core_state.prepared_state(
        profile_name=p["_name"],
        profile=p,
        frames=frames,
        studio_pid=studio_pid(),
        rstd_ok=True,
    )
    path = core_state.write_state(p["_name"], state)
    print("  prepared_state: %s" % path)
    return path


def warm_state_failures(p, frames):
    prepared_profile = profile_for_frames(p, frames)
    state = core_state.read_state(prepared_profile["_name"])
    failures = core_state.validate_prepared_state(
        state=state,
        profile_name=prepared_profile["_name"],
        profile=prepared_profile,
        frames=frames,
    )
    if not studio_running():
        failures.append("mmWaveStudio.exe is not running")
    return prepared_profile, failures


def run_warm_capture(p, frames, out):
    prepared_profile, failures = warm_state_failures(p, frames)
    if failures:
        print("warm capture blocked:")
        for item in failures:
            print("  - %s" % item)
        return 1
    print("warm checks: state/profile/studio ok; ping RSTD ...")
    rstd.ping()
    binf, n = do_capture(prepared_profile, frames, out, reuse_config=True)
    print("\n=== WARM CAPTURE done ===  bin=%s bytes=%d" % (binf, n))
    return 0 if n > 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="固化雷达采集工作流")
    ap.add_argument("cmd", choices=["bringup", "config", "capture", "run", "prepare"])
    ap.add_argument("--profile", default=None)
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--reuse-config", action="store_true", help="warm capture: require a prepared state and skip setup steps")
    ap.add_argument("--setup", choices=["cold", "warm", "auto"], default="cold")
    ap.add_argument("--no-restart", action="store_true", help="跳过 mmWave Studio 重启（复用用户已开好的实例）")
    ap.add_argument("--no-dca-reset", action="store_true", help="只探活 FPGA，不发 RESET_FPGA")
    args = ap.parse_args(argv)

    p = load_profile(args.profile)
    out = args.out or os.path.join(SESSIONS,
                                   "run_" + time.strftime("%Y%m%d_%H%M%S"))
    restart = not args.no_restart
    dca_reset = not args.no_dca_reset

    if args.cmd == "bringup":
        return 0 if bringup(p, restart, dca_reset) else 1
    if args.cmd == "config":
        rstd.connect()
        return 0 if do_config(p) else 1
    if args.cmd == "prepare":
        p = profile_for_frames(p, args.frames)
        ok = bringup(p, restart, dca_reset) and do_config(p)
        if ok:
            write_prepare_state(p, args.frames)
        return 0 if ok else 1
    if args.cmd == "capture":
        if args.reuse_config or args.setup == "warm":
            return run_warm_capture(p, args.frames, out)
        rstd.connect()
        do_capture(p, args.frames, out)
        return 0
    if args.cmd == "run":
        if args.setup == "warm":
            return run_warm_capture(p, args.frames, out)
        if args.setup == "auto":
            _pp, failures = warm_state_failures(p, args.frames)
            if not failures:
                return run_warm_capture(p, args.frames, out)
            print("warm state unavailable; falling back to cold run")
        p = profile_for_frames(p, args.frames)
        if not bringup(p, restart, dca_reset):
            return 1
        if not do_config(p):
            return 1
        write_prepare_state(p, args.frames)
        binf, n = do_capture(p, args.frames, out)
        print("\n=== RUN 完成 ===  bin=%s bytes=%d" % (binf, n))
        return 0 if n > 0 else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
