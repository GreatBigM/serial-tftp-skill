# TFTP 烧录波特率 & U-Boot 打断恢复

## 波特率速查

| 项目 | U-Boot 串口波特率 | 脚本参数 |
|------|------------------|---------|
| HM6502 | **921600** | `--baud 921600` |
| HM6801 | **115200** | 默认 |

HM6502 使用 `--baud 921600`，否则脚本读到空输出。HM6801 用默认 115200。

> **2026-07-17 纠正**：HM6502 波特率从 1500000 纠正为 921600（用户实测确认）。1500000 会读到乱码/空输出。

## `Failed to interrupt U-Boot` 恢复

脚本报错后不代表打断失败。串口日志洪流可能淹没 U-Boot 提示符。验证步骤：

```bash
stty -F /dev/ttyUSB0 921600 raw
echo -ne '\r' > /dev/ttyUSB0; sleep 0.5; cat /dev/ttyUSB0 | head -3
```

- 看到 `PRJ009#` -> 设备已在 U-Boot -> 重跑脚本加 `--at-uboot`
- 看到 `70mai login:` -> 设备仍在 Linux -> 重跑脚本不加参数
- 看到 `root@70mai` -> 已登录 -> 直接 reboot 后重跑

## TFTP 全量烧录擦除 /tmp

NOR 全片擦写（`sf erase 0x0 0xef0000`）后，设备 tmpfs 中所有文件丢失：
- iperf 测速工具
- 测试脚本（wifi_bench.sh 等）
- 临时日志文件

烧录后测试工具链断裂，必须重新推送。推送方式：
- ADB 在线：`adb push`
- ADB 离线：HTTP server + wget（`python3 -m http.server 9999 --directory /tmp` + 设备 `wget http://<host>:9999/<file> -O /tmp/<file>`）

## 2026-07-11 实测记录

- HM6502 auto-uboot-interrupt.py 默认 115200 -> 串口无回显
- 改为 `--baud 921600` -> 脚本检测到 Linux 模式、reboot 成功
- 但脚本报 `Failed to interrupt U-Boot` - 实际设备已在 PRJ009#
- 手动验证串口看到 PRJ009# -> `--at-uboot` 参数成功烧录
- 烧录后 iperf/脚本均不在设备上 -> 需 HTTP 推送
- 烧录后 **wlan0 无 IP**（RX/TX=0，`ifconfig` 无 inet addr）- algo 分区被擦除，WiFi 配置丢失。必须通过 Mi Home App 重新配网才能测无线吞吐。

## 2026-07-17 波特率纠正记录

- 原 skill 记录 HM6502 波特率 1500000（1.5M），实际为 **921600**
- 1500000 波特率下串口读到全乱码（`\r` 回车后返回不可读字符）
- 921600 波特率下串口输出清晰可读（U-Boot 启动日志、mai_tftp 输出等）
- 已同步修正 SKILL.md 项目配置表、踩坑记录、排障表，及本文档
