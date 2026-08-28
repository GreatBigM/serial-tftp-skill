---
name: ingenic-adb-debug
description: Ingenic 平台调试环境建立 — 串口盲打登录 → 查 DHCP IP → ADB 连接
category: devops
metadata:
  hermes:
    triggers: [ingenic, hm6502, hm6801, 串口登录, adb连接, 调试环境, 日志洪流]
---

# Ingenic 平台调试环境建立

> 应用日志淹没串口的条件下，通过串口登录 → 查 IP → ADB 连接，建立稳定的调试通道。

## 适用平台

- HM6502（T32 MIPS）
- HM6801（T32 PRJ009）
- 其他 Ingenic T32 平台（Linux shell + adbd 自启）

## 前置条件

- 串口线 `/dev/ttyUSB0`
- 设备已上电运行（Linux shell 可达）
- 开发机与设备 DHCP 同网段
- adbd 由 init 托管自启（不需要手动启动）

> ⚠️ **波特率不是固定 115200！** 控制台波特率由固件/uboot 决定，写在 cmdline（如 `console=ttyS1,921600n8`）。HM6502 历史值：1500000 → 921600（2026-07-16 起）。波特率不对时串口读出全是二进制乱码。确认方法：已知设备看 `/proc/cmdline` 的 `console=` 字段；未知设备按 §「波特率探测」逐一尝试。

## 波特率探测（未知/变更固件必做）

控制台波特率写入 cmdline，固件升级后可能改变。波特率不对 → 串口全是二进制乱码、`ser.read()` 拿不到可读文本。

```python
import subprocess, serial, time

for baud in [921600, 115200, 1500000, 57600, 9600]:
    subprocess.run(["sudo","stty","-F","/dev/ttyUSB0",str(baud),
        "cs8","-cstopb","-parenb","raw","-echo","-echoe","-echok"],
        capture_output=True)
    ser = serial.Serial("/dev/ttyUSB0", baud, timeout=0.5)
    time.sleep(0.3); ser.reset_input_buffer(); time.sleep(1.5)
    raw = ser.read(ser.in_waiting).decode(errors="replace")
    printable = sum(1 for c in raw if c.isprintable() or c in "\n\r\t ")
    ratio = printable / max(len(raw), 1)
    print(f"BAUD {baud}: {len(raw)}B, printable={ratio:.2f}, sample={repr(raw[:80])}")
    ser.close()
```

判断：正确波特率 → printable ratio > 0.7 且 sample 内容是可读日志/英文片段。错误波特率 → ratio 低或内容是乱码。⚠️ 115200 偶尔 ratio 看似高但内容仍是乱码（假阳性），必须看 sample 内容是否真可读，不能只看 ratio。

> ⚠️ **串口无数据恢复：** 如果 `serial.Serial()` 打开端口后 `ser.read()` 始终返回空，但 `sudo stty` + `cat /dev/ttyUSB0` 能读到数据，问题是 pyserial 被残留的 termios 设置污染了。**打开串口前先 stty 重置：**
> ```python
> import subprocess
> subprocess.run(["sudo", "stty", "-F", "/dev/ttyUSB0", "115200",
>     "cs8", "-cstopb", "-parenb", "raw", "-echo", "-echoe", "-echok"],
>     capture_output=True)
> ```

## 核心原则

- **盲打**：日志再凶也不等 login:，直接发 `root` + 空密码
- **密码兼容**：先试空密码（旧固件）。失败后用 `root`/`root`（新固件）。见 §常见问题。
- **查 IP 不杀进程**：用文件重定向法或 marker 法查 DHCP IP，不动 apphilogcat
- **查 IP 后再 ADB**：DHCP 可能动态分配，串口查到 IP 再 `adb connect`，重启后 IP 会变

## 零、第一步：发 CR 判断设备当前模式

**任何串口操作前必须先发 CR 判断模式。不要假设设备状态。**

```python
import serial, time
s = serial.Serial('/dev/ttyUSB0', 921600, timeout=0.5)
time.sleep(0.3); s.read(s.in_waiting)  # drain

# 发 3 次 CR
for _ in range(3):
    s.write(b'\r'); time.sleep(0.3)
time.sleep(1)

buf = bytearray()
dead = time.time() + 3
while time.time() < dead:
    if s.in_waiting: buf.extend(s.read(s.in_waiting))
    else: time.sleep(0.03)

txt = buf.decode(errors='replace').lower()

if len(buf) == 0:
    mode = 'DEAD'        # 设备断电/线松
elif any(p in txt for p in ['prj009#','hm6502#','hm6801#','=>']):
    mode = 'UBOOT'       # U-Boot 提示符
elif any(p in txt for p in ['login:','70mai login']):
    mode = 'LOGIN'       # Linux 未登录
elif any(p in txt for p in ['root@','# ','$ ']):
    mode = 'SHELL'       # Linux 已登录
else:
    mode = 'NOISE'       # 有输出但无提示符（login 可能挂死）
```

| 模式 | 含义 | 下一步 |
|------|------|--------|
| DEAD | 无任何输出 | 检查电源/串口线 |
| UBOOT | U-Boot 提示符 | 等待 autoboot 或手动 bootm |
| LOGIN | Linux,未登录 | 盲打登录 (§一) |
| SHELL | 已登录 root shell | 直接发命令 |
| NOISE | 有日志无提示符 | login 可能挂死 → 看门狗复位或物理断电 |

## 一、标准流程

> 串口盲打登录、日志洪流处理、查 IP 的基础方法详见 `serial-debug` 技能。本节仅列出 Ingenic 平台特化内容。

### 1.1 串口盲打登录（密码 fallback）

> 基础盲打登录方法见 `serial-debug`。Ingenic 平台特化：密码兼容性。

70mai/Smart 系列设备密码策略：
- 旧固件：空密码（直接回车）
- 新固件：`root`/`root`
- 先试空密码，失败后用 `root`/`root` 重试

```python
def try_login(pwd, delay=0.5):
    ser.write(b"root\n")
    time.sleep(delay)
    ser.write(pwd)
    time.sleep(delay)
    ser.read(ser.in_waiting)
    ser.write(b"echo OK > /tmp/_ok; cat /tmp/_ok\n")
    time.sleep(1)
    return "OK" in (ser.read(ser.in_waiting) or b"").decode(errors="replace")

# 先试空密码，再试 root/root
if not try_login(b"\n"):
    try_login(b"root\n")
```

### 1.2 查 DHCP IP（不杀日志）

> 文件重定向法和 Marker 包裹法详见 `serial-debug`。Ingenic 平台用同样的方法查 `ifconfig eth0` 的 `inet addr:` 字段。

### 1.3 ADB 连接

```bash
adb connect <IP>:5555
adb devices                # 确认 device 在线
```

### 1.4 就绪

ADB 连接成功后即可进行内核/应用调试。

## 二、日志洪流进阶

> 日志洪流下的循环 retry 登录、盲打 burst 模式详见 `serial-debug`。

### 极端日志洪流（c_mi_ipc 视频流日志）

当 c_mi_ipc 的 RINGBUF/MI IPC 日志（~100 msg/s）持续刷串口时，需循环 5-10 次 kill+login（init 自动重启 c_mi_ipc）：

```python
for attempt in range(10):
    ser.write(b"killall -9 apphilogcat c_mi_ipc 2>/dev/null\n")
    time.sleep(0.3)
    ser.write(b"root\n")
    time.sleep(0.3)
    ser.write(b"\n")
    time.sleep(0.5)
    ser.write(b"echo OK > /tmp/_ok; cat /tmp/_ok\n")
    time.sleep(1)
    if "OK" in (ser.read(ser.in_waiting) or b"").decode(errors="replace"):
        print("Login OK")
        break
```

## 三、ADB 后台进程 SIGHUP 问题

> 详细的 ADB SIGHUP 陷阱和解决方案见 `serial-debug`。要点：`adb shell 'cmd &'` 启动的后台进程在 ADB 断开后被 SIGHUP 杀。解决：通过串口启动后台进程（串口 shell 子进程不被 SIGHUP 影响）。

## 四、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 串口全是二进制乱码 | 波特率不对（固件改了 console 波特率） | 看 `/proc/cmdline` 的 `console=ttyN,BAUD`，或按 §波特率探测逐一尝试 |
| ADB connect 提示 No route to host | IP 不对或设备未就绪 | 串口重新查 IP |
| ADB 显示 offline | adbd 守护进程卡死 | `adb kill-server` → `adb connect`，或串口杀 adbd 重启 |
| ifconfig 输出看不到 | 日志密度极高 | 换 marker 法，或接受杀 apphilogcat |
| adbd 没起来 | init 放弃重启（`crash too many times`） | 不手动 `adbd &`，走降级方案（HTTP/wget 推送或纯串口） |
| **`adb connect` 持续 Connection refused，adbd netstat 显示 0.0.0.0:5555 LISTEN** | mihomo TUN 代理可能拦截 ADB TCP 握手。ping 通但 nc/bash /dev/tcp 均 Connection refused。 | 降级：串口查 IP → 宿主机 HTTP server → 设备 wget。详见 § ADB 降级方案 |
| DHCP IP 每次重启都变 | 正常行为 | 每次 ADB 前都串口查 IP |
| 串口无数据，stty+cat 却能读 | pyserial 被残留 termios 污染 | 在 `serial.Serial()` 前加 `subprocess.run(["sudo", "stty", "-F", "/dev/ttyUSB0", "115200", "cs8", "-cstopb", "-parenb", "raw", "-echo"])` |
| 密码错误 (Login incorrect) | 新固件 root 密码从空变为 root | 先试空密码，失败后用 `root`/`root` 重试 |

## 反模式（实战踩坑记录）

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| 日志洪流中不确认 shell 就发 reboot | `root\\n` + `\\n` 被日志冲掉没进 shell，reboot 命令没被执行。后面的刷屏全部浪费 | 发 `echo SHELL_OK` 等 1.5s 确认标记返回后再 reboot。连续 3 次无响应则 `killall -9 apphilogcat` 降噪 |
| 用 `cat /dev/ttyUSB0` 裸看串口 | 日志洪流刷屏，看不到输入的命令回显，也无法发命令 | 用 Python serial 发命令 + marker 法读输出。见 §1.1 |
| 靠眼神等 `login:` 提示 | 日志完全淹没 login: 提示，永远等不到 | 不等提示直接盲打 `root\\n` + `\\n`，用 echo 确认 |
| ADB push 二进制到 /tmp 后期望常驻运行 | ADB shell 退出子进程被杀。c_mi_ipc 等 daemon 无法这样运行 | init 系统托管（`paramset mai.ctl.service.reg` + `ohos.ctl.start`）或串口启动 |
| **用 `execute_code` 工具运行串口脚本** | Hermes venv Python 未安装 pyserial，报 `ModuleNotFoundError` | 用 `terminal` 工具 + `python3`（系统 Python）运行脚本 |
| **用 `cat /dev/ttyUSB0` 代替 pyserial** | Python serial 库的 read() 依赖于正确的 termios 配置，裸 cat 只适合视觉观察 | 先 `stty` 配置端口，再用 pyserial 读取 |

## 五、ADB 离线恢复

> ADB 离线恢复方法详见 `serial-debug`。快速恢复：`adb kill-server && adb connect <IP>:5555`。仍不通时串口重启 adbd。

## 六、ADB 降级方案 — HTTP 推送（mihomo TUN 拦截时用）

当 `adb connect` 持续报 `Connection refused`，但串口确认 adbd 在 0.0.0.0:5555 LISTEN 时，可能是 mihomo TUN 代理拦截了 TCP 握手。

### 诊断：确认 mihomo TUN 拦截

串口查设备 netstat，看是否有来自宿主机的大量半连接：

```bash
# 设备上执行
netstat -an | grep 5555
```

**输出特征：**
```
tcp  0  0 0.0.0.0:5555  0.0.0.0:*  LISTEN
tcp  0  0 172.17.151.160:5555  172.17.151.6:45412  SYN_RECV
tcp  0  0 172.17.151.160:5555  172.17.151.6:36194  SYN_RECV
```

- 设备在 LISTEN → adbd 正常
- 大量来自宿主机 IP 的 SYN_RECV → TCP 握手能到设备，但 ACK 不回（mihomo TUN 拦截）
- `ping` 通但 `nc <device_ip> 5555` 超时 → 进一步确认

确认拦截后使用降级方案。

### 1. 宿主机起 HTTP server（提供二进制文件）

```bash
cd <binary_dir> && python3 -m http.server 8888
```

用 `terminal(background=True)` 启动，不阻塞当前会话。

### 2. 设备 wget 下载

```python
# 串口登录后
ser.write(b'wget -q http://<host_ip>:8888/<binary> -O /tmp/<binary> && chmod +x /tmp/<binary> && ls -l /tmp/<binary>\n')
```

验证：`md5sum /tmp/<binary>` 对比宿主机和设备的 md5。

### 3. 启动常驻进程（串口，不走 ADB）

adbd 不可用时，二进制推送和进程启动全靠串口：

```python
ser.write(b'/tmp/<binary> > /tmp/<log> 2>&1 &\nsleep 4\ncat /tmp/<log>\n')
```

## 八、相关技能

- `hm6502-build-flash-test` — HM6502 编译/烧录/ADB/iperf3 全流程（含 eth0 优先策略）
- `serial-tftp` — TFTP 烧录 + switch_mode debug
- `bench-device-performance` — 性能/内存基线采集

## 九、HM6502 专项：eth0 免 RSA 认证

> **关键区别**：HM6502 上 eth0 ADB 永远是 `device` 状态（无需 RSA 密钥认证），WiFi ADB 几乎永远是 `offline`。烧录后必须用 eth0 IP 连 ADB。

### 烧录后等待稳定

HM6502 烧录后内核和应用日志会淹没串口约 60 秒（c_mi_ipc 启动、MI IPC 初始化等）。**串口查 IP 前必须等 60 秒**，否则盲打命令被日志冲掉，ifconfig 输出被埋没。

```python
import time
time.sleep(60)  # 等日志洪流消退
# 然后再走串口登录 → 查 IP 流程
```

> 不需要杀 apphilogcat——等 60 秒后日志密度自然降低到可盲打水平。

```python
import serial, time, re
ser = serial.Serial('/dev/ttyUSB0', 921600, timeout=2)
ser.reset_input_buffer()
ser.write(b'\r\nroot\r\n\r\n')      # 盲打登录（空密码）
time.sleep(2)
ser.reset_input_buffer()
ser.write(b'ifconfig eth0\r\n')
time.sleep(2)
out = ser.read(4096).decode('utf-8', errors='replace')
ser.close()
ips = re.findall(r'inet addr:(\d+\.\d+\.\d+\.\d+)', out)
print(ips[0] if ips else 'none')
```

> HM6502 DHCP 范围 172.17.150.0/23。重启后 IP 会变，每次需要重新查。

### ADB 连接 + 验证

```bash
adb connect <eth0_ip>:5555
adb devices   # 应显示 device（不是 offline）
```

### busybox 限制

HM6502 busybox 缺少 `head`/`cut`/`sort`/`uptime` applet。脚本中避免使用。进程列表用 `/proc/[0-9]*` + awk；负载用 `cat /proc/loadavg`。
