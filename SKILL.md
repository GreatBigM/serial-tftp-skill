---
name: serial-tftp
description: 嵌入式设备串口交互与 TFTP 刷机 — 环境预检、串口连接、模式判断、配网烧录、完成验证
version: 1.1.0
category: devops
metadata:
  hermes:
    triggers: [tftp, 刷机, 烧录, mai_tftp, tftpboot, auto_update_tftp, 串口, serial, ttyUSB, uboot, 串口登录]
---

## ⚡ 快速开始（AI 替你完成）

**本技能的使用方式是：用户指挥 AI，AI 替用户执行。用户不面对命令行。**

```
用户: 帮我配置烧录参数 / 烧录 / 刷机
AI:  读本文件参数说明 → 识别缺失参数 (ipaddr/serverip/tftp_dir)
AI:  对话层向用户询问缺失参数
用户: 设备 10.0.0.5，目录 /mnt/data/xxx
AI:  执行 serial-tftp（统一命令入口，含版本门卫）→ 回报结果
```

**铁律：用户说"烧录"→ AI 直接跑 `serial-tftp flash`，不解释手动步骤，不反问"你要不要先配置"。**
参数缺失 → AI 在对话层问，拿齐就干。全程不需要用户手动跑脚本。

> **AI 交互约定（agent 必读）**：
> - **统一入口：优先用 `serial-tftp` 命令**（脚本目录的 wrapper，含 py3 版本门卫 + 子命令分派），不要直接调 python 脚本
> - 参数写入方式：`serial-tftp config <key> <value>`（写缓存）或 `--ipaddr/--serverip/--tftp-dir`（单次）
> - 版本要求：Python 3.6+（2020 后系统自带）。py2-only 环境 wrapper 会友好提示，不会 SyntaxError 崩溃
> - 脚本 stdin 非 TTY 时会自动跳过交互向导、提示参数缺失——这是让 AI 走参数路径，不是 bug
> - 不要用管道喂 stdin 给向导（`printf '...' | script` 这类），向导只服务真实终端
> - 预检失败分两类：参数缺失（AI 问齐再补） vs 环境问题（TFTP 服务/目录/固件——提示用户修复）
> - 烧录完成回报：新 IP（串口 ifconfig eth0 查）、启动状态、剩余验证项

## serial-tftp 命令一览

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
  ├─ linux → login → reboot → 砸回车卡 U-Boot → Step 3
  └─ unknown → 检查波特率 / --at-uboot / 物理断电

Step 3: 配网 + 烧录
  ├─ setenv ipaddr/netmask/gatewayip/serverip
  ├─ ping 验证连通性（可选）
  └─ mai_tftp → 监控擦写输出

Step 4: 等待重启
  ├─ 检测 app 活信号 (cpu_loading=/seq:) 或 login:
  ├─ Kernel panic → 烧录失败
  └─ 超时 ≠ 失败（等 60-90s 再判断）
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

## 失败恢复

```
Step 0 失败 → 按提示修复（restart tftpd-hpa / 设 IP / 检查目录）
Step 1 无响应 → 物理断电 / 检查串口线
Step 2 打断失败 → 敲回车看状态：U-Boot# → --at-uboot / login → 重跑 / 无响应 → 断电
Step 3 TFTP 超时 → 检查网线/IP/目录 → --at-uboot 重试
Step 4 超时 → 等 60-90s，不要重烧
```

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

## 反模式

| 反模式 | 正确做法 |
|--------|---------|
| 没确认 U-Boot 就发 mai_tftp | 确认提示符再发 |
| 跨项目套擦除范围 | 先确认项目 |
| exit 1 就重烧 | 等 60-90s 确认 |
| 先讲步骤再跑脚本 | 直接跑脚本 |
| 烧完 adb connect 旧 IP | 串口查新 IP |
| 用 `\n` 作行终止符 | 用 `\r` |

---

## 参考资料

- `references/serial-console-notes.md` — 串口交互经验（登录策略、故障诊断、陷阱汇总）

## 适用平台

Ingenic T32 家族，16MB SPI NOR Flash，U-Boot `mai_tftp` 命令。
串口通道适用：设备离线 / adbd 挂死 / kernel panic / 首次刷机 / 全片重刷。
