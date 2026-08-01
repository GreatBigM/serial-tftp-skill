# Changelog

本文件记录版本历史。版本号定义在 SKILL.md frontmatter 的 `version` 字段（单一真相源）。

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
