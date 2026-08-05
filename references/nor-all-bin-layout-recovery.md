# NOR_ALL.bin 布局恢复与备选 Slot 启动

## 背景

2026-07-03 HM6502 会话：手动将新 squashfs 替换进 NOR_ALL.bin 后，分区边界偏移被破坏，
U-Boot bootcmd 默认从 slot B (0x800000) 读内核失败。通过 `printenv` + 手动 `sf read + bootm`
从 slot A (0x290000) 成功启动。

## 排查步骤

### 1. 进入 U-Boot 后查看分区布局

在 `PRJ009#` 或 `=>` 提示符下：

```
printenv
```

关键输出行：
```
bootargs=console=ttyS1,115200n8 mem=85M@0x0 rmem=43M@0x5500000 init=/linuxrc
  rootfstype=squashfs root=/dev/mtdblock1 ro
  mtdparts=sfc0_nor:256k(boot),2368k(rootfs),5568k@0x290000(kernel_system_a),
          5568k@0x800000(kernel_system_b),1536k@0xD70000(algo),...
  system=1

bootcmd=sf0 probe;sf0 read 0x80a00000 0x800000 0x600000;bootm 0x80a00000
```

### 2. 从 mtdparts 解析分区偏移

| 分区 | 偏移 | 大小 | 说明 |
|------|------|------|------|
| boot | 0x0 | 256K | U-Boot SPL |
| rootfs | 0x40000 | 2368K | squashfs 根文件系统 |
| kernel_system_a | 0x290000 | 5568K | system=0 时的启动 slot |
| kernel_system_b | 0x800000 | 5568K | system=1 时的启动 slot |
| algo | 0xD70000 | 1536K | 算法分区 |

`bootargs` 中 `system=1` 表示当前使用 slot B。`bootcmd` 中的 `sf read 0x80a00000 0x800000 0x600000`
从 slot B (0x800000) 读取 6MB (0x600000) 到内存 0x80a00000，然后 `bootm` 启动。

### 3. 从备选 slot 手动启动

```python
import serial, time

ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=3)
time.sleep(0.5)
ser.reset_input_buffer()

cmds = [
    'sf0 probe',
    'sf0 read 0x80a00000 0x290000 0x600000',  # 从 slot A 读
    'bootm 0x80a00000',
]
for cmd in cmds:
    ser.write(f'{cmd}\r\n'.encode())
    time.sleep(0.5)

time.sleep(10)  # 等 Linux 启动
output = ser.read(5000).decode('utf-8', errors='replace')
# 如果看到 apphilogcat 日志 → 启动成功
ser.close()
```

### 4. 串口噪音处理

当 `apphilogcat` 打印 AIM motion detection 日志（每 ~300ms 一行）时，串口被洪流淹没，
shell 命令和回显都无法通过。两种方法降噪：

**方法 A — 通过 init 框架停止服务**（推荐，命令不会被日志冲掉）：
```
paramset ohos.ctl.stop apphilogcat
```

**方法 B — killall**（可能被日志淹没，需多发几次）：
```
killall -9 apphilogcat c_mi_ipc miio_client 2>/dev/null
```

> 方法 A 更可靠，因为 `paramset` 通过 socket 通信绕过串口，不受日志噪音影响。
> 方法 B 的 `killall` 命令通过串口发送，日志洪流期间可能无法到达 shell。

## 教训

- **不要手动替换 NOR_ALL.bin 中的分区。** `mtdparts` 定义了严格的分区偏移和大小。
  squashfs 大小变化会破坏后续分区的偏移量。
- **正确的做法：** 更新 staging 目录 → 通过 `cmake && make -j && make pack_firmware` 完整重建。
- **恢复手段：** 如果已经写坏了，从备选 slot 手动 bootm。然后通过 `mai_tftp` 全量烧录一次正确的镜像。
