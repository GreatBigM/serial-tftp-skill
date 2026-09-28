---
name: serial-tftp
description: 嵌入式串口交互 + TFTP 刷机一站式：串口连接/盲打登录/命令执行/故障排查 + 环境预检/模式判断/配网烧录/完成验证。
version: 2.0.3
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
> - 脚本在 `<skill_dir>/scripts/` 内，agent 按需调用（见「脚本入口」章节）；无全局命令、无 PATH 注册
> - 预检失败分两类：参数缺失（AI 问齐再补） vs 环境问题（TFTP 服务/目录/固件——提示用户修复）
> - 烧录完成回报：新 IP（串口 ifconfig eth0 查）、启动状态、剩余验证项

## 脚本入口（skill 目录内，不全局注册）

本技能的所有脚本都在 `<skill_dir>/scripts/` 内，由 agent 按需调用（`<skill_dir>` = 本 SKILL.md 所在目录）。不提供全局命令、不注册 PATH 入口，完全归属于 agent：

```bash
# 统一入口 wrapper（skill 目录内，agent 可选调用）
python3 <skill_dir>/scripts/serial-tftp flash            # 一键烧录（主命令）
python3 <skill_dir>/scripts/serial-tftp flash --at-uboot # 设备已在 U-Boot
python3 <skill_dir>/scripts/serial-tftp setup            # 交互式参数设定
python3 <skill_dir>/scripts/serial-tftp config show      # 查看配置缓存
python3 <skill_dir>/scripts/serial-tftp cmd 'ifconfig eth0'  # 串口发单条命令
python3 <skill_dir>/scripts/serial-tftp capture          # 启动日志采集
python3 <skill_dir>/scripts/serial-tftp reboot-capture   # 循环重启采集
python3 <skill_dir>/scripts/serial-tftp stress --count 20    # 重启压力测试
python3 <skill_dir>/scripts/serial-tftp shell            # 交互式 U-Boot shell

# 或直接调用原语脚本（等价）
python3 <skill_dir>/scripts/auto-uboot-interrupt.py setup              # 交互式向导
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config ipaddr <DEV_IP>
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config serverip <HOST_IP>
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config tftp-dir <TFTP_DIR>
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash              # 一键烧录
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash --at-uboot   # 设备已在 U-Boot
python3 <skill_dir>/scripts/serial_cmd.py 'ifconfig eth0'             # 串口发命令
python3 <skill_dir>/scripts/auto-uboot-interrupt.py config show       # 查看配置
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
  │   ⚠ 2026-09-24 修：此预检曾因 `f"ping {ip}\\r"` 写成**字面反斜杠+r**而从未真的 ping 过（静默失效），
  │   且残渣会与下一条命令粘成一行；现在统一走 `uboot_cmd()`（真 `\r` + 写前清缓冲 + 读提示符）
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

ping 验证默认开启（`--no-ping` 跳过，同时跳过 IP 冲突预检）。mai_tftp 首次初始化 PHY，ping 失败不阻断。

**写 U-Boot 的纪律（踩过坑）**：一律用 `uboot_cmd(ser, cmd)` —— 真正的 `\r` 只在它内部拼，
写前 `reset_input_buffer()`，读回以提示符 `#` 为界。历史上 IP 冲突预检把 `\r` 写成字面反斜杠+r，
U-Boot 收不到 CR ⇒ 命令不执行、文本堆在输入缓冲里直到下一条真 CR 才被一起结清
（现场：`PRJ009# ping A\rping A\rping B` 粘成一行）。

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
6. 设备 shell **吃掉一层反斜杠** ⇒ echo 写文件/传参的转义必须**双写**：换行 `\\n`、引号 `\\42`、空格 `\\040`、tab `\\011`。单写会静默写出错内容（命令不报错）⇒ 写完必须 md5sum 比对。**不只 `\n` 要双写**——2026-09-17 按「只 \n」理解写了一版，实机全错
7. 双引号会被设备 shell 吞掉 ⇒ 主机侧卡在 `> ` 续行（脱出：依次发 `'`、`"`，或 Ctrl+D）；busybox `base64 -d` 可能静默产出 0 字节文件，别用它传文件
8. **busybox ash 不展开重定向目标里的 glob**：`echo 822 > $G/*/fixed_rate_idx` 报 `nonexistent directory`，**错误信息里带未展开的星号**（识别特征，看到星号就是没展开，别查权限/挂载）；同一变量在 `for` 里却能展开（POSIX：重定向的词不做路径名展开，bash 宽容、ash 不宽容）⇒ 先 `for f in $G/*/f; do … > "$f"; done`。配套设备侧常识：常无 `head`/`tail`（末尾 N 行用 `awk '{a[NR]=$0} END{for(i=…)}'`）、无 `iw`/`iwpriv`、**debugfs 不自动挂**（`mount -t debugfs none /sys/kernel/debug`）且重载后 phy 号会变 ⇒ 路径一律写 glob（`phy*/rwnx/rc/*/stats`），写死 phy 号会静默读到空。明细 → qwiki `hm6502_wifi/20260922-device-shell-and-rcstats-pitfalls.md`

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
| 有回显但命令不执行 | 未登录 / 业务槽 getty 丢失 | 见 references/serial-debug-diagnostics.md；业务槽常见"只剩回显、命令不执行"且该 boot 无网 ⇒ 只能重启恢复 |
| 反复 login 失败后彻底无 shell | 顶到 init respawn 限额 | **别反复重试**：提示符出现时一次登录（root + 空密码直接进）；实测 ~8 次失败后本 boot 再无 getty ⇒ 重启设备 |

---

## ⛔ 烧录门禁与高频坑（2026-09-11 沉淀，烧前必读）

> 完整账（含代价与分区类坑）：qwiki `hm6502_wifi/20260911-flash-partition-pitfalls-avoidance.md`
> 同步说明：本 skill 与 `~/.pi/agent/skills/serial-tftp/` 同源双份，改动须**双写**（2026-09-12 由反思 cron 补齐门禁段与 scripts 硬化）

**烧前 8 条门禁（缺一不烧）**
1. 产物新鲜：`system_b.img`/`NOR_ALL`/FIT 时间戳 ≥ `.ko` 时间戳
2. `.ko` 一致性用 **.text/.data 比对**（md5 因 strip 必不同）
3. `auto_update_tftp.txt` 必须是**全量版**：`tftpboot <proj>_NOR_ALL.bin` + `sf erase 0x0 0xF70000`（范围与 `partition_layout/partitions.conf` 一致）
4. TFTP server 在跑且 `TFTP_DIRECTORY` = 产物目录（删 `out/` 后必须重启 server）
5. 本地自检：`curl -s tftp://127.0.0.1/<proj>_NOR_ALL.bin -o /dev/null -w '%{size_download}'` = 16777216
6. **串口单进程**：`fuser -v /dev/ttyUSB0` 为空（禁止后台+前台并发，会 `multiple access on port` 且输入错乱）
7. U-Boot env **四件套**并 `printenv` 核对：
   `setenv ipaddr 172.17.150.200; setenv netmask 255.255.255.0; setenv gatewayip 172.17.150.1; setenv serverip 172.17.151.6; mai_tftp`
8. 烧后反证：U-Boot 打印的 kernel/system 地址大小与布局一致；启动后 `/proc/version` 时间戳 + 新参数存在（防"烧了旧镜像"）

**高频坑**
- 只设 `ipaddr/serverip` → env 残留 `gatewayip=192.168.2.1` → `sending through gateway 192.168.2.1` + `T T T`（serverip 与设备不同网段）
- `mai_tftp` 无参走 CPSPR 解码 IP；CPSPR 空 → 兜底 10.3.2.4 → fetch 失败却像成功（**假阳性**）；脚本已改显式 `mai_tftp auto_update_tftp.txt` + 失败标记判负（`Retry count exceeded`/`Abort`/`No ethernet found`/`T T T`）+ 成功须见 `bytes written`
- **CPSPR 触发在本机 U-Boot 不可靠**（解锁→写→锁定→reboot 仍正常引导）；主路径 = 断电冷启动 + 上电瞬间连打 CR 抢 U-Boot
- GMAC 只由 `mai_tftp` 初始化：先单独 `ping`/`tftpboot` 会 `No ethernet found`
- 温重启挂死（负载态）会截断"reboot → 抢 U-Boot"路径 → 必须断电冷启动
- **非 shell 状态禁止盲发命令**：login 提示符下命令会被当用户名（一串 `Login incorrect`），先发 CR 判模式
- `pkill -f <name>` 会匹配自身命令行导致自杀；用 `pkill -f "[a]utoboot"` 或 `setsid`

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
