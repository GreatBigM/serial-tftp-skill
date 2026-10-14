# Working Python Patterns (Verified on <项目A> Busybox Serial)

## Login + Drain Helper

```python
def drain(ser, t=2.0):
    buf = bytearray()
    dl = time.time() + t
    while time.time() < dl:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
            dl = time.time() + t
        else:
            time.sleep(0.02)
    return buf.decode(errors='replace')

def login(ser):
    # 30 rounds blind burst
    for i in range(30):
        ser.write(b"root\r")
        time.sleep(0.03)
        ser.write(b"\r")
        time.sleep(0.03)
    time.sleep(1.0)
    ser.reset_input_buffer()
    ts = str(int(time.time()))
    ser.write(f"echo L_{ts}\r".encode())
    time.sleep(2.5)
    resp = drain(ser, 3.0)
    return f"L_{ts}" in resp
```

## 精确时序登录（日志洪流环境，2026-08-04 实战）

**盲打 30 次在日志洪流下不可靠**——getty 收到错位的 root/空行组合会报 `Login incorrect`，且之前输入残留会污染后续命令（`ifconfig` 被吞进 login 提示符）。正确做法：**等提示符 → 单步发 → 等回显 → 再发**。

```python
def read_until(ser, patterns, timeout=8):
    buf = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = ser.read(4096)
        if data:
            buf += data
            for p in patterns:
                if p in buf:
                    return buf
    return buf

def login_precise(ser):
    """精确时序登录。<项目A>/<项目E>: root + 空密码（不是 root/root！）"""
    # 1. 等 login 提示符
    ser.reset_input_buffer()
    time.sleep(1)
    buf = read_until(ser, [b'login:'], timeout=10)
    if b'login:' not in buf:
        return False
    # 2. 发用户名
    ser.write(b'root\r')
    time.sleep(1.5)
    buf = read_until(ser, [b'Password', b'incorrect', b'login:'], timeout=5)
    # 3. 发空密码（关键：密码是空，不是 root）
    ser.write(b'\r')
    time.sleep(1.5)
    buf = read_until(ser, [b'root@70mai', b'incorrect', b'login:', b'#'], timeout=6)
    return b'root@70mai' in buf or buf.rstrip().endswith(b'$') or b'#' in buf

# 日志洪流降噪（login 被刷屏淹没时先杀日志进程）:
# ser.write(b'killall -9 apphilogcat c_mi_ipc miio_client 2>/dev/null\r')
```

**要点**：
- **密码是空密码**，不是 root/root——第二次 `root\r` 会被当 shell 命令执行（`-sh: root: not found`）或导致 `Login incorrect`
- 每个发送之间必须有足够 sleep + read_until 等待回显，命令不能连发（getty 缓冲错位）
- 登录失败会回 `70mai login:` 提示符，可重试（先等提示符再发）
- 日志洪流（MikeInit 每 ~300ms 刷屏）严重干扰登录：先 `killall -9 apphilogcat c_mi_ipc miio_client` 降噪
- 完整可运行脚本：`/tmp/serial_login_ip.py`（会话中验证通过，登录+查 IP 一体）

## Script Write + Run + Cat (Reliable Pattern)

```python
def wsh(ser, name, body):
    """Write a script file on device via echo."""
    safe = body.replace("'", "'\\''")
    ser.write(f"echo '{safe}' > {name}\r".encode())
    time.sleep(0.5)
    drain(ser, 0.5)
    ser.write(f"chmod +x {name}\r".encode())
    time.sleep(0.3)
    drain(ser, 0.3)

def rsh(ser, name, wait=3.0):
    """Run script → cat output file. Returns output text."""
    ser.reset_input_buffer()
    ser.write(f"sh {name} > /tmp/_r 2>&1\r".encode())
    time.sleep(wait)
    drain(ser, wait * 0.3)
    ser.reset_input_buffer()
    ser.write(b"cat /tmp/_r\r")
    time.sleep(wait * 0.5)
    return drain(ser, wait)

# Usage:
body = "echo PATH; echo $PATH; echo WPA; ls /usr/bin/wpa* 2>&1"
wsh(ser, "/tmp/disc", body)
result = rsh(ser, "/tmp/disc", 4.0)
```

## Finding Binaries (No which/command -v)

```python
body = ("echo PWPA; ls /usr/bin/wpa* /usr/sbin/wpa* /bin/wpa* /sbin/wpa* 2>&1; "
        "echo PIPERF; ls /usr/bin/iperf* /usr/sbin/iperf* /tmp/i3 2>&1; "
        "echo PPATH; echo $PATH")
wsh(ser, "/tmp/find", body)
r = rsh(ser, "/tmp/find", 4.0)
# Parse: look for lines between echo markers
```

## Running iperf3 in Background

```python
tx_body = f"/usr/sbin/iperf3 -c {SERVER} -t 10 -P 5 > /tmp/tx.log 2>&1"
wsh(ser, "/tmp/rtx", tx_body)
ser.write(b"sh /tmp/rtx &\r".encode())
time.sleep(1.0)

# Wait 12s (test duration + margin)
for i in range(12):
    time.sleep(1)

# Read result
ser.write(b"cat /tmp/tx.log\r".encode())
time.sleep(1.0)
result = drain(ser, 2.0)
```

## stty Reset (Before Any Serial Open)

```python
import subprocess
subprocess.run(['stty', '-F', '/dev/ttyUSB0', '921600',
    'cs8', '-cstopb', '-parenb', 'raw', '-echo', '-echoe', '-echok'],
    capture_output=True)
time.sleep(0.3)
```

## <项目A> Serial Parameters

| Parameter | Value |
|-----------|-------|
| Port | `/dev/ttyUSB0` |
| Baud | 921600 |
| Line terminator | `\r` (CR only, NOT `\n`) |
| Shell | busybox ash |
| Default shell prompt | `[root@70mai:]$ ` |
| IP cmd | `ifconfig` (busybox applet, not `ip`) |
| PATH | `/system/bin:/bin:/sbin:/usr/bin:/usr/sbin` |
| wpa_supplicant | `/usr/bin/wpa_supplicant` |
| wpa_cli | `/usr/bin/wpa_cli` |
| udhcpc | `/sbin/udhcpc` |
| iperf3 | Not built-in, must cross-compile |
| Log spammers | `apphilogcat`, `c_mi_ipc`, `mike_app`, `mike` |
