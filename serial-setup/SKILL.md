---
name: serial-setup
description: 嵌入式设备串口连接建立与故障排查 — 无输出/日志洪流/命令截断/login丢失的完整诊断流程
category: devops
metadata:
  hermes:
    triggers: [串口, serial, ttyUSB, 乱码, 无响应, 日志洪流, login失败]
---

# 串口连接建立与故障排查

> 故障诊断聚焦。完整操作参考见 `serial-dev-console`。

## 一、故障诊断决策树

```
串口不通？
├─ 无任何输出
│  ├─ 设备断电？ → 查电源灯/万用表
│  ├─ 波特率不对？ → 乱码 → 探测波特率 [921600, 115200, 1500000, 57600, 9600]
│  ├─ 串口线松动？ → 重插 /dev/ttyUSB0
│  └─ pyserial 读不到？ → stty 重置端口参数
├─ 有输出但命令不执行
│  ├─ 未登录？ → 盲打 burst 登录
│  └─ login 进程挂死？ → 看门狗复位或物理断电
├─ 日志洪流淹没输出
│  ├─ 文件重定向法 — `cmd > /tmp/_f; cat /tmp/_f`
│  ├─ marker 包裹法 — `echo "START"; cmd; echo "END"`
│  └─ 仍不行 → 切 ADB（stdout 不受日志影响）
└─ 长命令被截断
   ├─ 拆为 < 80 字符的短命令
   └─ 写脚本到文件再执行
```

## 二、常见故障诊断

### 2.1 串口无数据

**症状**：`ser.read()` 持续返回空，但 `cat /dev/ttyUSB0` 能读。

**根因**：pyserial 被残留 termios 设置污染。

**修复**：在 `serial.Serial()` 之前重置端口：

```python
import subprocess
subprocess.run(['stty', '-F', '/dev/ttyUSB0', '921600',
    'cs8', '-cstopb', '-parenb', 'raw', '-echo', '-echoe', '-echok'],
    capture_output=True)
```

### 2.2 串口乱码

**症状**：全是不可读二进制。

**根因**：波特率不匹配。

**修复**：逐一探测：

```python
for baud in [921600, 115200, 1500000, 57600, 9600]:
    # stty 重置 → serial.Serial → 读数据 → 检查 printable ratio
```

<项目>: **921600**（`console=ttyS1,921600n8`）

### 2.3 命令发送了但没执行

**症状**：写 `reboot\r` 后设备不重启，继续输出日志。

**根因**：未登录——`reboot` 被 login 提示符当作用户名处理。

**修复铁律**：发任何命令前**必须先登录并验证**。

```python
# ① 盲打登录
for i in range(25):
    ser.write(b'root\r'); time.sleep(0.03)
    ser.write(b'\r'); time.sleep(0.03)

# ② 验证（时间戳唯一化防残留文件误判）
ts = str(int(time.time()))
ser.write(f'echo L_{ts}\r'.encode())
time.sleep(1.5)
# 检查输出中是否包含 L_{ts}
```

### 2.4 日志洪流

**症状**：c_mi_ipc + miio_client 日志持续刷屏（~100 msg/s），`ifconfig` 等命令输出被淹没。

**修复优先级**：

| 优先级 | 方法 | 适用场景 |
|-------|------|---------|
| 1 | **文件重定向** `cmd > /tmp/_f; cat /tmp/_f` | 任何日志密度 |
| 2 | **marker 包裹** `echo "START_${ts}"; cmd; echo "END_${ts}"` | 中等密度 |
| 3 | **切 ADB** | eth0 ADB 可用时首选 |
| 4 | **杀日志进程** `killall apphilogcat` | 最终手段（会丢日志） |

### 2.5 长命令截断

**症状**：串口 raw 模式下 > 80 字符的命令被截断。

**修复**：
- 拆为多条短命令
- 或写脚本到文件：`echo 'cmd1; cmd2' > /tmp/s; sh /tmp/s`

### 2.6 login 反复掉线

**症状**：登录成功几秒后又回到 login 提示符。

**根因**：串口 idle timeout 或 getty 重启。

**修复**：每次重要命令前都验证登录状态（时间戳 echo）。

## 三、快速启动序列（<项目>）

```python
import serial, time, subprocess

BAUD = 921600
# ① 重置端口
subprocess.run(['stty', '-F', '/dev/ttyUSB0', str(BAUD),
    'cs8', '-cstopb', '-parenb', 'raw', '-echo', '-echoe', '-echok'],
    capture_output=True)
time.sleep(0.3)

ser = serial.Serial('/dev/ttyUSB0', BAUD, timeout=0.2)
time.sleep(0.3)
ser.read(ser.in_waiting)

# ② 盲打登录（25 轮，0.03s 间隔）
for i in range(25):
    ser.write(b'root\r'); time.sleep(0.03)
    ser.write(b'\r'); time.sleep(0.03)

# ③ 验证登录
ts = str(int(time.time()))
ser.write(f'echo L_{ts}\r'.encode())
time.sleep(1.5)
buf = bytearray()
deadline = time.time() + 2
while time.time() < deadline:
    if ser.in_waiting: buf.extend(ser.read(ser.in_waiting))
    else: time.sleep(0.02)
if f'L_{ts}' not in buf.decode(errors='replace'):
    print('LOGIN FAILED — retry or check power/baud')
    exit(1)

# ④ 清理 + 设静态 IP
ser.read(ser.in_waiting)
ser.write(b'ifconfig eth0 <DEV_IP> netmask 255.255.254.0 up\r')
time.sleep(1)
```

## 四、行终止符陷阱

**`\r` (CR) 是 enter 键，`\n` (LF) 不是！**

在 `stty raw` 模式下，getty 只认 `\r` 为行终止符。

```python
# ❌ — LF 被忽略，输入静默丢失
ser.write(b'root\n')

# ✅ — CR 才是回车键
ser.write(b'root\r')
```

## 五、故障速查（if-X-then-Y）

### 登录失败
```
IF echo 验证不通过
THEN 盲打 burst: root\r + \r, 50轮, 0.01s间隔 → 时间戳 echo 验证
```

### 命令输出被日志淹没
```
IF ser.read() 返回大量应用日志但无命令输出
THEN 文件重定向: cmd > /tmp/_f 2>&1; cat /tmp/_f
```

### 长命令被截断
```
IF 命令 > 80 字符
THEN 拆为多条短命令 / echo 写脚本文件再执行
```

### reboot 不生效
```
IF 发 reboot 后 5s 还在输出应用日志
THEN 未登录！reboot 被 login 当用户名。重新登录→验证→再 reboot
```

### 串口无数据
```
IF ser.read() 持续返回空但 cat /dev/ttyUSB0 能读
THEN stty 重置端口参数后重新 serial.Serial()
```

## 六、反模式

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| 不验证登录就发 reboot | reboot 被 login 当作用户名吃掉 | 先 echo 验证登录 |
| 用 `\n` 作行终止符 | 所有输入静默丢失 | 始终用 `\r` |
| 长命令一条 send | 串口 raw 模式截断 | 拆为 < 80 字符或写文件 |
| 反复读取后清空 buf | 累积数据丢失，看起来像零输出 | 持续追加到同一 buffer |
| 日志洪流中 try `cat /dev/ttyUSB0` | 输出完全不可解析 | 用 pyserial + 文件重定向法 |
| `adb push` 到旧 IP 假设同设备 | push 到错误设备 | 串口确认当前 IP 再 connect |
