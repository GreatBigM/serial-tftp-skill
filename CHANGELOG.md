# Changelog

本文件记录版本历史。版本号定义在 SKILL.md frontmatter 的 `version` 字段（单一真相源）。

## 1.4.0 (2026-08-01)

### Fixed（HM6502 真机实践复盘，三轮 LOOP 优化）
- **IP 冲突预检**：配网后 ping 设备自身 IP，通 = 被占用 → 中止并给排查路径（根因：设备 IP 与局域网设备冲突导致 TFTP T T T T 反复失败）
- **打断 U-Boot 提示符探测化**：不再硬编码 `<项目>#`（真实设备是 PRJ009# 匹配不上），改正则匹配行尾 # 或 =>
- **静默窗口打断**：有输出时不发回车，静默 ≥0.3s 才砸——避免和 mai_tftp 重试循环的 T 输出打架
- **失败恢复提示细化**：mai_tftp 循环（静默窗口 Ctrl+C）/ IP 冲突（ip neigh 排查）/ 打断失败三场景具体路径
- SKILL.md 流程铁律同步：IP 冲突预检 + 提示符探测 + 失败恢复速查

### Changed
- 版本 1.3.0 → 1.4.0

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
