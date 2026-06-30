"""Device auto-detect and per-device routing for mmWave Studio/DCA flows."""

from __future__ import annotations

from dataclasses import dataclass
import os

STUDIO_ROOT = r"C:\ti\mmwave_studio_02_01_01_00"

_ES2_ES3_MASK = 0x03FC0000
_ES2_ES3_SHIFT = 18


@dataclass(frozen=True)
class DeviceRoute:
    part_id: int
    frequency_band: str | None
    bss_fw: str
    mss_fw: str
    lpmod_args: tuple[int, int]
    lvds_lane_args: tuple[int, int, int, int, int, int, int, int]
    dca_mode_args: tuple[int, int, int, int, int, int]
    project_profile: str | None
    note: str


def decode_part_id(efuse_device: int, efuse_es1_device: int) -> int:
    """Decode mmWave Studio efuse register values into a TI partId."""
    es2_es3 = (int(efuse_device) & _ES2_ES3_MASK) >> _ES2_ES3_SHIFT
    es1_bits = int(efuse_es1_device) & 0x3

    if es2_es3 == 0:
        if es1_bits == 0:
            return 1243
        if es1_bits == 1:
            return 1443
        return 1642

    if es2_es3 == 0xE0 and es1_bits == 2:
        return 6843

    if es2_es3 in {0x20, 0x21, 0x80}:
        return 1243
    if es2_es3 in {0xA0, 0x40}:
        return 1443
    if es2_es3 in {0x60, 0x61, 0x04, 0x62, 0x67, 0x66, 0x01, 0xC0, 0xC1}:
        return 1642
    if es2_es3 in {0x70, 0x71, 0xD0, 0x05}:
        return 1843
    if es2_es3 in {0xE0, 0xE1, 0xE2, 0xE3, 0xE4}:
        return 6843

    raise ValueError(
        "unknown mmWave efuse device code 0x%X from efuse_device=0x%X"
        % (es2_es3, int(efuse_device))
    )


def decode_es_version(es_version_register: int) -> int:
    """Decode the ESVersion register value reported by mmWave Studio."""
    return int(es_version_register) & 0xFF


def route_for_part_id(part_id: int, studio_root: str = STUDIO_ROOT) -> DeviceRoute:
    """Return the mmWave Studio route for a supported partId."""
    part_id = int(part_id)
    fw = os.path.join(studio_root, "rf_eval_firmware")

    if part_id == 1243:
        return DeviceRoute(
            part_id=part_id,
            frequency_band=None,
            bss_fw=os.path.join(fw, "radarss", "xwr12xx_xwr14xx_radarss_ES2.0.bin"),
            mss_fw=os.path.join(fw, "masterss", "xwr12xx_xwr14xx_masterss_ES2.0.bin"),
            lpmod_args=(0, 0),
            lvds_lane_args=(0, 1, 1, 1, 1, 1, 0, 0),
            dca_mode_args=(1, 1, 1, 2, 3, 30),
            project_profile=None,
            note="route known from DCAconnect.lua; no validated project profile yet",
        )

    if part_id == 1443:
        return DeviceRoute(
            part_id=part_id,
            frequency_band=None,
            bss_fw=os.path.join(fw, "radarss", "xwr12xx_xwr14xx_radarss.bin"),
            mss_fw=os.path.join(fw, "masterss", "xwr12xx_xwr14xx_masterss.bin"),
            lpmod_args=(0, 0),
            lvds_lane_args=(0, 1, 1, 1, 1, 1, 0, 0),
            dca_mode_args=(1, 1, 1, 2, 3, 30),
            project_profile=None,
            note="route known from DCAconnect.lua; no validated project profile yet",
        )

    if part_id == 1642:
        return DeviceRoute(
            part_id=part_id,
            frequency_band=None,
            bss_fw=os.path.join(fw, "radarss", "xwr16xx_radarss.bin"),
            mss_fw=os.path.join(fw, "masterss", "xwr16xx_masterss.bin"),
            lpmod_args=(0, 1),
            lvds_lane_args=(0, 1, 1, 0, 0, 1, 0, 0),
            dca_mode_args=(1, 2, 1, 2, 3, 30),
            project_profile=None,
            note="route known from DCAconnect.lua; no validated project profile yet",
        )

    if part_id == 1843:
        return DeviceRoute(
            part_id=part_id,
            frequency_band=None,
            bss_fw=os.path.join(fw, "radarss", "xwr18xx_radarss.bin"),
            mss_fw=os.path.join(fw, "masterss", "xwr18xx_masterss.bin"),
            lpmod_args=(0, 0),
            lvds_lane_args=(0, 1, 1, 0, 0, 1, 0, 0),
            dca_mode_args=(1, 2, 1, 2, 3, 30),
            project_profile=None,
            note="route known from DCAconnect.lua; no validated project profile yet",
        )

    if part_id == 6843:
        return DeviceRoute(
            part_id=part_id,
            frequency_band="60G",
            bss_fw=os.path.join(fw, "radarss", "xwr68xx_radarss.bin"),
            mss_fw=os.path.join(fw, "masterss", "xwr68xx_masterss.bin"),
            lpmod_args=(0, 0),
            lvds_lane_args=(0, 1, 1, 0, 0, 1, 0, 0),
            dca_mode_args=(1, 2, 1, 2, 3, 30),
            project_profile="default_6843",
            note="project-validated AWR6843ISK + DCA1000 route",
        )

    raise ValueError("unsupported mmWave partId: %s" % part_id)


def csv_args(values: tuple[int, ...]) -> str:
    return ",".join(str(v) for v in values)


def lua_args(values: tuple[int, ...]) -> str:
    return ", ".join(str(v) for v in values)

