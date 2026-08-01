#!/usr/bin/env python3
"""
reboot_capture.py — 嵌入式设备循环重启 + 串口日志采集

用法:
    python3 reboot_capture.py [次数] [抓取秒数]
    python3 reboot_capture.py 100 180   # 重启100次, 每次抓180s

流程:
    1. 打开串口
    2. killall 降噪 → login → 验证
    3. 发送 reboot
    4. 读取串口输出 N 秒 → 保存到文件
    5. 验证文件中有 U-Boot/Linux 启动信息
    6. 重复

⚠️ 铁律:
    - 必须先 login 再 reboot，否则 reboot 被 login 提示符静默吞噬
    - 第一次 login 前必须先 killall 降噪
    - 不要在 terminal(background=true) 脚本中用 fuser -k
    - 日志保存到 /tmp/reboot_logs/iter_XXX.log
"""
import serial, time, subprocess, os, sys, re

PORT = "/dev/ttyUSB0"
BAUD = 115200
ITERATIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
CAPTURE_SEC = int(sys.argv[2]) if len(sys.argv) > 2 else 180
LOG_DIR = "/tmp/reboot_logs"

os.makedirs(LOG_DIR, exist_ok=True)

def serial_open():
    subprocess.run(["sudo", "stty", "-F", PORT, str(BAUD),
        "cs8", "-cstopb", "-parenb", "raw", "-echo", "-echoe", "-echok"],
        capture_output=True)
    time.sleep(0.3)
    s = serial.Serial(PORT, BAUD, timeout=1)
    time.sleep(0.5)
    s.reset_input_buffer()
    return s

def serial_login(s, max_attempts=15):
    """Login with killall + retry. Returns True on success."""
    # First: kill log flood — critical for reliable login
    s.write(b"killall -9 apphilogcat 2>/dev/null\r")
    time.sleep(0.5)
    s.read(s.in_waiting)
    s.write(b"killall -9 miio_client c_mi_ipc 2>/dev/null\r")
    time.sleep(0.5)
    s.read(s.in_waiting)

    for attempt in range(max_attempts):
        s.write(b"\r")
        time.sleep(0.15)
        s.write(b"root\r")
        time.sleep(0.5)
        s.write(b"\r")
        time.sleep(1.5)
        s.read(s.in_waiting)

        # Verify with unique time-stamped marker written to file
        ts = int(time.time() * 1000) % 100000
        s.write(f"echo OK_{ts} > /tmp/_ok 2>/dev/null && cat /tmp/_ok\r".encode())
        time.sleep(1.5)
        buf = bytearray()
        deadline = time.time() + 3
        while time.time() < deadline:
            if s.in_waiting:
                buf.extend(s.read(s.in_waiting))
            else:
                time.sleep(0.05)

        if f"OK_{ts}".encode() in buf:
            return True

        # Kill logs again mid-retry
        if attempt in (5, 10):
            s.write(b"killall -9 apphilogcat 2>/dev/null\r")
            time.sleep(0.3)
            s.read(s.in_waiting)
        if attempt == 12:
            time.sleep(3)

    return False

def verify_reboot_in_log(filepath):
    """Check if the log file contains U-Boot or Linux boot messages."""
    with open(filepath, 'rb') as f:
        head = f.read(50000)  # check first 50KB
    text = head.decode('utf-8', errors='replace')
    has_uboot = 'U-Boot' in text
    has_linux = 'Linux version' in text
    return has_uboot, has_linux

def run_iteration(tag):
    """Login → reboot → capture → verify. Returns True if reboot verified."""
    fpath = f"{LOG_DIR}/{tag}.log"

    s = serial_open()
    if not serial_login(s):
        print(f"  [{tag}] ❌ login failed")
        s.close()
        return False

    s.write(b"reboot\r")
    
    # Capture serial output (U-Boot → kernel → runtime)
    buf = bytearray()
    deadline = time.time() + CAPTURE_SEC
    last_flush = time.time()
    
    while time.time() < deadline:
        try:
            if s.in_waiting:
                buf.extend(s.read(s.in_waiting))
            else:
                time.sleep(0.05)
            if time.time() - last_flush >= 10:
                with open(fpath, 'ab') as f:
                    f.write(buf)
                buf.clear()
                last_flush = time.time()
        except:
            break
    
    if buf:
        with open(fpath, 'ab') as f:
            f.write(buf)
    s.close()

    # Verify reboot happened
    has_uboot, has_linux = verify_reboot_in_log(fpath)
    size = os.path.getsize(fpath) // 1024
    status = "✅" if (has_uboot or has_linux) else "⚠️"
    print(f"  [{tag}] {size}KB {status} U-Boot={int(has_uboot)} Linux={int(has_linux)}")
    return has_uboot or has_linux

def main():
    print(f"=== 循环重启日志采集 ({ITERATIONS}次, 每次{CAPTURE_SEC}s) ===")
    print(f"日志目录: {LOG_DIR}")
    sys.stdout.flush()

    ok = 0
    fail = 0

    for i in range(1, ITERATIONS + 1):
        tag = f"iter_{i:03d}"
        print(f"[{i:3d}/{ITERATIONS}] rebooting...", end=" ")
        sys.stdout.flush()

        if run_iteration(tag):
            ok += 1
        else:
            fail += 1

    print(f"\n完成: ok={ok} fail={fail} 日志: {LOG_DIR}")

if __name__ == "__main__":
    main()
