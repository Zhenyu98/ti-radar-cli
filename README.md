<h1 align="center">
  <img src="docs/assets/logo.svg" alt="ti-radar-cli logo" width="64" />
  <br />
  ti-radar-cli
</h1>

<p align="center">
  <strong>Reliability-first command-line tools and an agent skill for TI mmWave radar capture.</strong>
</p>

<p align="center">
  <strong>Inspect hardware state</strong> ·
  <strong>record packet verdicts</strong> ·
  <strong>operate safely with agents</strong>
</p>

<p align="center">
  <a href="https://github.com/Zhenyu98/ti-radar-cli/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/Zhenyu98/ti-radar-cli?style=for-the-badge&logo=github"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge"></a>
  <a href="https://www.python.org/"><img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white"></a>
  <a href="src/ti_radar/cli.py"><img alt="CLI ti-radar" src="https://img.shields.io/badge/CLI-ti--radar-0f172a?style=for-the-badge"></a>
</p>

<p align="center">
  <a href="#why">Why</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#agent-setup">Agent Setup</a> ·
  <a href="#device-verification">Device Verification</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="README_zh.md">简体中文</a>
</p>

<p align="center">
  <img src="docs/assets/hero.svg" alt="ti-radar-cli evidence workflow" width="92%" />
</p>

## Why

TI mmWave radar capture usually fails at the state boundary: device identity, firmware route, COM ports, RSTD, mmWave Studio launch context, DCA1000 Ethernet, LVDS layout, packet logs, and raw bin verification.

`ti-radar-cli` turns those fragile boundaries into a small command surface that can be inspected by a person or operated by a coding agent.

| Manual radar bring-up | With `ti-radar-cli` |
|---|---|
| Recreate GUI steps from memory. | Run named readiness and capture commands. |
| Trust a raw bin exists. | Read a manifest with packet counters and verdict. |
| Let agents guess Lua or hardware sequence. | Give agents a skill with approval gates and safe defaults. |
| Share vague hardware support claims. | Label routes as `verified`, `scaffold`, or community evidence. |

## Quick Start

```powershell
git clone https://github.com/Zhenyu98/ti-radar-cli.git
cd ti-radar-cli
python -m pip install -e .
ti-radar version
ti-radar doctor
ti-radar capture smoke --backend mock
ti-radar session inspect latest
```

Expected success signal:

```text
ti-radar version prints package and Python information
ti-radar doctor completes without starting capture
capture smoke writes a mock session
session inspect latest reads manifest.yaml
```

Optional hardware extras:

```powershell
python -m pip install -e ".[studio,serial,plot]"
```

`pythonnet` is required for direct RSTD control. `pyserial` improves COM-port checks. `matplotlib` is used for quicklook plots.

Hardware connection reference: [TI DCA1000 + mmWave Studio hardware guide](https://dev.ti.com/tirex/content/radar_toolbox_2_20_00_05/docs/hardware_guides/dca1000_mmwave_studio_user_guide.html).

## Agent Setup

Copy this to Codex, Claude Code, Cursor, or another coding agent:

```text
Read https://github.com/Zhenyu98/ti-radar-cli/blob/main/agent-setup.md and follow it to install and configure ti-radar-cli for me.
Goal: inspect the environment first, run the non-hardware smoke path, and ask before hardware state changes.
```

The agent guide points to `README.md` and `skills/ti-radar/SKILL.md`, then starts with `ti-radar version`, `ti-radar doctor`, `ti-radar capture smoke --backend mock`, and `ti-radar session inspect latest`.

## Hardware Readiness

Inspection commands:

```powershell
ti-radar doctor --profile default_6843
ti-radar studio status
ti-radar studio ping
ti-radar studio identify
```

Short capture pilot, after you intentionally approve hardware state changes:

```powershell
ti-radar studio run --profile default_6843 --frames 10
ti-radar session inspect latest
```

## CLI Shape

Top-level help stays small:

```text
version
doctor
studio    Expert backend commands
capture
session
device
```

Expert mmWave Studio/RSTD commands stay under:

```powershell
ti-radar studio --help
```

Typical user-facing commands:

```powershell
ti-radar doctor
ti-radar capture smoke --backend mock
ti-radar capture raw --backend studio --profile default_6843 --frames 10
ti-radar session list
ti-radar session inspect latest
ti-radar device route --part-id 6843
```

## Device Verification

Hardware coverage is labeled by evidence level.

| Device/profile | Path | Verification level | Evidence expectation |
|---|---|---|---|
| `default_6843` / xWR6843-style route | mmWave Studio + RSTD + DCA1000 | `verified` for the author's lab route | clean short capture with manifest and DCA packet verdict |
| Other xWR/AWR/IWR routes | device decode scaffolds | `scaffold` | derived from TI route semantics, needs contributor packet-log evidence before promotion |

The default DCA1000 network values are common board defaults:

```text
PC DCA adapter: 192.168.33.30/24
DCA1000 FPGA:   192.168.33.180
Command port:   4096
Data port:      4098
```

Always run `ti-radar doctor` before capture on a new machine.

## Capture Verdict

Capture sessions write `manifest.yaml` with a strict verdict:

```yaml
verdict: pass
failure_reasons: []
```

Failure reasons include missing raw bin, tiny raw bin, missing DCA packet log, zero received packets, out-of-order packets, and zero-filled packets/bytes.

## FAQ

**Can this run without hardware?**

Yes. Use `ti-radar capture smoke --backend mock` and `ti-radar session inspect latest` for the non-hardware path.

**Does `ti-radar studio identify` start RF or capture frames?**

It reads device identity through RSTD and should avoid firmware download, RF enable, and `StartFrame`.

**What makes a capture usable?**

A usable capture has a passing manifest verdict, a raw bin larger than the minimum threshold, received packets above zero, and zero out-of-sequence or zero-filled packet counters.

## Roadmap

`ti-radar-cli` is moving toward a broader, agent-operable TI radar workflow:

- `cfg explain` and profile linting for zero-hardware setup checks.
- A headless SDK + DCA1000 path for Linux-friendly raw capture.
- A device configuration table so more TI radar boards can be added with clear verification levels.
- Raw ADC quicklook tools for range-Doppler sanity checks after capture.

Stay tuned. Contributions from more developers and hardware users are welcome.

## Acknowledgements

This project is shaped by TI's public mmWave Studio, DCA1000, and radar toolbox concepts. TI binaries and private lab captures remain outside this repository.

## Contributing

Issues and pull requests are welcome. Please include the device/profile, backend, command line, manifest verdict, and packet-log counters when reporting hardware behavior. Keep secrets and local machine details out of logs and screenshots.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).

## Star History

<a href="https://www.star-history.com/#Zhenyu98/ti-radar-cli&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Zhenyu98/ti-radar-cli&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Zhenyu98/ti-radar-cli&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Zhenyu98/ti-radar-cli&type=Date" />
  </picture>
</a>
