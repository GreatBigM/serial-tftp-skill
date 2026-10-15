#!/usr/bin/env python3
"""串口精确时序登录 + 查 IP（<项目A>/<项目E> 日志洪流环境，2026-08-04 实战验证）

用法:
    python3 serial_login_ip.py [port] [baud]
    默认 /dev/ttyUSB0 921600

关键点:
    - 密码是空密码（root + 空，不是 root/root）
    - 等 `login` 提示 → 发 root → 等 `Password` 提示 → 发空 → 查 IP
    - 日志洪流（MikeInit 刷屏）下先降噪: killall -9 apphilogcat c_mi_ipc miio_client
"""
import serial, time, re, sys

port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 921600

ser = serial.Serial(port, baud, timeout=0.3)

def read_until(patterns, timeout=8):
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

# 1. 清缓冲
ser.reset_input_buffer()
time.sleep(1)

# 2. 等 login 提示符
print("等待 login 提示符...")
buf = read_until([b'login:'], timeout=10)
if b'login:' not in buf:
    print("  无 login 提示符（设备可能已登录或未就绪）")

# 3. 发用户名 root
ser.write(b'root\r')
time.sleep(1.5)
buf = read_until([b'Password', b'incorrect', b'login:'], timeout=5)
print(f"  用户名后: {buf[-60:]!r}")

# 4. 发空密码（不是 root！）
ser.write(b'\r')
time.sleep(1.5)
buf = read_until([b'root@', b'incorrect', b'login:', b'#'], timeout=6)
print(f"  密码后: {buf[-60:]!r}")

# 5. 查 eth0 IP
ser.write(b'ifconfig eth0\r')
time.sleep(1.5)
buf = read_until([b'inet addr'], timeout=5)
ips = re.findall(rb'inet addr:([0-9.]+)', buf)
print(f"  eth0 IP: {ips[0].decode() if ips else '未获取'}")

ser.close()
