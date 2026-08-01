#!/usr/bin/env python3
"""
串口全启动日志采集 — 两种模式：

模式 1（默认）: 登录运行中的设备 → reboot → 捕获完整启动日志
  python3 capture_boot_log.py              # 默认 115200, 75s
  python3 capture_boot_log.py 115200 90    # 自定义波特率和时长

模式 2（poweron）: 设备已关机，用户手动上电 → 纯监听捕获
  python3 capture_boot_log.py --poweron              # 默认 115200, 180s
  python3 capture_boot_log.py --poweron 115200 300   # 自定义波特率和时长

输出: /tmp/boot_capture_<timestamp>.log

⚠️ 关键改进（vs 旧版）:
  - stty_reset() 防 pyserial 参数污染
  - 用 \\r (CR) 而非 \\r\\n — stty raw 模式下只认 CR
  - killall 降噪后再登录
  - 时间戳唯一标记验证登录成功
  - login retry 循环（~10 次）
  - 全部 try/except 包裹
"""
import serial, time, sys, os, subprocess
from datetime import datetime

# ── 默认参数 ──
DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200

# ── 工具函数 ──

def stty_reset(port, baud):
    """重置串口参数，防 pyserial 参数污染"""
    try:
        subprocess.run(["sudo", "stty", "-F", port, str(baud),
            "cs8", "-cstopb", "-parenb", "raw", "-echo", "-echoe", "-echok"],
            capture_output=True, timeout=10)
    except FileNotFoundError:
        pass
    time.sleep(0.3)


def drain(ser):
    """清空串口缓冲区"""
    data = b""
    if ser.in_waiting:
        data = ser.read(ser.in_waiting)
    time.sleep(0.2)
    if ser.in_waiting:
        data += ser.read(ser.in_waiting)
    return data


def collect_loop(ser, duration, all_data, callback=None):
    """
    采集循环：持续读串口直到 duration 秒
    callback(data, elapsed) — 可选，每块数据到达时调用
    """
    start = time.time()
    last_report = 0
    while time.time() - start < duration:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting)
            all_data.extend(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.flush()
            if callback:
                callback(chunk, time.time() - start)
        else:
            time.sleep(0.05)
        # 每 30s 报告进度
        elapsed = time.time() - start
        if elapsed - last_report >= 30:
            last_report = elapsed
            print(f"\n  [{int(elapsed)}s] {len(all_data)/1024:.0f}KB", flush=True)


def login_retry(ser, max_attempts=10):
    """登录设备，带 killall 降噪 + 时间戳验证。返回 True/False"""
    # 先尝试一次快速登录
    for attempt in range(max_attempts):
        drain(ser)
        # kill log flood
        ser.write(b"killall -9 apphilogcat c_mi_ipc miio_client 2>/dev/null\r")
        time.sleep(0.3)
        drain(ser)
        # send username + password
        ser.write(b"root\r")
        time.sleep(0.5)
        ser.write(b"\r")
        time.sleep(1)
        # verify with timestamped marker
        ts = int(time.time() * 1000)
        ser.write(f"echo OK_{ts} > /tmp/_ok && cat /tmp/_ok\r".encode())
        time.sleep(1.5)
        buf = bytearray()
        deadline = time.time() + 3
        while time.time() < deadline:
            if ser.in_waiting:
                buf.extend(ser.read(ser.in_waiting))
            else:
                time.sleep(0.05)
        if f"OK_{ts}".encode() in buf:
            print(f"[+] Login verified (attempt {attempt + 1})", flush=True)
            return True
    return False


# ── Main ──

def main():
    # Parse args
    POWERON = '--poweron' in sys.argv
    SHOW_DEVICE = '--show-device' in sys.argv  # 显示设备模式信息后继续
    args = [a for a in sys.argv[1:] if a not in ('--poweron', '--show-device')]

    BAUD = int(args[0]) if len(args) > 0 else DEFAULT_BAUD
    DURATION = int(args[1]) if len(args) > 1 else (180 if POWERON else 75)
    PORT = DEFAULT_PORT

    # ── 串口初始化 ──
    stty_reset(PORT, BAUD)

    all_data = bytearray()
    output_path = f'/tmp/boot_capture_{datetime.now().strftime("%H%M%S")}.log'

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5)
        ser.reset_input_buffer()
        time.sleep(0.5)
        drain(ser)
    except serial.SerialException as e:
        print(f"[-] Cannot open {PORT}: {e}", flush=True)
        sys.exit(1)

    print(f"=== Boot capture: {datetime.now().isoformat()} ===", flush=True)
    print(f"Serial: {PORT} @ {BAUD} baud, duration: {DURATION}s", flush=True)
    print(f"Output: {output_path}", flush=True)

    if POWERON:
        # ════ 模式 2: 纯监听，设备已关机 ════
        print("\n--- Waiting for device power-on data ---", flush=True)
        collect_loop(ser, DURATION, all_data)

    else:
        # ════ 模式 1（默认）: 登录 → reboot → 捕获 ════
        print("\n--- Logging into device ---", flush=True)
        if not login_retry(ser):
            print("[-] Login failed after retries", flush=True)
            ser.close()
            sys.exit(1)

        print("\n--- REBOOT ---", flush=True)
        ser.reset_input_buffer()
        # 注意：用 \r 不是 \n（stty raw 下只认 CR 为回车）
        ser.write(b"reboot\r")
        ser.flush()
        time.sleep(0.5)

        # 开始采集（设备重启后 U-Boot → kernel → init 全周期）
        print(f"\n--- Capturing boot log ({DURATION}s) ---", flush=True)
        collect_loop(ser, DURATION, all_data)

    ser.close()

    # ── 保存 ──
    with open(output_path, 'wb') as f:
        f.write(all_data)
    print(f"\n=== Saved: {output_path} ({len(all_data)/1024:.0f}KB) ===", flush=True)


if __name__ == "__main__":
    main()
