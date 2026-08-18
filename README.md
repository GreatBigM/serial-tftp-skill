# serial-tftp-skill

嵌入式设备串口交互与 TFTP 刷机技能（Ingenic T32 平台）。

## 功能

- **TFTP 刷机**：环境预检 → 串口连接 → 模式判断 → 配网烧录 → 完成验证
- **串口交互**：单命令执行、启动日志采集、循环重启测试
- **配置缓存**：波特率/IP/TFTP目录等参数首次设定后自动复用

## 安装

本 skill 支持多 agent 目标：Hermes / Claude Code / Codex / ZCode。安装脚本自动探测本机已安装的 agent，让用户选择安装目标。

```bash
# 方式 1：交互选择安装目标（推荐，先下载再执行以保留交互）
curl -fsSL https://gitee.com/GreatBigM/serial-tftp-skill/raw/main/install.sh -o /tmp/install.sh && bash /tmp/install.sh

# 方式 2：指定目标（非交互，含 ZCode）
curl -fsSL https://gitee.com/GreatBigM/serial-tftp-skill/raw/main/install.sh | bash -s -- --target hermes,claude,zcode

# 方式 3：安装到全部检测到的 agent
curl -fsSL https://gitee.com/GreatBigM/serial-tftp-skill/raw/main/install.sh | bash -s -- --all
```

> 脚本等价于手动复制（clone + cp），不经过安全扫描，可先审阅脚本内容再执行。
> 已安装时自动备份旧版本到 `<skill_dir>.bak.<时间戳>`，重跑即升级（含版本对比提示）。

## 使用方式

**本技能的使用方式是：用户指挥 AI，AI 替用户执行。** 用户说"配置烧录参数/烧录/刷机"，AI 读技能参数说明、对话层询问缺失参数、写入缓存并直接执行，用户不面对命令行。

无 AI 时可在终端直连（安装脚本已建统一命令入口 `serial-tftp` → `~/.local/bin/`）：

```bash
# 方式 A（推荐）：交互式向导，逐项输入，回车接受默认值
serial-tftp setup

# 方式 B：命令行直设（适合脚本化/已知参数）
serial-tftp config ipaddr <设备IP>
serial-tftp config serverip <主机IP>
serial-tftp config tftp-dir <TFTP目录>

# 一键烧录
serial-tftp flash
```

> 若未建命令入口（手动复制安装），可直接调脚本：`python3 <skill目录>/scripts/auto-uboot-interrupt.py setup`（skill 目录随安装位置而定：`~/.hermes/skills/`、`~/.claude/skills/`、`~/.zcode/skills/` 等）。

参数自动缓存到 ~/.config/serial-tftp/config.json，后续烧录免输入。

## 依赖

- **Python 3.6+**（必需，2020 年后 Linux 发行版自带；Python 2 不支持，serial-tftp 命令有版本门卫）
- pyserial（可选：有则用，无则自动 fallback 到内置标准库兼容层 serial_compat.py，零安装）
- tftpd-hpa（TFTP 服务器）
- 串口线连接 /dev/ttyUSB0

## 目录结构

```
├── SKILL.md              # 技能定义（五步烧录流程）
├── scripts/
│   ├── flash_config.py   # 统一配置管理
│   ├── auto-uboot-interrupt.py  # 烧录主脚本
│   ├── serial_cmd.py     # 串口命令工具
│   ├── capture_boot_log.py      # 启动日志采集
│   ├── reboot_capture.py        # 循环重启采集
│   └── reboot-stress.py         # 重启压力测试
├── references/
│   └── serial-console-notes.md  # 串口经验笔记
├── install.sh
└── README.md
```
