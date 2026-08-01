# serial-tftp-skill

嵌入式设备串口 + TFTP 烧录技能集（Hermes Agent skills）—— 4 个技能覆盖从串口连接、设备交互到君正 T32 NOR 烧录的完整调试链路。

```
serial-setup              串口连接建立与故障排查（无输出/乱码/日志洪流/命令截断）
serial-dev-console        串口交互（登录/设IP/启adbd/杀进程/查状态 + Python 脚本）
ingenic-flash             君正 T32 NOR 烧录（auto-uboot TFTP 自动烧录 + 手动 U-Boot 备选）
ingenic-basic-tftp-flash  TFTP 刷机完整流程（TFTP server 搭建/mai_tftp/auto_update_tftp.txt + 故障速查）
```

## 安装（推荐：一键脚本）

```bash
# 安装全部 4 个技能
curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash

# 只装单个技能（可选）
curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash -s serial-setup
```

> 脚本等价于手动复制（clone + cp），不经过安全扫描，可先审阅脚本内容再执行。
> 已安装时自动备份旧版本到 `~/.hermes/skills/<name>.bak.<时间戳>`。
> 安装后：会话内 /reload-skills，或新开会话自动加载。

## 安装（备选：手动复制）

```bash
git clone https://github.com/GreatBigM/serial-tftp-skill.git
cp -r serial-tftp-skill/serial-setup ~/.hermes/skills/
cp -r serial-tftp-skill/serial-dev-console ~/.hermes/skills/
cp -r serial-tftp-skill/ingenic-flash ~/.hermes/skills/
cp -r serial-tftp-skill/ingenic-basic-tftp-flash ~/.hermes/skills/
```

> ⚠️ `hermes skills install`（tap/URL 方式）对含 shell 命令/AGENTS.md 引用的技能会触发安全扫描拦截（误报），
> 且 community 来源 + dangerous 判定不可用 --force 绕过。**请使用一键脚本或手动复制。**

## 快速上手

```bash
# 1. 串口连接（serial-setup）：确认端口 + 波特率，登录设备
sudo chmod 666 /dev/ttyUSB0
python3 serial-dev-console/scripts/serial_cmd.py     # 交互式串口

# 2. 查 IP / 启 ADB（serial-dev-console）
#    设备 shell 里: ifconfig eth0
#    adbd 不在则: adbd --root &

# 3. TFTP 烧录（ingenic-basic-tftp-flash）：自动烧录
python3 ingenic-basic-tftp-flash/scripts/auto-uboot-interrupt.py flash --baud <波特率>
```

## 技能清单

| 技能 | 覆盖场景 | 附带脚本 |
|------|---------|---------|
| serial-setup | 串口不通/乱码/日志洪流/长命令截断的决策树诊断 | — |
| serial-dev-console | 登录/设IP/启adbd/杀进程/查状态/重启捕获 | serial_cmd.py / capture_boot_log.py / reboot_capture.py |
| ingenic-flash | NOR 烧录标准流程 + 手动 U-Boot 备选 | — |
| ingenic-basic-tftp-flash | TFTP server / mai_tftp / 烧录故障速查表 | auto-uboot-interrupt.py / reboot-stress.py |

## 平台说明

- 适用平台：君正 Ingenic T32 系列（NOR flash + U-Boot + mai_tftp）
- 波特率因项目而异（典型 115200 / 921600），技能内有探测方法
- 文中 IP/路径均为占位符（`<HOST_IP>`/`<TFTP_DIR>`），按实际环境替换

## License

MIT
