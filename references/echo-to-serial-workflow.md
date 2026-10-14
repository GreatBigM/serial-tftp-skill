# Echo-to-Serial Workflow

> 2026-07-25 session: <项目A> push+WiFi+iperf3 serial test
> Host: Linux x86_64, Device: <项目A> (Ingenic T32), Baud: 921600

## 背景

标准 pyserial 方法（`ser.read()` + `ser.write()`）在以下场景失效：
- **后台 capture 进程独占端口** — 第一个 pyserial reader 吃掉所有数据，第二个 reader 空读
- **`ser.read(ser.in_waiting)` flush 丢数据** — 紧接 `ser.write()` 之前清空 buf 会丢弃设备返回
- **不想写 Python 脚本** — 只需要发几条简单命令

**echo-to-serial 法**用 `echo -ne 'cmd\r' > /dev/ttyUSB0` 发命令，配合幕后单一 capture 进程读取结果，完全绕过 pyserial 竞态。

## 工作流

### 0. 前置准备

```bash
# 重置串口（每次连接前执行一次）
stty -F /dev/ttyUSB0 921600 cs8 -cstopb -parenb raw -echo -echoe -echok
```

### 1. 启动后台 Capture（整个会话一次）

```bash
python3 -c "
import serial, time, subprocess
subprocess.run(['stty','-F','/dev/ttyUSB0','921600','cs8','-cstopb','-parenb','raw','-echo','-echoe','-echok'])
ser = serial.Serial('/dev/ttyUSB0', 921600, timeout=0.2)
f = open('/tmp/serial_capture.log','w',buffering=1)
while True:
  if ser.in_waiting: f.write(ser.read(ser.in_waiting).decode(errors='replace')); f.flush()
  else: time.sleep(0.05)
" &
```

### 2. 验证已登录

```bash
echo -ne 'echo ALIVE_$(date +%s)\r' > /dev/ttyUSB0
sleep 1.5
tail -c 200 /tmp/serial_capture.log
# 输出含 "ALIVE_" 即为已登录
```

### 3. 发送命令 + 读结果

```bash
echo -ne 'cmd\r' > /dev/ttyUSB0
sleep <wait_seconds>
tail -c 500 /tmp/serial_capture.log
```

### 4. 清理

```bash
kill %1
rm -f /tmp/serial_capture.log
```

## 陷阱

| 陷阱 | 后果 | 避免 |
|------|------|------|
| 同时运行两个 pyserial reader | 先开者独占数据，后者空读 | 单一 capture + echo-to-serial |
| `echo 'cmd'` 无 `\r` | 命令不执行 | 始终 `echo -ne 'cmd\r'` |
| pyserial `ser.read(ser.in_waiting)` flush | flush 丢数据 | 别混用；一致用 echo + capture.log |
| 后台 capture 未 kill 就重启 | 新 capture 空读（旧进程锁端口） | `killall python3; rm -f /tmp/serial_capture.log` |
| `sleep` 太短 | 命令未完成，读空 | 设备慢时加长 sleep |

## 适用场景对比

| 方法 | 适用 | 不适用 |
|------|------|--------|
| **echo-to-serial** | 逐条短命令，快速诊断 | 交互式 shell（top/vi）、复合脚本 |
| **pyserial reader+writer** | 完整自动化测试 | 多人同时操作的设备（竞态） |
| **ADB shell** | 可靠输出，无日志洪流 | 需要串口直接交互（U-Boot/kernel panic） |
