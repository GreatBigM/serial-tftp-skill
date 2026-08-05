# HM6502 TFTP 烧录 timing & ZB25VQ128 变体记录

日期: 2026-07-17

## 设备信息

- 项目: HM6502 (Ingenic T32, PRJ009)
- Flash IC 实测: **ZB25VQ128** (不是 doc 中的 EN25QX128A)
- 串口波特率: 921600
- 固件大小: 16777216 bytes (16MB, 0x1000000)
- auto_update_tftp.txt 擦除范围: `0xef0000` (部分擦, 15663104 bytes)
- 脚本: `auto-uboot-interrupt.py flash --at-uboot --baud 921600`

## 各阶段耗时

| 阶段 | 耗时 | 说明 |
|------|------|------|
| TFTP 下载 16MB | ~几秒 | 2 MiB/s |
| sf probe (ZB25VQ128) | 1 ms | 自动检测 |
| sf erase 0x0 0xef0000 (15.6MB) | **35972 ms (~36s)** | 擦除速度 ~435 KB/s |
| sf write 0x80600000 0x0 0xef0000 | >60s (未完成时超时) | 写速度比擦除慢，估算 ~260 KB/s |
| mai_tftp 总体 | ~120s | 含 download + erase + write + reset |

## Flash 变体

| 文档值 | 实测值 |
|--------|--------|
| EN25QX128A | ZB25Q128 |

ZB25VQ128 是 Zbit Semiconductor 的 16MB SPI NOR Flash，与 EN25QX128A (EON) 功能兼容。SF probe 自动识别厂商 ID 和型号，U-Boot 驱动对两者同样支持。

## 串口刷屏现象

HM6502 固件启动后，c_mi_ipc 应用层立即向串口输出日志:
- ISP/VPU 初始化
- Motor calibration 完成
- IMP_Encoder_GetStream 每 ~25 帧/次 (~1s 间隔)
- CPU loading / free_mem 每 ~3s
- MI WATCHDOG connect daemon socket failed 每 ~3s
- PhotoSen 感光检测每 ~30s

这些串口输出淹没了 `login:` 提示符，导致 `auto-uboot-interrupt.py` 的 post-flash login 检测超时退出 (exit code 1) — 即使烧录完全成功、设备正常运行。

## 经验教训

1. 脚本 exit code 1 "Login prompt not detected" 可能在**部分擦**时也出现（非仅全擦超时），根因是固件串口日志刷屏
2. 确认烧录成功的方法: 串口日志中出现新固件的 U-Boot 启动 → kernel 启动 → c_mi_ipc 应用日志
3. `--at-uboot` 恢复路径可靠: 设备在 PRJ009# 时的烧录完全正常
4. 擦除 15.6MB 需要 ~36s，写入需 ~60s+ — post-flash 监控超时应适当放宽
