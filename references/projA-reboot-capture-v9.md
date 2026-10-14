# <项目A> 循环重启采集 v9 方案

## 脚本路径
`<用户目录>/<项目A>_reboot_capture_v9.py`

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

## ⚠️ 2026-09-12 实测：reboot 压测脚本三禁（返工代价 ≈1.5h）

reboot 压测与「抢 U-Boot 烧录」目的相反——**压测期间绝不能敲键**，否则把设备钉在 U-Boot 提示符上：

1. **reboot 后到 `70mai login:` 出现前一律纯读**：内核 reboot 置 warm 标志 `CPSPR=0x3535` → U-Boot bootdelay 缩到 ~1s，**任何写入字节都打断 autoboot → 设备停在 `PRJ009#`**（现象像"卡在 boot"，需手敲 `boot` 或冷启动）。压测循环里唯一允许的写入（login 的 `\r`）必须等 login 提示出现后再发。
2. **启动判定不得匹配 shell 回显**：发 `reboot` 后第一段输出含自身命令行回显 `[root@70mai:tmp]$ reboot`，拿它当"起来了" = **假 OK**（曾骗过首版脚本）。正确判据：见 `70mai login:` 或 `Linux version`，且要求本轮确实见过 `Restarting system|U-Boot 20` 才算真 reboot。
3. **状态不跨 reboot**：① 会话会丢——每轮先重登，否则 `reboot` 被当 login 用户名 → `Password` 提示 → 白等 60s 超时（曾被记成"OK 62s"）；② `/tmp` 是 tmpfs——`iperf3` 每轮消失，`[ -x /tmp/iperf3 ] || wget` 必须每轮执行，否则静默退化成"关联态"而非"负载态"（症状 `-sh: /tmp/iperf3: not found`）。

参考脚本：`/tmp/r2_stress.py`（负载态压测 v2）、`/tmp/r2_flash2.py`（从 shell 抓 U-Boot 版）、`/tmp/r2_regress.py`（空载+吞吐+rmmod+dmesg）。

## ⚠️ 2026-09-13 实测：设备压测脚本自证 5 条（3 次返工均因「没核返回」）

1. **起脚本前先过语法**：py<3.12 下 f-string 嵌套同类引号 = `SyntaxError`（脚本**没启动**却当"跑完了"）→ 先 `python3 -c "import ast;ast.parse(open('x.py').read())"` 再拉起。
2. **丢包率别用 `sed -n '$p'`**：`ping` 输出的**倒数第二行**才是统计行（最后一行是 RTT）→ 用 `grep 'packet loss'`（旧写法只拿到 RTT → 假"0% 丢包"）。
3. **健康 grep 带冒号 `WARNING:`**：驱动日志里存在 "WARNING" 纯文本，不区分冒号会把正常日志判成内核告警。
4. **后台脚本会被父 shell 会话连带杀掉**（父会话退出即 SIGHUP）→ `setsid nohup <cmd> < /dev/null &`。
5. **每步自证**：登录后 `echo MARK` 回读、参数写入后回读、命令输出非空、`uptime` 单调 —— 这一节与上面「三禁」是同一件事的两面：**没有回读就没有事实**（"脚本跑完了/测试通过了"必须由返回内容证明，不能由脚本没报错推断）。

## 参考
- `serial-debug` skill — 通用串口交互
- `<项目A>-stress-test` skill — 压力测试上下文
