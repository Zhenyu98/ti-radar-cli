# Publish Audit

Status: local pre-publish gate for `ti-radar-cli`.
Date: 2026-06-30.

This file records the intended public scope and the checks that must pass before any GitHub push, public release, package registry upload, or promotion post.

## Target

- Platform: GitHub
- Owner/account: `Zhenyu98`
- Repository/package: `ti-radar-cli`
- Repository URL: `https://github.com/Zhenyu98/ti-radar-cli`
- Display name: `ti-radar-cli`
- One-line description: Reliability-first command-line tools and an agent skill for TI mmWave radar capture with mmWave Studio, RSTD, and DCA1000.

## Visibility

- Initial visibility: confirm before external write
- Public release now: no, pending explicit user approval
- Package registry publication: no, requires a separate audit
- GitHub Pages / public deployment: disabled unless explicitly approved
- GitHub Actions / Discussions / Wiki: disabled unless explicitly approved

Public release approval must be explicit:

```text
Explicit public release approval: GitHub repository Zhenyu98/ti-radar-cli
Name: ti-radar-cli
Scope: publish/ti-radar-cli repository contents listed in this audit
Desensitization confirmed: yes
```

## Contents

Include:

- `src/ti_radar/**`
- `tests/**`
- `skills/ti-radar/SKILL.md`
- `docs/assets/logo.svg`
- `docs/assets/hero.svg`
- `README.md`
- `README_zh.md`
- `agent-setup.md`
- `PUBLISH_AUDIT.md`
- `pyproject.toml`
- `LICENSE`
- `.gitignore`

Exclude:

- `sessions/**`
- `.radar_state/**`
- raw ADC `*.bin` captures
- DCA packet logs such as `*_LogFile.csv` and `*_LogFile.txt`
- private multi-sensor synchronization experiments
- private lab notes and local run logs
- screenshots containing account, machine, path, or hardware state
- `.env`, credentials, API keys, OAuth state, SSH keys, certificates, token caches
- local absolute paths that reveal private directory structure

## Desensitization

Recommended scan command:

```powershell
rg -n "token|secret|password|passwd|apikey|api_key|authorization|bearer|cookie|oauth|client_secret|ownerToken|sk-[A-Za-z0-9_-]+|-----BEGIN|\.env|auth\.json|id_rsa|\.pem|\.key|trycloudflare\.com|workers\.dev|kvNamespace|accountId|C:\\|E:\\|ZhenyuWu|email|@|192\.168\.100|\.bin" .
```

Latest local scan summary:

- No credential files were found in the tracked publish scope.
- False positives include test-created fake `.bin` files, README safety language about raw ADC bins, TI firmware filenames, internal code strings containing `@`, and non-private DCA1000 default network values.
- Standard TI install paths such as `C:\ti\...` may appear as expected runtime defaults; review any added local path before publication.

Required before external write:

1. Run the scan again from the repository root.
2. Review every hit manually.
3. Record any removed or changed files in this section.

Removed or changed in this audit pass:

- Public README files now follow the public README template with a centered title, badges, navigation, visual assets, quick start, Agent Setup entry, FAQ, contributing notes, license, and Star History.
- `docs/assets/logo.svg` and `docs/assets/hero.svg` were added as public visual assets.
- `agent-setup.md` now tells agents to ask before publishing or exposing files.
- `.gitignore` excludes sessions, raw captures, DCA logs, credentials, images, and caches.

## Public Text

- Name: `ti-radar-cli`
- README language: English main README plus Simplified Chinese README
- Agent setup: present as `agent-setup.md`
- Visual assets: present as `docs/assets/logo.svg` and `docs/assets/hero.svg`
- Skill: present as `skills/ti-radar/SKILL.md`
- Acknowledgements: README credits TI public mmWave Studio, DCA1000, and radar toolbox concepts without redistributing TI binaries
- Support wording: hardware coverage is labeled by verification level; only the author's `default_6843` route is presented as verified

## Local Verification To Run

Preferred commands:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build --sdist --wheel
ti-radar version
ti-radar doctor
ti-radar capture smoke --backend mock
ti-radar session inspect latest
```

Low-impact fallback if the CLI is not installed:

```powershell
set PYTHONPATH=src
python tests/test_cli_local.py
```

## Actions Waiting For Approval

1. Confirm exact GitHub target and visibility.
2. Confirm this repository content scope.
3. Confirm desensitization scan result.
4. Push local changes to `Zhenyu98/ti-radar-cli`.
5. Open or update a draft pull request if the push is not directly to the intended branch.
6. Create any release tag or package upload only after a separate approval packet.
