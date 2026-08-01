#!/usr/bin/env python3
"""自动打断 U-Boot autoboot + TFTP 刷机 — 三步流程 + 串口预检.

Step 0: 串口端口预检 — 清残留进程 + 重置参数 + 验证连通
Step 1: 判断环境 → 若在 Linux 则登录 → reboot → 持续砸回车打断进 U-Boot
Step 2: U-Boot 中设网络 → mai_tftp 烧录 → 自动重启
Step 3: 等待 20s → 确认 login 提示符出现 → 完成

Usage:
    python3 auto-uboot-interrupt.py flash
    python3 auto-uboot-interrupt.py flash --serverip <HOST_IP>6
    python3 auto-uboot-interrupt.py flash --at-uboot
    python3 auto-uboot-interrupt.py shell
"""

import serial, time, sys, argparse, os, subprocess

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
DEFAULT_IPADDR = "<DEV_IP>"
DEFAULT_NETMASK = "255.255.254.0"
DEFAULT_GATEWAY = "<HOST_IP>"
DEFAULT_SERVERIP = "<HOST_IP>6"


def find_serial():
    """自动发现串口端口"""
    for path in ("/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyAMA0"):
        if os.path.exists(path):
            return path
    return None


# ── Step 0: 串口预检 ──────────────────────────────────────────────


def serial_port_init(port, baud):
    """串口预检：端口存在性 → 自动发现 → 权限 → fuser -k 清残留 → stty 重置参数

    避免以下已知问题：
    - pyserial 参数污染导致 read() 始终返回空（输出 0 bytes 不断超时）
    - 上一个 session 的 pyserial 进程残留占用端口
    - 权限不足导致 Serial() open 失败
    """
    # 端口自动发现
    if not port or not os.path.exists(port):
        alt = find_serial()
        if alt:
            print(f"[*] Serial port not found, auto-detected {alt}")
            port = alt
        else:
            print("[-] No serial port found. Check connections.")
            sys.exit(1)

    # 端口权限
    if not os.access(port, os.R_OK | os.W_OK):
        print(f"[*] Fixing permissions on {port}...")
        subprocess.run(["sudo", "chmod", "666", port],
                       capture_output=True, timeout=10)

    # fuser -k: 清残留进程
    try:
        result = subprocess.run(["fuser", port], capture_output=True,
                                text=True, timeout=10)
        if result.returncode == 0:
            print(f"[*] Killing residual processes on {port}...")
            subprocess.run(["fuser", "-k", port], capture_output=True, timeout=10)
            time.sleep(0.5)
    except FileNotFoundError:
        # fuser 不存在（如 Docker 内），静默跳过
        pass

    # stty: 重置串口参数（解决 pyserial 参数污染）
    stty_cmd = [
        "stty", "-F", port, str(baud),
        "cs8", "-cstopb", "-parenb", "raw",
        "-echo", "-echoe", "-echok"
    ]
    try:
        proc = subprocess.run(stty_cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            # retry with sudo
            proc = subprocess.run(["sudo"] + stty_cmd, capture_output=True,
                                  text=True, timeout=10)
    except FileNotFoundError:
        # stty 不存在时静默跳过
        pass

    time.sleep(0.3)

    # 验证：发 \r 检查回显
    try:
        ser = serial.Serial(port, baud, timeout=1)
        ser.reset_input_buffer()
        time.sleep(0.3)
        ser.write(b"\r\n")
        time.sleep(0.5)
        echo = ser.read(50)
        ser.close()
        if not echo:
            print("[-] Serial port not responding (no echo on \\r)")
            print("    Try: physical power cycle the device")
            sys.exit(1)
    except serial.SerialException as e:
        print(f"[-] Cannot open serial port {port}: {e}")
        sys.exit(1)

    print(f"[+] Serial port {port} ready ({baud} baud)")
    return port


def drain(ser):
    data = ser.read(ser.in_waiting) if ser.in_waiting else b""
    time.sleep(0.2)
    data += ser.read(ser.in_waiting) if ser.in_waiting else b""
    return data


# ── Step 1: 判断环境 + 登录 + 打断进 U-Boot ──────────────────────────


def detect_mode(ser):
    for _ in range(3):
        drain(ser)
        ser.write(b"\r\n")
        time.sleep(0.4)
    drain(ser)
    ser.write(b"\r\n")
    time.sleep(1)
    out = drain(ser).decode(errors="replace").lower()
    # U-Boot 提示符匹配列表：prj009# 为当前平台默认，<项目># 按设备实际提示符增补
    if any(p in out for p in ["prj009#", "<项目>#", "=>"]):
        return "uboot"
    elif any(p in out for p in ["login:", "root@", "# "]):
        return "linux"
    print(f"[debug] detect_mode received: {out[:200]!r}")
    return "unknown"


def login(ser):
    drain(ser)
    time.sleep(0.3)
    drain(ser)
    ser.write(b"root\r")
    time.sleep(1.5)
    drain(ser)
    ser.write(b"\r")
    time.sleep(1)
    drain(ser)
    marker = f"LOGIN_{int(time.time())}"
    ser.write(f"echo {marker}\r".encode())
    time.sleep(1.5)
    out = drain(ser).decode(errors="replace")
    if marker in out:
        print("[+] Login verified")
        return True
    # retry: kill log flood first
    ser.write(b"killall -9 apphilogcat c_mi_ipc 2>/dev/null\r")
    time.sleep(1)
    drain(ser)
    ser.write(b"root\r")
    time.sleep(1.5)
    drain(ser)
    ser.write(b"\r")
    time.sleep(1)
    drain(ser)
    marker2 = f"LOGIN2_{int(time.time())}"
    ser.write(f"echo {marker2}\r".encode())
    time.sleep(1.5)
    out = drain(ser).decode(errors="replace")
    if marker2 in out:
        print("[+] Login verified on retry")
        return True
    return False


def interrupt_uboot(ser, timeout=20):
    """Step 1: reboot + 砸回车打断 autoboot 进 U-Boot, 边砸边读即时检测提示符。

    旧版缺陷 1: 砸 12s 回车(write-only)再 drain 一次性读——<项目> 实测 reboot 到
    U-Boot 起来要 ~13-15s, 且 write-only 期间 OS 串口缓冲可能溢出丢掉 PRJ009#
    提示符, 导致 drain 没抓到而误报 "Failed to interrupt" (设备实已进 U-Boot)。
    旧版缺陷 2 (首轮修复引入): 用 "u-boot" 做 marker, 它在启动 banner (U-Boot
    2013.07...) 出现时就命中, 但提示符尚未就绪, set_network 的 setenv 发早,
    ipaddr/netmask 未生效, TFTP 用旧 IP 失败。
    修复: 边砸边读 (read 夹在 write 间) 避免缓冲溢出丢提示符; timeout 延到 20s
    覆盖 reboot 时长; marker 只认交互提示符 (prj009#/<项目>#/=>),
    不认 "u-boot" banner; 命中后再发 \r 确认提示符就绪才返回。
    """
    print("[*] Sending reboot...")
    ser.write(b"reboot\r")
    # 只认交互提示符 (含 # 或 =>), 不认 "u-boot" banner — banner 出现时
    # 提示符尚未就绪, setenv 会发早丢失 (<项目> 实测 ipaddr/netmask 未生效)
    MARKERS = ["prj009#", "<项目>#", "=>"]
    end = time.time() + timeout
    buf = ""
    while time.time() < end:
        ser.write(b"\r\n")
        time.sleep(0.05)
        # 边砸边读, 避免缓冲溢出丢提示符
        if ser.in_waiting:
            buf += ser.read(ser.in_waiting).decode(errors="replace")
        low = buf.lower()
        if any(m in low for m in MARKERS):
            # 命中后发 \r 确认提示符已就绪 (避免匹配到 banner 期的残留 #)
            time.sleep(0.4)
            ser.write(b"\r")
            time.sleep(0.4)
            confirm = drain(ser).decode(errors="replace")
            if any(m in confirm.lower() for m in MARKERS):
                print("[+] U-Boot interrupted successfully!")
                return True
    # 末尾再 drain 一次兜底 (U-Boot 刚起来时)
    time.sleep(0.5)
    buf += drain(ser).decode(errors="replace")
    if any(m in buf.lower() for m in MARKERS):
        print("[+] U-Boot interrupted successfully! (late drain)")
        return True
    print("[-] Failed to interrupt U-Boot (last 200 chars: %r)" % buf[-200:])
    return False


# ── Step 2: U-Boot 中设网络 + TFTP 烧录 ─────────────────────────


def set_network(ser, ipaddr, netmask, gateway, serverip):
    # 先 settle: 发 \r + drain 确保在干净的 U-Boot 提示符, 防 interrupt 刚返回
    # 提示符未就绪导致 setenv (尤其 ipaddr/netmask) 发早丢失 (<项目> 实测)
    ser.write(b"\r")
    time.sleep(0.4)
    drain(ser)
    cmds = [
        f"setenv ipaddr {ipaddr}\r",
        f"setenv netmask {netmask}\r",
        f"setenv gatewayip {gateway}\r",
        f"setenv serverip {serverip}\r",
    ]
    for cmd in cmds:
        ser.write(cmd.encode())
        time.sleep(0.3)
    time.sleep(0.5)
    out = drain(ser).decode(errors="replace")
    if "#" not in out:
        print("[-] Network settings may have failed")
        return False
    print("[+] Network configured")
    return True


def run_mai_tftp(ser, timeout=150):
    print(f"[*] Starting mai_tftp flash (max {timeout}s)...")
    ser.write(b"mai_tftp\r")
    start = time.time()
    last_text = ""
    while time.time() - start < timeout:
        try:
            data = ser.read(4096)
            if data:
                text = data.decode(errors="replace")
                sys.stdout.write(text)
                sys.stdout.flush()
                last_text += text
                # 设备已 reset 进内核启动 = 烧录完成，提前结束，不傻等满 timeout
                if "Linux version" in last_text or "Uncompressing lzma Kernel Image" in last_text:
                    print("\n[+] Kernel booting — flash done, leaving mai_tftp monitor early")
                    break
            else:
                time.sleep(0.5)
        except:
            break
    ok = "reset" in last_text.lower() or "Written" in last_text
    print("\n[+] Flash monitoring ended")
    return ok


# ── Step 3: 等待 20s 确认烧录完成 ────────────────────────────────


def verify_boot(ser, timeout=25):
    """等 app 活信号 (cpu_loading=/seq:) 判成功；Kernel panic 判失败。

    用 cpu_loading=/seq: 而非 login:，因 c_mi_ipc 启动后立即刷屏会淹没 login 提示符
    导致误报失败（实测 <项目>）。app 活信号出现即返回，不跑满 timeout。
    """
    print("[*] Verifying flash...")
    start = time.time()
    while time.time() - start < timeout:
        data = ser.read(2048)
        if data:
            text = data.decode(errors="replace")
            if "Kernel panic" in text or "Unable to mount root" in text:
                print("\n[-] Kernel panic detected! Flash failed.")
                return False
            # app 已活 = 烧录成功 (IPCMain 周期输出 cpu_loading=，video stream 输出 seq:)
            if "cpu_loading=" in text or "seq: " in text:
                print("\n[+] App alive (cpu_loading=/seq:) — flash OK")
                return True
            # 兜底：login/shell 提示符 (未被刷屏淹没时)
            if "设备厂商 login:" in text or "login:" in text or "root@" in text or "# " in text:
                print("\n[+] Login/shell prompt detected — flash OK")
                return True
        else:
            time.sleep(0.5)
    print("\n[-] No app-alive signal within timeout (可能仍启动中, 串口看 seq 递增即成功)")
    return False


# ── 交互 U-Boot shell ────────────────────────────────────────


def shell_mode(ser):
    interrupt_uboot(ser)
    print("[*] Interactive U-Boot shell. Press Ctrl+C to exit.")
    try:
        while True:
            data = ser.read(1024)
            if data:
                sys.stdout.write(data.decode(errors="replace"))
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n[*] Exiting.")


def main():
    parser = argparse.ArgumentParser(description="Auto U-Boot interrupt + TFTP flash")
    parser.add_argument("mode", choices=["flash", "shell"])
    parser.add_argument("--port", default=None,
                        help="Serial port (default: auto-detect)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--ipaddr", default=DEFAULT_IPADDR)
    parser.add_argument("--netmask", default=DEFAULT_NETMASK)
    parser.add_argument("--gateway", default=DEFAULT_GATEWAY)
    parser.add_argument("--serverip", default=DEFAULT_SERVERIP)
    parser.add_argument("--at-uboot", action="store_true",
                        help="Device already in U-Boot, skip login+reboot")
    parser.add_argument("--no-precheck", action="store_true",
                        help="Skip serial port precheck (fuser/stty)")
    args = parser.parse_args()

    # ── Step 0: 串口预检 ──
    if args.no_precheck:
        if args.port and os.path.exists(args.port):
            port = args.port
        else:
            port = args.port or find_serial() or DEFAULT_PORT
    else:
        port = serial_port_init(args.port, args.baud)

    ser = serial.Serial(port, args.baud, timeout=0.5)
    ser.reset_input_buffer()
    time.sleep(0.5)
    drain(ser)

    if args.mode == "flash":
        # ── Step 1 ──
        if args.at_uboot:
            print("[*] Already in U-Boot (--at-uboot), skip Step 1")
        else:
            mode = detect_mode(ser)
            print(f"[*] Device mode: {mode}")
            if mode == "uboot":
                print("[*] Already in U-Boot, skip login+reboot")
            elif mode == "linux":
                if not login(ser):
                    print("[-] Step 1: Login failed")
                    ser.close()
                    sys.exit(1)
                if not interrupt_uboot(ser):
                    print("[-] Step 1: U-Boot interrupt failed")
                    ser.close()
                    sys.exit(1)
            else:
                print("[-] Device mode unknown. Try --at-uboot if device is at U-Boot prompt.")
                ser.close()
                sys.exit(1)

        # ── Step 2 ──
        set_network(ser, args.ipaddr, args.netmask, args.gateway, args.serverip)
        flash_ok = run_mai_tftp(ser)
        if not flash_ok:
            print("[-] Step 2: Flash may have failed")
            ser.close()
            sys.exit(1)

        # ── Step 3 ──
        if not verify_boot(ser):
            print("[-] Step 3: Boot verification failed")
            ser.close()
            sys.exit(1)

    elif args.mode == "shell":
        shell_mode(ser)

    ser.close()
    if args.mode == "flash":
        print("\n" + "=" * 50)
        print("  烧录完成")
        print("=" * 50)
        print("  设备已启动，用串口查 IP 后 adb connect")
        print("=" * 50)


if __name__ == "__main__":
    main()
