# 串口交互经验笔记

> 原 serial-debug 技能的实战经验汇总。按需查阅，非必读。

## 致命陷阱

### 行终止符：用 `\r` 不用 `\n`

`stty raw` 模式下，getty/login 只认 `\r` (CR) 为回车。`\n` (LF) 不识别，输入静默丢失。

```python
# ❌ 错误
ser.write(b'root\n')
# ✅ 正确
ser.write(b'root\r')
```

### 回显 ≠ 执行

串口回显所有输入字符，但未登录时命令不执行。验证：发 `echo MARKER`，检查 marker 出现在非 echo 行。

### 未登录就发 reboot

`reboot` 被 login 当作用户名吃掉 → 先登录验证再发命令。

---

## 登录策略

设备：用户 `root`，密码空（直接回车）。

### 日志洪流下的循环 retry

```python
ser.read(5000)  # drain noise
for attempt in range(10):
    ser.write(b"killall -9 apphilogcat c_mi_ipc 2>/dev/null\r")
    time.sleep(0.3)
    ser.write(b"root\r")
    time.sleep(0.3)
    ser.write(b"\r")
    time.sleep(0.3)
    ts = int(time.time())
    ser.write(f"echo OK_{ts}\r".encode())
    time.sleep(1.5)
    buf = bytearray()
    deadline = time.time() + 3
    while time.time() < deadline:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
        else:
            time.sleep(0.02)
    if f"OK_{ts}".encode() in buf:
        break
```

### 盲打 burst（极端日志洪流）

```python
for i in range(15):
    ser.write(b"root\r")
    time.sleep(0.08)
    ser.write(b"\r")
    time.sleep(0.08)
# 最后验证一次
```

---

## 日志洪流下的命令输出获取

| 优先级 | 方法 | 适用 |
|-------|------|------|
| 1 | 文件重定向 `cmd > /tmp/_f; cat /tmp/_f` | 任何密度 |
| 2 | marker 包裹 `echo START; cmd; echo END` | 中等密度 |
| 3 | 切 ADB | eth0 可用时 |
| 4 | `killall apphilogcat` | 最终手段 |

---

## pyserial 端口参数污染

上一个 session 遗留参数导致 `ser.read()` 返回空。修复：

```bash
sudo stty -F /dev/ttyUSB0 <baud> cs8 -cstopb -parenb raw -echo -echoe -echok
```

然后重新 `serial.Serial()`。

---

## 后台串口捕获

picocom/screen 在 background 模式静默退出。用 Python 脚本：

```python
python3 -c "
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.3)
with open('/tmp/serial.log', 'a') as f:
    while True:
        if ser.in_waiting:
            f.write(ser.read(ser.in_waiting).decode(errors='replace'))
            f.flush()
        time.sleep(0.1)
" &
```

启动后 5s 内验证文件增长：`wc -l /tmp/serial.log`。

---

## 故障诊断决策树

```
串口不通？
├─ 无输出
│  ├─ 设备断电？→ 查电源
│  ├─ 波特率不对？→ 探测 [921600, 115200, 1500000, 57600, 9600]
│  ├─ 串口线松动？→ 重插
│  └─ pyserial 读不到？→ stty 重置
├─ 有输出但命令不执行
│  ├─ 未登录？→ 盲打 burst
│  └─ login 挂死？→ 物理断电
├─ 日志洪流
│  ├─ 文件重定向法
│  └─ 切 ADB
└─ 长命令截断（>80字符）
   └─ 写脚本文件执行
```

---

## 常用 U-Boot 命令

| 命令 | 用途 |
|------|------|
| `sf probe` | 探测 SPI NOR Flash |
| `sf read <addr> <offset> <len>` | 读 NOR |
| `bootm <addr>` | 启动内核 |
| `setenv <var> <value>` | 设环境变量（重启丢失） |
| `reset` | 软复位 |
| `ping <ip>` | 网络连通测试 |
| `mai_tftp` | 自动初始化以太网 + 下载执行 auto_update_tftp.txt |
| `tftpboot <addr> <file>` | TFTP 下载 |
| `printenv` | 查看所有环境变量 |

---

## 设备状态检测代码

```python
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=2)
ser.reset_input_buffer()
for _ in range(3):
    ser.write(b'\r\n')
    time.sleep(0.3)
    ser.read(ser.in_waiting)
ser.write(b'\r\n')
time.sleep(1)
out = ser.read(500).decode(errors='replace').lower()
if any(p in out for p in ['<项目>#', '=>']):
    print("U-Boot")
elif any(p in out for p in ['login:', 'root@', '# ']):
    print("Linux")
else:
    print("Unknown")
```

---

## 注意事项速查

| 项目 | 说明 |
|------|------|
| 超时 | busybox 命令 1-2s，复杂命令 3-5s |
| 权限 | `sudo chmod 666 /dev/ttyUSB0` |
| 持久 shell | 串口 shell 后台进程不随退出被杀 |
| stdout 缓冲 | 重定向后 printf 不即时写入，用 stderr |
| 前台超时 ≠ 失败 | 串口命令可能已执行，监控确认 |
| 0 字节输出 | fuser -k → stty → 手动回车 → 物理断电 |
