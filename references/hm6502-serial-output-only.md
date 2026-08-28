# HM6502 串口调试记录（2026-06-30） — 结论修正

## ⚠️ 本文件的历史结论有误

以下是原始调试记录，**但最终结论是错误的**。串口实际双向正常，问题是用错了行终止符。

## 原始错误结论

~~串口 `/dev/ttyUSB0` 是 output-only（单工）。可以接收设备日志，无法发送指令。~~

## 实际根因：行终止符用 `\n` 而非 `\r`

发送的唯一标记字符串不回显，不是因为 TX 不通，而是因为：
1. `stty raw` 模式下 getty/login 只识别 `\r` (CR, 0x0D) 为回车键
2. `\n` (LF, 0x0A) 不被识别为行结束符，输入静默丢失
3. 验证命令 `echo MARKER` 没有被 shell 执行（因为 shell 根本没启动）

**修复：** 将所有 `\n` 替换为 `\r` 后，首次尝试登录成功率 100%（验证 84 轮）。

## 验证方法（修正版）

```python
import serial, time
s = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.5)
time.sleep(0.5)
s.reset_input_buffer()
time.sleep(2)
s.read(100000)

# ❌ 错误：用 \n
marker = 'TEST_MARKER_12345'
s.write(f'{marker}\n'.encode())     # ← 不会回显，因为 \n 不是回车

# ✅ 正确：用 \r
s.write(f'{marker}\r'.encode())     # ← 会被 shell/getty 接收
time.sleep(2)

data = bytearray()
while s.in_waiting:
    data.extend(s.read(s.in_waiting))

if marker in data.decode(errors='replace'):
    print("Bidirectional (using \\r)")
else:
    print("No echo — check:\\n 1. Is \\r used instead of \\n?\\n 2. Is device at login: prompt (need root login first)?")
```

## 教训

| 症状 | 可能原因 |
|------|---------|
| 发送字符 0 回显 | 用了 `\n` 而非 `\r` |
| 发送字符有回显但命令不执行 | 设备在 `login:` 提示符，需要先登录 |
| 无任何串口输出 | 设备断电，或串口线 TX 引脚断线 |

**正确的调试顺序：**
1. `fuser -k /dev/ttyUSB0` — 清端口
2. `stty -F /dev/ttyUSB0 115200 raw` — 设参数
3. 用 `\r` 发命令，验证回显
4. 登录 `root\r` + `\r`（空密码）

## 采集脚本成功率（修正后）

| 版本 | 方案 | 成功率 | 原因 |
|------|------|--------|------|
| v1-v2 | 用 `\n` 登录 | 6/20 (30%) | 设备恰好处于 shell 状态 |
| v3-v8 | 仍用 `\n` | 0% | 设备在 login:，`\n` 不生效 |
| **v9** | **用 `\r`** | **100%** | 修正行终止符 |


## HM6502 启动日志特征

- c_mi_ipc PID 438 持续输出 ~500B/s 日志
- 日志以 `[06-30 HH:MM:SS.sss PID TID LEVEL MODULE...]` 格式
- 常见关键字：ALGO(img_detection_ai_detect), videohal, MikeSrc, md(motion_detection)
- 没有传统 Linux login: 提示符（被日志淹没或不存在）
- 即使发送 root\n\n，0 次 Password/login/incorrect 回显
