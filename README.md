# ti-radar-cli

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![CLI](https://img.shields.io/badge/CLI-ti--radar-black.svg)](src/ti_radar/cli.py)

Reliability-first command-line tools and an agent skill for TI mmWave radar capture with mmWave Studio, RSTD, and DCA1000.

> 中文文档见 [README_zh.md](README_zh.md).

## Why

TI mmWave radar capture is rarely blocked by one API call. It is usually blocked by state: device identity, firmware, COM ports, RSTD, mmWave Studio launch context, DCA1000 Ethernet, LVDS layout, packet logs, and raw bin verification.

`ti-radar-cli` turns that state into a small, inspectable command surface:

- safe readiness checks before capture
- mmWave Studio/RSTD expert backend commands
- profile validation and device routing
- strict capture manifests and verdicts
- raw ADC sanity processing
- an agent skill that keeps operational rules outside CLI help

## Install

```powershell
git clone https://github.com/Zhenyu98/ti-radar-cli.git
cd ti-radar-cli
python -m pip install -e .
ti-radar version
```

Optional dependencies:

```powershell
python -m pip install pythonnet pyserial matplotlib
```

`pythonnet` is required for direct RSTD control. `pyserial` improves COM-port checks. `matplotlib` is only needed for quicklook plots.

## Quick Start

Non-hardware smoke path:

```powershell
ti-radar version
ti-radar doctor
ti-radar capture smoke --backend mock
ti-radar session inspect latest
```

Hardware readiness, without starting capture:

```powershell
ti-radar doctor --profile default_6843
ti-radar studio status
ti-radar studio ping
ti-radar studio identify
```

Short capture pilot:

```powershell
ti-radar studio run --profile default_6843 --frames 10
ti-radar session inspect latest
```

## CLI Shape

Top-level help is intentionally small:

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

## Safety Model

CLI help only documents commands and arguments. Operational policy lives in the skill:

```text
skills/ti-radar/SKILL.md
```

Default low-risk operations:

- read profiles and paths
- validate profile timing
- inspect saved sessions
- run mock captures
- route known device IDs

Operations that affect hardware state must be deliberate:

- firmware download
- RF enable
- DCA1000 reset/probe
- StartFrame
- long raw ADC capture
- changing NIC settings

## Hardware Defaults

The included `default_6843` route targets an AWR6843-style Studio flow and DCA1000 defaults:

```text
PC DCA adapter: 192.168.33.30/24
DCA1000 FPGA:   192.168.33.180
Command port:   4096
Data port:      4098
```

These are common DCA1000 defaults, not a promise that your machine is already configured correctly. Always run `ti-radar doctor` before capture.

## Capture Verdict

Capture sessions write `manifest.yaml` with a strict verdict:

```yaml
verdict: pass
failure_reasons: []
```

Failures include missing raw bin, tiny raw bin, missing DCA packet log, zero received packets, out-of-order packets, or zero-filled packets/bytes.

## Agent Setup

For Codex, Claude Code, Cursor, or other coding agents, start with:

```text
agent-setup.md
```

The setup guide tells the agent to inspect first, avoid hardware actions by default, and ask before risky operations.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Zhenyu98/ti-radar-cli&type=Date)](https://www.star-history.com/#Zhenyu98/ti-radar-cli&Date)

## Scope

This repository publishes only the generic TI radar CLI and skill layer.

It intentionally does not include project-specific multi-sensor synchronization experiments, local sessions, private lab data, or captured raw ADC bins.

## License

MIT License. See [LICENSE](LICENSE).
