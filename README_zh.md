# ti-radar-cli

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)

面向 TI mmWave 雷达采集的可靠优先 CLI 和 Agent Skill，当前重点支持 mmWave Studio / RSTD / DCA1000 路线。

English: [README.md](README.md)

## 这个项目解决什么

TI 雷达采集失败通常不是因为某个 API 不会调，而是硬件状态没有被证明：

- 雷达型号和 efuse 身份
- BSS/MSS 固件路径
- COM 口
- mmWave Studio 启动目录
- RSTD 连接状态
- DCA1000 网卡 IP 和 UDP 端口
- LVDS / DCA mode / packet delay
- raw bin 是否真的落盘
- packet log 是否存在乱序或 zero-fill

`ti-radar-cli` 把这些状态变成可检查、可记录、可复现的命令。

## 安装

```powershell
git clone https://github.com/Zhenyu98/ti-radar-cli.git
cd ti-radar-cli
python -m pip install -e .
ti-radar version
```

可选依赖：

```powershell
python -m pip install pythonnet pyserial matplotlib
```

## 快速开始

无硬件 smoke：

```powershell
ti-radar version
ti-radar doctor
ti-radar capture smoke --backend mock
ti-radar session inspect latest
```

硬件预检，不采集：

```powershell
ti-radar doctor --profile default_6843
ti-radar studio status
ti-radar studio ping
ti-radar studio identify
```

短帧 pilot：

```powershell
ti-radar studio run --profile default_6843 --frames 10
ti-radar session inspect latest
```

## CLI 分层

顶层 help 故意保持简洁：

```text
version
doctor
studio    Expert backend commands
capture
session
device
```

专家命令在：

```powershell
ti-radar studio --help
```

## 安全边界

CLI help 只负责说明命令和参数。Agent 操作规程在：

```text
skills/ti-radar/SKILL.md
```

默认低风险动作：

- 查看版本和 profile
- profile timing 检查
- mock capture
- session manifest 检查
- device route 查询

需要明确意图的动作：

- 下载固件
- RF enable
- DCA1000 reset/probe
- StartFrame
- 长时间 raw ADC 采集
- 修改网卡设置

## DCA1000 默认配置

默认 DCA1000 网络参数：

```text
PC DCA 网卡: 192.168.33.30/24
DCA1000 FPGA: 192.168.33.180
命令端口:     4096
数据端口:     4098
```

这些是常见默认值，不代表你的机器已经配置正确。采集前先跑 `ti-radar doctor`。

## Session Verdict

真实采集会写 `manifest.yaml`：

```yaml
verdict: pass
failure_reasons: []
```

以下情况会 fail：缺 raw bin、bin 太小、缺 DCA packet log、received packets 为 0、乱序、zero-filled packet/byte。

## Agent 使用

给 Codex / Claude Code / Cursor 等 Agent 使用时，先看：

```text
agent-setup.md
```

原则是：先检查，默认不动硬件；涉及硬件状态、长采集、发布、删除等动作时先请求用户确认。

## 发布范围

本仓库只发布通用 TI radar CLI 和 skill。

不包含多传感器同步实验、不包含本地 session、不包含私有实验数据、不包含 raw ADC bin。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Zhenyu98/ti-radar-cli&type=Date)](https://www.star-history.com/#Zhenyu98/ti-radar-cli&Date)

## License

MIT License. See [LICENSE](LICENSE).
