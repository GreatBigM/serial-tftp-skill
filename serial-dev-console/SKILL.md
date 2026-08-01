---
name: serial-dev-console
description: 嵌入式设备串口交互与故障诊断 — 登录、设IP、启adbd、杀进程、查状态、诊断决策树
category: devops
metadata:
  hermes:
    triggers: [串口, 串口登录, serial console, ttyUSB, mai_tftp, TFTP烧录, uboot烧录, 网络烧录, 串口烧录, 乱码, 无响应, 日志洪流, login失败]
---

# 串口设备交互与故障诊断

> 通过 python3 serial 脚本与嵌入式设备交互，避开 ADB 不可用时的窘境

## 前提

- 串口设备 `/dev/ttyUSB0`（FTDI），需 `sudo chmod 666`
- python3 + pyserial 可用
- 设备 busybox 环境，无 `head/which/strings/getprop/uname`

### ⚠️ 波特率项目相关，不硬编码 115200

| 项目 | 波特率 | 备注 |
|------|--------|------|
| <项目> | 115200 | 默认值 |
| <项目> | **921600** | 2026-07-17 实测纠正，非 1500000 |

波特率不对 -> 串口全是二进制乱码。代码模板中的 `BAUD` 变量需按项目设置。未知设备用「波特率探测」逐一尝试 [921600, 115200, 1500000, 57600, 9600]。

### ⚠️ 第一件事：确认串口是否双向（TX 通）

**盲目假设串口双向是最常见的翻车原因。** 先验证再动手：

```python
import serial, time
s = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.5)
time.sleep(0.5)
s.reset_input_buffer()
time.sleep(2)
s.read(100000)  # drain all noise

# 发唯一标记，看有没有回显
marker = 'XYZZYX_UNIQUE_MARKER_9876543210'
s.write(f'{marker}\n'.encode())
time.sleep(3)

data = bytearray()
while s.in_waiting:
    data.extend(s.read(s.in_waiting))

if marker in data.decode(errors='replace'):
    print("✅ 串口双向 OK")
else:
    print("❌ 串口 OUTPUT-ONLY（TX 不通）")
s.close()
```

如果 TX 不通，**所有基于串口登录/发命令的方案都不可行**，必须走 ADB、物理断电重启或继电器。此验证应在任何串口自动化脚本的第一步执行。

## 基础交互模板

```python
import serial, time, subprocess

BAUD = 115200  # ← 按项目设置：<项目>=115200, <项目>=921600
# ⚠️ 关键：先 reset 串口参数，否则 pyserial 可能读不到数据
subprocess.run(["sudo", "stty", "-F", "/dev/ttyUSB0", str(BAUD),
    "cs8", "-cstopb", "-parenb", "raw", "-echo", "-echoe", "-echok"],
    capture_output=True)
time.sleep(0.3)

ser = serial.Serial('/dev/ttyUSB0', BAUD, timeout=0.5)
time.sleep(0.2)
ser.write(b'\\n')          # 唤醒提示符
time.sleep(0.3)
ser.write(b'<command>\\n') # 发命令
time.sleep(1)
data = ser.read(4096)
print(data.decode('utf-8', errors='replace'))
ser.close()
```

### 轻量级单命令模式（无需 pyserial）

快速发一条命令 + 读响应，适合一次性状态查询，不依赖 Python serial 库：

```bash
# 开后台读串口
(cat /dev/ttyUSB0 &) 2>/dev/null
SERIAL_PID=$!
sleep 0.3
# 发命令（必须用 \\r 作为行终止符）
echo -ne '<command>\\r' > /dev/ttyUSB0
sleep 1
kill $SERIAL_PID 2>/dev/null
wait $SERIAL_PID 2>/dev/null
```

**限制：** 输出和日志洪流混在一起，需要用 `grep` 过滤。适合快速查状态（IP、进程、路由表）。

## 常见操作

### 登录

设备厂商/设备 系列设备：用户 `root`，密码为空（直接回车）。设备日志（尤其是 SD 卡挂载失败、camera ISP 初始化）可能持续淹没提示符。

**可靠登录序列（已验证）：**

```python
import serial, time
BAUD = 115200  # ← 按项目设置：<项目>=115200, <项目>=921600
ser = serial.Serial('/dev/ttyUSB0', BAUD, timeout=0.5)
time.sleep(0.3)
ser.reset_input_buffer()

# 1. 唤醒
ser.write(b'\r\n')
time.sleep(1.5)
ser.read(ser.in_waiting)  # drain noise

# 2. 发送用户名
ser.write(b'root\r\n')
time.sleep(2.5)
out = ser.read(ser.in_waiting).decode('utf-8', errors='replace')

# 3. 等待 Password: 提示（关键：不是盲发，是等提示）
if 'assword' in out.lower():
    ser.write(b'\r\n')  # 空密码
    time.sleep(2)
    out = ser.read(ser.in_waiting).decode('utf-8', errors='replace')

# 4. 验证登录成功（echo 命令的输出会出现在独立行，不是回显行）
marker = f'LOGIN_TEST_{int(time.time())}'
ser.write(f'echo {marker}\r\n'.encode())
time.sleep(1.5)
out = ser.read(ser.in_waiting).decode('utf-8', errors='replace')
logged_in = any(marker in l and 'echo' not in l for l in out.split('\n'))
```

## ⚠️ 致命陷阱：行终止符用 `\\n` 不用 `\\r`

**在 `stty raw` 模式下，getty/login 只把 `\\r` (CR, 0x0D) 当成"回车键"。`\\n` (LF, 0x0A) 不会被识别为行结束符，所有输入静默丢失。** 2026-06-30 <项目> 踩了 2 小时的坑。

### 症状
发送 `ser.write(b'root\\n')` 后，root 字符不回显，无 `Password:` 提示，shell 永远不出现。串口持续输出应用日志但输入石沉大海。

### 修复
始终用 `\\r` 作为行终止符：
```python
# ❌ 错误 — LF 在 raw 模式下不被识别为回车
ser.write(b'root\\n');  ser.write(b'\\n')

# ✅ 正确 — CR 才是回车键
ser.write(b'root\\r');  ser.write(b'\\r')

# ✅ 也正确 — CR+LF 也可以（设备行规程会处理 LF）
ser.write(b'root\\r\\n');  ser.write(b'\\r\\n')
```

### 验证
发任意字符后查回显。如果 0 回显且无 `Password:` 响应，**先检查行终止符是不是 `\\r` 而不是 `\\n`**。这是比"串口是否双向"更常见的翻车原因。

---

## 常见操作

### 登录

设备厂商/设备 系列设备：用户 `root`，密码为空（直接回车）。设备日志（尤其是 SD 卡挂载失败、camera ISP 初始化）可能持续淹没提示符。

1. **回显 ≠ 执行**：串口会回显所有输入的字符，但未登录时命令不会被执行。验证方法：发 `echo UNIQUE_MARKER`，检查 marker 是否出现在「不含 echo 关键字」的行中
2. **日志洪流**：设备启动时 SD 卡检测、camera ISP 等模块可能每秒输出数条日志，完全淹没 login 提示符。此时 `read_until_keyword` 等逐行等待策略会超时——改用「盲打 + 适当等待 + drain」策略
3. **c_mi_ipc 自动重启**：`killall -9 apphilogcat c_mi_ipc` 后 c_mi_ipc 被 init 自动重启，日志 1-2s 内恢复。需要以 **循环 retry 模式** 登录——发 `killall + root + 密码 + echo 验证` 为一个尝试，循环 5-15 次直到成功，中间不留 `read()` 长时间等待。

**日志洪流下的循环 retry 登录模式：**

```python
ser.read(5000)  # drain initial noise
for attempt in range(10):
    ser.write(b"killall -9 apphilogcat c_mi_ipc 2>/dev/null\r")
    time.sleep(0.3)
    ser.write(b"root\r")
    time.sleep(0.3)
    ser.write(b"\r")
    用 `echo X > /tmp/_ok; cat /tmp/_ok`（文件重定向）而非 `echo X`（避免被日志流切割）
    - 每次尝试仅 2-3s，10 次才 30s——不会无限等待
    - 文件重定向确保即使串口被日志淹没，验证标记也能从文件读到

    **⚠️ 文件标记法两个陷阱：**
    1. **假阳性**：残留文件导致后续失败的 attempt 误判为登录成功
    2. **读不够**：`ser.read(N)` 固定大小在日志洪流时标记可能在前 N 字节之外

    **防御措施（时间戳唯一化 + 循环累积读取）：**
    ```python
    # 时间戳唯一化防残留
    ts = int(time.time())
    ser.write(f'echo OK_{ts} > /tmp/ok_{ts} && cat /tmp/ok_{ts}\r'.encode())
    time.sleep(1.5)

    # 循环累积读取防截断
    buf = bytearray()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
        else:
            time.sleep(0.02)

    if f"OK_{ts}".encode() in buf:
        print("Login confirmed")
    ```

**⚠️ 文件标记法最大陷阱：假阳性登录检测。** 当 /tmp/_ok 被前一个成功的 attempt 写入后，后续失败的 attempt 执行 cat /tmp/_ok 仍会输出 SHELL_OK。

**防御措施（文件标记唯一化 + 验证输出独立性）：**
```python
# 用时间戳唯一化标记，防止残留文件误判
ts = int(time.time())
ser.write(f'echo OK_{ts} > /tmp/ok_{ts} && cat /tmp/ok_{ts}\\n'.encode())
time.sleep(1.5)
out = ser.read(2000).decode(errors="replace")
if f"OK_{ts}" in out:
    print("Login confirmed")
```

**另一个连带风险：** 登录成功后紧跟着的 Enter 锤击（捕捉 U-Boot 倒计时）会污染串口缓冲区，登录时的 `reboot\n` 可能与 Enter 锤击混杂，导致命令被截断。**正确做法：** 登录验证 → 清空串口缓冲区 → 发 `reboot` → 立即 Enter 锤击，三者间加足延迟和 drain。
| 监控脚本缓冲区错误清空 | 用循环 `while` + `ser.read()` 监控串口输出时，**不要在每次迭代中 `buf = b''` 清空缓冲区**。这会导致之前累积的数据丢失，看起来像「设备 30 秒零输出」——实际上设备一直在发数据，只是脚本每轮都丢弃了。正确做法：持续追加到同一个 buffer，周期性检查关键词（如 `login:`）
   - **典型症状**：监控 30s 输出「0 lines, 0 bytes」但设备实际在正常输出——因为每轮 `buf=b''` 把上次读到的数据全扔了。设备在上电后持续输出 U-Boot→Kernel→Init 日志，但脚本每 0.1s 清空一次，永远看不到完整行
3. **不应依赖 `login:` 关键词**：日志洪流中 `login:` 可能根本到达不了 read buffer，直接用 `\\r\\n` 唤醒 + `root\\r\\n` + 等 `Password:` 更可靠
4. **ADB 连接的正确顺序：先查 IP，再 connect**。不要在上电后立即尝试 ADB——设备 IP 由 DHCP 分配，重启后会变。正确流程：串口登录 → 杀日志降噪 → `ifconfig eth0` 查到 IP → `adb connect <IP>:5555`
5. **adbd 崩溃**：有时 `adbd &` 后 init 报 `crash too many times` 并拉黑该服务，但 ADB 仍可能已成功监听 5555——直接 `adb connect` 尝试，不要被 init 日志误导
5. **设备硬件测试锁死后必须重启恢复**：DMA/PIO 硬件加速器测试可能锁死整个设备，软件复位无效。不要尝试在脏状态下原地排查——'调试环境脏了偏好重置设备从头来，而非原地排查'。完整流程：kill 串口进程 → 串口 reboot → 等待 20s → 登录 → 设 IP → 启 ADB → 推送测试（见「完整调试启动序列」）

### 查 IP（日志洪流下）

设备 DHCP 自动分配 IP，不要手动设静态 IP 覆盖。先杀日志降噪，再查 IP：

```bash
killall -9 apphilogcat 2>/dev/null
sleep 3
ifconfig eth0 | grep inet
```

如果 `killall` 后日志仍在刷，等 3-5s 让剩余缓冲清空。查到 IP 后再 ADB connect。

> ⚠️ **不要先 ADB 再查 IP**。ADB 连接依赖正确的目标 IP，必须在串口确认 IP 后再 connect。

### 设静态 IP + 网关（仅 DHCP 不可用时）

```bash
ifconfig eth0 <ip> netmask <mask> gw <gateway> up
route add default gw <gateway>   # 备用
```

⚠️ 设备厂商 有线绑定需要接口级网关（`ifconfig ... gw`），仅 `route add` 不够——应用读接口配置不读路由表。
> ⚠️ 静态 IP 是 Plan B。优先用 DHCP 自动分配，串口查 IP 即可。

### ADBD 状态检查（不手动启动）

ADBD 由 init 托管自启，调试不要手动 `adbd &`。只需确认状态：

```bash
# 确认 adbd 在运行
ps | grep adbd

# 确认端口在监听
cat /proc/net/tcp | grep "15B3"   # 0x15B3 = port 5555

# 如果 adbd 不在 → 检查 init 是否已放弃
dmesg | grep -i "crash too many" | grep adbd
```

> init 放弃后不要再手动 `adbd &`——走降级方案（HTTP/wget 或纯串口）。`cannot bind 'tcp:5037'` 在 dmesg 中是正常输出（adbd 尝试绑定宿主机侧的 5037 端口失败），不影响设备侧 5555 监听。

### ADB 不可用时的替代方案：busybox telnetd

部分精简固件不包含 adbd（`-sh: adbd: not found`）。此时可启用 busybox telnetd 作为远程调试通道：

```bash
# 1. 先查设备上有什么远程工具
busybox --list 2>/dev/null | grep -iE "telnet|ftp|httpd|nc"
ls /system/bin/ | grep -iE "telnet|ssh|dropbear|nc|adbd|tcpsvd"

# 2. 启动 telnetd（busybox telnetd 默认监听端口 23）
busybox telnetd &

# 3. 确认端口已监听
cat /proc/net/tcp | grep "0017"   # 0x0017 = port 23

# 4. 设备有静态 IP 后，宿主机直连
telnet <device_ip>
# 用户名: root, 密码: 空
```

> **注意：** telnetd 默认不加密，仅用于内网调试。部分企业网络防火墙会阻断 23 端口，此时串口仍是唯一可靠通道。
> 
> **验证流程：** `ps | grep telnet` 确认进程在运行 → `cat /proc/net/tcp | grep 0017` 确认端口监听 → 宿主机 `timeout 5 bash -c 'echo -e "root\n" | telnet <IP> 2>&1'` 测试连通性。

### 设网关 + DNS

应用需要出外网时必须配，否则云连接 DNS 失败：

```bash
route add default gw <gateway>
echo "nameserver <dns_ip>" > /etc/resolv.conf
```

### 通过 init 启动/重启服务

设备厂商 设备使用 `paramset` 命令来管理 init 服务：

```bash
# 手动启动 c_mi_ipc（通过 init 托管）
/system/bin/paramset ohos.ctl.start mi_ipc_start

# 注册服务配置（在批处理脚本中使用）
/system/bin/paramset mai.ctl.service.reg /system/service_cfg/<name>.cfg
```

> 服务配置文件在 `/system/service_cfg/` 目录下。`once: 0` 表示服务退出后自动重启。注册后 init 接管生命周期，无需手动干预。

常用服务列表：
- `mi_ipc_start` — c_mi_ipc 主应用
- `apphilogcat` — 日志采集
- `adb.usb` — ADB 守护进程

### 重启设备

**⚠️ 铁律：必须先 login 再发 reboot，否则 reboot 被 login 提示符静默吞噬。**

发送 `reboot\r` 时如果设备还在 login 提示符下（未登录），`reboot` 被解释为用户名，`\r` 提交后等待密码，密码不匹配 → `Login incorrect` → 回到 login 提示符。**设备从未重启，串口看起来一切正常，但所有后续操作都在同一个 session 上运行。** 2026-07-01 <项目> 因此浪费了 101 份日志（全部来自同一个未重启的 session）。

正确流程：
```python
# ✅ 先登录
ser.write(b"root\r")
time.sleep(1)
ser.write(b"\r")
time.sleep(1)
# 验证登录成功
ts = int(time.time())
ser.write(f"echo OK_{ts} > /tmp/_ok && cat /tmp/_ok\r".encode())
# ... 确认 OK_{ts} 出现在 stdout 中 ...
# ✅ 再 reboot
ser.write(b"reboot\r")
```

**典型错误症状：** 发送 `reboot\r` 后，串口在 1-2 秒内继续输出应用日志（apphilogcat、AI 检测等），没有 U-Boot 启动信息。**这是最常见的串口自动化翻车原因，比 `\n` vs `\r` 更隐蔽——因为命令看起来被"发送"了，只是没执行。** 验证方法：在 reboot 后 5s 检查串口是否出现 U-Boot 或 kernel 启动信息。没有就是没执行。

> **⚠️ `reboot shutdown` 是错误用法（2026-06-17 <项目> 踩坑）：** 个别设备/固件中存在 `reboot shutdown` 命令（`/sbin/reboot` 的一个子命令），但它不是「重启」而是「进入某种关机状态」，会触发内核 `We should NOT come here` 死循环，ADB 断开、串口只重复打印这句话，必须物理断电才能恢复。**永远不要用 `reboot shutdown`。**

> **✅ <项目> 当前固件 `reboot` 正常工作（2026-06-18 三次烧录验证）。** 直接 `reboot` 触发正常硬件复位，串口会输出 U-Boot 初始化序列。如需进 U-Boot 烧录，`reboot` 后立即持续按回车 ~12s 打断倒计时即可。不需要物理断电。

> **⚠️ c_mi_ipc 手动启动 crash：** 使用 `/system/bin/paramset ohos.ctl.start mi_ipc_start` 手动启动 c_mi_ipc 会在 `message_main_function` 中触发 SIGSEGV（地址 0x0048ae7c，空指针解引用）。但**冷启动时 init 自动拉起 c_mi_ipc 是正常的**（跑了 13 分钟无崩溃）。不要在 init 已经启动后手动触发 `mi_ipc_start`——如果 c_mi_ipc 没自启，先 `switch_mode.sh debug` 让设备冷启，init 会在开机时正确启动它。

### 串口终端恢复（看门狗复位）

当串口终端因滥发命令（如把 `mai_tftp` 发到 Linux shell）导致 login 进程挂死、只有硬件回显无 shell 响应时：

**方法 A — 看门狗复位（推荐，可远程触发）**

设备存在 `/dev/watchdog` 节点，写入数据触发硬件看门狗，60 秒超时后冷重启：
```bash
# ADB 还活着时
adb shell "dd if=/dev/zero of=/dev/watchdog bs=1 count=100"

# 或通过串口
echo 'dd if=/dev/zero of=/dev/watchdog bs=1 count=100' > /dev/ttyUSB0
```
等待约 60 秒，设备应为冷启动（不经过 kexec），串口重新输出 U-Boot → Kernel → login。

> **⚠️ <项目> 看门狗限制（2026-06-17 实测）：** 看门狗复位是 CPU 级别热启（非 SoC 级冷启），仍可能触发 kexec 绕过 U-Boot——最终进入 Linux 而非 U-Boot 提示符。但串口终端会恢复正常（login 进程重新启动）。如需进 U-Boot 烧录，仍需**物理复位**。

**方法 B — Break 信号（通常无效）**

`ser.send_break(duration=0.3)` 可能复位 UART 控制器，但无法恢复 shell 进程。实测 Ingenic T32 平台上 break 信号不产生任何效果。

**方法 C — 物理断电（最终手段）**

按设备复位键或断电重上电。这是唯一能确保进 U-Boot 的方法。

> **排查原则（2026-06-16 用户纠正）：** 怀疑设备状态异常时，先用 ADB 或串口在设备上实际验证，不要仅靠构建产物推断。c_mi_ipc 的 exit 127 可能是串口 shell 环境问题（`&` 后台进程被 SIGHUP），不是库路径问题。库在 rootfs 的 `/usr/lib/` 中。

**⚠️ 滥发 U-Boot 命令到 Linux shell 导致终端挂死（2026-06-17 <项目> 踩坑）：** 当 `mai_tftp`、`setenv` 等 U-Boot 命令意外发送到 Linux shell 时，shell 尝试执行这些无效命令。后续串口仅剩硬件回显（输入字符能看到，但 login 进程挂死），`ser.read()` 只返回 `\\\\r\\\\n`，无 shell 响应。**必须通过物理断电或看门狗复位恢复，Break 信号无效。** 避免方法：发送任何 U-Boot 命令前先确认收到 `<U-Boot提示符>#` 或 `=>` 提示符。

**⚠️ `mai_tftp` 烧录后不要锤击 Enter（2026-06-19 <项目> 踩坑）：** `mai_tftp` 逐行执行 `auto_update_tftp.txt`，最后一条是 `reset`。设备自动重启后，会显示 `Hit any key to stop autoboot: 1 0` 倒计时。**此时必须停止敲 Enter，否则会打断 kernel 自启，设备卡在 `<U-Boot提示符>#` 提示符。** 正确做法：烧录监控脚本检测到 `reset` 关键字后，立即停止写串口，只读等待，让 kernel 自然启动。等 `login:` 出现再交互。

**⚠️ `switch_mode.sh debug` 会立即触发 reboot（2026-06-19 <项目> 踩坑）：** 在 Linux shell 中执行 `switch_mode.sh debug` 后，设备**不会在本次启动中切换模式**，而是打印 `Enter user debug mode!!!` 后立即重启。**测试脚本不能** `switch_mode.sh debug` → 等 20s 检查 c_mi_ipc，因为设备正在重启。正确流程：`switch_mode.sh debug` → 等 reboot 完成 → 重新登录 → 再检查。



```bash
# ① 看到成功标志后，不立即操作
# ② 等设备重启完成（通常 20-30s）
# ③ 再等 15s 系统稳定
# ④ 然后串口登录 → 查 IP → ADB connect
```

> **原则**：看到成功标志 → 等重启 → 等 15s 稳定 → 再操作。不要看到标志就马上 connect 或发命令。

### 完整调试启动序列（从设备挂起恢复）

当设备被硬件测试锁死后（如 DMA 引擎挂起），按此流程恢复：

```bash
# 1. 杀所有使用串口的后台进程
fuser -k /dev/ttyUSB0

# 2. 通过串口重启设备
python3 /tmp/serial_cmd.py 'reboot' 5 <baud>

# 3. 等待设备完全启动 (~15-20s)
sleep 20

# 4. 检查串口是否有输出
python3 /tmp/serial_cmd.py '\\r' 5 <baud>
# 如果输出 "(no output)" → 串口无任何数据，优先怀疑设备已物理断电
#   检查电源灯、串口线连接、万用表测电压
#   若确实有电→考虑全量 SD 卡烧录恢复
# 如果输出带 U-Boot/Kernel 启动日志但未到 login → 等待更久或确认内核分区正确

# 4. 登录
python3 /tmp/serial_cmd.py 'root' 5 <baud>
sleep 1
python3 /tmp/serial_cmd.py '\r' 3 <baud>

# 5. 验证登录成功
python3 /tmp/serial_cmd.py 'echo LOGIN_OK' 3 <baud>
# 输出应包含 LOGIN_OK（在非 echo 回显行）

# 6. 设置网络（ADBD 由 init 自启，检查端口即可）
python3 /tmp/serial_cmd.py 'ifconfig eth0 <ip> netmask <mask> up' 3 <baud>
python3 /tmp/serial_cmd.py 'route add default gw <gateway>' 3 <baud>

# 7. 宿主机 ADB 连接
adb disconnect <ip>; adb connect <ip>:5555

# 8. 推送测试
adb -s <ip>:5555 push <binary> /tmp/
adb -s <ip>:5555 shell '<binary>'
```

> **关键原则**：每次硬件加速器测试后，如果设备无响应（DMA/PIO 挂起），必须完整执行此序列。不要尝试在脏状态下原地修复——硬件状态机可能已被锁死。

> **用户偏好序列（加速器调试）**：`fuser -k /dev/ttyUSB0 → 登录判断是否root → reboot → 等待重启完成 → 登录 → 设IP → adb connect → push → test`。每次都从头来，不在脏环境排查。

### 快速刷内核分区（替代全量烧录）

当只改内核驱动代码时，可用 `dd` 直接写 `vmlinux.bin` 或 `uImage` 到 kernel 分区，跳过全量固件烧录：

**⚠️ 只刷单分区，不要刷全分区镜像！** `NOR_ALL.bin` 是完整 16MB NOR Flash 镜像，写入 5.5MB 的 kernel 分区会被截断且静默破坏引导。

**若误写 NOR_ALL.bin 到 kernel 分区的恢复步骤：**
```bash
# 1. 确认 kernel 分区号（通常是 mtd0 或 mtd2）
cat /proc/mtd | grep kernel

# 2. 擦除 + 写入正确的 uImage
adb push out/image_<project>/uImage /tmp/
adb shell 'flash_eraseall /dev/mtd<X> 2>/dev/null; dd if=/tmp/uImage of=/dev/mtd<X> bs=4096'

# 3. 断电重启
# 4. 若串口和网络都无响应 → 优先怀疑物理断电，而非 flash 损坏
# ⚠️ 如果物理确认有电但串口仍无输出，不要继续串口调试：
#    → 应把全量 NOR_ALL.bin 交给用户自行 SD 卡烧录
#    → 用户偏好这条路：直接拿固件文件自己烧，比串口恢复快
```

```bash
# 1. 编译内核 + 打包（make → cmake make + make pack_firmware）
# 2. 推送 vmlinux.bin 到设备
adb push out/image_<project>/vmlinux.bin /tmp/
# 3. 写入内核分区（以 mtd2 kernel_system_a 为例）
adb shell 'flash_eraseall /dev/mtd2 2>/dev/null; dd if=/tmp/vmlinux.bin of=/dev/mtd2 bs=4096'
# 4. 断电重启
```

**确认分区号**：`cat /proc/mtd` 或 `cat /proc/cmdline | grep mtdparts`

### 起常驻后台进程

串口 shell 启动的后台进程不会随 shell 退出被杀（与 ADB shell 不同），适合启动 daemon：

```bash
/tmp/<binary> < /dev/null > /tmp/<name>.log 2>&1 &
```

### ⚠️ ADB SIGHUP 陷阱：后台进程在 ADB 断开后被杀

**现象：** `adb shell "cmd &"` 启动后台进程后，ADB shell 正常退出（或超时），进程收到 SIGHUP 被杀死。进程在 ps 中短暂可见后又消失，或显示 Z（僵尸）状态。

**根因：** ADB shell 不是持久会话。shell 退出时向进程组广播 SIGHUP。Shell 脚本中的 `&` 不能防护 SIGHUP，`disown` 在 busybox 中不存在。

**解决方法：**
1. **串口 shell（首选, 持久）** — 串口 shell 是持久会话，后台进程不随退出被杀。登录后执行 `cmd &` 即可。
2. **前台运行（ADB 超时可接受）** — `adb shell "exec /tmp/binary"` 保持前台，`terminal(timeout=较大值)` 超时后进程仍在设备上运行。
3. **init 服务（长期方案）** — 通过 `paramset mai.ctl.service.reg /system/service_cfg/<name>.cfg` 注册为系统服务，由 init 管理生命周期。

**验证存活：** 启动后重新 `adb connect`（或串口），`ps | grep <name>` 检查是否仍是 S 状态（非 Z）。

### 杀进程

```bash
killall <name> 2>/dev/null
```

### 日志洪流下的数据采集（文件重定向法）

当设备应用层持续刷日志（如 camera ISP AWB、MikeSDK 日志）完全淹没串口提示符时，**不要尝试从串口回显中解析命令输出**（回显行和执行结果都会被日志穿插打碎）。

**可靠做法：将命令输出写入文件，再读取文件内容。**

```bash
# ① 命令输出重定向到文件（不依赖串口回显）
cat /proc/ingenic_aes_stats > /tmp/_out 2>&1

# ② 从文件读取（仅取目标内容，无日志干扰）
cat /tmp/_out
```

Python 模板（串口洪流下的可靠数据采集）：

```python
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.5)
# 登录
ser.write(b'root\n')
time.sleep(2)
ser.reset_input_buffer()

# 写结果到文件（抑制所有串口回显）
ser.write(b'<command> > /tmp/_r 2>&1; sync\n')
time.sleep(3)
ser.reset_input_buffer()

# 读回文件内容
ser.write(b'cat /tmp/_r\n')
time.sleep(2)
data = ser.read(2000)
```

> **核心思路**：`<cmd> > /tmp/_r` 写入时设备日志也在串口上刷，但数据已安全存到文件。后续 `cat /tmp/_r` 只输出文件内容，日志不会混入。**不要试图从回显行里解析——100% 会丢数据。**

**文件重定向法失效时的升级策略：** 当设备应用层日志过于密集（如每秒数十条 MI CLOUD/ALGO/ringbuffer 日志），即使 `cat /tmp/_r` 的输出也会被日志流埋没而无法读取。此时两种逃生方案：

| 方案 | 操作 | 适用场景 |
|:----|:-----|:---------|
| **ADB 接管**（首选） | 通过 ADB shell 执行命令，日志只输出到设备 console 但不影响 ADB 的 stdout | 设备已有网络 IP，`adbd` 在运行 |
| **杀日志服务**（次选） | `killall apphilogcat mai_log_service 2>/dev/null` 暂时静默，获取数据后重启 | ADB 不可用，必须用串口 |

**优先 ADB。** ADB 的 stdout/stderr 独立于设备 console 日志流，不会受日志洪流影响。串口登录后第一件事就是启 `adbd --root &` 然后 ADB 接管所有后续操作（top 采样、文件拉取等）。只有在 ADB 不可用且必须用串口时才考虑杀日志服务。

#### 应用日志洪流下获取设备 IP

当设备应用层日志（AI 检测、P2P 推流等）持续每秒数十条刷屏，串口发送 `ifconfig eth0` 后输出被日志完全淹没时：

**方法 A（首选）：Marker 包裹法（使用时间戳防碰撞）**

日志密度极高时，用唯一前后标记定位命令输出，不受日志流切割影响。
**关键：使用时间戳生成唯一 marker，避免静态字符串被设备日志意外匹配。**

```python
import serial, time, re
s = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.5)
time.sleep(0.3)
s.reset_input_buffer()
time.sleep(2)
s.read(s.in_waiting)

# 盲打登录
s.write(b'root\\n')
time.sleep(3)
s.read(s.in_waiting)
s.write(b'\\n')
time.sleep(2)
s.read(s.in_waiting)

# 查 IP：用时间戳标记防碰撞，日志不混入提取区间
ts = int(time.time())
s.write(f'echo "IP_{ts}_START" && ifconfig eth0 && echo "IP_{ts}_END"\\n'.encode())
time.sleep(3)
raw = (s.read(s.in_waiting) or b"").decode(errors="replace")
m = re.search(rf'IP_{ts}_START\s*(.*?)\s*IP_{ts}_END', raw, re.DOTALL)
if m:
    ipm = re.search(r'inet addr:(\d+\.\d+\.\d+\.\d+)', m.group(1))
    ip = ipm.group(1) if ipm else None
else:
    ip = None
s.close()
```

**方法 B：文件重定向（不杀日志服务）**

不依赖串口回显时序，也不杀任何进程：

```python
import serial, time, re
s = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.5)
time.sleep(0.3)
s.reset_input_buffer()
time.sleep(2)
s.read(s.in_waiting)

# 盲打登录
s.write(b'root\\n')
time.sleep(3)
s.read(s.in_waiting)
s.write(b'\\n')
time.sleep(2)
s.read(s.in_waiting)

# 查 IP：命令输出重定向到文件，日志不混入
s.write(b'ifconfig eth0 > /tmp/_r 2>&1; cat /tmp/_r\\n')
time.sleep(4)
raw = (s.read(s.in_waiting) or b"").decode(errors="replace")
m = re.search(r'inet addr:(\\d+\\.\\d+\\.\\d+\\.\\d+)', raw)
ip = m.group(1) if m else None
s.close()
```

**方法 C（备用）：杀日志服务**

仅当文件重定向和 marker 都不可靠时，才杀日志降噪：

```python
s.write(b'killall -9 apphilogcat 2>/dev/null\\n')
time.sleep(3)
s.read(1000)
s.write(b'ifconfig eth0\\n')
time.sleep(3)
raw = s.read(3000).decode('utf-8', errors='replace')
```

> ⚠️ Marker 包裹法比文件重定向更鲁棒：后者在极端日志洪流下 `cat` 的输出可能被日志流切割，导致 `inet addr:` 出现在回显行之外的乱序数据中。优先用 marker 包裹法，`cat` 方法作为备选。杀 apphilogcat 会丢失后续日志，仅 ADB 建立后不再依赖串口时使用。

**适用场景：** 查看 proc 统计、meminfo、dmesg 过滤结果、任何多行文本输出。

### 查状态

```bash
ifconfig eth0 | grep inet
ps | grep <name>
df -h /tmp
```

### 网络诊断

```bash
route -n                          # 路由表（关注 default gw）
cat /etc/resolv.conf              # DNS 配置
ping -c 1 <ip/域名>               # 连通性测试
```

### ⚠️ 多设备环境下的 IP 验证（2026-06-26 踩坑）

当网络中有多台同型号设备时，**不要依赖 ADB 或 ping 扫描得到的第一台设备 IP**。串口确认的 IP 才是当前设备的真实 IP。

**正确流程：**

```
串口登录 → 杀日志降噪 → ifconfig eth0 查 IP → 用该 IP 做 ADB connect + push
```

**常见陷阱：**
1. `adb devices` 显示的设备可能来自其他项目（如 <项目>），不是当前烧录的设备
2. ping 扫描到的第一个存活 IP 不一定是当前设备
3. 烧录后 DHCP 可能分配新 IP、或不同设备的 DHCP 租约交叉——**串口是唯一权威来源**

**验签流程（烧录后必做）：**
```bash
# 串口确认 IP 后，同时验证固件版本
dmesg | grep "Linux version"
# 确认编译时间戳与本地产物一致，避免刷错设备
```

### ADB 离线恢复

⚠️ **ADB connect IP 格式陷阱：** 如果设备 IP 为 `<HOST_IP>`，**不要**写 `adb connect <HOST_IP>:5555` — ADB server 会把完整地址解析为 `<HOST_IP>:5555:5555`（端口被二次追加），连接失败。只用 `adb connect <HOST_IP>`（ADB server 默认使用 5555 端口）。

ADB 状态显示 `offline` 时，通常是 adbd 守护进程卡死。不要反复 reconnect：

```bash
# 宿主机重启 ADB server（最快速，首选）
adb kill-server
sleep 2
adb connect <IP>:5555

# 如果仍 offline，ADBD 由 init 托管，不手动重启。
# 走降级方案：串口直接操作或 HTTP/wget 推送。
```

**常见问题**：设备连不上外网/云服务 → 99% 是缺默认网关或 DNS。
```bash
route add default gw <gateway_ip>
echo "nameserver <dns_ip>" > /etc/resolv.conf
```

### 收集性能参数

内存/CPU/Flash 基准采集：
```bash
cat /proc/meminfo; free -k; cat /proc/loadavg
cat /proc/mtd; df -k; mount
cat /proc/<pid>/status           # 应用进程详情
```
busybox `ps` 不支持 `-eo`，用 `ps` 或 `ps w`。

### 连续内存 / CMA / Buddy 诊断

当怀疑 CMA 耗尽或内存碎片导致驱动分配失败时，组合以下 /proc 节点诊断：

```bash
# 1. CMA 总量与剩余（用户态可见）
cat /proc/meminfo | grep -E "CmaTotal|CmaFree"

# 2. Buddy 空闲块分布（碎片化程度）
cat /proc/buddyinfo
# 每列 = order N 的空闲块数: order 0=4K, 1=8K, ... 8=1M
# 如果高阶 order 为 0 说明大块连续内存已碎片化

# 3. 按迁移类型分（CMA/Movable/Unmovable 各占多少）
cat /proc/pagetypeinfo
# CMA 列 = CMA 池的空闲页分布
# 如果 CMA 列只有 order 0 有值，说明 CMA 只剩 4KB 碎片

# 4. Zone 级详情（watermark、nr_free_cma）
cat /proc/zoneinfo
# nr_free_cma: CMA 空闲页数
# free < low → 内存紧张，free < min → 触发直接回收

# 5. vmalloc 分配情况（大块连续虚拟地址）
cat /proc/vmallocinfo | awk '{sum+=$2} END {printf "Vmalloc used: %.0f kB\n", sum/1024}'
```

**用法示例（Ingenic T32 平台）：**

```bash
# 快速判断 CMA 是否健康
cma_free=$(grep CmaFree /proc/meminfo | awk '{print $2}')
buddy_order0=$(awk '/Normal.*CMA/ {print $6}' /proc/pagetypeinfo)
echo "CMA free: ${cma_free}kB, CMA order-0 pages: ${buddy_order0}"
# CMA free < 64kB 且 CMA order-0 < 16 → CMA 严重碎片化
```

**常见场景：**

| /proc 数据特征 | 诊断结论 |
|---------------|---------|
| CmaFree < 64kB, CMA 列只有 order 0 有值 | CMA 耗尽 + 碎片，驱动 DMA 分配大概率失败 |
| buddyinfo 高阶 order 6+ 全 0 | Normal zone 大块连续内存碎片化 |
| nr_free_cma 持续下降 | 可能有 CMA 泄漏或 TNPU/ISP 持有未释放 |
| pagetypeinfo CMA 块数少但碎片多 | CMA 池太小，需要增大或减少 TNPU 占用 |

### SoC 专用调试节点 (/proc/<soc>/)

嵌入式 SoC 厂商常在 `/proc/<soc>/` 下暴露硬件调试接口。**先发现再诊断**：

```bash
# 发现 SoC 调试目录
ls /proc/ | grep -iE "jz|ingenic|ambarella|sigmastar|mediatek|hisilicon|rockchip|allwinner"
```

以 Ingenic T32 为例：
```
/proc/jz/
├── audio     # 音频流信息（samplerate, channel, frame loss）
├── clock     # 时钟频率
├── ddr       # DDR 控制器寄存器 + 带宽监控
├── debug     # watch 节点
├── gpio      # GPIO 状态
├── isp       # ISP 管道状态（核心多媒体调试）
│   ├── isp-fs     # Frame source 通道、运行状态
│   ├── isp-msca   # MSCA 多通道缩放（各 VIN/CH 格式/stride/stream）
│   ├── isp-w00~02 # CSI/Sensor/VIC 状态
│   └── isp-m0     # 帧计数、ISP 管道各模块 done/error 计数
├── mdio      # 以太网 PHY
├── reset     # 复位、看门狗状态
└── watchdog  # WDT 超时、hibernate/recovery 模式
```

**ISP 状态快速诊断：**
```bash
# 检查帧计数（非零 = 有视频流）
grep "frameNum\|ch0 Done\|ch1 Done\|frames" /proc/jz/isp/isp-m0

# 检查错误计数器（非零 = 硬件异常）
grep "errNum\|Err\|error\|overflow\|timeout" /proc/jz/isp/isp-m0

# 检查传感器是否在线
grep "sensor id\|null\|sensor_stream" /proc/jz/isp/isp-msca

# 检查 ISP 管道是否已配置
grep "width\|height\|format\|mipi\|raw" /proc/jz/isp/isp-w02
```

### 持续采集系统负载（top -bn1 + 循环）

busybox `top` 支持 `-bn1`（单次输出），可用于持续采集。注意 busybox 通常缺少 `head`/`sort`/`wc` 等工具，用 `awk` 或 `sed` 代替：

```bash
# 采集 5 分钟，每秒一次，只抓 CPU/Mem/TOP3 进程
for i in $(seq 1 100); do
  echo "=== $(date +%H:%M:%S) [${i}/100] ==="
  top -bn1 2>/dev/null | sed -n '1,5p'   # top -bn1 输出 5 行
  sleep 3
done > /tmp/top_5min.log
```

> ⚠️ busybox 常见缺省命令：`head`, `sort`, `wc`, `grep -o`, `tr`。优先用 `sed 'Np'` 和 `awk` 替代。

**离线分析模板：**
```python
import re, statistics
samples = []
with open('/tmp/top_5min.log') as f:
    for line in f:
        m = re.search(r'CPU:.*?([\d.]+)%\s+usr.*?([\d.]+)%\s+sys.*?([\d.]+)%\s+idle', line)
        if m:
            samples.append(float(m.group(3)))  # idle %
print(f"采样 {len(samples)} 次, CPU Idle: min={min(samples):.1f}% max={max(samples):.1f}% avg={statistics.mean(samples):.1f}%")
```

## ⚠️ 致命陷阱：后台进程中的串口操作

**背景进程中的串口自动化脚本有特殊问题需要处理：**

### 1. `fuser -k` 会杀死自己的父进程

在 `terminal(background=true)` 启动的脚本中调用 `fuser -k /dev/ttyUSB0`，可能**杀死脚本自身的父进程组**。因为 background 进程的进程组与串口访问进程关联。2026-07-02 <项目> 实测：background 脚本前几条 `fuser -k` 命令导致后续 serial.open() 后的 read() 全部返回 0 字节。

**解决方案：** background 串口脚本不要以 `fuser -k` 开头。改为先检查串口可访问性（`os.access`），失败时打印提示让用户手动清理。或在脚本内部用更精确的 PID 匹配清理。

```python
# ❌ 危险 — background 进程会误杀自己
subprocess.run(["fuser", "-k", "/dev/ttyUSB0"])

# ✅ 安全 — 只检查权限，让用户处理残留
if not os.access("/dev/ttyUSB0", os.R_OK | os.W_OK):
    print("Permission denied on /dev/ttyUSB0")
    # 或：仅杀 Python 进程（不杀 shell）
    subprocess.run(["pkill", "-f", "python.*serial"])
```

### 2. 多次 login 失败会导致 login 进程永久挂死

连续发送用户名/密码到未登录的串口（如 apphilogcat 洪流淹没 login 提示符），login 进程**可能**进入不可恢复状态。表现为：串口能写能读（硬件回显正常），但设备不再响应任何登录尝试，`ser.read()` 只返回 `\r\n`。

**触发条件：** ~10 次以上连续的 failed login 序列（root → Enter → echo 验证），中间没有有效的 killall 降噪，**并且**每次 attempt 有较长的间隔（>1s）。

**例外：短间隔盲打（0.08s）不会挂死 login 进程。** 2026-07-02 <项目> 实测：以 0.08s 间隔连续发送 15× `root\r\n`（总耗时 ~2.5s），login 进程不挂死，且至少一次登录成功。原因是短间隔下每个 attempt 被 getty 完整接收，不触发失败计数。

**登录策略对比：**

| 策略 | 手法 | 适用场景 | 可靠性 |
|------|------|---------|--------|
| 常规登录 | killall → wait → root → wait → verify | 设备刚启动，噪声小 | ✅ 可靠 |
| 循环 retry | (killall+root+verify)×10 | 设备运行中，中等噪声 | ✅ 可靠 |
| **盲打 burst (v4)** | 15×(root+enter) @ 0.08s → 验证1次 → 发 reboot | 设备运行+3min以上，ALGO/AI 极重度洪流 | ✅ 得到验证 |

盲打 burst 核心代码：
```python
def blind_login(ser, attempts=15):
    """暴力盲打登录：连续发 root+enter，不依赖验证。最后验证一次。"""
    for i in range(attempts):
        ser.write(b"root\r")
        time.sleep(0.08)
        ser.write(b"\r")
        time.sleep(0.08)
    # Verify once at the end
    ts = str(int(time.time() * 1000000))
    ser.write(("echo LOGIN_" + ts + "\r").encode())
    time.sleep(1)
    buf = bytearray()
    deadline = time.time() + 2
    while time.time() < deadline:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
    return ("LOGIN_" + ts).encode() in buf
```

**"reboot 前必须先 login" 的例外：** 当盲打 burst 后验证失败时，**仍然可以发送 reboot**。因为 15 次盲打中至少有一次成功登录了，随后的 `reboot\\r` 会被已登录的 shell 执行。如果盲打全部失败（极低概率下），reboot 被 login 吃掉也无妨——下一轮盲打 burst 会继续尝试。

相关脚本：`<skill_dir>/scripts/<项目>-reboot-20x3min.py`（盲打 burst + 立即 capture 的完整实现，用于 N 次循环重启日志采集）

### 3. reboot 前必须先 login（否则静默失效）

见「重启设备」章节的铁律。

---

## 注意事项

1. **日志淹没提示符**：设备日志可能持续输出，在命令前先发 `\n` 换行唤醒
2. **stdout 缓冲问题**：嵌入式系统 stdout 是行缓冲的，重定向到文件后 `printf` 可能不立即写入。用 `fprintf(stderr, ...)` 替代可保证即时输出（stderr 无缓冲）
3. **超时**：busybox 命令通常 1-2s 返回，复杂命令（如 mount）3-5s
3. **无 root 权限**：`sudo chmod 666 /dev/ttyUSB0` 才能读写串口
4. **波特率（项目相关，不硬编码）**：<项目> = 115200，<项目> = 921600（2026-07-17 实测纠正，非 1500000）。代码模板中的 `BAUD` 变量需按项目设置。未知设备用「波特率探测」逐一尝试
5. **持久 shell 优势**：串口 shell 是持久会话，后台进程不随退出被杀——适合启动需要持续运行的守护进程（ADB shell 做不到这点）
6. **pyserial 端口参数污染**：上一个串口 session 遗留的参数设置会导致 pyserial 能写但读不到数据（`ser.read()` 返回空）。打开串口前必须用 `stty` 重置端口参数：`sudo stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb raw -echo -echoe -echok`。然后 pyserial 初始化才有正确数据返回
7. **后台串口捕获验证（log 文件 0 字节排查协议）**：启动后台串口捕获（picocom、screen 或 Python 脚本）后，5 秒内验证文件增长。若 `wc -l /tmp/logfile` 持续为 0，按序排查：`fuser /dev/ttyUSB0` 检查是否有残留进程占用端口 → `kill -9 <pid>` 释放 → 等待 1s → `fuser` 确认端口空闲 → `stty -F /dev/ttyUSB0 <baud> cs8 -cstopb -parenb raw -echo` 重置参数 → 重新启动捕获。**不要等捕获结束才发现文件是空的。** 常见残留进程来源：前序失败的 picocom session、残留的 `cat /dev/ttyUSB0` 进程、未正确销毁的 screen session。
7. **前台超时 ≠ 操作失败**：当串口交互脚本（如 mai_tftp reboot 序列）在前台 `terminal()` 中超时，**不代表命令没执行**。串口可能因为 apphilogcat 日志洪流导致登录缓慢，但 `reboot` 和后续密钥操作可能已经成功发送。此时应单独用 `terminal(background=true)` 监控串口输出确认状态，而不是重复整个序列。
10. **串口返回 0 字节 — 设备可能处于半死状态**：`ser.read()` 连续返回 0 字节，即使 `stty` 重置后仍无效。可能原因：① login 进程因之前滥发命令挂死 ② 设备被硬件测试锁死 ③ 串口线松动。**排查顺序：** `fuser -k /dev/ttyUSB0` → `sudo stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb raw -echo -echoe -echok` → 手动发回车确认 → 发 Break 信号 → 物理断电重启。不要连续重试脚本，脚本不会自己修复串口状态。

### 设备状态检测（判断当前在 U-Boot 还是 Linux）

打开串口后发一个回车，根据响应判断设备状态。**注意串口残留数据陷阱：** 上一轮 failed login（如 `Login incorrect`）会混入缓冲区，导致第一次 CR 读到的内容包含旧数据。需要多发几轮 CR 冲刷干净。

```python
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=2)
time.sleep(0.3)
ser.reset_input_buffer()
# 多发几轮冲刷残留
for _ in range(3):
    ser.write(b'\r\n')
    time.sleep(0.3)
    ser.read(ser.in_waiting)
ser.write(b'\r\n')
time.sleep(1)
out = ser.read(500).decode(errors='replace').lower()
if any(p in out for p in ['<U-Boot提示符>#', '<项目>#', '=>']):
    print("Mode: U-Boot")
elif any(p in out for p in ['login:', 'root@', '# ']):
    print("Mode: Linux")
else:
    print("Mode: Unknown / No power")
```

> **2026-06-17 踩坑：** 没确认在 U-Boot 就发 `mai_tftp` → 命令发到 Linux shell → login 进程挂死 → 终端只剩硬件回显。必须先确认提示符。

> **2026-06-22 踩坑（时序陷阱）：** 设备在 `login:` 状态时直接发 `reboot` → `reboot` 被解释为用户名，后续砸回车变成密码尝试 → `Login incorrect` → 回到 login 提示符，U-Boot 窗口已错过。**烧录脚本第一步必须是模式检测**，`login:` 要先输入用户名+密码再 reboot。不要见字符就发 reboot。

## NOR Flash 烧录与 U-Boot 操作

### SD 卡自动烧录流程

设备短接 BOOT 脚上电，U-Boot 自动执行 SD 卡上的 `auto_update_sdcard.txt` 脚本。烧录约 55s（erase 13s + write 27s）。完成后断电、松开 BOOT 脚、重新上电。

### 网络烧录（TFTP via mai_tftp）

设备厂商 系列 U-Boot 提供 `mai_tftp` 自定义命令，自动初始化以太网并执行 TFTP 烧录。

**前提：** 开发机已安装 TFTP server（见 `tftp-flash-server` skill），产物目录设为 TFTP 根目录。

**U-Boot 操作：**
```
# 配同网段 IP（重启后丢失，此 U-Boot 无 saveenv）
setenv ipaddr <同网段IP>
setenv netmask <掩码>
setenv serverip <开发机IP>

# 执行 TFTP 烧录（自动 init 以太网 → 下载 auto_update_tftp.txt → 逐行执行）
mai_tftp
```

**`auto_update_tftp.txt` 格式（放 TFTP 根目录，< 4KB）：**
```
# <- 注释行
tftpboot 0x80600000 <项目>_NOR_ALL.bin
sf probe
sf erase 0x0 0x1000000
sf write 0x80600000 0x0 0x1000000
reset
% <- 文件结束标记
```

**`mai_tftp` 执行流程：**
1. 自动初始化 GMAC 以太网控制器（Jz4775-9161），无需手动 `sf probe`
2. TFTP 下载 `auto_update_tftp.txt` 到内存
3. 解析脚本并逐行执行
4. 16MB 全量烧录耗时约 21s（erase ~13s + write ~8s @2MiB/s）
5. 完成后 `reset` 自动重启，串口出现 `设备厂商 login:` 即成功

**⚠️ 无 saveenv：** 此 U-Boot 有 `env set` 但没有 `saveenv`。`setenv` 配置的 IP 重启后丢失。如需持久化需修改 U-Boot 默认环境变量源码。

### 监视烧录进度

```python
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=2)
while True:
    chunk = ser.read(4096)
    if chunk:
        print(chunk.decode(errors='replace'), end='', flush=True)
        if b'completed successfully' in chunk:
            print('\n=== 烧录完成 ===')
            break
    else:
        time.sleep(0.5)
```

### U-Boot 手动引导 NOR

烧录后 env CRC 可能损坏导致默认从 SD 卡启动。手动从 NOR：

```
sf probe
sf read 0x80600000 <kernel_offset> <kernel_size>
setenv bootargs console=ttyS1,115200n8 mem=88M@0x0 rmem=40M@0x5800000 init=/linuxrc rootfstype=squashfs root=/dev/mtdblock1 ro system=1
bootm 0x80600000
```

### 自动中断 U-Boot 倒计时

倒计时仅 2 秒，需要快速按键或自动脚本。 获取 Python 自动中断脚本。

### 常用 U-Boot 命令

| 命令 | 用途 |
|------|------|
| `sf probe` | 探测 SPI NOR Flash |
| `sf read <addr> <offset> <len>` | 读 NOR 到内存 |
| `bootm <addr>` | 从内存地址启动内核 |
| `setenv <var> <value>` | 设环境变量（重启丢失 - 无 saveenv） |
| `reset` | 软复位 |
| `ping <ip>` | ICMP 连通性测试（需先 mai_tftp 初始化以太网） |
| `mai_tftp` | 设备厂商 自研 — 自动初始化以太网 + 下载 auto_update_tftp.txt 逐行执行 |
| `tftpboot <addr> <file>` | TFTP 下载文件到内存 |
| `env set/delete/print` | 环境变量增删查（替代 setenv/printenv） |

### 完整上电日志采集（reboot 到 crash 全周期）

当需要捕获从 reboot 到应用启动再到 crash 的完整串口日志时，使用 Python 脚本自动完成登录→reboot→定时捕获→保存。核心模板和注意事项。

### 持久化串口日志（后台记录到文件）

当需要长时间监控设备启动日志但无法保持前台交互时，启动后台 Python 进程将持续记录串口输出到文件。**必须将输出写入文件而非 stdout**——背景进程的 stdout 在 `terminal(background=true)` 模式下几乎不可见（输出预览为空），即使 `-u` flag 也无效。用文件输出 + 周期性 `cat` 读取的方式替代。

#### ⚠️ 后台串口捕获工具选择：picocom 在 background 模式静默退出

`picocom` 在 `terminal(background=true)` 模式下**会立即静默退出**，日志文件产生 0 字节，且 `ps aux` 看不到进程残留。原因是 picocom 需要 PTY/TTY 终端，background 模式不提供。同样，`screen` 的 `-dmS` 搭配 `-L -Logfile` 也可能因端口被占用而静默创建 0 字节 log。

| 工具 | background 模式行为 | 诊断 |
|------|-------------------|------|
| `picocom` | 立即静默退出，0 字节 log | 启动后 `ps aux | grep picocom` 为空 |
| `screen -dmS` | 进程存活但 log 可能 0 字节（端口被占时） | `screen -ls` 可见 session，但 `wc -l log` = 0 |
| Python serial 脚本 | ✅ 稳定工作（推荐） | 自行写循环 `read()` + 写文件 |

**推荐做法：** 使用 Python 脚本（见下模板）而非 picocom/screen 进行后台串口捕获。如果必须用 picocom/screen，启动后立即验证：`ps aux | grep <tool>` 确认存活、`wc -l /tmp/logfile` 确认文件增长。5 秒后仍为 0 字节则换方案。

```python
# 后台串口 logger — 写入 /tmp/<项目>_serial.log
python3 -c "
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.3)
time.sleep(0.3)
ser.reset_input_buffer()
with open('/tmp/<项目>_serial.log', 'a') as f:
    f.write(f'\n=== {time.strftime(\"%Y-%m-%d %H:%M:%S\")} ===\n')
    while True:
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            f.write(data.decode('utf-8', errors='replace'))
            f.flush()
        time.sleep(0.1)
" &
```

**注意事项**：
- 启动后立即验证：`wc -l /tmp/<项目>_serial.log`，3-5 秒后重复验证。如果文件不增长，检查进程是否存活：`ps aux | grep "python.*serial"`，并排查端口占用：`fuser /dev/ttyUSB0`
- 进程无超时退出，需手动 `kill` 停止
- 日志可能含二进制控制字符，用 `strings` 或 `cat | tr -d '\\r'` 过滤
- 不要和前台串口脚本同时运行（会竞争串口）
- <项目> 日志路径：`/tmp/<项目>_serial.log`

### 完整启动日志采集（boot capture）

`scripts/capture_boot_log.py`（已被重写，2026-07-02，关键修复见下方说明）：

```bash
python3 scripts/capture_boot_log.py <baud> <duration_sec>   # 模式1
python3 scripts/capture_boot_log.py --poweron <baud> <duration_sec>  # 模式2
```

**模式1（默认）：** 登录 shell → `switch_mode.sh debug` → `reboot` → 持续捕获 U-Boot / 内核 / init / 应用输出 → 写入时间戳文件

**模式2（`--poweron`）：** 跳过登录重启步骤，直接监听串口等待数据。适用于设备已关机、用户手动上电的场景。默认 180s（覆盖完整启动到应用稳定）。

**默认参数：** baud=115200, duration=75s（模式2默认180s）

**重写说明（2026-07-02 审查发现）：** 旧版缺少 stty_reset、用 `\\r\\n` 而非 `\\r`、无 killall 降噪、无 login retry 循环。**重写尚未执行** — 属 P0 优先级，待用户确认后重写，复用 <项目>-reboot-stress.py 已验证的模式。

### 循环重启采集 (v9 方案)

多次重启 + 每次采集 120s 启动日志的方案。

**关键点：**
- 用 `\r` (CR) 作为行终止符，**不能用 `\n` (LF)**
- 登录验证用循环累积读取 (`read_all_data(ser, timeout_sec)`) 而非固定 `ser.read(N)`
- 日志文件增量写入 (每块数据立即 `f.flush(); os.fsync(f.fileno())`)，**中断不丢数据**

**数据分析：** 采集完成后。 的「结构化多轮分析」方法（时间线 → 模块分类 → 正常运行验证 → 分级排序）。

**使用场景：**
- 应用在 init 托管下反复 crash 重启，dmesg 被滚掉，需要完整启动→崩溃→重启循环
- 需要 U-Boot 阶段日志（reset reason、DDR 初始化、Flash 探测）
- 设备 ADB 不可用，但串口仍在输出

**已知陷阱：**\n1. **脚本必须从 reboot 之前开始跑** — 不能事后补采。设备已死机时脚本返回 0 字节\n2. **`CPU0 RESET ERROR PC:XXXX`** — 内核引导时若出现此行，表示上次崩溃的 PC 值。这是调试 crash 根因的重要线索，不要忽略\n3. **`Kernel panic: VFS: Unable to mount root`** — 刷机后出现此错误表示 rootfs 镜像溢出分区（见 `ingenic-basic-tftp-flash` 的刷机恢复章节）\n4. **0 字节输出** → 设备已断电。检查电源/串口线，不要调试无电设备\n5. **启动后 adbd 可能已被 init 放弃**（`crash too many times`），ADB 需通过串口重新启 `adbd --root &`\n6. **应用日志可能混入二进制控制字符** — 输出文件用 `cat -v` 或 `strings` 清洗后查看\n7. **init.sh 等 Shell 脚本的 `echo`/`cat` 输出不在 dmesg 中** — 这些命令输出到串口 stdout，不进入内核 ring buffer。`dmesg | grep MEM` 抓不到 Shell 脚本的 MEM 日志标记。需在串口实时监控或通过 `cat /proc/kmsg`/早期 syslog 捕获。\n8. **capture_boot_log.py 在设备已在 shell 提示符下时登录失败（2026-06-28 实测）：** 序列中无 `killall` 降噪，也无 retry 循环。已在 `[root@设备厂商:]$` 提示符时，`root` 被 shell 解释为命令（`-sh: root: not found`）。脚本卡在后续步骤。**跑脚本前先确认设备不在 shell 提示符下，或先手动 `killall -9 apphilogcat c_mi_ipc miio_client 2>/dev/null` 降噪后再跑。**

## 相关技能

- `ingenic-basic-tftp-flash` — TFTP 烧录（串口通道，U-Boot 打断，同仓库技能）

## 项目特定

各项目串口参数（波特率、用户名、密码）见 memory 或 `AGENTS.md §1`。

网络配置（同网段 IP + 网关 + DNS）。

## 故障诊断（决策树 + 故障速查）

> 故障诊断章节。串口不通/乱码/日志洪流/命令截断/login 丢失的诊断流程。

### 一、故障诊断决策树

```
串口不通？
├─ 无任何输出
│  ├─ 设备断电？ → 查电源灯/万用表
│  ├─ 波特率不对？ → 乱码 → 探测波特率 [921600, 115200, 1500000, 57600, 9600]
│  ├─ 串口线松动？ → 重插 /dev/ttyUSB0
│  └─ pyserial 读不到？ → stty 重置端口参数
├─ 有输出但命令不执行
│  ├─ 未登录？ → 盲打 burst 登录
│  └─ login 进程挂死？ → 看门狗复位或物理断电
├─ 日志洪流淹没输出
│  ├─ 文件重定向法 — `cmd > /tmp/_f; cat /tmp/_f`
│  ├─ marker 包裹法 — `echo "START"; cmd; echo "END"`
│  └─ 仍不行 → 切 ADB（stdout 不受日志影响）
└─ 长命令被截断
   ├─ 拆为 < 80 字符的短命令
   └─ 写脚本到文件再执行
```

### 二、常见故障诊断

**2.1 串口无数据**：`ser.read()` 持续返回空，但 `cat /dev/ttyUSB0` 能读 → pyserial 被残留 termios 污染 → `serial.Serial()` 前 stty 重置端口参数。

**2.2 串口乱码**：全是不可读二进制 → 波特率不匹配 → 逐一探测 `[921600, 115200, 1500000, 57600, 9600]`，检查 printable ratio。

**2.3 命令发送了但没执行**：写 `reboot\r` 后设备不重启 → 未登录，命令被 login 当作用户名 → **发任何命令前必须先登录并验证**（时间戳 echo 验证）。

**2.4 日志洪流**：应用日志持续刷屏（~100 msg/s），命令输出被淹没 → 修复优先级：

| 优先级 | 方法 | 适用场景 |
|-------|------|---------|
| 1 | **文件重定向** `cmd > /tmp/_f; cat /tmp/_f` | 任何日志密度 |
| 2 | **marker 包裹** `echo "START_${ts}"; cmd; echo "END_${ts}"` | 中等密度 |
| 3 | **切 ADB** | eth0 ADB 可用时首选 |
| 4 | **杀日志进程** `killall apphilogcat` | 最终手段（会丢日志） |

**2.5 长命令截断**：raw 模式下 > 80 字符被截断 → 拆为短命令或写脚本文件执行（`echo 'cmd1; cmd2' > /tmp/s; sh /tmp/s`）。

**2.6 login 反复掉线**：登录成功几秒后又回 login 提示符 → 串口 idle timeout / getty 重启 → 每次重要命令前验证登录状态。

### 三、故障速查（if-X-then-Y）

| 症状 | 处理 |
|------|------|
| echo 验证不通过 | 盲打 burst：`root\r` + `\r`，50 轮，0.01s 间隔 → 时间戳 echo 验证 |
| ser.read() 大量应用日志但无命令输出 | 文件重定向：`cmd > /tmp/_f 2>&1; cat /tmp/_f` |
| 命令 > 80 字符 | 拆为多条短命令 / echo 写脚本文件再执行 |
| 发 reboot 后 5s 还在输出应用日志 | 未登录！reboot 被 login 当用户名。重新登录→验证→再 reboot |
| ser.read() 持续返回空但 cat 能读 | stty 重置端口参数后重新 serial.Serial() |

### 四、反模式

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| 不验证登录就发 reboot | reboot 被 login 当作用户名吃掉 | 先 echo 验证登录 |
| 用 `\n` 作行终止符 | 所有输入静默丢失 | 始终用 `\r` |
| 长命令一条 send | 串口 raw 模式截断 | 拆为 < 80 字符或写文件 |
| 反复读取后清空 buf | 累积数据丢失，看起来像零输出 | 持续追加到同一 buffer |
| 日志洪流中 try `cat /dev/ttyUSB0` | 输出完全不可解析 | 用 pyserial + 文件重定向法 |
| `adb push` 到旧 IP 假设同设备 | push 到错误设备 | 串口确认当前 IP 再 connect |
