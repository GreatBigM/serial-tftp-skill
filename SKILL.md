---
name: serial-tftp
description: 嵌入式串口交互 + TFTP 刷机一站式：串口连接/盲打登录/命令执行/故障排查 + 环境预检/模式判断/配网烧录/完成验证。
version: 2.1.4
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
用户: 设备 <IP-1>，目录 <代码树>/xxx
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
bash <skill_dir>/scripts/serial-tftp flash            # 一键烧录（主命令）
bash <skill_dir>/scripts/serial-tftp flash --at-uboot # 设备已在 U-Boot
bash <skill_dir>/scripts/serial-tftp setup            # 交互式参数设定
bash <skill_dir>/scripts/serial-tftp config show      # 查看配置缓存
bash <skill_dir>/scripts/serial-tftp cmd 'ifconfig eth0'  # 串口发单条命令
bash <skill_dir>/scripts/serial-tftp capture          # 启动日志采集
bash <skill_dir>/scripts/serial-tftp reboot-capture   # 循环重启采集
bash <skill_dir>/scripts/serial-tftp stress --count 20    # 重启压力测试
bash <skill_dir>/scripts/serial-tftp shell            # 交互式 U-Boot shell

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
| `<项目E>` | 115200 |
| `<项目A>` | **921600** |

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
（现场：`<项目E># ping A\rping A\rping B` 粘成一行）。

---

## Step 4: 等待重启

| 信号 | 判定 |
|------|------|
| `cpu_loading=` / `seq:` | ✅ 成功 |
| `login:` | ✅ 成功 |
| `Kernel panic` | ❌ 失败 |
| 超时 30s | ⚠️ 等 60-90s 人工确认 |

**烧录后：** 串口 `ifconfig eth0` 查新 IP → `adb kill-server && adb connect <新IP>:5555`
（部分镜像 eth0 走 DHCP，烧完自己就有 IP ⇒ 不必先串口设 IP，`adb connect` 直接可用；adb 拿到后后续采集都改走 adb，串口只留作兜底）

**烧后自证清单（按改动类型取用，别只报「烧录成功」）**
1. `cat /proc/uptime` < 120s ⇒ 确实是新启动，不是旧进程。
2. 本次改动逐项读回（sysctl/参数/版本号），与源码/脚本里写的**逐条对照**；只读回不回对照 = 没验证。
3. `/proc/version` 编译时间戳 + 新增模块参数存在（防烧到旧镜像）。

**抽测 ≠ 回归判据**：烧后跑一次 iperf3/功能抽测只证明「网络栈/链路可用」。业务态未调优的单次吞吐（常见 20–40Mbps 级塌陷）是设备常态，**不能拿来判回归**；回归结论必须在同 boot 内做 A/B/A' 或与同工况基线比。把抽测数字写进报告时要标明「不作判据」。

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
| `<项目E>` | `<TFTP_DIR>` | <DEV_IP> | 0x1000000（全） | 115200 |
| `<项目A>` | `<TFTP_DIR>` | <DEV_IP> | 0xf60000（部分）/ 0x1000000 | **921600** |

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
| `flash_config.py` | 统一配置管理 + 环境预检（`~/.config/serial-tftp/config.json`） |
| `serial_login_ip.py` | 精确时序登录 + 查 IP（日志洪流环境实测） |
| `serial_compat.py` | pyserial 兼容层（无 pyserial 时零依赖替代） |
| `publish-check.py` | 发布前脱敏闸门（自带 `--self-test`）；随 `scripts/` 一并安装，仅供本仓维护者使用，日常烧录不涉及 |

所有脚本共享配置缓存，波特率自动复用。

---

## 串口调试（非烧录场景，并入自 serial-debug）

烧录之外的串口日常：登录、命令执行、查状态、设 IP、启 adbd、故障排查。ADB 不可用时的首选通道。

### 铁律：第一步永远是发 CR 判断模式

盲打发 3 次 CR（`\r`，0x0d）观察回显，**不假设设备状态**：

> ⚠️ **探活有副作用：CR 会命中 U-Boot 的 `Hit any key` 而打断 autoboot**。设备恰在 2s 倒计时窗口内时，探活的 CR 会把本该正常引导的设备**停在 U-Boot**（2026-10-16 一天内两次实踩；恢复只能断电冷启动）。
> 纪律：先想清设备可能处在哪个阶段——**刚上电 / 刚 reboot 的 0–5s 内不要连发 CR**，先读串口日志等 `login:` 或提示符自然出现；误打断后 `reboot` 或断电冷启动复位，**不要继续在 U-Boot 里盲发命令**。

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
8. **busybox ash 不展开重定向目标里的 glob**：`echo 822 > $G/*/fixed_rate_idx` 报 `nonexistent directory`，**错误信息里带未展开的星号**（识别特征，看到星号就是没展开，别查权限/挂载）；同一变量在 `for` 里却能展开（POSIX：重定向的词不做路径名展开，bash 宽容、ash 不宽容）⇒ 先 `for f in $G/*/f; do … > "$f"; done`。配套设备侧常识：常无 `head`/`tail`（末尾 N 行用 `awk '{a[NR]=$0} END{for(i=…)}'`）、无 `iw`/`iwpriv`、**debugfs 不自动挂**（`mount -t debugfs none /sys/kernel/debug`）且重载后 phy 号会变 ⇒ 路径一律写 glob（`phy*/rwnx/rc/*/stats`），写死 phy 号会静默读到空。明细 → qwiki `<项目A>_wifi/20260922-device-shell-and-rcstats-pitfalls.md`

### 盲打登录

用户 `root`，密码**按固件版本**：旧版为空（直接回车），新版 `root`/`root`——**先用空密码，失败再试 `root`/`root`**。设备日志可能持续淹没提示符，登录前先 drain。

**先读提示符，再决定要不要登录**：有些镜像（supervisor 起 shell 的那种）开机**自动登录为 root**，串口上根本等不到 `login:`。此时若照抄登录序列盲发 `root`，它会被当命令执行、回显 `-sh: root: not found`，而脚本还误判「没有密码提示 = 登录失败」。判据：读到 `[root@<host>:]<dir>$` 一类提示符 ⇒ 已登录，直接发命令；连发 3 次 CR 仍只有提示符、没有 `login:` ⇒ 同上。`root: not found` 是本坑的识别特征，见到它不要重试登录。

> ⚠️ **淹没提示符的常常是业务 app 的 console 输出，不走 printk**（`dmesg` 里查不到、也不是内核日志）⇒ 提示符迟迟不出现时**别判「shell/getty 挂了」**：先 drain，再发唯一标记看回显确认双向，并按日志节奏挑窗口登录。2026-10-16 实测：业务 console 洪流把 `login:` 淹掉，被自动脚本误判为「无 getty」；真凶是洪流不是 getty（同类结局还有「反复 login 失败顶到 init respawn 限额」——见故障速查）。

```python
import serial, time
BAUD = 921600   # 项目相关：常见 921600 / 115200
ser = serial.Serial('/dev/ttyUSB0', BAUD, timeout=0.5)
time.sleep(0.3); ser.reset_input_buffer()
ser.write(b'\r\n'); time.sleep(1.5)   # 唤醒
ser.read(ser.in_waiting)              # drain noise
ser.write(b'root\r'); time.sleep(0.5)
ser.write(b'\r'); time.sleep(0.5)      # 密码按固件版本：旧固件为空 → 直接回车；新固件发 b'root\r'
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
| 反复 login 失败后彻底无 shell | 顶到 init respawn 限额 | **别反复重试**：提示符出现时一次登录（root + 按固件版本密码，先试空密码）；实测 ~8 次失败后本 boot 再无 getty ⇒ 重启设备 |
| 本 boot 再也没 shell，只能断电 | 在 `login:` 提示符出现**之前**连发一串命令/用户名（子代理高频），触发 CRASH_COUNT_LIMIT 崩溃计数 → getty 被杀 | 登录前**只发一个 CR**，看到 `login:` 再发用户名，一次一条等回显；已踩到就只能等重启/物理断电（11-03 实证：一次连发 7 条后 getty 被杀、该 boot 无网络恢复路径） |
| 命令发出后串口毫无反应（连提示符也不回） | `cat $(ls ...)` / `for f in $(...)` 前景命令的 glob 匹配为空 ⇒ `cat` 退化为读 stdin，把串口 shell 独占 | 先判空再 cat（`ls ... >/dev/null 2>&1 && cat ...`），或写脚本隔离；已挂死先发 Ctrl+C（多数可恢复），仍挂则重启 shell/设备 |
| 探活后设备停在 U-Boot（本该正常引导） | 发 CR 命中 autoboot 的 `Hit any key` | 断电冷启动复位；刚上电/刚 reboot 的 0–5s 内不连发 CR |
| 命令发出无回显 / 结果明显不对（实验空跑） | 上一条**前台命令还没返回提示符**，新命令被输入缓冲吞掉或粘成参数 | 等提示符回显再发下一条；长命令一律走后台 + 结果文件（`sh x.sh > /tmp/_r 2>&1 &`） |
| 「串口彻底没输出」疑似硬件坏 | 长命令在**业务日志洪流**下丢字符、引号没闭合 ⇒ shell 停在 `>`（PS2）续行，后续所有输入被当续行吞掉 | **先发 Ctrl+C** 回提示符再重试；Ctrl+C 能立刻恢复 ⇒ 不是线/口/FT232 问题，别换线换口（10-28 白耗 ~30min） |
| `-sh: root: not found` / `-sh: <用户名>: not found` | 设备**已自动登录**（无 `login:` 阶段），盲发的用户名被当命令执行 | 别再「重试登录」；看到 shell 提示符就直接发目标命令 |
| 脚本报 `ModuleNotFoundError: No module named 'serial'` | 跑脚本的解释器没装 pyserial（默认 `python3` 可能是 Hermes 自带解释器） | 用 `/usr/bin/python3` 跑（系统 site-packages 有 pyserial）；本技能的串口脚本一律显式用它 |

---

## 接手现场（会话交接 / 烧录可能正在跑）

接手别人的（或上个会话留下的）烧录/测量现场时，**先查在跑进程，再决定动不动串口**：

```bash
pgrep -af "auto-uboot-interrupt|serial-tftp|mai_tftp|flash"   # 有没有在跑的烧录
fuser -v /dev/ttyUSB*                                          # 串口有没有被占
ls -lt <change>/data/**/flash_*.log | head                     # 日志最后写入时间
```

- **有在跑的烧录 ⇒ 不要开串口、不要 kill、不要重烧**：烧录脚本自己会 `tee` 日志，直接 `tail` 日志判进度即可。并发打开串口 = `multiple access on port`，kill 掉可能正好卡在 `sf erase` 之后、写之前 —— 那才是真变砖。
- **日志停在 `sf erase 0x0 0xexxxx` 不是卡死**：16MB 擦除 + 写入 + 重启实测 ~100–150s 无新输出；判据是进程还在（`pgrep`）+ 日志文件 mtime 在动。
- **判完成看脚本自己的成功标记**（`Kernel booting` / 烧录流程完成 / login prompt），不要凭「`Bytes transferred` 出现」就宣布成功 —— 那只说明 TFTP 下载完了。
- 进程已消失但日志没写完成标记 ⇒ 才是失败，按 `references/troubleshooting.md` 恢复（`--at-uboot` / 断电冷启动）。
- 接手后第一件事把现场结论落盘（烧的是哪个 md5、当前 IP、adb 通不通），否则下一个会话又得重猜。

---

## ⛔ 烧录门禁与高频坑（2026-09-11 沉淀，烧前必读）

> 完整账（含代价与分区类坑）：qwiki `<项目A>_wifi/20260911-flash-partition-pitfalls-avoidance.md`
> 同步说明：pi 目标副本由 `bash install.sh --target pi` 安装到 `~/.pi/agent/skills/serial-tftp/`；改动本仓后重跑安装脚本即同步（不再有「双写」约定——先前提到的同源目录在本机并不存在）

**烧前 11 条门禁（缺一不烧）**
1. 产物新鲜：`system_b.img`/`NOR_ALL`/FIT 时间戳 ≥ `.ko` 时间戳
2. `.ko` 一致性用 **.text/.data 比对**（md5 因 strip 必不同）
3. `auto_update_tftp.txt` 必须是**全量版**：`tftpboot <proj>_NOR_ALL.bin` + `sf erase 0x0 0xF70000`（范围与 `partition_layout/partitions.conf` 一致）
4. TFTP server 在跑且 `TFTP_DIRECTORY` = 产物目录（删 `out/` 后必须重启 server）
5. 本地自检：`curl -s tftp://127.0.0.1/<proj>_NOR_ALL.bin -o /dev/null -w '%{size_download}'` = 16777216
6. **串口单进程**：`fuser -v /dev/ttyUSB0` 为空（禁止后台+前台并发，会 `multiple access on port` 且输入错乱）
7. U-Boot env **四件套**并 `printenv` 核对：
   `setenv ipaddr <IP-2>; setenv netmask 255.255.255.0; setenv gatewayip <IP-3>; setenv serverip <IP-4>; mai_tftp`
8. 烧后反证：U-Boot 打印的 kernel/system 地址大小与布局一致；启动后 `/proc/version` 时间戳 + 新参数存在（防"烧了旧镜像"）
9. **eth0 物理链路**：TFTP 只能走网口，设备 Linux 侧 `carrier=0`（没插线 / 交换机端口没起来）时 U-Boot 也拿不到链路 ⇒ 烧录必然空等。判据是 U-Boot 日志出现 `Link UP` + `Link is with 100M Speed`，**不是在 Linux 侧 ping**（双网的设备可能只有 wlan0 通）。
10. **烧录长度按产物 `stat` 动态生成 + 事后验真**（2026-10-23 实证）：<项目A> 一次沿用旧常量 `0x541200`（实际 `0x542200`）少写 `0xE00` → FIT `RSA` 校验 −13 后 U-Boot **自动 recover 回 A 分区**，串口依旧打印 `Written: OK` ⇒ 白烧一轮还误判「新 ko 没生效」。判据链：`Written: OK` + FIT `RSA ... OK` **不等于生效**，必须启动后核 **`srcversion`**（`cat /sys/module/<mod>/srcversion` 或 `strings <ko>`）**+ `.text` 逐字节/`.ko` md5** 与产物一致，并确认设备跑的是 B 分区（`/proc/cmdline` 分区参数）。
11. **擦写脚本必须硬门控**（2026-11-02 实证，代价 = 设备变砖）：任何 `sf erase`/`sf write` 都要整体包在「tftp 已返回 `Bytes transferred = <全量>`」**之后**，任一步失败立即 `exit`。只门控 `reset` 等于没门控——tftp 报 `No ethernet found` 后脚本照样整片擦写，把从未加载的 RAM 垃圾写进 NOR `0x0–0xef0000`，U-Boot 签名头被毁、串口全哑、CPSPR/TFTP/adb/sysrq 全断，只能 SD 卡启动恢复（见 `references/bricked-nor-recovery.md`）。**优先用仓库现成脚本**（`mai_tftp auto_update_tftp.txt` 逐行执行、天然门控），不要自写裸 `tftpboot` + `sf` 序列。

**高频坑**
- **`rmmod` 必崩 ⇒ 驱动 A/B 只能烧镜像**（2026-10-23 实证，<项目A> AIC8800）：`rmmod aic8800_fdrv` 崩在 `aicwf_rx_deinit+0xec → kthread_stop → __put_task_struct → exit_creds`（BadVA=0），模块卡 `Unloading`、`reboot` 无效，但 **`echo b > /proc/sysrq-trigger` 免断电强制复位**。⇒ 换 `.ko` 做 A/B 的路线在带 RX 线程的驱动上先验一次 `rmmod` 再规划，否则整轮实验作废
- 只设 `ipaddr/serverip` → env 残留 `gatewayip=<IP-5>` → `sending through gateway <IP-5>` + `T T T`（serverip 与设备不同网段）
- `mai_tftp` 无参走 CPSPR 解码 IP；CPSPR 空 → 兜底 <IP-6> → fetch 失败却像成功（**假阳性**）；脚本已改显式 `mai_tftp auto_update_tftp.txt` + 失败标记判负（`Retry count exceeded`/`Abort`/`No ethernet found`/`T T T`）+ 成功须见 `bytes written`
- **CPSPR 触发可用性随内核变化**（判据 = 内核是否带 `AF_SIGNATURE` 保护，与成对 skill `adb-tftp` 同口径）：无保护内核解锁→写→锁定→reboot 仍正常引导（不进 TFTP）；带保护内核（2026-09-18 修复）实测 `Mod: CPSPR = 0x97060909` 活过 reboot ⇒ **换内核/换镜像必重测**。稳妥主路径仍 = 断电冷启动 + 上电瞬间连打 CR 抢 U-Boot。依据：qwiki `projects/<项目A>_wifi/20260918-cpspr-af-signature-515-regression.md`
- GMAC 只由 `mai_tftp` 初始化：先单独 `ping`/`tftpboot` 会 `No ethernet found` ⇒ **派生铁律：不许绕过 `mai_tftp` 自写 `tftpboot`+`sf` 组合**（2026-11-02 烧砖直接原因；坑早写在同一条里仍被绕过 ⇒ 安全设计要长在脚本里，不靠人记）
- 温重启挂死（负载态）会截断"reboot → 抢 U-Boot"路径 → 必须断电冷启动
- **非 shell 状态禁止盲发命令**：login 提示符下命令会被当用户名（一串 `Login incorrect`），先发 CR 判模式
- `pkill -f <name>` 会匹配自身命令行导致自杀；用 `pkill -f "[a]utoboot"` 或 `setsid`

---

## 手动刷机（备选）

```bash
# 串口敲回车判断模式
# Linux: root + 密码（先试空密码，失败再 root/root）→ reboot → 持续回车 12s
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
- `references/projA-full-erase-flash-20260717.md` — 全擦烧录实录
- `references/projA-partial-erase-flash-at-uboot-recovery-20260717.md` — 部分擦除 + U-Boot 恢复
- `references/projA-flash-timing-zb25vq128.md` — 烧录 timing & ZB25VQ128 变体
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
- `references/uboot-interrupt.md` — U-Boot 自动中断（打断 autoboot）
- `references/projA-serial.md` — <项目A> 串口参数
- `references/projA-serial-output-only.md` — <项目A> 串口只输出无输入（结论修正）
- `references/echo-to-serial-workflow.md` — Echo-to-Serial 工作流
- `references/full-boot-capture.md` — 完整上电日志采集（reboot 到 crash 全周期）
- `references/projA-reboot-capture-v9.md` — <项目A> 循环重启采集 v9 方案
- `references/userspace-probe-debugging.md` — 用户态 Probe 日志采集与诊断
- `references/miio-client-log-analysis.md` — miio_client 日志分析
- `references/mips-binary-disassembly.md` — MIPS 预编译二进制反汇编指南
- `references/working-python-patterns.md` — 可用 Python 模式（Busybox 串口环境实测）
- `references/network_setup.md` — <项目A> 开发环境网络配置
- `references/ingenic-isp-sensor-debug.md` — Ingenic T32 ISP/Sensor 调试
- `references/projE-auto-start-chain.md` — <项目E> 开机自启链 & 关掉 c_mi_ipc
- `references/projE-rmem-pool.md` — <项目E> rmem 池管理
- `references/projE-sensor-mclk-fix.md` — <项目E> os08f10 传感器 MCLK 配置修复

> 以上烧录类参考资料 2026-08-05 并入（原 ingenic-basic-tftp-flash 技能）。

## 适用平台

Ingenic T32 家族，16MB SPI NOR Flash，U-Boot `mai_tftp` 命令。
串口通道适用：设备离线 / adbd 挂死 / kernel panic / 首次刷机 / 全片重刷。
