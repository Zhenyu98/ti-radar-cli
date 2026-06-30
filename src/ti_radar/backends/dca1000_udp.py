"""DCA1000 UDP command helpers for ti-radar."""

from __future__ import annotations

import socket
import struct

DCA_FPGA_IP = "192.168.33.180"
DCA_PC_IP = "192.168.33.30"
DCA_CMD_PORT = 4096
DCA_DATA_PORT = 4098
DCA_NETMASK_PREFIX = 24

HDR = 0xA55A
FTR = 0xEEAA
CMD_SYSTEM_CONNECT = 0x09
CMD_RESET_FPGA = 0x01


def dca_packet(code: int, payload: bytes = b"") -> bytes:
    return struct.pack("<HHH", HDR, code, len(payload)) + payload + struct.pack("<H", FTR)


def dca_command(sock: socket.socket, code: int, fpga_ip: str = DCA_FPGA_IP, cmd_port: int = DCA_CMD_PORT) -> int | None:
    sock.sendto(dca_packet(code), (fpga_ip, cmd_port))
    try:
        reply, _ = sock.recvfrom(2048)
        if len(reply) >= 8:
            _, _reply_code, status, _ = struct.unpack("<HHHH", reply[:8])
            return status
    except socket.timeout:
        return None
    return None


def can_bind_pc_ip(pc_ip: str = DCA_PC_IP) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((pc_ip, 0))
        sock.close()
        return True
    except OSError:
        return False


def check_nic() -> bool:
    """Return whether the PC DCA IP can be bound; prints the legacy operator hint."""
    if can_bind_pc_ip():
        print("  [NIC] %s OK" % DCA_PC_IP)
        return True
    print("  [NIC] %s FAIL  需要把 DCA 网卡(以太网2)配为 %s/%d" % (DCA_PC_IP, DCA_PC_IP, DCA_NETMASK_PREFIX))
    return False


def dca_probe() -> bool:
    """Probe SYSTEM_CONNECT only; does not reset FPGA."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((DCA_PC_IP, DCA_CMD_PORT))
    except OSError as exc:
        print("  [DCA] 绑定失败：%s" % exc)
        return False
    sock.settimeout(3.0)
    status = dca_command(sock, CMD_SYSTEM_CONNECT)
    sock.close()
    print("  [DCA] 探活 SYSTEM_CONNECT=%s" % status)
    return status is not None


def dca_reset_and_probe() -> bool:
    """Return True when FPGA responds before and after RESET_FPGA."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((DCA_PC_IP, DCA_CMD_PORT))
    except OSError as exc:
        print("  [DCA] 绑定 %s:%d 失败：%s（网口未配好或被占用）" % (DCA_PC_IP, DCA_CMD_PORT, exc))
        return False
    sock.settimeout(3.0)
    status0 = dca_command(sock, CMD_SYSTEM_CONNECT)
    if status0 is None:
        sock.close()
        return False
    dca_command(sock, CMD_RESET_FPGA)
    status1 = dca_command(sock, CMD_SYSTEM_CONNECT)
    sock.close()
    print("  [DCA] SYSTEM_CONNECT=%s, RESET_FPGA 后 reconnect=%s" % (status0, status1))
    return status1 is not None
