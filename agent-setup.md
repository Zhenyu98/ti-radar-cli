# Agent Setup

## Copy-Paste Prompt

```text
Please read https://github.com/Zhenyu98/ti-radar-cli/blob/main/agent-setup.md, README.md, and skills/ti-radar/SKILL.md, then help me use ti-radar-cli safely.
Goal: inspect the environment first, run only non-hardware checks by default, and prepare a reliable TI mmWave radar capture path.
Before changing files, touching hardware state, running StartFrame, publishing, or deleting anything, show me the plan and ask for approval.
Run the smoke path first: ti-radar version, ti-radar doctor, ti-radar capture smoke --backend mock, and ti-radar session inspect latest.
Report the exact commands run, files changed, and verification result.
```

## Prerequisites

- Python 3.10+
- Windows for mmWave Studio/RSTD workflows
- TI mmWave Studio installed when using the `studio` backend
- DCA1000EVM configured on its own Ethernet adapter when doing real capture
- Optional: `pythonnet`, `pyserial`, `matplotlib`

## Setup Steps

```powershell
git clone https://github.com/Zhenyu98/ti-radar-cli.git
cd ti-radar-cli
python -m pip install -e .
python -m pip install -e ".[studio,serial,plot]"
ti-radar version
ti-radar doctor
ti-radar capture smoke --backend mock
ti-radar session inspect latest
```

## Success Signal

- `ti-radar version` prints package and Python information.
- `ti-radar doctor` runs without starting capture.
- `capture smoke --backend mock` creates a mock session.
- `session inspect latest` reads the session manifest.

## Safety Rules

- Do not run `ti-radar studio run`, `ti-radar capture raw`, `ti-radar doctor --hardware`, or `ti-radar studio ethinit-probe` without explicit user approval.
- Do not modify NIC settings automatically.
- Do not call `StartFrame` during inspection.
- Do not publish sessions, raw ADC bins, packet logs, screenshots, or local machine paths.
- Do not push, publish, create releases, enable Pages, or upload packages without an explicit publish confirmation packet.
- Keep project-specific synchronization experiments outside this repository unless the user explicitly asks for a separate release.

## Release Safety

Before GitHub or package publication, inspect `PUBLISH_AUDIT.md` and confirm the target, visibility, included files, excluded files, and desensitization scan result with the user.
