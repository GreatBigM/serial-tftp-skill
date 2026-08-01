#!/usr/bin/env python3
"""serial-tftp 统一配置管理 + 环境预检。

配置文件: ~/.config/serial-tftp/config.json
缓存项: baud / port / ipaddr / serverip / netmask / tftp_dir

子命令:
  config show              — 查看全部缓存
  config baud [值|reset|detect]
  config port [值|reset]
  config ipaddr [值|reset]
  config serverip [值|reset]
  config tftp-dir [路径|reset]
  config reset             — 清除全部缓存

依赖: Python 3.6+（2020 年后 Linux 发行版自带；Python 2 不支持）
"""
import sys
if sys.version_info < (3, 6):
    sys.stderr.write(
        "错误: 本脚本需要 Python 3.6+\n"
        "检测到 Python %d.%d (Python 2 已于 2020 年停止维护)\n"
        "请安装 python3: sudo apt-get install -y python3\n" % sys.version_info[:2])
    sys.exit(1)

import json
import os
import re
import subprocess
import time

CONFIG_DIR = os.path.expanduser("~/.config/serial-tftp")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
BAUD_CANDIDATES = [115200, 921600, 1500000, 57600, 9600]

IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# ─── 配置读写 ────────────────────────────────────────────────────────


def load_config():
    """读取配置文件，返回 dict。"""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(cfg):
    """写入配置文件（自动创建目录）。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get(key):
    """读取单个缓存值。"""
    return load_config().get(key)


def set(key, value):
    """设定单个缓存值。"""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


def reset(key=None):
    """清除缓存。key=None 清除全部。"""
    if key is None:
        save_config({})
    else:
        cfg = load_config()
        cfg.pop(key, None)
        save_config(cfg)


# ─── 波特率探测 ──────────────────────────────────────────────────────


def detect_baud(port="/dev/ttyUSB0"):
    """自动探测波特率：逐一尝试候选值，发 CR 看响应可打印字符占比 > 70%。"""
    import serial

    for baud in BAUD_CANDIDATES:
        try:
            subprocess.run(["stty", "-F", port, str(baud),
                            "cs8", "-cstopb", "-parenb", "raw",
                            "-echo", "-echoe", "-echok"],
                           capture_output=True, timeout=5)
            time.sleep(0.2)
            ser = serial.Serial(port, baud, timeout=1)
            ser.reset_input_buffer()
            time.sleep(0.3)
            ser.write(b"\r")
            time.sleep(1.5)
            data = ser.read(ser.in_waiting or 200)
            ser.close()
            if not data or len(data) < 2:
                continue
            printable = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
            if printable / len(data) > 0.7:
                return baud
        except Exception:
            continue
    return None


def resolve_baud(baud_arg, port="/dev/ttyUSB0"):
    """统一波特率解析：auto(缓存/探测) / detect(强制) / 数值(直接)。"""
    if baud_arg not in ("auto", "detect"):
        baud = int(baud_arg)
        set("baud", baud)
        return baud

    if baud_arg == "detect":
        print(f"[*] Force detecting baud rate on {port}...")
        baud = detect_baud(port)
        if baud:
            set("baud", baud)
            print(f"[+] Detected: {baud} (cached)")
            return baud
        print("[-] Detection failed. Specify: --baud 115200")
        sys.exit(1)

    # auto: 缓存优先
    cached = get("baud")
    if cached and isinstance(cached, int):
        print(f"[*] Baud rate: {cached} (cached)")
        return cached

    print(f"[*] First use — detecting baud rate on {port}...")
    baud = detect_baud(port)
    if baud:
        set("baud", baud)
        print(f"[+] Detected: {baud} (cached to {CONFIG_FILE})")
        return baud

    print("[-] Baud rate detection failed (device silent?).")
    print("    Specify: --baud 115200  or  config baud 921600")
    sys.exit(1)


# ─── 交互式参数设定向导 ────────────────────────────────────────────


def _valid_ip(s):
    """IP 格式校验：4 段 0-255。"""
    if not IP_RE.match(s):
        return False
    return all(0 <= int(p) <= 255 for p in s.split("."))


def _ask(prompt, default=None, validator=None, hint=""):
    """交互输入一行。回车接受默认值；返回 None 表示用户取消（q/quit）。"""
    while True:
        suffix = f" [{default}]" if default else ""
        hint_s = f" ({hint})" if hint else ""
        try:
            val = input(f"{prompt}{hint_s}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if val.lower() in ("q", "quit", "exit"):
            return None
        if not val and default:
            return default
        if not val:
            print("  ⚠ 必填项，直接回车取消 (q)")
            continue
        if validator and not validator(val):
            print(f"  ⚠ 无效输入: {val}")
            continue
        return val


def wizard():
    """交互式参数设定向导：逐项输入并校验，回车接受默认值。

    全部输入完成后一次性写盘——中途取消（q/EOF）不产生任何副作用。
    """
    cfg = load_config()
    print()
    print("┌─ serial-tftp 参数设定 ─────────────────────┐")
    print("│ 直接回车接受 [] 内默认值，输入 q 取消       │")
    print("└─────────────────────────────────────────────┘")

    # 先收集全部输入（不写盘）
    ipaddr = _ask(
        "设备 IP", default=cfg.get("ipaddr", ""),
        validator=_valid_ip, hint="如 192.168.1.10")
    if ipaddr is None:
        print("[-] 已取消，配置未修改")
        return False

    serverip = _ask(
        "TFTP 服务器 IP", default=cfg.get("serverip", ""),
        validator=_valid_ip, hint="开发机 IP，如 192.168.1.1")
    if serverip is None:
        print("[-] 已取消，配置未修改")
        return False

    tftp_dir = _ask(
        "TFTP 固件目录", default=cfg.get("tftp_dir", ""),
        validator=lambda p: os.path.isdir(os.path.expanduser(p)),
        hint="含 auto_update_tftp.txt + *_NOR_ALL.bin")
    if tftp_dir is None:
        print("[-] 已取消，配置未修改")
        return False

    baud = _ask(
        "波特率", default=str(cfg.get("baud", "") or "auto"),
        validator=lambda v: v.lower() in ("auto", "detect") or v.isdigit(),
        hint="auto=缓存/探测")
    if baud is None:
        print("[-] 已取消，配置未修改")
        return False

    port = _ask(
        "串口", default=cfg.get("port", "/dev/ttyUSB0"),
        validator=lambda p: os.path.exists(p),
        hint="回车用默认，或输入实际端口")
    if port is None:
        print("[-] 已取消，配置未修改")
        return False

    # 全部通过 → 统一写盘
    set("ipaddr", ipaddr)
    set("serverip", serverip)
    set("tftp_dir", os.path.abspath(os.path.expanduser(tftp_dir)))
    if baud.lower() in ("auto", "detect"):
        set("baud", None)  # 回退到自动探测
    else:
        set("baud", int(baud))
    set("port", port)

    print()
    print("[+] 配置已保存:")
    for k in CONFIG_KEYS:
        v = get(k)
        print(f"    {k:12s} = {v if v is not None else '(auto)'}")
    print("    随时用 `config show` 查看，或重跑 `setup` 修改")
    return True


# ─── 环境预检 ────────────────────────────────────────────────────────


def preflight(port, tftp_dir, ipaddr, serverip, skip_tftp=False):
    """Step 0: 环境预检。返回 (ok: bool, messages: list)。

    检查项:
      1. 串口存在
      2. TFTP 服务运行中
      3. TFTP 目录配置正确
      4. 固件文件存在 (auto_update_tftp.txt)
      5. 设备 IP / 服务器 IP 已设定（非占位符）
    """
    errors = []
    warnings = []

    # ── 1. 串口 ──
    if not os.path.exists(port):
        errors.append(f"串口不存在: {port}")
        errors.append(f"  修复: 检查 USB 串口线连接，或指定 --port /dev/ttyUSBx")
    else:
        if not os.access(port, os.R_OK | os.W_OK):
            warnings.append(f"串口权限不足: {port}，尝试 chmod...")
            subprocess.run(["sudo", "chmod", "666", port],
                           capture_output=True, timeout=10)

    # ── 2. TFTP 服务 ──
    if not skip_tftp:
        try:
            r = subprocess.run(["systemctl", "is-active", "tftpd-hpa"],
                               capture_output=True, text=True, timeout=5)
            if r.stdout.strip() != "active":
                errors.append("TFTP 服务未运行")
                errors.append("  修复: sudo systemctl restart tftpd-hpa")
        except FileNotFoundError:
            warnings.append("systemctl 不可用，跳过 TFTP 服务检查")

        # ── 3. TFTP 目录 ──
        if not tftp_dir:
            errors.append("TFTP 目录未设定")
            errors.append("  修复: --tftp-dir <路径> 或 config tftp-dir <路径>")
        elif not os.path.isdir(tftp_dir):
            errors.append(f"TFTP 目录不存在: {tftp_dir}")
        else:
            # ── 4. 固件文件 ──
            tftp_txt = os.path.join(tftp_dir, "auto_update_tftp.txt")
            if not os.path.isfile(tftp_txt):
                errors.append(f"固件脚本不存在: {tftp_txt}")
                errors.append("  修复: 确认 TFTP 目录指向正确的产物目录")
            else:
                # 从 auto_update_tftp.txt 提取 bin 文件名验证
                try:
                    with open(tftp_txt) as f:
                        for line in f:
                            if "tftpboot" in line and ".bin" in line:
                                parts = line.strip().split()
                                bin_name = parts[-1] if parts else None
                                if bin_name:
                                    bin_path = os.path.join(tftp_dir, bin_name)
                                    if not os.path.isfile(bin_path):
                                        errors.append(f"固件文件不存在: {bin_path}")
                                    else:
                                        size = os.path.getsize(bin_path)
                                        if size < 1024 * 1024:
                                            warnings.append(
                                                f"固件文件异常小: {bin_name} ({size} bytes)")
                                break
                except OSError:
                    pass

    # ── 5. IP 设定 ──
    PLACEHOLDERS = ("<DEV_IP>", "<HOST_IP>", "")
    if not ipaddr or ipaddr in PLACEHOLDERS:
        errors.append("设备 IP 未设定")
        errors.append("  修复: --ipaddr <设备IP> 或 config ipaddr <设备IP>")
    if not serverip or serverip in PLACEHOLDERS:
        errors.append("TFTP 服务器 IP 未设定")
        errors.append("  修复: --serverip <主机IP> 或 config serverip <主机IP>")

    # ── 输出 ──
    ok = len(errors) == 0
    if errors:
        print("╔══════════════════════════════════════╗")
        print("║       环境预检失败 (Preflight)       ║")
        print("╚══════════════════════════════════════╝")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")
    if ok:
        print(f"[+] Preflight OK: port={port}, tftp={tftp_dir}, "
              f"dev={ipaddr}, server={serverip}")

    return ok, errors


# ─── config 子命令 ───────────────────────────────────────────────────

CONFIG_KEYS = ["baud", "port", "ipaddr", "serverip", "netmask", "tftp_dir"]


def handle_config_subcommand(args):
    """处理 config 子命令。返回 True 表示已处理。"""
    if not args or args[0] != "config":
        return False

    # config show / config (无参数)
    if len(args) == 1 or (len(args) == 2 and args[1] == "show"):
        cfg = load_config()
        print(f"Config: {CONFIG_FILE}")
        print("─" * 40)
        for k in CONFIG_KEYS:
            v = cfg.get(k, "(not set)")
            print(f"  {k:12s} = {v}")
        return True

    # config setup — 交互式向导
    if len(args) == 2 and args[1] in ("setup", "wizard"):
        wizard()
        return True

    # config reset (全部)
    if len(args) == 2 and args[1] == "reset":
        reset()
        print("[+] All config cleared.")
        return True

    # config <key> [value|reset|detect]
    key_map = {"tftp-dir": "tftp_dir"}  # CLI 友好名 → 内部 key
    key = key_map.get(args[1], args[1])

    if key not in CONFIG_KEYS:
        print(f"Unknown key: {args[1]}")
        print(f"Available: {', '.join(CONFIG_KEYS)}")
        print("  config baud [值|reset|detect]")
        print("  config port [值|reset]")
        print("  config ipaddr [值|reset]")
        print("  config serverip [值|reset]")
        print("  config netmask [值|reset]")
        print("  config tftp-dir [路径|reset]")
        print("  config show / config reset")
        return True

    # 查看
    if len(args) == 2:
        v = get(key)
        if v is not None:
            print(f"{key} = {v}  ({CONFIG_FILE})")
        else:
            print(f"{key} = (not set)")
        return True

    value = args[2]

    # 特殊: baud detect
    if key == "baud" and value == "detect":
        port = args[3] if len(args) > 3 else (get("port") or "/dev/ttyUSB0")
        print(f"[*] Detecting baud rate on {port}...")
        baud = detect_baud(port)
        if baud:
            set("baud", baud)
            print(f"[+] Detected and cached: {baud}")
        else:
            print("[-] Detection failed (device silent?).")
        return True

    # reset
    if value == "reset":
        reset(key)
        print(f"[+] {key} cleared.")
        return True

    # 设定值
    if key == "baud":
        try:
            set("baud", int(value))
            print(f"[+] baud = {value}")
        except ValueError:
            print(f"[-] Invalid baud: {value}")
    elif key == "tftp_dir":
        if os.path.isdir(value):
            set("tftp_dir", os.path.abspath(value))
            print(f"[+] tftp_dir = {os.path.abspath(value)}")
        else:
            print(f"[-] Directory not found: {value}")
    else:
        set(key, value)
        print(f"[+] {key} = {value}")

    return True
