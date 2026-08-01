# Changelog

本文件记录版本历史。版本号定义在 SKILL.md frontmatter 的 `version` 字段（单一真相源）。

## 1.2.0 (2026-08-01)

### Added
- **serial_compat.py：pyserial 兼容层（标准库 termios 实现，零依赖）**——环境无 pyserial 时自动 fallback，无需 pip install
- 6 个脚本 import 统一改为 try/except fallback（有 pyserial 用 pyserial，无则用标准库）
- 解决协作者环境差异：py3 必有 + pyserial 可能缺失的场景全覆盖

### Changed
- 版本 1.1.0 → 1.2.0

## 1.1.0 (2026-08-01)

### Added
- **统一命令入口 `serial-tftp`**（scripts/serial-tftp wrapper）：版本门卫（py3 检测在 Python 解析前拦截 py2-only 环境，友好提示不崩溃）+ 子命令分派（flash/setup/config/cmd/capture/reboot-capture/stress/shell）
- install.sh 安装 wrapper 到 ~/.local/bin/serial-tftp
- py3 版本检测：flash_config.py 顶部 sys.version_info < 3.6 拦截（3.0-3.5 提示）

### Changed
- README/SKILL.md：使用方式主推 `serial-tftp` 命令入口，依赖明确 Python 3.6+

## 1.0.0 (2026-08-01)

### Added
- 初始发布：serial-tftp 单技能（串口交互 + TFTP 刷机五步流程）
- 由 serial-dev-console + ingenic-basic-tftp-flash 两技能收敛合并（消除重叠）
- 顶部新增「AI 替你完成」使用哲学头节 + AI 交互约定（agent 走参数路径，不用管道喂 stdin）
- setup 交互式参数设定向导：逐项输入+校验，回车接受默认值，q 取消，取消零副作用
- flash 预检失败自动引导：参数缺失 → 询问是否进入交互设定（isatty 分界）
- 脱敏：prj009# → <项目>#，进程名加"按设备调整"说明
- scripts: auto-uboot-interrupt.py / flash_config.py / serial_cmd.py / capture_boot_log.py / reboot_capture.py / reboot-stress.py
- references/serial-console-notes.md 串口交互经验
