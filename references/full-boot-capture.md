# 完整上电日志采集（reboot 到 crash 全周期）

> 通过串口自动完成：登录 → 发 reboot → 定时捕获 U-Boot/内核/init/应用启动/crash → 保存到文件

## 典型采集模板

```python
#!/usr/bin/env python3
import serial, time, sys

BAUD = 115200
DEVICE = '/dev/ttyUSB0'
OUTPUT = '/tmp/boot_capture.log'
CAPTURE_SEC = 90  # 覆盖 u-boot(~2s) + kernel(~15s) + init + app init + crash loop(~40s)

ser = serial.Serial(DEVICE, BAUD, timeout=0.3)
time.sleep(0.3)
ser.reset_input_buffer()
all_data = bytearray()

def read_all():
    data = ser.read(ser.in_waiting) if ser.in_waiting else b''
    if data:
        all_data.extend(data)
        sys.stdout.write(data.decode('utf-8', errors='replace'))
        sys.stdout.flush()

# Phase 1: 登录（可能在 shell 或 login 提示符）
time.sleep(3); read_all()
ser.write(b'root\r\n'); time.sleep(2); read_all()
ser.write(b'\r\n')  # 空密码
time.sleep(2); read_all()

# 可选：切到 debug 模式让应用自启动
ser.write(b'switch_mode.sh debug\r\n'); time.sleep(2); read_all()

# Phase 2: 发 reboot，开始捕获
ser.write(b'reboot\r\n'); time.sleep(1); read_all()

# Phase 3: 持续捕获
start = time.time()
while time.time() - start < CAPTURE_SEC:
    read_all(); time.sleep(0.1)

time.sleep(1); read_all()
ser.close()
with open(OUTPUT, 'wb') as f: f.write(all_data)
print(f"\n保存: {OUTPUT} ({len(all_data)/1024:.0f}KB)")
```

## 关键要点

| 场景 | 做法 |
|------|------|
| **设备已在启动中**（串口出 kernel 日志） | 延时 3s 等待登录提示 → 正常登录 → reboot |
| **设备未启动**（串口无输出）| 脚本直接进入 Phase 3 等待 U-Boot 输出（改为纯监听模式） |
| **设备卡在 U-Boot** | 设置环境变量后 `boot` 继续引导 |
| **应用日志淹没串口** | `killall apphilogcat 2>/dev/null` 后采集数据，或直接用 ADB 接管 |
| **设备不自启 adbd** | `killall adbd; adbd &` 手动启动 |
| **busybox 缺命令**（head/tail/uptime/uname）| 用 `sed -n` 替代 `head/tail`，用 `cat /proc/uptime` 替代 `uptime` |

### ⚠️ 启动 capture 后立即验证捕获是否存活

串口 capture 脚本可能因以下原因**静默不工作**：端口被残留进程占用（前序 picocom/cat/screen）、波特率错误、设备已断电。启动 capture 后不要等它跑完再检查：

```bash
# capture 启动后 5 秒：
wc -l /tmp/boot_capture.log
# 如果为 0：
fuser /dev/ttyUSB0         # 查谁占着端口
kill -9 <pid>              # 释放
stty -F /dev/ttyUSB0 <baud> cs8 -cstopb -parenb raw -echo  # 重置参数
# 重新启动 capture

# 如果文件在增长但全是二进制乱码：
# → 波特率不对，改 BAUD 重试
```

同样，如果 capture 跑完但文件为 0 或极小（<1KB），说明 capture 从未工作过，不要分析空文件。

## 采集时长指导

| 观测目标 | 推荐时长 |
|---------|---------|
| U-Boot + 完整内核启动 | 30s |
| init + 应用初始化 + 首次 crash | 60s |
| 完整 crash 循环（多个 restart 到 crash too many times）| 90s |
| 长稳测试（后台持续采集）| 按需，用 `&` 后台运行 |

## 数据分析技巧

### 关键词平面扫描

崩溃分析时从日志中提取关键行：

```bash
# Error/fail 行（不含 debug info）
grep -iE "error|fail|SIGSEGV|fault|warn_alloc|Failed|crash|panic|oom" boot.log | grep -v "^\[D\]"

# I2C 错误
grep -iE "I2C.*error|NoACK|txabrt" boot.log

# 内存分配失败
grep -iE "Failed to allocate|warn_alloc|OOM|oom_kill" boot.log

# CMA 状态
grep -iE "cma|CMA|free_cma|Alloc.*CMA" boot.log

# 应用 crash（CrashLog/tombstone 行）
grep -iE "CrashLog|tombstone|Segmentation fault|SIGSEGV" boot.log

# 内核警告
grep -i "WARNING" boot.log

# DMA / I2C / ISP 错误
grep -inE "dma.*error|i2c.*error|isp.*error" boot.log

# timeout
grep -in "timeout\|timed out" boot.log

# null pointer
grep -inE "null pointer|NULL" boot.log | grep -iv "test\|cmd\|name\|file"
```

### 结构化多轮分析（推荐）

单次 grep 容易漏。推荐三轮分析，逐渐收窄：

**第一轮：提取关键时间线**
```bash
# U-Boot 版本 + 内核版本
head -100 boot.log | grep -E "U-Boot|Linux version"

# 内核命令行（分区 / mem 配置）
grep "Kernel command line" boot.log

# Reset 原因
grep "RESET ERROR" boot.log

# init 服务注册
grep "setparam.*cfg" boot.log

# 设备网络 IP
grep -oP "IP=\d+\.\d+\.\d+\.\d+" boot.log

# 应用启动时间（应用层第一条日志时间戳）
grep -oP "\d{2}-\d{2} \d{2}:\d{2}:\d{2}" boot.log | head -3
```

**第二轮：按模块分类扫描异常**
```bash
# 高优先级：持续运行的硬件/驱动级错误
grep -c "awb statistic error\|ispcore: irq-status\|I2C.*NACK\|DMA.*error" boot.log

# 中优先级：启动阶段的配置/加载失败
grep -iE "failed with error\|Can not get\|open.*failed\|doesn't start on\|force read-only\|Unknown controller" boot.log

# 低优先级：启动时序导致的连接拒绝（非持续）
grep -iE "Connection refused\|connect.*failed\|fetch failed\|config save error\|time sync fail\|not int" boot.log
```

**第三轮：确认正常运行的模块（验证启动成功）**
```bash
# 视频流已启动
grep "IMP_Encoder_GetStream.*seq.*1[0-9][0-9]" boot.log | head -2

# 网络已就绪
grep "LAN info retrieved\|inet addr" boot.log

# 电机校准完成
grep "calibration done\|Centering done" boot.log

# 外设正常
grep "MJAC.*DID\|i2c.*register ok\|DMA initialized\|SD.*Mount" boot.log
```

### 异常排序原则

按实际影响排序，不按 grep 命中数排序：

| 严重度 | 标准 | 例子 |
|--------|------|------|
| 🔴 高 | 持续运行中反复出现，影响功能 | ISP AWB 统计错误 ×83，I2C NACK 风暴 |
| 🟡 中 | 启动阶段出现一次，但最终恢复或影响次要功能 | WiFi 首次加载失败后恢复，分区对齐问题 |
| 🔵 低 | 启动时序正常现象，不持续 | Connection refused, time sync fail, unqlite fetch failed |

### 常见假阳性过滤

```bash
# 排除正常的 debug 回显
grep -v "echo\|\[D\]"

# 排除正常的 recv/send/test 操作（不是真正的错误）
grep -v "recv\|send\|test\|cmd\|name\|step\|state\|start\|dinfo" | grep -iE "error|fail"
```

## 注意

- `fuser -k /dev/ttyUSB0` 先杀占用进程
- `sudo chmod 666 /dev/ttyUSB0` 放权限
- 多次采集时 cover 同一文件会导致数据丢失
- 设备启动后 IP 可能 DHCP 变化，串口采集完后用 `adb connect <new_ip>` 接管进行后续诊断
