#!/usr/bin/env python3
"""自动 TFTP 刷机 — 完整五步流程 + 环境预检 + 失败恢复指引。

Flow:
  Step 0: 环境预检 — TFTP 服务/目录/固件 + 串口 + IP 设定
  Step 1: 建立串口连接 — 波特率缓存/探测 + 端口预检
  Step 2: 模式判断 — uboot→直接烧 / linux→reboot卡boot / unknown→提示断电
  Step 3: 配网 + 烧录 — setenv + ping 验证 + mai_tftp
  Step 4: 等待重启 — 确认 app 活信号 / login 提示符

Usage:
    python3 auto-uboot-interrupt.py flash --ipaddr <DEV_IP> --serverip <HOST_IP> --tftp-dir <DIR>
    python3 auto-uboot-interrupt.py flash                    # 使用缓存配置
    python3 auto-uboot-interrupt.py flash --at-uboot         # 设备已在 U-Boot
    python3 auto-uboot-interrupt.py flash --baud 921600      # 指定波特率
    python3 auto-uboot-interrupt.py flash --baud detect      # 强制重新探测
    python3 auto-uboot-interrupt.py shell                    # 仅进入 U-Boot shell
    python3 auto-uboot-interrupt.py config show              # 查看缓存配置
    python3 auto-uboot-interrupt.py config baud 921600       # 设定波特率
    python3 auto-uboot-interrupt.py config tftp-dir <DIR>    # 设定 TFTP 目录
    python3 auto-uboot-interrupt.py config ipaddr <IP>       # 设定设备 IP
    python3 auto-uboot-interrupt.py config reset             # 清除全部缓存
"""

try:
    import serial  # pyserial
except ImportError:
    import serial_compat as serial  # 标准库 termios 兼容层（零依赖）
import time, sys, argparse, os, subprocess
from flash_config import (
    resolve_baud, handle_config_subcommand, preflight, wizard,
    get, set, load_config, CONFIG_FILE
)

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = "auto"


def find_serial():
    """自动发现串口端口。"""
    for path in ("/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyAMA0"):
        if os.path.exists(path):
            return path
    return None


# ─── Step 1: 串口连接 ────────────────────────────────────────────────


def serial_port_init(port, baud):
    """串口预检：端口存在 → 权限 → fuser -k 清残留 → stty 重置 → 验证回显。"""
    if not port or not os.path.exists(port):
        alt = find_serial()
        if alt:
            print(f"[*] Serial port auto-detected: {alt}")
            port = alt
        else:
            print("[-] No serial port found.")
            print("    修复: 检查 USB 串口线连接，ls /dev/ttyUSB*")
            sys.exit(1)

    # 权限
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
        pass

    # stty: 重置串口参数
    stty_cmd = ["stty", "-F", port, str(baud),
                "cs8", "-cstopb", "-parenb", "raw",
                "-echo", "-echoe", "-echok"]
    try:
        proc = subprocess.run(stty_cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            subprocess.run(["sudo"] + stty_cmd, capture_output=True,
                           text=True, timeout=10)
    except FileNotFoundError:
        pass

    time.sleep(0.3)

    # 验证回显
    try:
        ser = serial.Serial(port, baud, timeout=1)
        ser.reset_input_buffer()
        time.sleep(0.3)
        ser.write(b"\r\n")
        time.sleep(0.5)
        echo = ser.read(50)
        ser.close()
        if not echo:
            print("[-] Serial port not responding (no echo)")
            print("    修复: 物理断电重启设备，检查串口线 TX/RX")
            sys.exit(1)
    except serial.SerialException as e:
        print(f"[-] Cannot open {port}: {e}")
        sys.exit(1)

    print(f"[+] Serial port ready: {port} @ {baud} baud")
    return port


def drain(ser):
    data = ser.read(ser.in_waiting) if ser.in_waiting else b""
    time.sleep(0.2)
    data += ser.read(ser.in_waiting) if ser.in_waiting else b""
    return data


# ─── Step 2: 模式判断 ────────────────────────────────────────────────


def detect_mode(ser):
    """发回车判断设备当前模式: uboot / linux / unknown。"""
    for _ in range(3):
        drain(ser)
        ser.write(b"\r\n")
        time.sleep(0.4)
    drain(ser)
    ser.write(b"\r\n")
    time.sleep(1)
    out = drain(ser).decode(errors="replace").lower()

    if any(p in out for p in ["<项目>#", "=>"]):
        return "uboot"
    elif any(p in out for p in ["login:", "root@", "# "]):
        return "linux"
    print(f"[debug] detect_mode received: {out[:200]!r}")
    return "unknown"


def login(ser):
    """Linux 登录（root 空密码），含降噪重试。"""
    drain(ser)
    time.sleep(0.3)
    drain(ser)
    ser.write(b"root\r")
    time.sleep(1.5)
    drain(ser)
    ser.write(b"\r")  # 空密码
    time.sleep(1)
    drain(ser)
    marker = f"LOGIN_{int(time.time())}"
    ser.write(f"echo {marker}\r".encode())
    time.sleep(1.5)
    out = drain(ser).decode(errors="replace")
    if marker in out:
        print("[+] Login verified")
        return True

    # retry: 降噪
    print("[*] Login retry: killing log flood...")
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
    """reboot + 砸回车打断 autoboot，边砸边读即时检测 U-Boot 提示符。"""
    print("[*] Sending reboot + interrupting U-Boot...")
    ser.write(b"reboot\r")
    MARKERS = ["<项目>#", "=>"]
    end = time.time() + timeout
    buf = ""
    while time.time() < end:
        ser.write(b"\r\n")
        time.sleep(0.05)
        if ser.in_waiting:
            buf += ser.read(ser.in_waiting).decode(errors="replace")
        low = buf.lower()
        if any(m in low for m in MARKERS):
            time.sleep(0.4)
            ser.write(b"\r")
            time.sleep(0.4)
            confirm = drain(ser).decode(errors="replace")
            if any(m in confirm.lower() for m in MARKERS):
                print("[+] U-Boot interrupted successfully!")
                return True
    # 兜底
    time.sleep(0.5)
    buf += drain(ser).decode(errors="replace")
    if any(m in buf.lower() for m in MARKERS):
        print("[+] U-Boot interrupted! (late drain)")
        return True

    print("[-] Failed to interrupt U-Boot")
    print("    恢复方案:")
    print("    1. 串口敲回车看实际状态")
    print("    2. 看到 U-Boot# → 重跑: flash --at-uboot")
    print("    3. 看到 login: → 等启动完重跑 flash")
    print("    4. 无响应 → 物理断电重启")
    return False


# ─── Step 3: 配网 + 烧录 ─────────────────────────────────────────────


def set_network(ser, ipaddr, netmask, gateway, serverip):
    """U-Boot 中设置网络环境变量。"""
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
        print("[-] Network settings may have failed (no U-Boot prompt)")
        return False
    print(f"[+] Network configured: dev={ipaddr} server={serverip}")
    return True


def ping_verify(ser, serverip, retries=2):
    """U-Boot ping 验证网络连通性（可选）。"""
    # 提取纯 IP（去掉可能的后缀）
    ip = serverip.rstrip("0123456789") if serverip[-1].isdigit() and len(serverip) > 15 else serverip
    # 简单取 serverip 本身
    ip = serverip
    print(f"[*] Ping {ip} ...")
    ser.write(f"ping {ip}\r".encode())
    time.sleep(3)
    out = drain(ser).decode(errors="replace")
    if "alive" in out.lower() or "bytes" in out.lower():
        print(f"[+] Ping OK: {ip} reachable")
        return True
    # retry
    for i in range(retries):
        time.sleep(2)
        ser.write(f"ping {ip}\r".encode())
        time.sleep(3)
        out = drain(ser).decode(errors="replace")
        if "alive" in out.lower() or "bytes" in out.lower():
            print(f"[+] Ping OK (retry {i+1})")
            return True
    print(f"[-] Ping failed: {ip} unreachable")
    print("    检查: 网线连接 / IP 网段 / 交换机")
    return False


def run_mai_tftp(ser, timeout=150):
    """执行 mai_tftp 烧录并监控输出。"""
    print(f"[*] Starting mai_tftp (max {timeout}s)...")
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
                if "Linux version" in last_text or "Uncompressing lzma Kernel Image" in last_text:
                    print("\n[+] Kernel booting — flash done")
                    break
            else:
                time.sleep(0.5)
        except Exception:
            break
    ok = "reset" in last_text.lower() or "Written" in last_text or "Linux version" in last_text
    print("\n[+] Flash monitoring ended")
    return ok


# ─── Step 4: 等待重启 ────────────────────────────────────────────────


def verify_boot(ser, timeout=30):
    """等待设备重启完成，检测 app 活信号或 login 提示符。"""
    print(f"[*] Waiting for boot (max {timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        data = ser.read(2048)
        if data:
            text = data.decode(errors="replace")
            if "Kernel panic" in text or "Unable to mount root" in text:
                print("\n[-] Kernel panic! Flash failed.")
                print("    恢复: 检查固件完整性，重烧")
                return False
            if "cpu_loading=" in text or "seq: " in text:
                print("\n[+] App alive — flash OK")
                return True
            if "login:" in text or "root@" in text:
                print("\n[+] Login prompt — flash OK")
                return True
        else:
            time.sleep(0.5)
    print("\n[!] Timeout waiting for boot signal.")
    print("    注意: 超时 ≠ 失败！全擦 16MB 耗时长。")
    print("    等 60-90s 后串口敲回车看 login:")
    print("    不要因超时就重烧（可能打断进行中的擦写）")
    return False


# ─── 交互 shell ──────────────────────────────────────────────────────


def shell_mode(ser):
    interrupt_uboot(ser)
    print("[*] Interactive U-Boot shell. Ctrl+C to exit.")
    try:
        while True:
            data = ser.read(1024)
            if data:
                sys.stdout.write(data.decode(errors="replace"))
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n[*] Exiting.")


# ─── main ────────────────────────────────────────────────────────────


def main():
    # setup / wizard 子命令拦截
    if len(sys.argv) > 1 and sys.argv[1] in ("setup", "wizard"):
        wizard()
        return

    # config 子命令拦截
    if handle_config_subcommand(sys.argv[1:]):
        return

    parser = argparse.ArgumentParser(
        description="TFTP 刷机: 预检→串口→模式判断→配网烧录→验证")
    parser.add_argument("mode", choices=["flash", "shell"])
    parser.add_argument("--port", default=None,
                        help="串口 (default: cached/auto-detect)")
    parser.add_argument("--baud", default=DEFAULT_BAUD,
                        help="波特率: auto/detect/数值 (default: auto)")
    parser.add_argument("--ipaddr", default=None,
                        help="设备 IP (default: cached)")
    parser.add_argument("--serverip", default=None,
                        help="TFTP 服务器 IP (default: cached)")
    parser.add_argument("--netmask", default=None,
                        help="子网掩码 (default: cached/255.255.254.0)")
    parser.add_argument("--gateway", default=None,
                        help="网关 (default: same as serverip)")
    parser.add_argument("--tftp-dir", default=None,
                        help="TFTP 固件目录 (default: cached)")
    parser.add_argument("--at-uboot", action="store_true",
                        help="设备已在 U-Boot，跳过模式判断")
    parser.add_argument("--no-precheck", action="store_true",
                        help="跳过环境预检")
    parser.add_argument("--no-ping", action="store_true",
                        help="跳过 ping 验证")
    args = parser.parse_args()

    # ── 参数解析：CLI > 缓存 > 默认值 ──
    port = args.port or get("port") or find_serial() or DEFAULT_PORT
    ipaddr = args.ipaddr or get("ipaddr") or ""
    serverip = args.serverip or get("serverip") or ""
    netmask = args.netmask or get("netmask") or "255.255.254.0"
    gateway = args.gateway or serverip
    tftp_dir = args.tftp_dir or get("tftp_dir") or ""

    # 缓存用户指定的参数（下次免输入）
    if args.port:
        set("port", args.port)
    if args.ipaddr:
        set("ipaddr", args.ipaddr)
    if args.serverip:
        set("serverip", args.serverip)
    if args.netmask:
        set("netmask", args.netmask)
    if args.tftp_dir:
        set("tftp_dir", os.path.abspath(args.tftp_dir))

    # ══════════════════════════════════════════════════════════════
    # Step 0: 环境预检
    # ══════════════════════════════════════════════════════════════
    if not args.no_precheck:
        print("\n── Step 0: 环境预检 ──")
        ok, errors = preflight(port, tftp_dir, ipaddr, serverip,
                               skip_tftp=(args.mode == "shell"))
        if not ok:
            print(f"\n[-] Preflight failed. Fix above issues and retry.")
            # 交互式引导：参数缺失时询问是否进入 setup 向导
            missing = [e for e in errors if "未设定" in e or "不存在" in e]
            if missing and not sys.stdin.isatty():
                print("    Tip: 首次使用请运行: python3 auto-uboot-interrupt.py setup")
                sys.exit(1)
            try:
                ans = input("\n是否进入交互式参数设定? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "n"
            if ans in ("y", "yes"):
                if not wizard():
                    sys.exit(1)
                # 重载缓存后重跑预检
                port = args.port or get("port") or find_serial() or DEFAULT_PORT
                ipaddr = args.ipaddr or get("ipaddr") or ""
                serverip = args.serverip or get("serverip") or ""
                netmask = args.netmask or get("netmask") or "255.255.254.0"
                gateway = args.gateway or serverip
                tftp_dir = args.tftp_dir or get("tftp_dir") or ""
                ok, errors = preflight(port, tftp_dir, ipaddr, serverip,
                                       skip_tftp=(args.mode == "shell"))
                if not ok:
                    print("\n[-] Preflight still failing after setup.")
                    sys.exit(1)
            else:
                print("    Tip: 首次使用请运行: python3 auto-uboot-interrupt.py setup")
                sys.exit(1)
    else:
        print("[*] Preflight skipped (--no-precheck)")

    # ══════════════════════════════════════════════════════════════
    # Step 1: 建立串口连接
    # ══════════════════════════════════════════════════════════════
    print("\n── Step 1: 串口连接 ──")
    baud = resolve_baud(args.baud, port)
    port = serial_port_init(port, baud)

    ser = serial.Serial(port, baud, timeout=0.5)
    ser.reset_input_buffer()
    time.sleep(0.5)
    drain(ser)

    if args.mode == "shell":
        shell_mode(ser)
        ser.close()
        return

    # ══════════════════════════════════════════════════════════════
    # Step 2: 模式判断
    # ══════════════════════════════════════════════════════════════
    print("\n── Step 2: 模式判断 ──")
    if args.at_uboot:
        print("[*] --at-uboot: skip mode detection")
    else:
        mode = detect_mode(ser)
        print(f"[*] Device mode: {mode}")

        if mode == "uboot":
            print("[+] Already in U-Boot, proceed to flash")
        elif mode == "linux":
            print("[*] In Linux, login → reboot → interrupt...")
            if not login(ser):
                print("[-] Login failed")
                print("    恢复: 等日志刷屏停止后重试，或物理断电")
                ser.close()
                sys.exit(1)
            if not interrupt_uboot(ser):
                ser.close()
                sys.exit(1)
        else:
            print("[-] Device mode unknown (no response)")
            print("    恢复方案:")
            print("    1. 检查波特率: --baud detect 或 --baud 921600")
            print("    2. 试 --at-uboot（设备可能已在 U-Boot）")
            print("    3. 物理断电重启设备后重试")
            ser.close()
            sys.exit(1)

    # ══════════════════════════════════════════════════════════════
    # Step 3: 配网 + 烧录
    # ══════════════════════════════════════════════════════════════
    print("\n── Step 3: 配网 + 烧录 ──")
    if not set_network(ser, ipaddr, netmask, gateway, serverip):
        print("[-] Network config failed")
        print("    恢复: 确认设备在 U-Boot（串口看提示符）")
        ser.close()
        sys.exit(1)

    # ping 验证（可选）
    if not args.no_ping:
        if not ping_verify(ser, serverip):
            print("[!] Ping failed but continuing (mai_tftp will init PHY)...")
            # 不退出：mai_tftp 首次会初始化 GMAC PHY，ping 时 PHY 可能未就绪

    flash_ok = run_mai_tftp(ser)
    if not flash_ok:
        print("[-] Flash may have failed")
        print("    恢复: 设备应仍在 U-Boot，重跑 flash --at-uboot")
        ser.close()
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════
    # Step 4: 等待重启
    # ══════════════════════════════════════════════════════════════
    print("\n── Step 4: 等待重启 ──")
    verify_boot(ser, timeout=30)

    ser.close()
    print("\n" + "═" * 50)
    print("  烧录流程完成")
    print("═" * 50)
    print("  后续: 串口 ifconfig eth0 查 IP → adb connect")
    print("  验证: cat /proc/uptime < 120s 确认是新启动")
    print("═" * 50)


if __name__ == "__main__":
    main()
