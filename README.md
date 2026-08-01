# serial-tftp-skill

嵌入式设备串口 + TFTP 烧录技能集（Hermes Agent skills）—— 2 个技能覆盖从串口连接、设备交互到君正 T32 NOR 烧录的完整调试链路。

```
serial-dev-console        串口交互与故障诊断（登录/设IP/启adbd/杀进程/查状态 + 诊断决策树 + Python 脚本）
ingenic-basic-tftp-flash  君正 T32 NOR TFTP 烧录完整流程（TFTP server/mai_tftp/自动烧录 + 故障速查）
```

## 安装（推荐：一键脚本）

```bash
# 安装全部 2 个技能
curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash

# 只装单个技能（可选）
curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash -s -- serial-dev-console
```

> 脚本等价于手动复制（clone + cp），不经过安全扫描，可先审阅脚本内容再执行。
> 已安装时自动备份旧版本到 `~/.hermes/skills/<name>.bak.<时间戳>`。
> 安装后：会话内 /reload-skills，或新开会话自动加载。

## 安装（备选：手动复制）

```bash
git clone https://github.com/GreatBigM/serial-tftp-skill.git
cp -r serial-tftp-skill/serial-dev-console ~/.hermes/skills/
cp -r serial-tftp-skill/ingenic-basic-tftp-flash ~/.hermes/skills/
```

> ⚠️ `hermes skills install`（tap/URL 方式）对含 shell 命令/AGENTS.md 引用的技能会触发安全扫描拦截（误报），
> 且 community 来源 + dangerous 判定不可用 --force 绕过。**请使用一键脚本或手动复制。**

## 快速上手

```bash
# 1. 串口连接（serial-dev-console）：确认端口 + 波特率，登录设备
sudo chmod 666 /dev/ttyUSB0
python3 <skill_dir>/scripts/serial_cmd.py     # 交互式串口

# 2. 查 IP / 启 ADB
#    设备 shell 里: ifconfig eth0
#    adbd 不在则: adbd --root &

# 3. TFTP 烧录（ingenic-basic-tftp-flash）：自动烧录
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash --baud <波特率>
```

## 技能清单

| 技能 | 覆盖场景 | 附带脚本 |
|------|---------|---------|
| serial-dev-console | 登录/设IP/启adbd/杀进程/查状态/重启捕获 + 故障诊断决策树 | serial_cmd.py / capture_boot_log.py / reboot_capture.py |
| ingenic-basic-tftp-flash | TFTP server / mai_tftp / 自动烧录 / 故障速查 | auto-uboot-interrupt.py / reboot-stress.py |

## 平台说明

- 适用平台：君正 Ingenic T32 系列（NOR flash + U-Boot + mai_tftp）
- 波特率因项目而异（典型 115200 / 921600），技能内有探测方法
- 文中 IP/路径均为占位符（`<HOST_IP>`/`<TFTP_DIR>`/`<项目>`），按实际环境替换

## License

MIT
