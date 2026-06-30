"""RSTD client for mmWave Studio via pythonnet."""

from __future__ import annotations

import sys

DLL_DIR = r"C:\ti\mmwave_studio_02_01_01_00\mmWaveStudio\Clients\RtttNetClientController"
RSTD_ADDR = "127.0.0.1"
RSTD_PORT = 2777
OK_STATUSES = {0, 30000}

_client = None


def _load():
    global _client
    if _client is not None:
        return _client
    import clr  # pythonnet
    if DLL_DIR not in sys.path:
        sys.path.append(DLL_DIR)
    clr.AddReference("RtttNetClientAPI")
    from RtttNetClientAPI import RtttNetClient  # noqa: E402
    _client = RtttNetClient
    return _client


def connect(addr=RSTD_ADDR, port=RSTD_PORT):
    c = _load()
    try:
        if c.IsConnected():
            return
    except Exception:
        pass
    es = c.Init()
    if es != 0:
        raise RuntimeError("RSTD Init 失败: %d" % es)
    es = c.Connect(addr, port)
    if es != 0:
        raise RuntimeError(
            "RSTD Connect 失败: %d "
            "(在 mmWaveStudio Lua 控制台 RSTD.NetClose() 后 RSTD.NetStart() 再试)" % es
        )


def send_command(lua):
    c = _load()
    ret = c.SendCommand(lua)
    status = _send_status(ret)
    if status not in OK_STATUSES:
        raise RuntimeError("RSTD SendCommand 失败(status=%r): %s" % (status, lua[:100]))
    return status


def _send_status(ret):
    """Extract RSTD SendCommand status across pythonnet return shapes."""
    if isinstance(ret, (tuple, list)):
        return ret[0]
    return ret


def dofile(lua_path):
    return send_command('dofile("%s")' % lua_path.replace("\\", "\\\\"))


def ping():
    connect()
    send_command('WriteToLog("ti_radar: RSTD ping ok\\n", "green")')
    print("[rstd] RSTD 连接 + 通信 OK")
