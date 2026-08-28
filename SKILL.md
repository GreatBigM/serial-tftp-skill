---
name: serial-tftp
description: 嵌入式串口交互 + TFTP 刷机一站式：串口连接/盲打登录/命令执行/故障排查 + 环境预检/模式判断/配网烧录/完成验证。
version: 1.9.1
category: devops
metadata:
  agent:
    tags: [serial, uart, ttyUSB, tftp, 刷机, 烧录, 串口, 调试]
    triggers: [tftp, 刷机, 烧录, mai_tftp, tftpboot, auto_update_tftp, 串口, serial, ttyUSB, uboot, 串口登录, 盲打登录, 波特率, 串口无数据, 串口乱码]
---

## ⚡ 快速开始（AI 替你完成）

**本技能的使用方式是：用户指挥 AI，AI 替用户执行。用户不面对命令行。**

```
用户: 帮我配置烧录参数 / 烧录 / 刷机
AI:  读本文件参数说明 → 识别缺失参数 (ipaddr/serverip/tftp_dir)
AI:  对话层向用户询问缺失参数
用户: 设备 10.0.0.5，目录 /mnt/data/xxx
AI:  执行烧录流程（按本文件流程铁律）→ 回报结果
```

**铁律：用户说"烧录"→ AI 直接执行烧录流程，不解释手动步骤，不反问"你要不要先配置"。**
参数缺失 → AI 在对话层问，拿齐就干。全程不需要用户手动跑命令。

> **模板定位（agent 必读）**：
> - `scripts/` 下的脚本是**伪代码参考**：展示烧录流程长什么样、有哪些坑（如 `\r` 行终止、日志洪流、U-Boot 打断时机）
> - **约束的是流程行为，不是代码细节**——AI 执行时行为必须符合本文件流程铁律（五步顺序/先查后动/`\r` 不 `\n`/烧录后验证/失败不重烧），具体实现方式不限
> - 有 `serial-tftp` 命令可直接用（省事、含版本门卫）；没有或环境不适配时，AI 按流程自行实现等价操作也符合本技能
> - 预检失败分两类：参数缺失（AI 问齐再补） vs 环境问题（TFTP 服务/目录/固件——提示用户修复）
> - 烧录完成回报：新 IP（串口 ifconfig eth0 查）、启动状态、剩余验证项

## 便捷入口（可选）

有 `serial-tftp` 命令时可直接调用（省事，含版本门卫）；没有时 AI 按流程自行实现等价操作：

```bash
serial-tftp flash                 # 一键烧录（主命令）
serial-tftp flash --at-uboot      # 设备已在 U-Boot
serial-tftp setup                 # 交互式参数设定（终端直连）
serial-tftp config show           # 查看配置缓存
serial-tftp cmd 'ifconfig eth0'   # 串口发单条命令
serial-tftp capture               # 启动日志采集
serial-tftp reboot-capture        # 循环重启采集
serial-tftp stress --count 20     # 重启压力测试
serial-tftp shell                 # 交互式 U-Boot shell
```

## 终端直连（无 AI 时的备选）

用户自己跑脚本的场景（脚本化 / 无 agent 环境）：

```bash
# 方式 A（交互式向导）：逐项输入，回车接受默认值，q 取消
python3 <skill_dir>/scripts/auto-uboot-interrupt.py setup

# 方式 B（命令行直设）：适合已知参数
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config ipaddr <DEV_IP>
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config serverip <HOST_IP>
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config tftp-dir <TFTP_DIR>

# 一键烧录
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash

# 设备已在 U-Boot
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash --at-uboot

# 串口发命令
python3 <skill_dir>/scripts/serial_cmd.py 'ifconfig eth0'

# 查看/管理配置
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config show
```

---

## 完整工作流程（五步）

```
Step 0: 环境预检
  ├─ TFTP 服务运行中？
  ├─ TFTP 目录正确？固件文件存在？
  ├─ 串口存在？（--port 或自动发现）
  └─ 设备 IP / 服务器 IP 已设定？

Step 1: 建立串口连接
  ├─ 波特率：缓存优先 / 自动探测 / 手动指定
  └─ 端口预检：fuser -k 清残留 + stty 重置 + 回显验证

Step 2: 模式判断
  ├─ uboot → 直接进 Step 3
  ├─ linux → login → reboot → 打断 U-Boot（提示符探测：行尾 # 或 =>，非硬编码项目名）
  └─ unknown → 检查波特率 / --at-uboot / 物理断电

Step 3: 配网 + 烧录
  ├─ setenv ipaddr/netmask/gatewayip/serverip
  ├─ IP 冲突预检：ping 设备自身 IP，通 = 被占用 → 换 IP（根因见 `references/troubleshooting.md`）
  ├─ ping 验证连通性（可选）
  └─ mai_tftp → 监控擦写输出

Step 4: 等待重启
  ├─ 检测 app 活信号 (cpu_loading=/seq:) 或 login:
  ├─ Kernel panic → 烧录失败
  └─ 超时 ≠ 失败（等 60-90s 再判断）

失败处理 → 见 `references/troubleshooting.md`（排障参考，按需查）
```

---

## Step 0: 环境预检

首次使用需设定三个参数（自动缓存）：

| 参数 | 设定 | 说明 |
|------|------|------|
| TFTP 目录 | `config tftp-dir <路径>` | 含 auto_update_tftp.txt + *_NOR_ALL.bin |
| 设备 IP | `config ipaddr <IP>` | U-Boot 中设备以太网 IP |
| 服务器 IP | `config serverip <IP>` | 开发机 IP |

**TFTP server 搭建（一次性）：**
```bash
sudo apt-get install -y tftpd-hpa
# /etc/default/tftpd-hpa: TFTP_DIRECTORY="<TFTP_DIR>"
sudo systemctl restart tftpd-hpa && sudo systemctl enable tftpd-hpa
```

---

## Step 1: 串口连接 + 波特率

**波特率缓存：** 首次自动探测 [115200, 921600, 1500000, 57600, 9600]，后续读缓存零等待。

| 项目 | 波特率 |
|------|--------|
| <项目> | 115200 |
| <项目> | **921600** |

管理：`config baud [值|reset|detect]`

**端口预检（自动）：** fuser -k → stty 重置 → 发 `\r` 验证回显。

---

## Step 2: 模式判断

| 模式 | 标志 | 处理 |
|------|------|------|
| uboot | `<项目>#` / `=>` | 直接 Step 3 |
| linux | `login:` / `root@` | login → reboot → 砸回车 20s |
| unknown | 无响应 | 检查波特率 / --at-uboot / 断电 |

**U-Boot 打断要点：**
- `CONFIG_BOOTDELAY=1`（~1s），reboot 后持续砸回车
- 只认交互提示符，不认 "U-Boot" banner
- 边砸边读，避免缓冲溢出

---

## Step 3: 配网 + 烧录

```
setenv ipaddr <DEV_IP>
setenv netmask 255.255.254.0
setenv gatewayip <HOST_IP>
setenv serverip <HOST_IP>
mai_tftp
```

ping 验证默认开启（`--no-ping` 跳过）。mai_tftp 首次初始化 PHY，ping 失败不阻断。

---

## Step 4: 等待重启

| 信号 | 判定 |
|------|------|
| `cpu_loading=` / `seq:` | ✅ 成功 |
| `login:` | ✅ 成功 |
| `Kernel panic` | ❌ 失败 |
| 超时 30s | ⚠️ 等 60-90s 人工确认 |

**烧录后：** 串口 `ifconfig eth0` 查新 IP → `adb kill-server && adb connect <新IP>:5555`

---

## 配置管理

所有参数缓存在 `~/.config/serial-tftp/config.json`，首次指定后自动复用。

```bash
config show              # 全部
config baud 921600       # 波特率
config port /dev/ttyUSB1 # 串口
config ipaddr <IP>       # 设备 IP
config serverip <IP>     # 服务器 IP
config tftp-dir <DIR>    # TFTP 目录
config reset             # 清除全部
```

优先级：`--参数` > 缓存 > 默认值。CLI 指定同时更新缓存。

---

## 项目配置表

| 项目 | TFTP 目录 | 设备 IP | 擦除范围 | 波特率 |
|------|-----------|---------|---------|--------|
| <项目> | `<TFTP_DIR>` | <DEV_IP> | 0x1000000（全） | 115200 |
| <项目> | `<TFTP_DIR>` | <DEV_IP> | 0xf60000（部分）/ 0x1000000 | **921600** |

---

## auto_update_tftp.txt

```
tftpboot 0x80600000 <项目>_NOR_ALL.bin
sf probe
sf erase 0x0 <擦除范围>
sf write 0x80600000 0x0 <擦除范围>
reset
%
```

改擦除范围需同时改源码 + 产物两份。

---

## 串口工具

| 脚本 | 用途 |
|------|------|
| `serial_cmd.py '<cmd>' [timeout] [baud]` | 发单条命令读输出 |
| `capture_boot_log.py [baud] [sec]` | 完整启动日志采集 |
| `reboot_capture.py [次数] [秒数] [baud]` | 循环重启采集 |
| `reboot-stress.py --count N` | 重启压力测试 |

所有脚本共享配置缓存，波特率自动复用。

---

## 串口调试（非烧录场景，并入自 serial-debug）

烧录之外的串口日常：登录、命令执行、查状态、设 IP、启 adbd、故障排查。ADB 不可用时的首选通道。

### 铁律：第一步永远是发 CR 判断模式

盲打发 3 次 CR（`\r`，0x0d）观察回显，**不假设设备状态**：

| 回显 | 当前模式 | 下一步 |
|------|---------|--------|
| `U-Boot>` / `Hit any key` | U-Boot | 烧录/打断启动（见上文） |
| `login:` | 未登录 | 走「登录」 |
| shell 提示符（`#`/`~#`） | 已登录 | 直接发命令，**不要发 root**（会被当命令执行） |
| 无回显/乱码/噪声 | 波特率错或 TX 不通 | 走「故障速查」 |

### 连接建立

1. 串口设备 `/dev/ttyUSB0`，权限 `sudo chmod 666 /dev/ttyUSB0`
2. 波特率项目相关：逐一尝试 [921600, 115200, 1500000, 57600]。波特率错 → 全是二进制乱码
3. 第一件事确认双向（TX 通）——发唯一标记看回显，TX 不通则串口方案不可行
4. 先 reset 串口参数再读写：`sudo stty -F /dev/ttyUSB0 <BAUD> cs8 -cstopb -parenb raw -echo -echoe -echok`
5. 行终止符用 `\r`（CR），**LF 被 getty 忽略，输入静默丢失**

### 盲打登录

用户 `root`，密码为空（直接回车）。设备日志可能持续淹没提示符，登录前先 drain。

```python
import serial, time
BAUD = 921600   # 项目相关：常见 921600 / 115200
ser = serial.Serial('/dev/ttyUSB0', BAUD, timeout=0.5)
time.sleep(0.3); ser.reset_input_buffer()
ser.write(b'\r\n'); time.sleep(1.5)   # 唤醒
ser.read(ser.in_waiting)              # drain noise
ser.write(b'root\r'); time.sleep(0.5)
ser.write(b'\r'); time.sleep(0.5)      # 密码为空：直接回车
data = ser.read(4096)
print(data.decode('utf-8', errors='replace'))
ser.close()
```

### 命令执行模式

| 场景 | 方式 |
|------|------|
| 简单命令 | 直接发 + 读响应 |
| 需要输出过滤 | 轻量级单命令（后台读 + echo `\r`） |
| 复杂/多步 | 脚本隔离法（写脚本执行，防截断） |
| 长任务 | 后台执行（`&`），SIGHUP 不杀 |

### 常见操作

- 设 IP：`ifconfig eth0 <IP> netmask 255.255.255.0 up`（设完确认 ifconfig 回显）
- 启 adbd：`adbd &`（先查是否已跑 `ps|grep adbd`）
- 杀进程：`ps|grep <name>|grep -v grep` 拿 PID → `kill -9 <pid>`
- 查状态：`ps`、`ifconfig`、`route`、`cat /proc/meminfo`（日志洪流时用 grep 过滤）

### 故障速查

| 症状 | 原因 | 处理 |
|------|------|------|
| 串口无数据 | 权限/驱动/波特率 | 见 references/serial-debug-diagnostics.md |
| 全乱码 | 波特率错 | 换 [921600, 115200, 1500000, 57600] 逐一试 |
| 命令发了没执行 | LF 行终止符 | 改用 `\r`（CR） |
| 日志洪流淹没 | 设备日志持续刷 | 登录前 drain，命令输出用 grep 过滤 |
| 长命令截断 | 终端缓冲限制 | 脚本隔离法 |
| login 反复掉线 | getty 竞争/噪声 | 见 references/serial-debug-diagnostics.md |

---

## 手动刷机（备选）

```bash
# 串口敲回车判断模式
# Linux: root + 空密码 → reboot → 持续回车 12s
# U-Boot:
setenv ipaddr <DEV_IP>
setenv netmask 255.255.254.0
setenv serverip <HOST_IP>
mai_tftp
# 等 90-120s
```

---

## 参考资料

- `references/troubleshooting.md` — 烧录排障（失败恢复速查、各步骤失败处理、反模式）
- `references/serial-debug-diagnostics.md` — 串口连接诊断（权限/驱动/波特率/getty 竞争）
- `references/command-execution-patterns.md` — 命令执行模式（单命令/脚本隔离/后台任务）
- `references/ingenic-serial-boot-login.md` — 盲打登录细节
- `references/serial-console-notes.md` — 串口交互经验（登录策略、故障诊断、陷阱汇总）
- `references/post-flash-md5-verification.md` — 烧录后 MD5 三方对齐验证（铁律）
- `references/hm6502-full-erase-flash-20260717.md` — 全擦烧录实录
- `references/hm6502-partial-erase-flash-at-uboot-recovery-20260717.md` — 部分擦除 + U-Boot 恢复
- `references/hm6502-flash-timing-zb25vq128.md` — 烧录 timing & ZB25VQ128 变体
- `references/tftp-flash-baud-uboot-recovery.md` — 波特率 & U-Boot 打断恢复
- `references/20260717-shell-timeout-recovery.md` — shell 超时 --at-uboot 恢复
- `references/bricked-nor-recovery.md` — 变砖恢复（NOR 损坏）
- `references/nor-all-bin-layout-recovery.md` — NOR_ALL.bin 布局恢复与备选 Slot
- `references/flash-network-diagnosis-anti-pattern-20260722.md` — 烧录网络诊断反模式
- `references/flash-verify-boot-changes.md` — 烧录后 boot 序列变更验证
- `references/flashing-concurrent-prevention.md` — 烧录并发冲突预防
- `references/build-output-staleness-verification.md` — 构建产物一致性验证
- `references/post-flash-wifi-reconnect.md` — 烧录后 WiFi 重连
- `references/skill-failure-handling.md` — 技能失败处理原则

> 以上烧录类参考资料 2026-08-05 并入（原 ingenic-basic-tftp-flash 技能）。

## 适用平台

Ingenic T32 家族，16MB SPI NOR Flash，U-Boot `mai_tftp` 命令。
串口通道适用：设备离线 / adbd 挂死 / kernel panic / 首次刷机 / 全片重刷。
