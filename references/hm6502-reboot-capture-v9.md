# HM6502 循环重启采集 v9 方案

## 脚本路径
`/home/liusen/hm6502_reboot_capture_v9.py`

## 核心逻辑
```
for each iteration:
  1. reset_serial() + open_ser()
  2. login_and_reboot(ser):
     a. Press Enter (\r) to wake getty
     b. Send "root\r" (username)
     c. Send "\r" (empty password)
     d. Wait 3s for shell init
     e. Drain 2s of echo + log flood
     f. Send unique marker to /tmp/ok_{ts}
     g. read_accum(ser, 3s) — search full 3s buffer for marker
     h. If marker found, send "reboot\r"
  3. Close serial, wait 5s for device to reboot
  4. reset_serial() + open_ser()
  5. capture_120s(): read serial for 120s, write incrementally with f.flush()+os.fsync()
  6. Close serial, save file
```

## 关键设计

### 1. 换行符 `\r` 而非 `\n`
`stty raw` 模式下，getty/login 只把 `\r` (CR, 0x0D) 当作回车键。
`\n` (LF, 0x0A) 不会被识别为行结束符。

### 2. 循环累积读取
```python
def read_all_data(ser, timeout_sec):
    buf = bytearray()
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
        else:
            time.sleep(0.02)
    return buf
```
在 `timeout_sec` 内持续读取所有串口数据，不是固定 `ser.read(N)`。
当日志洪流 ~500B/s 时，5 秒内累积 50KB+，固定读取只取前 N 字节，验证标记在后 40KB 中读不到。

### 3. 增量日志写入
```python
with open(fpath, 'wb') as f:
    while time.time() - start < CAPTURE_SEC:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting)
            f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
```
每收到数据立即 flush + fsync 到磁盘。进程被 `SIGKILL`/`SIGTERM`/断电中断时，已采集部分不丢失。

## 分析模式
脚本自动检测以下 4 类错误：
1. **I2C**: ABORT, NoACK, NACK, txabrt
2. **internal:did not int**: miio_client 特有
3. **DID**: "get did OK", "mjac did=", "config save did success"
4. **Critical**: SIGSEGV, Kernel panic, OOM, segmentation fault, crash

## 常见失败模式

| 现象 | 原因 | 解决 |
|------|------|------|
| 登录失败 (0/10 attempts) | 1. 串口 TX 不通 2. 设备已断电 3. 用了 `\n` 而非 `\r` | 先验证串口双向 + 设备有电 |
| 采集 0KB | 设备在 capture 期间无输出（可能已死机/断电） | 物理检查设备电源灯 |
| 采集 ~60KB 但无 DID | ISP 复位循环（c_mi_ipc 未完成初始化） | 已知问题，概率 ~5% |
| 长期运行后全失败 | 设备 ~65 次重启后进入不可恢复状态 | 物理断电 10s 后重启 |

## 参考
- `serial-debug` skill — 通用串口交互
- `hm6502-stress-test` skill — 压力测试上下文
