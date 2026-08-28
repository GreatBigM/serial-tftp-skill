# 用户态 Probe 日志采集与诊断

> 从串口 / dmesg 中找到特定函数调用 probe（如 `GetFrame`、`GetStream`）的日志，确认其 OK/FAIL、返回值、指针参数等。

## 背景

嵌入式设备中，probe 日志是诊断用户态进程内部状态的关键线索。但 probe 的输出位置（dmesg vs serial console）和触发时机（启动时 vs 调用时）因实现而异，采集前需先定位。

## 采集方法论

### Step 1 — 查 dmesg（kernel ring buffer）

```bash
adb shell dmesg | grep -i "GetFrame\|get_frame\|probe"
```

- **命中**：说明 probe 走 kernel printk，已在 ring buffer。直接分析即可。
- **未命中**：probe 可能在用户态进程的 stdout/stderr（输出到 serial console），或已编译排除。

### Step 2 — 配置串口并捕获

```bash
# 配置波特率（HM6502=921600）
stty -F /dev/ttyUSB0 921600 cs8 -cstopb -parenb raw -echo

# 后台捕获 serial 输出
cat /dev/ttyUSB0 &
```

### Step 3 — 强制进程重启（捕获启动日志）

如果 probe 在启动时打印，需要 kill 目标进程并捕获 init 自动重启的输出：

```bash
# 查 PID
adb shell ps | grep c_mi_ipc

# 杀掉进程（init 自动重启）
adb shell kill -9 <PID>

# 等待 8-15s 完成重启和初始化
```

### Step 4 — 搜索捕获的串口日志

```bash
# 查看全量日志
grep -i "GetFrame\|get_frame\|probe" <captured_log>
```

### Step 5 — 未找到时的诊断

若 dmesg 和 serial 均无 probe 日志，有且仅有两种可能：

| 原因 | 证据 | 处理 |
|------|------|------|
| **编译排除** (compiled out) | probe 被 `#ifdef DEBUG` / `MI_LOG_DEBUG` 等宏守卫 | 启用 debug 编译 flag，重新部署 |
| **按需触发** (on-demand only) | probe 不是启动时打印，而是在被 IPC 调用时打印 | 通过 test client 或其他 IPC 工具实际调用该函数触发 |

## 实例：c_mi_ipc GetFrame probe (HM6502, 2026-07-17)

**采集结果：**

| 检查项 | 结果 |
|--------|------|
| dmesg 搜索 `GetFrame\|getframe\|get_frame\|probe` | ❌ 未找到 |
| Serial 启动日志搜索 `GetFrame` | ❌ 未找到 |
| PID 453 → kill → PID 802 → kill → PID 1065 (新) | 进程正确重启 |
| 串口捕获全量启动日志 ~110KB | 含完整的 MikeInit、MI CLOUD、AI 初始化、ISP 初始化、编码器初始化 |

**诊断结论：** GetFrame probe 在 HM6502 当前固件中：
- **不**在 dmesg 中（非 kernel module 输出）
- **不**在进程启动时输出（非初始化预热阶段）
- 推测为 **按需触发模式** — 仅当上层通过 IPC 调用 `IMP_FrameSource_GetFrame` 时，才打印 probe 日志
- 或 **编译排除** — 被 `MI_LOG_DEBUG` 或类似 log level 门控编译排除

**下一步建议：**
1. 检查 c_mi_ipc 源码中 GetFrame probe 的日志级别（`MI_LOG_DEBUG` vs `MI_LOG_INFO`）
2. 若为 DEBUG 级别，尝试设置环境变量或 log level mask 启用
3. 或通过 IPC client 实际触发 GetFrame 调用，同时监控串口输出

## 技巧

- **区分 kernel vs userspace**：dmesg 只有 kernel printk。用户的 `printf`/`MI_LOG` 输出到 stdout/stderr → serial console
- **进程重启 vs 设备 reboot**：进程 kill 后 init 自动重启（几秒级）vs 设备 reboot（30-60s）。进程重启保留 `/tmp` 和 dmesg，更适合快速验证
- **串口波特率必须匹配**：HM6502 = 921600，HM6801 = 115200。波特率不对 -> 二进制乱码
- **负结果也是结果**：确认 probe 不存在的诊断链（dmesg→serial→触发时机分析）是有价值的知识，避免后续在同一方向浪费 time
