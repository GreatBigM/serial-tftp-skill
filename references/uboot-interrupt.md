# U-Boot 自动中断（打断 autoboot）

> 串口 reboot 后，在 U-Boot 2 秒倒计时内按键中断，进入 `PRJ009#`/`<项目A>#` 提示符。

## 适用场景

- 需要进入 U-Boot 命令行执行 `mai_tftp`、`sf probe`、`setenv`、`tftpboot` 等操作
- 设备重启后自动进入 Linux，需要干预引导过程

## 关键词检测清单

U-Boot 启动时会输出以下关键词之一，检测到即可开始发送打断字符：

```
U-Boot, uboot, Hit any key, stop autoboot, SPI Nor ID,
SPI, SF: Detected, DRAM:, Press, T32, Ingenic
```

倒计时文本示例（<项目E> PRJ009）：
```
Hit any key to stop autoboot:  2 \b\b\b 1 \b\b\b 0
```
倒计时仅 **2 秒**，手动操作需在 U-Boot 日志一出现就连按回车。

## Python 自动中断脚本

```python
import serial, time

BAUD = 115200
DEV = '/dev/ttyUSB0'

ser = serial.Serial(DEV, BAUD, timeout=0.1)
time.sleep(0.3)
ser.reset_input_buffer()

# Phase 1: Send reboot
ser.write(b'reboot\r')
time.sleep(1)
ser.read(4096)  # drain immediate output

# Phase 2: Wait for U-Boot and interrupt
start = time.time()
uboot_detected = False
enter_count = 0

while time.time() - start < 40:  # max 40s for full boot cycle
    chunk = ser.read(4096)
    if chunk:
        text = chunk.decode('utf-8', errors='replace')
        
        if not uboot_detected:
            for kw in ['U-Boot', 'uboot', 'Hit any key', 'stop autoboot',
                       'SPI Nor', 'SF: Detected', 'DRAM:', 'Press',
                       'T32', 'Ingenic']:
                if kw.lower() in text.lower():
                    uboot_detected = True
                    break
        
        if uboot_detected and enter_count < 50:
            ser.write(b'\r' * 3)   # spam Enter
            enter_count += 3
            time.sleep(0.05)
    else:
        time.sleep(0.1)

print(f"Enter sent {enter_count} times")
ser.close()
```

## 硬件平台差异

| 平台 | U-Boot 提示符 | 倒计时 | 备注 |
|------|--------------|--------|------|
| <项目E> (PRJ009) | `PRJ009#` | 2s | 实测通过 |
| <项目A> | `<项目A>#` (推测) | 待测 | 结构相同 |

## 注意事项

- 倒计时极短（2s），用关键词检测 + 批量发 Enter 比依赖精确 timing 可靠
- 检测到 U-Boot 后持续发 Enter 直到超出最大次数（50次约覆盖 2.5s），确保不会错过窗口
- 若 40s 后仍无 U-Boot 输出，检查串口连接和波特率
