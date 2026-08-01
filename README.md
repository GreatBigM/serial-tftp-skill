# serial-tftp-skill

嵌入式设备串口交互与 TFTP 刷机技能（Ingenic T32 平台）。

## 功能

- **TFTP 刷机**：环境预检 → 串口连接 → 模式判断 → 配网烧录 → 完成验证
- **串口交互**：单命令执行、启动日志采集、循环重启测试
- **配置缓存**：波特率/IP/TFTP目录等参数首次设定后自动复用

## 安装

```bash
curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash
```

或手动：
```bash
git clone https://github.com/GreatBigM/serial-tftp-skill.git
mkdir -p ~/.hermes/skills/serial-tftp
cp serial-tftp-skill/SKILL.md ~/.hermes/skills/serial-tftp/
cp -r serial-tftp-skill/scripts ~/.hermes/skills/serial-tftp/
cp -r serial-tftp-skill/references ~/.hermes/skills/serial-tftp/
```

## 首次使用

```bash
# 方式 A（推荐）：交互式向导，逐项输入，回车接受默认值
python3 ~/.hermes/skills/serial-tftp/scripts/auto-uboot-interrupt.py setup

# 方式 B：命令行直设（适合脚本化/已知参数）
python3 ~/.hermes/skills/serial-tftp/scripts/auto-uboot-interrupt.py config ipaddr <设备IP>
python3 ~/.hermes/skills/serial-tftp/scripts/auto-uboot-interrupt.py config serverip <主机IP>
python3 ~/.hermes/skills/serial-tftp/scripts/auto-uboot-interrupt.py config tftp-dir <TFTP目录>

# 一键烧录
python3 ~/.hermes/skills/serial-tftp/scripts/auto-uboot-interrupt.py flash
```

参数自动缓存到 ~/.config/serial-tftp/config.json，后续烧录免输入。

## 依赖

- python3 + pyserial
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
