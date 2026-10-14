---
name: serial-debug
description: Reliable patterns for executing commands on embedded Linux devices over raw serial (busybox) — script isolation, binary discovery, output capture in log-flooded environments.
category: devops
metadata:
  hermes:
    triggers: [串口, serial, busybox, 命令执行, script, 复合命令, 二进制发现, 路径查找]
---

# Embedded Serial Command Execution

> Reliable patterns for running commands on embedded Linux over raw serial.
> Complements `serial-debug` (connection) and `debug-playbook` (pitfalls).
> These skills are manually authored; this skill captures patterns that belong there but cannot be directly patched.

## 零、第一步：发 CR 判断设备当前模式（必做）

**任何串口操作前必须先发 3 次 CR，收集回显判断状态。不假设设备状态。**

```python
s.write(b'\r'); time.sleep(0.3)
s.write(b'\r'); time.sleep(0.3)
s.write(b'\r'); time.sleep(1)
buf = read_all(s, 3).decode(errors='replace').lower()

if len(buf) == 0:           mode = 'DEAD'
elif any(p in buf for p in ['prj009#','=>','<项目A>#']): mode = 'UBOOT'
elif 'login:' in buf:       mode = 'LOGIN'
elif any(p in buf for p in ['root@','# ','$ ']): mode = 'SHELL'
else:                       mode = 'NOISE'
```

| 模式 | 下一步 |
|------|--------|
| DEAD | 检查电源/线 |
| UBOOT | 等 autoboot |
| LOGIN | 盲打登录 |
| SHELL | **直接发命令，不要再发 root** |
| NOISE | 等 5s 重试，或看门狗复位 |

### SHELL 误判陷阱（2026-07-27 <项目A> 实踩）

症状：发 `root\r` 回显 `-sh: root: not found`，反复"登录失败"。
根因：设备已在 `[root@70mai:]$` 下，`root` 被当 shell 命令执行。
教训：**跳过 CR 检测直接盲打是反模式。** SHELL 模式下直接发命令。

## 一、核心原则

嵌入式设备串口（busybox, raw tty）与桌面 Linux bash 有显著差异：

| 桌面习惯 | 串口坑 | 正确做法 |
|---------|--------|---------|
| `echo X && cmd && echo Y` | 引号/&& 被吞，输出混乱 | 脚本隔离法（见下） |
| `which` / `command -v` | 很多系统没有 | `ls /usr/bin/wp* /bin/wp*` |
| `test -x /path` | 可以误判（文件存在但不可执行） | 配合 `ls -la` 验证 |
| `ip addr show` | busybox applet 可能缺 | 用 `ifconfig` 替代 |
| `timeout` / `head` 命令 | **精简 busybox 可能没有（2026-08-08 <项目A> 实踩：busybox 无 timeout applet，无 head）** | 用工具自带退出条件（如 `tcpdump -c N` 抓满即退）或后台 + sleep + kill 兜底 |
| 一次 send 长命令 | > 80 字符被截断 | 写脚本文件再执行 |
| `echo "long body" > /tmp/s.sh` | 长 body 中引号/特殊字符被吞 | 拆多个 `echo >>` 拼接，或用 Python 控制 |

## 二、可靠命令执行模式

### 2.1 脚本隔离法（推荐）

这是目前唯一在所有嵌入式 busybox 上都验证可靠的模式：

```python
def write_and_run(ser, body, wait=3.0):
    """Write script → execute → cat output file."""
    import random
    name = f"/tmp/s_{int(time.time())}_{random.randint(100,999)}"
    safe = body.replace("'", "'\\''")
    
    # ① 写脚本
    ser.write(f"echo '{safe}' > {name}\\r".encode())
    time.sleep(0.3)
    drain(ser, 0.3)
    ser.write(f"chmod +x {name}\\r".encode())
    time.sleep(0.3)
    drain(ser, 0.3)
    
    # ② 执行并重定向到文件
    ser.write(f"sh {name} > /tmp/_r 2>&1\\r".encode())
    time.sleep(wait)
    drain(ser, wait * 0.5)
    
    # ③ 读结果文件
    ser.write(b"cat /tmp/_r\\r".encode())
    time.sleep(wait * 0.5)
    return drain(ser, wait * 0.7 + 1.0)
```

**适用场景**：
- 任何复杂的 shell 命令
- 需要管道、重定向、循环的命令
- 命令输出可能被日志洪流淹没

### 2.2 后台执行法（长时间任务）

```python
# 写脚本
ser.write(f"echo '{long_command}' > /tmp/run.sh\\r".encode())
time.sleep(0.3)
ser.write(b"chmod +x /tmp/run.sh\\r".encode())
time.sleep(0.3)

# 后台执行（&，非 -B）
ser.write(b"sh /tmp/run.sh &\\r".encode())
time.sleep(1.0)

# 等完成
time.sleep(wait_s)

# 读结果
ser.write(b"cat /tmp/output.log\\r".encode())
time.sleep(1.0)
result = drain(ser, 2.0)
```

**适用场景**：
- iperf3 测试（-t 10 等）
- 长时间网络操作
- 任何预计运行 > 5 秒的命令

### 2.3 直接简短法（仅简单命令）

仅用于 < 80 字符、预计 < 3 秒、输出可预测的简单命令：

```python
ser.write(b"echo test\\r".encode())
time.sleep(0.5)
result = drain(ser, 1.0)
```

## 三、二进制路径发现

嵌入式设备可能没有 `which`、`command -v`、`type`。`test -x` 也可能误判。

### 3.1 可靠查找流程

```python
# 最可靠的二进制发现方式
cmd = "ls /usr/bin/wp* /usr/sbin/wp* /bin/wp* /sbin/wp* 2>&1; "
cmd += "echo '---'; "
cmd += "ls /usr/bin/iperf* /usr/sbin/iperf* /tmp/iperf* /tmp/i3 2>&1"

# 用脚本隔离法执行
```

### 3.2 已知实际路径（<项目A>）

| 二进制 | 实际路径 |
|--------|---------|
| wpa_supplicant | `/usr/bin/wpa_supplicant` (NOT `/usr/sbin/`) |
| wpa_cli | `/usr/bin/wpa_cli` |
| udhcpc | `/sbin/udhcpc` (busybox applet) |
| iperf3 | ❌ 固件不自带，需 cross-compile + push |

## 四、PATH 确认

```bash
echo $PATH
```
<项目A> 典型值：`/system/bin:/bin:/sbin:/usr/bin:/usr/sbin`

## 五、已知 Busybox 行为

| 行为 | 说明 |
|------|------|
| `ip` 是 applet | `ip addr show` 可能不存在，用 `ifconfig` 代替 |
| `file` 命令 | 可能缺失，无法判断 ELF 格式 |
| `which` | 可能缺失，用 `command -v` 或 `ls` |
| `/usr/sbin/` | 是 busybox symlink farm，不是独立二进制 |
| 进程查看 | 用 `ps 2>/dev/null`（stderr 重定向） |
| 后台 | 默认没有 nohup/disown，用 subshell `(cmd &)` 或 `cmd &` 直接后台 |

## 六、反模式

| 反模式 | 后果 |
|--------|------|
| `echo 'MARKER' && cmd && echo '/MARKER'` | busybox raw serial 下引号/&& 被截断，输出混乱 |
| `test -x /path` 发现二进制 | 文件存在但不可执行时误判 |
| 把桌面 `which` 当作可靠 | 嵌入式设备常无此命令 |
| 一次 send 长 shell 行 | raw tty 截断 |
| `cat /dev/ttyUSB0` 直接读 | 应用日志淹没输出 |
| **两个进程同时打开串口**（如串口 logger 采集 + serial_cmd 发命令并行） | pyserial 报 `SerialException: device reports readiness to read but returned no data (device disconnected or multiple access on port?)`——logger 先占端口，命令脚本读不到数据崩溃。**串口同一时刻只允许一个读者**，即使读/写混合也会冲突 |

### 串口独占铁律（2026-08-04/05 多次实踩）

串口（pyserial 默认独占）同一时刻只能有一个进程打开。logger 采集 + 命令执行不能并行：

```
❌ 先启 logger → 再跑 serial_cmd.py → SerialException（读不到数据，命令实际可能没发出）
✅ 正确顺序：先串口发命令（启动 iperf3 等）→ 再启 logger 采集 → 测试完停 logger
```

修复顺序（logger 已在跑时）：kill logger → 串口发命令 → 重启 logger。写自动化脚本时把"串口独占"作为前置约束：任何"采集 + 执行"组合都要串行化（执行在前、采集在后），或采集脚本内部处理瞬时竞争（`try/except` 跳过 + `time.sleep(1)` 重试，参考本 skill `references/echo-to-serial-workflow.md` 的完全绕过方案）。

## 七、参考文件

- `references/working-python-patterns.md` — 经过 <项目A> 实际验证的 Python 模板（login、script write/run/cat、binary discovery、iperf3 background、stty reset 完整模式）
- `references/echo-to-serial-workflow.md` — echo-to-serial 替代法：用 `echo -ne 'cmd\r' > /dev/ttyUSB0` 发命令 + 后台 capture.log 读结果，完全绕过 pyserial 竞态冲突
- `scripts/serial_login_ip.py` — 精确时序登录+查 IP 一体脚本（root+空密码，日志洪流环境可用，2026-08-04 验证）
