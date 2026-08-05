# 2026-07-17: HM6502 Partial-Erase Flash via --at-uboot Recovery

## 背景

- **项目**: HM6502 (Ingenic T32)
- **波特率**: 921600
- **擦除范围**: `0xef0000`（部分擦，保留 env/data/log 分区）
- **固件**: `hm6502_NOR_ALL.bin` 16MB
- **脚本**: `auto-uboot-interrupt.py flash`
- **主机 IP**: 172.17.151.6

## 执行流程

### 尝试 1: 普通 flash（失败）

```bash
python3 auto-uboot-interrupt.py flash --baud 921600
```

**输出:**
```
[+] Serial port /dev/ttyUSB0 ready (921600 baud)
[*] Device mode: linux
[+] Login verified
[*] Sending reboot...
[-] Failed to interrupt U-Boot
```

**串口检查（关键步骤）：**
```
python3 -c "import serial, time; ...
s.write(b'\r\n')
# 返回: \r\nPRJ009# \r\nPRJ009#
```

设备实际已在 U-Boot 提示符下！脚本的 reboot 触发成功（设备重启进入了 U-Boot），但脚本的 ~12s 回车洪流未覆盖到 U-Boot 的 ~1s bootdelay 窗口，超时退出。

**正确断定：** 脚本 exit code 1 + 串口 PRJ009# → 设备在 U-Boot → 直接 `--at-uboot` 重试，不要断电，不要放弃。

### 尝试 2: --at-uboot flash（成功）

```bash
python3 auto-uboot-interrupt.py flash --at-uboot --baud 921600
```

**产出物:**
- tftpboot: `Bytes transferred = 16777216` (16MB) ✓
- sf probe: `Detected ZB25VQ128, flash size: 16MB` ✓
- sf erase `0x0 0xef0000`: `Erased: OK` (35720ms) ✓
- sf write: 完成 ✓
- 设备自动 reset → 启动新固件（c_mi_ipc、motor calibration、video encoding 全部正常）

### 烧录后验证

| 检查项 | 结果 |
|--------|------|
| 旧 ADB IP (172.17.151.200) | ❌ 连不上 |
| 新 IP (串口 `ifconfig eth0`) | `172.17.150.56`（DHCP 重新分配） |
| ADB kill-server + connect | ✅ 正常 |
| c_mi_ipc 运行 | ✅ PID 453 正常工作 |
| 设备启动 | ✅ 日志可见新固件 |

## 关键教训

1. **`Failed to interrupt U-Boot` 不是失败，是信号。** 不要放弃，先看串口。PRJ009# 存在则设备状态正确，直接 `--at-uboot`。

2. **部分擦（`0xef0000`）保留 env，但 DHCP 仍可能换 IP。** 不要假设保留 env 就能维持旧 IP。全擦和部分擦后都必须用串口确认新 IP。

3. **`--at-uboot` 跳过 Steps 0-1（login/reboot/interrupt），直接触发 mai_tftp。** 这是最简单的恢复路径。

4. **成功判定依据（优先级由高到低）：**
   - `sf probe` + `sf erase` + `sf write` 全部完成 = 烧录成功
   - 设备 reset 后出现新固件的 kernel/U-Boot 日志 = 烧录生效
   - 脚本 exit code 1 但 mai_tftp 阶段已输出成功标志 → 忽略 exit code
