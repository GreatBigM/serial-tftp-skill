#!/usr/bin/env python3
"""
<项目>/<项目> 重启压力测试 — N 次循环，采集 I2C/进程/崩溃数据

用法:
    python3 scripts/reboot-stress.py           # 默认 20 次
    python3 scripts/reboot-stress.py --count 100  # 100 次

策略:
  串口登录 + 查 IP → ADB 采集（更快）→ reboot → 循环

依赖:
  python3, pyserial, adb, /dev/ttyUSB0

数据采集项（每次重启后）:
  ABORT     - dmesg | grep -c "ABORT"  (I2C ABORT 计数)
  I2C_TO    - dmesg | grep -c "i2c.*timeout" (I2C 超时计数)
  SEG       - dmesg | grep -c "Segmentation fault" (段错误)
  I2C_OK    - dmesg | grep -c "i2c.*register ok"  (I2C 初始化状态)
  PS        - ps | grep -c c_mi_ipc  (主应用存活)
  MJAC      - grep -c mjac /tmp/miio_client.log (安全芯片状态)
  UPTIME    - cat /proc/uptime (启动时间)
"""
import serial, time, re, subprocess, sys, os, argparse

PORT = "/dev/ttyUSB0"
BAUD = 115200
DEFAULT_COUNT = 20
REBOOT_WAIT = 28

results = []
errors = []

def stty_reset():
    subprocess.run(["sudo", "stty", "-F", PORT, str(BAUD),
        "cs8", "-cstopb", "-parenb", "raw", "-echo", "-echoe", "-echok"],
        capture_output=True)
    time.sleep(0.3)

def serial_open():
    stty_reset()
    s = serial.Serial(PORT, BAUD, timeout=1)
    time.sleep(0.5); s.reset_input_buffer(); time.sleep(2); s.read(s.in_waiting)
    return s

def serial_drain(s):
    if s.in_waiting: s.read(s.in_waiting)
    time.sleep(0.1)
    if s.in_waiting: s.read(s.in_waiting)

def serial_login(s, attempts=6):
    for _ in range(attempts):
        serial_drain(s)
        s.write(b"\r"); time.sleep(0.15)
        s.write(b"root\r"); time.sleep(0.3)
        s.write(b"\r"); time.sleep(1.2)
        s.read(s.in_waiting)
        # kill noise for this cycle (not just at the end)
        s.write(b"killall -9 apphilogcat miio_client 2>/dev/null\r")
        time.sleep(0.5); s.read(s.in_waiting)
        # verify immediately with timestamp marker — break if OK
        ts = int(time.time())
        s.write(f"echo OK_{ts} > /tmp/_ok && cat /tmp/_ok\r".encode())
        time.sleep(1.5)
        buf = bytearray()
        deadline = time.time() + 3
        while time.time() < deadline:
            if s.in_waiting: buf.extend(s.read(s.in_waiting))
            else: time.sleep(0.05)
        if f"OK_{ts}".encode() in buf:
            return True
    return False

def get_ip(s):
    """查 IP，失败则杀日志再设静态 IP"""
    # First: kill noise for a clean serial read
    s.write(b"killall -9 apphilogcat mai_log_service miio_client c_mi_ipc 2>/dev/null\r")
    time.sleep(2); s.read(s.in_waiting)
    for attempt in range(2):
        s.write(b"ifconfig eth0 > /tmp/_ip 2>&1; cat /tmp/_ip\r")
        time.sleep(2.5)
        buf = bytearray()
        deadline = time.time() + 3
        while time.time() < deadline:
            if s.in_waiting: buf.extend(s.read(s.in_waiting))
            else: time.sleep(0.05)
        raw = buf.decode(errors="replace")
        m = re.search(r'inet addr:(\d+\.\d+\.\d+\.\d+)', raw)
        if m: return m.group(1)
        # No IP — set static IP directly
        if attempt == 0:
            s.write(b"ifconfig eth0 <HOST_IP> netmask 255.255.240.0 up > /tmp/_is 2>&1; cat /tmp/_is; ifconfig eth0 > /tmp/_ip2; cat /tmp/_ip2\r")
            time.sleep(3)
    return None

def adb_setup(ip):
    """快速检查 ADB 是否可用（3s 超时）"""
    try:
        subprocess.run(["adb", "disconnect", f"{ip}:5555"], capture_output=True, timeout=5)
        time.sleep(0.5)
        conn = subprocess.run(["adb", "connect", f"{ip}:5555"], capture_output=True, text=True, timeout=3)
        return "connected" in conn.stdout
    except:
        return False

def serial_setup_adb(s, ip):
    """通过串口杀日志 + 启 adbd，让 ADB 可用"""
    try:
        s.write(b"killall -9 apphilogcat mai_log_service miio_client 2>/dev/null\r")
        time.sleep(1); s.read(s.in_waiting)
        s.write(b"killall adbd 2>/dev/null; adbd &\r")
        time.sleep(3); s.read(s.in_waiting)
        subprocess.run(["adb", "disconnect", f"{ip}:5555"], capture_output=True, timeout=3)
        time.sleep(0.5)
        conn = subprocess.run(["adb", "connect", f"{ip}:5555"], capture_output=True, text=True, timeout=3)
        return "connected" in conn.stdout
    except:
        return False

def adb_collect(ip):
    """通过 ADB 采集数据 — 写临时脚本到设备执行，避免 shell 转义"""
    try:
        def sh(cmd, t=10):
            r = subprocess.run(["adb", "-s", f"{ip}:5555", "shell", cmd],
                               capture_output=True, text=True, timeout=t)
            return r.stdout.strip()
        # 写脚本到设备，避免 adb shell 引号转义问题
        sh("cat > /tmp/_collect.sh << 'SCRIPT'\n"
           "echo ABORT=$(dmesg | grep -c 'ABORT')\n"
           "echo I2C_TO=$(dmesg | grep -c 'i2c.*timeout')\n"
           "echo SEG=$(dmesg | grep -c 'Segmentation fault')\n"
           "echo I2C_OK=$(dmesg | grep -c 'i2c.*register ok')\n"
           "echo PS=$(ps 2>/dev/null | grep -c c_mi_ipc)\n"
           "echo MJAC=$(grep -c mjac /tmp/miio_client.log 2>/dev/null || echo 0)\n"
           "echo UPTIME=$(cat /proc/uptime | cut -d' ' -f1)\n"
           "SCRIPT")
        raw = sh("sh /tmp/_collect.sh", t=10)
        data = {}
        for line in raw.split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                data[k.strip()] = v.strip()
        return data
    except Exception as e:
        return None

def serial_collect(s):
    """串口采集 — 写入数据到临时文件，再一次性读取（抗日志洪流）"""
    s.write(b"echo ABORT=$(dmesg | grep -c 'ABORT') > /tmp/_collect2 && "
            b"echo I2C_TO=$(dmesg | grep -c 'i2c.*timeout') >> /tmp/_collect2 && "
            b"echo SEG=$(dmesg | grep -c 'Segmentation fault') >> /tmp/_collect2 && "
            b"echo I2C_OK=$(dmesg | grep -c 'i2c.*register ok') >> /tmp/_collect2 && "
            b"echo PS=$(ps 2>/dev/null | grep -c c_mi_ipc) >> /tmp/_collect2 && "
            b"cat /tmp/_collect2\r")
    time.sleep(3)
    buf = bytearray()
    deadline = time.time() + 3
    while time.time() < deadline:
        if s.in_waiting: buf.extend(s.read(s.in_waiting))
        else: time.sleep(0.05)
    raw = buf.decode(errors="replace")
    data = {}
    for line in raw.split('\n'):
        line = line.strip()
        if re.match(r'^[A-Z_][A-Z_0-9]+=\d+$', line):
            k, v = line.split('=', 1)
            data[k.strip()] = v.strip()
    data.setdefault('UPTIME', '?')
    data.setdefault('MJAC', '?')
    return data

def analyze(results_data):
    print("\n" + "=" * 70)
    print(f"=== 压力测试分析报告 ({len(results_data)} 次成功采样) ===")
    print("=" * 70)
    if not results_data:
        print("无有效数据")
        return
    def pull(vals, name):
        valid = [v for v in vals if v >= 0]
        if not valid: return
        nz = sum(1 for v in valid if v > 0)
        print(f"  {name}: min={min(valid)} max={max(valid)} 非零={nz}/{len(valid)} ({100*nz//len(valid)}%)")
    aborts = []; tos = []; segs = []; i2c_oks = []; pss = []; uptimes = []
    for data, _ in results_data:
        try: aborts.append(int(data.get('ABORT', 0)))
        except: aborts.append(-1)
        try: tos.append(int(data.get('I2C_TO', 0)))
        except: tos.append(-1)
        try: segs.append(int(data.get('SEG', 0)))
        except: segs.append(-1)
        try: i2c_oks.append(int(data.get('I2C_OK', 0)))
        except: i2c_oks.append(-1)
        try: pss.append(int(data.get('PS', 0)))
        except: pss.append(-1)
        try: uptimes.append(float(data.get('UPTIME', 0)))
        except: uptimes.append(-1)
    print("\n--- I2C ABORT ---"); pull(aborts, "ABORT")
    print("\n--- I2C 超时 ---"); pull(tos, "TIMEOUT")
    print("\n--- Segfault ---"); pull(segs, "SEGFAULT")
    nr = sum(1 for v in i2c_oks if v < 2)
    print(f"\n--- I2C 初始化 --- {'✅ 全部注册' if nr==0 else f'⚠️ {nr}/{len(i2c_oks)} 次未完全注册'}")
    alive = sum(1 for v in pss if v >= 1)
    print(f"\n--- c_mi_ipc 存活: {alive}/{len(pss)} ({100*alive//len(pss)}%)")
    vu = [v for v in uptimes if v > 0]
    if vu: print(f"\n--- 启动时间: avg={sum(vu)/len(vu):.1f}s min={min(vu):.1f}s max={max(vu):.1f}s")
    print(f"\n--- 总次数: {DEFAULT_COUNT} 成功: {len(results_data)} 失败: {len(errors)}")
    if errors:
        print(f" 错误 (前10):")
        for e in errors[:10]: print(f"   {e}")

def main():
    global DEFAULT_COUNT
    parser = argparse.ArgumentParser(description="<项目>/<项目> 重启压力测试")
    parser.add_argument("--count", type=int, default=20, help="重启次数 (默认20)")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="串口 (默认 /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()
    DEFAULT_COUNT = args.count
    global PORT; PORT = args.port
    global BAUD; BAUD = args.baud

    n = DEFAULT_COUNT
    print(f"=== <项目> I2C 压力测试 ({n}次) ===")
    print(f"串口: {args.port} @ {args.baud}")
    print(f"开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"预计: ~{n * 60 // 60}min")
    sys.stdout.flush()

    for i in range(1, n + 1):
        iter_start = time.time()
        try:
            s = serial_open()
            if not serial_login(s):
                s.close(); errors.append(f"Iter {i}: login failed")
                print(f"[{i:3d}/{n}] ❌ login failed"); sys.stdout.flush()
                time.sleep(REBOOT_WAIT); continue
            ip = get_ip(s)
            if not ip:
                # Static IP as last resort
                s.write(b"ifconfig eth0 <HOST_IP> netmask 255.255.240.0 up 2>/dev/null\r")
                time.sleep(3)
                # Re-check
                s.write(b"ifconfig eth0 > /tmp/_ip2 2>&1; cat /tmp/_ip2\r")
                time.sleep(2.5)
                buf = bytearray()
                deadline = time.time() + 3
                while time.time() < deadline:
                    if s.in_waiting: buf.extend(s.read(s.in_waiting))
                    else: time.sleep(0.05)
                m = re.search(r'inet addr:(\d+\.\d+\.\d+\.\d+)', buf.decode(errors="replace"))
                if m: ip = m.group(1)
            if not ip:
                s.close(); errors.append(f"Iter {i}: get IP failed")
                print(f"[{i:3d}/{n}] ❌ no IP"); sys.stdout.flush()
                time.sleep(REBOOT_WAIT); continue
            # Setup ADB: 快速尝试，不行就用串口
            if not adb_setup(ip):
                print(f"[{i:3d}/{n}] ⚠ ADB not ready, setup via serial..."); sys.stdout.flush()
                serial_setup_adb(s, ip)
                if not adb_setup(ip):
                    print(f"[{i:3d}/{n}] ⚠ ADB failed, using serial"); sys.stdout.flush()
                    data = None
                else:
                    data = adb_collect(ip)
            else:
                data = adb_collect(ip)
            if data is None:
                # serial fallback: 杀所有日志进程
                s.write(b"killall -9 apphilogcat mai_log_service miio_client c_mi_ipc 2>/dev/null\r")
                time.sleep(2); s.read(s.in_waiting)
                data = serial_collect(s)
            data['_ip'] = ip
            elapsed = time.time() - iter_start
            results.append((data, elapsed))
            a = data.get('ABORT','?'); to = data.get('I2C_TO','?'); seg = data.get('SEG','?')
            i2c = data.get('I2C_OK','?'); ps = data.get('PS','?')
            print(f"[{i:3d}/{n}] IP={ip} ({elapsed:.0f}s) ABORT={a} TO={to} SEG={seg} I2C={i2c} PS={ps}")
            sys.stdout.flush()
            s.write(b"reboot\r"); s.close()
        except Exception as e:
            errors.append(f"Iter {i}: {e}")
            print(f"[{i:3d}/{n}] ❌ {e}"); sys.stdout.flush()
            time.sleep(REBOOT_WAIT); continue
        remaining = REBOOT_WAIT - (time.time() - iter_start - (data is not None and elapsed or 0))
        if remaining > 0: time.sleep(remaining)

    print(f"\n完成: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    analyze(results)

if __name__ == "__main__":
    main()
