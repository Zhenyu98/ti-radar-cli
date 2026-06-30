---
name: ti-radar
description: Use when operating or developing ti-radar-cli for TI mmWave radar capture, mmWave Studio, RSTD, AWR/IWR/xWR devices, DCA1000, raw ADC checks, profile validation, or agent-driven radar bring-up.
---

# ti-radar

## Purpose

Use this skill with `ti-radar-cli` to keep TI mmWave radar operation evidence-first and hardware-safe.

The CLI executes checks and capture workflows. This skill defines the operating discipline: what is safe by default, what requires approval, and how to isolate failures without jumping straight to `StartFrame`.

## Core Rule

Prove each boundary before widening the run:

```text
profile sanity -> Studio/RSTD readiness -> device identity -> DCA network -> short capture -> packet verdict -> longer run
```

Do not treat a nonzero raw bin as sufficient evidence. A usable capture also needs a packet log with no out-of-order or zero-filled packets/bytes.

## Low-Risk Default Actions

These can be run during inspection:

```powershell
ti-radar version
ti-radar doctor
ti-radar studio status
ti-radar studio validate-profile
ti-radar capture smoke --backend mock
ti-radar session list
ti-radar session inspect latest
ti-radar device route --part-id 6843
```

`ti-radar studio identify` is low RF risk but live: it connects to RSTD and reads device identity registers. It must not download firmware, enable RF, or start frames.

## Actions Requiring User Approval

Ask before running:

```powershell
ti-radar doctor --hardware
ti-radar studio start --method wmi --ping
ti-radar studio bringup
ti-radar studio config
ti-radar studio capture
ti-radar studio run
ti-radar capture raw
ti-radar studio ethinit-probe
```

Also ask before:

- changing NIC settings
- killing or restarting mmWave Studio
- downloading firmware
- enabling RF
- calling `StartFrame`
- long captures
- deleting, overwriting, publishing, or moving sessions

## CLI Boundary

Top-level CLI help should stay small and user-facing:

```text
version
doctor
studio    Expert backend commands
capture
session
device
```

Expert controls belong under:

```powershell
ti-radar studio --help
```

Do not put long runbooks or safety doctrine into CLI help. Keep those in this skill and README docs.

## Profile And Device Boundary

- Device decode and routing logic belongs in `src/ti_radar/core/device.py`.
- Profile loading, derived quantities, and `ProfileConfig` Lua generation belong in `src/ti_radar/core/profile.py`.
- Session manifest and verdict logic belongs in `src/ti_radar/core/session.py`.
- mmWave Studio/RSTD step planning belongs in `src/ti_radar/backends/studio_rstd.py`.
- DCA1000 UDP helper logic belongs in `src/ti_radar/backends/dca1000_udp.py`.
- CLI code should parse arguments and orchestrate calls, not carry business rules.

## DCA1000 Defaults

The included DCA1000 defaults are:

```text
PC DCA adapter: 192.168.33.30/24
DCA1000 FPGA:   192.168.33.180
Command port:   4096
Data port:      4098
```

These are hardware defaults, not proof that the current machine is configured correctly.

## Recommended Bring-Up

1. Install and import-check the CLI.
2. Run `ti-radar doctor`.
3. Run `ti-radar capture smoke --backend mock`.
4. Start mmWave Studio from its `RunTime` directory.
5. Run `ti-radar studio status`.
6. Run `ti-radar studio ping`.
7. Run `ti-radar studio identify`.
8. Only with approval, run a short capture:

```powershell
ti-radar studio run --profile default_6843 --frames 10
ti-radar session inspect latest
```

## Pass Criteria

A capture is only usable when the manifest verdict passes:

```text
verdict: pass
raw bin bytes > 64
received_packets > 0
out_of_sequence = 0
zero_filled_packets = 0
zero_filled_bytes = 0
```

If verdict is fail, preserve the session for debugging but do not use it as validated data.

## Common Failure Hints

- Watching `adc_data.bin` can be misleading; mmWave Studio often writes `adc_data_Raw_0.bin`.
- RSTD connection errors usually mean mmWave Studio was not started from `RunTime` or `RSTD.NetStart()` did not run.
- `pythonnet` must be installed in the same Python environment used to run `ti-radar`.
- DCA1000 does not need to answer ICMP ping; use the CLI's DCA/RSTD evidence instead.
- Frame period must be long enough for the configured chirp loop.

## Publishing Boundary

Never publish sessions, raw ADC bins, packet logs, screenshots, local machine paths, or private lab notes. Public releases should include only the generic CLI, skill, tests, and documentation.
