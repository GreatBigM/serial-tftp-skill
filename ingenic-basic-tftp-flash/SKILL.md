---
name: ingenic-basic-tftp-flash
description: Ingenic T32 平台 设备厂商 设备 TFTP 刷机 — TFTP server 搭建、U-Boot mai_tftp 命令用法、auto_update_tftp.txt 格式、完整刷机流程

<!-- ═══════════════ TL;DR 摘要 ═══════════════ -->
## ⚡ 一键命令

```bash
# 全自动脚本
python3 ~/.hermes/skills/devops/ingenic-basic-tftp-flash/scripts/auto-uboot-interrupt.py flash --baud 921600

# 设备已在 U-Boot
python3 ~/.hermes/skills/devops/ingenic-basic-tftp-flash/scripts/auto-uboot-interrupt.py flash --at-uboot --baud 921600
```

**U-Boot 手动：** `setenv ipaddr <HOST_IP>; setenv serverip <HOST_IP>6; mai_tftp`

| 项目 | 波特率 | 擦除范围 |
|------|--------|---------|
| <项目> | **921600** | 0xf60000（部分）/ 0x1000000（全擦） |
| <项目> | 115200 | 0x1000000 |

**失败恢复：** Failed→串口见`<U-Boot提示符>#`则 `--at-uboot` / 无输出先试`--at-uboot`仍不成→断电 / exit1≠失败等60s确认 / FIT签名失败→system_a引导或全片含U-Boot
<!-- ════════════════════════════════════════ -->
category: devops
metadata:
  hermes:
    triggers: [tftp, 刷机, mai_tftp, tfptboot, auto_update_tftp]
---

## 🔀 通道选择（先看这里）

本 skill 是**串口通道**（U-Boot 打断），适用于：设备离线 / adbd 挂死 / kernel panic loop / 首次刷机 / adbd_report.conf 未配置 / U-Boot 环境损坏 / 全片重刷。**君正 T32 家族全部适用。**

**设备 ADB 在线且要日常迭代按分区烧（rootfs / system_b / algo / env）？** → 用 ADB CPSPR 通道（更快更静，同芯片方案家族通用，首次换项目需按分区表适配）。

## ⚡ 快速参考

**铁律：第一步永远是运行脚本，不是解释命令。** 用户说"烧录"时，直接 `terminal(background=true)` 跑 `auto-uboot-interrupt.py flash`。禁止先列出串口步骤、禁止先解释 U-Boot 命令、禁止让用户手动输入。脚本失败时再查错误信息排障或加参数重试。

**⚠️ 脚本路径说明：** `scripts/` 目录存在于本 skill 目录下，**不在项目根目录（如 `<TFTP_DIR>/`）中**。执行脚本时必须指明全路径或先 cd 到 skill 目录：

```bash
# ✅ 正确：用全路径（不限 CWD，推荐）
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash

# ✅ 正确：从 skill 目录运行
cd <skill_dir>/ingenic-basic-tftp-flash && python3 scripts/auto-uboot-interrupt.py flash

# ✅ 等效：用绝对路径运行
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash

# ❌ 错误：从项目根目录运行（无 scripts/ 目录）
cd <TFTP_DIR> && python3 scripts/auto-uboot-interrupt.py flash
```

**执行前预检（防重复启动）：** 脚本默认会 `fuser -k /dev/ttyUSB0` 清理残留进程。但如果已有烧录进程正在运行，kill 后再启动新进程可能中断正在进行的 erase/write，损坏 NOR。执行前先检查：

```bash
ps aux | grep -E "auto-uboot|ttyUSB0" | grep -v grep
# 有已存在进程时，先确认其状态再决定是否终止
```

**一键脚本（用全路径直接执行）：**
```bash
# 三步一键烧录：串口预检→登录→打断→TFTP→验证
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash

# 设备已在 U-Boot（如 kernel panic boot loop 恢复）
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash --at-uboot

# 跳过串口预检（fuser/stty 已在其他进程处理）
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash --no-precheck

# 仅打断进入 U-Boot shell（不刷机）
python3 <skill_dir>/scripts/auto-uboot-interrupt.py shell
```

> **Step 0 串口预检：** 脚本自动检测端口 → `fuser -k` 清残留进程 → `stty` 重置参数 → 发 `\\r` 验证回显。这些步骤已直接内置在 Python 脚本 `auto-uboot-interrupt.py` 中。

**🔥 失败恢复决策树（Fire when you see `Failed to interrupt U-Boot`）**

```
auto-uboot-interrupt.py flash 报 Failed to interrupt U-Boot
  │
  ▼ 立即发回车看串口返回（检查波特率 --baud！<项目>=921600）
  │
  ├── 看到 <U-Boot提示符># / => / <项目>#
  │   → ✅ 设备实际已在 U-Boot！
  │   → 脚本只是错过 ~1s bootdelay 检测窗口，设备状态完全正确
  │   → 立即 retry（不需放弃，不需断电）:
  │     python3 auto-uboot-interrupt.py flash --at-uboot --baud <波特率>
  │   → 这是 #1 恢复路径，已实战验证完全可靠
  │
  ├── 看到 login: / root@
  │   → 设备进了 Linux（autoboot 跑完了）
  │   → 等完全启动后重跑普通 flash（不加 --at-uboot）
  │
  └── 完全无输出（含 `shell` 命令超时无回显）
      → 先试 `--at-uboot`！串口可能处于过渡状态（reboot 后设备已回到 U-Boot 或正处于 Linux→U-Boot 过渡期），
        `shell` 命令 timeout 不一定是设备挂死。
      → `python3 scripts/auto-uboot-interrupt.py flash --at-uboot --baud <波特率>`
      → 2026-07-17 实战：第一次 `flash` 报 Failed to interrupt U-Boot → `shell` 超时无输出 → `--at-uboot` 成功烧录。
      → 若 `--at-uboot` 也失败（mai_tftp 发到 Linux shell 打坏终端），再物理断电重启。
```

TFTP 环境确认（开发机）：
```bash
cat /etc/default/tftpd-hpa | grep TFTP_DIRECTORY
# 不对则改：
sudo sed -i 's|TFTP_DIRECTORY=.*|TFTP_DIRECTORY="<TFTP_DIR>"|' /etc/default/tftpd-hpa
sudo systemctl restart tftpd-hpa
cd /tmp && echo -e "get <项目>_NOR_ALL.bin\\nquit" | tftp 127.0.0.1 && ls -lh <项目>_NOR_ALL.bin
```

串口刷机命令序列（波特率 115200）：

**第一步：判断设备当前模式**

打开串口后发一个回车，看返回什么：
```
# 如果看到 <U-Boot提示符># / <项目># / =>  → 直接在 U-Boot 中
# 如果看到 设备厂商 login: / [root@设备厂商:]$  → 在 Linux 中
# 如果无任何输出 → 设备未上电
```

**模式 A：已在 U-Boot（直接烧录）**
```
setenv ipaddr <DEV_IP>
setenv netmask 255.255.254.0
setenv gatewayip <HOST_IP>
setenv serverip <HOST_IP>6
mai_tftp
```

**模式 B：在 Linux 中（需重启进 U-Boot）**
```
# 登录
root
<回车>

# reboot + 立即持续砸回车 ~12s
# 覆盖 U-Boot 的 ~1s 倒计时窗口（CONFIG_BOOTDELAY=1 编译时固定）
reboot
# 立即猛按回车 12 秒...

# 抓到 U-Boot 后设网络烧录
# ⚠️ 确认 <U-Boot提示符># 提示符再发命令，发到 Linux shell 会打坏终端
setenv ipaddr <DEV_IP>
setenv netmask 255.255.254.0
setenv gatewayip <HOST_IP>
setenv serverip <HOST_IP>6
mai_tftp
```

> **说明：** U-Boot 的 bootdelay 是编译时固定值 `CONFIG_BOOTDELAY=1`（约 1s），`fw_setenv bootdelay` 写入的 env 变量 U-Boot 不读取。直接 reboot 后按回车即可，不需要 `fw_setenv bootdelay`。

**烧录后（脚本自动完成）：**
```
# 脚本等待约 20s 检测 login: 提示符 → 确认烧录成功
# 用串口查 IP 后 adb 连接
ifconfig eth0
adb connect <IP>:5555
```

> **串口噪音处理：** 脚本内置 retry 机制——首次登录失败后自动 `killall -9 apphilogcat c_mi_ipc miio_client 2>/dev/null` 降噪再重试。手动登录时同理。如果 `killall` 命令因日志洪流（如 AIM motion detection 每 ~300ms 刷屏）无法送达 shell，改用 `paramset ohos.ctl.stop apphilogcat` 通过 init 框架停止日志服务再重试。\n> **⚠️ 刷后 IP 会变（铁律，全擦和部分擦均适用）：** 无论全擦还是部分擦，DHCP 都可能分配新的 IP 地址。2026-07-17 实测：<项目> 部分擦（`0xef0000` 保留 env 分区）后，eth0 IP 从 `<HOST_IP>` 变为 `<HOST_IP>`。烧录后不要直接 `adb connect <旧IP>`。先 `adb kill-server` 断开所有旧连接，通过串口 `ifconfig eth0` 确认新 IP 后再连接。\n> **GPIO22（MJAC 复位引脚）：** 由 `init.sh:109-111` 导出并设为输出：`echo 22 > /sys/class/gpio/export; echo out > /sys/class/gpio/gpio22/direction`。c_mi_ipc、SDK、miio_client 均可通过 `/sys/class/gpio/gpio22/value` 控制复位。

## <项目>/<项目> U-Boot 打断策略

| 项目 | reboot 行为 | 进 U-Boot 方法 | 说明 |
|------|-----------|---------------|------|
| <项目> | `reboot` 正常工作 | `reboot` + 持续按回车 ~12s | 2026-06-24 实测：<项目> 当前固件（2026-06-24 编译）`reboot` 正常进 U-Boot，`auto-uboot-interrupt.py` 的 reboot 锤击法适用。不再需要 `echo b > /proc/sysrq-trigger`。 |
| <项目> | `reboot` 正常重启（当前固件已验证 2026-06-18） | `reboot` + 持续按回车 ~12s | reboot 触发正常重启，进入 U-Boot。冷启后 bootdelay=1（编译时固定 CONFIG_BOOTDELAY=1），需在 ~1s 窗口内按回车打断。`fw_setenv bootdelay` 不生效（U-Boot 不读取）。|

**推荐刷机流程：**
```
python3 scripts/auto-uboot-interrupt.py flash
# 三步：登录→reboot打断→TFTP烧录→等待~20s验证login
```

> **注意：** 不需要 `fw_setenv bootdelay`，U-Boot 不读取该变量。直接 reboot 后连续按回车即可覆盖倒计时窗口。

> **必须先确认 U-Boot 提示符再发 U-Boot 命令。** 如果没抓到 U-Boot（输出 `login:` 或 `root@`），`mai_tftp` 发到 Linux shell 会打坏终端（login 进程挂死，只能断电恢复）。这是 2026-06-17 <项目> 踩坑。

## 适用平台

- **<项目>** (Ingenic T32, <U-Boot提示符>) — auto_update_tftp.txt, 16MB SPI NOR **EN25QX128A**
- **<项目>** (Ingenic T32, <U-Boot提示符>) — auto_update_tftp.txt, 16MB SPI NOR EN25QX128A

## 前置条件

- 开发机 Ubuntu/Debian，串口线连接 `/dev/ttyUSB0`，115200 波特率
- 设备以太网口与开发机在同一网段
- 产物目录有 `<项目>_NOR_ALL.bin`（或对应项目的全量固件）和 `auto_update_tftp.txt`

### 预检清单（刷前必查）

| 检查项 | 命令 | 通过标准 |
|--------|------|---------|
| TFTP 目录路径 | `cat /etc/default/tftpd-hpa \| grep TFTP_DIRECTORY` | 指向当前项目产物目录 |
| 固件文件存在 | `ls -lh out/*/<项目>_NOR_ALL.bin` | 16MB，时间戳新鲜 |
| 所有本地 commit 已确认 | `cd <repo_root> && repo forall -c 'git log --oneline @{u}..HEAD 2>/dev/null \| head -3'` | unpushed commits 是需要的 |
| c_mi_ipc md5 | `md5sum out/*/.tmp/bin/c_mi_ipc` | 与设备 `adb shell md5sum /system/bin/c_mi_ipc` 一致 |
| pack_firmware 未过时 | 比较 NOR_ALL.bin vs c_mi_ipc 时间戳 | NOR_ALL.bin 应 ≥ c_mi_ipc |
| U-Boot/rootfs 改动后 NOR 镜像已重打包 | `ls -l --time-style=full out/image_*/<项目>_NOR_ALL.bin out/image_*/u-boot-with-spl.bin out/image_*/rootfs.img` | NOR_ALL.bin 时间戳 ≥ 所有组件（u-boot-with-spl.bin, rootfs.img） |

## 1. TFTP Server 配置

```bash
sudo apt-get install -y tftpd-hpa
```

配置 `/etc/default/tftpd-hpa`：
```ini
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="<TFTP_DIR>"   # 指向当前项目产物
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure"
```

重启服务：`sudo systemctl restart tftpd-hpa && sudo systemctl enable tftpd-hpa`

本地验证：`cd /tmp && echo -e "get <项目>_NOR_ALL.bin\\nquit" | tftp 127.0.0.1 && ls -lh <项目>_NOR_ALL.bin`

> 多项目共用开发机时，切项目刷机前必须确认 TFTP_DIRECTORY 指向正确的项目产物目录。

## 2. auto_update_tftp.txt

放在 TFTP 根目录（产物目录），`mai_tftp` 自动下载并逐行执行：

```
tftpboot 0x80600000 <项目>_NOR_ALL.bin
sf probe
sf erase 0x0 <擦除范围>
sf write 0x80600000 0x0 <擦除范围>
reset
% <- 文件结束标记
```

**擦除范围（项目相关）：**

| 项目 | 擦除范围 | 说明 |
|------|---------|------|
| <项目> | `0x1000000`（全 16MB） | 全片擦写，log 分区也被清空 |
| <项目> | `0x1000000`（全擦，16MB） | **2026-07-15 用户要求改为全擦**。auto_update_tftp.txt 源码+产物双份已改 `0xf60000`->`0x1000000`。全擦清空整片含 env/factory/log。注意：全擦后 env 分区被清空，U-Boot 默认环境变量生效，首次启动可能需 `env default -a` 重置（此 U-Boot 无 saveenv，断电后需重做） |

> **⚠️ <项目> 目前使用 `0x1000000`（全 16MB 擦写），但这是临时方案。** 原因：<项目> 没有烧录 MAC 地址，存在 bug 导致 log 分区残留旧 KV 数据会引发 SIGSEGV。后续修复后应改回部分擦，与 <项目> 默认行为一致。
>
> **<项目> 擦除范围说明：** 默认部分擦 `0xf60000`（保留尾部 ~640K log/data）。需要全擦时改为 `0x1000000`（整片 16MB）。全擦后 env 分区被清空，U-Boot 使用默认环境变量；<项目> 无 saveenv，断电后需在 U-Boot 中 `env default -a` 重置（仅内存生效，每次断电后需重做）。
>
> **⚠️ 旧版 skill 曾记 <项目> = `0xef0000`，但实际文件已演变为 `0xf60000`（分区布局调整后，2026-07-15 实测确认）。以实际文件内容为准，不盲信文档值。**

### 全擦/部分擦切换步骤

用户要求"全擦"时，修改 auto_update_tftp.txt 中的 `sf erase` 和 `sf write` 两个范围值：

```
部分擦（默认）: sf erase 0x0 0xf60000 / sf write 0x80600000 0x0 0xf60000
全擦（整片16MB）: sf erase 0x0 0x1000000 / sf write 0x80600000 0x0 0x1000000
```

1. 改源码（持久）: `device/soc/ingenic/pkg_tool/<项目>/auto_update_tftp.txt`
2. 改产物（立即生效）: `out/image_<项目>/auto_update_tftp.txt`
3. 确认 NOR_ALL.bin 大小 = `0x1000000`（16MB），与全擦范围匹配
4. 烧录后：env 被清 -> U-Boot 中 `env default -a` 重置环境变量（<项目> 无 saveenv，仅内存生效）

> 必须同时改源码 + 产物两份文件。只改产物的话下次 `make pack_firmware` 会被源码覆盖。

## 3. 手动刷机步骤（脚本不可用时备选）

**① Linux 登录**
```
root         ← 用户名
<回车>       ← 空密码
```

> 如果日志刷屏导致登录困难：`killall -9 apphilogcat c_mi_ipc miio_client 2>/dev/null` 降噪。

**② reboot + 打断 U-Boot**
```bash
reboot
# 立即持续发送回车 ~10s，覆盖 U-Boot 倒计时
```

**③ U-Boot 设网络**
```bash
setenv ipaddr <DEV_IP>
setenv netmask 255.255.254.0
setenv gatewayip <HOST_IP>
setenv serverip <HOST_IP>6
```

**④ mai_tftp**（等待 90-120s，自动烧录并重启）

**⑤ 等 login 提示符出现，确认烧录完成**
```bash
# login: 出现即表示烧录成功，用串口查 IP
ifconfig eth0
adb connect <IP>:5555
```

> 不要用 `run bootcmd` 替代 `mai_tftp` — bootcmd 读 NOR 本地内核，TFTP 远程升级必须用 `mai_tftp`。

### 3a. 设备已在 U-Boot 提示符下（常见场景）

如果设备因刷机中断、kernel panic 后 fallback 等原因已经停在 `<U-Boot提示符>#` 或 `=>` 提示符下，不需要 reboot + 打断步骤，直接从③开始：

```bash
# ③ U-Boot 设网络（确认主机 IP 和网段）
setenv ipaddr <HOST_IP>
setenv netmask 255.255.254.0
setenv serverip <HOST_IP>6    # 主机 IP

# ④ 执行烧录
mai_tftp
```

**分区级烧录（非全片）**：如果需要只烧 rootfs+system_b 而非全片 NOR_ALL.bin，可以先复用 `ingenic-adb-tftp-flash` skill 中的 gen_tftp_script.py 生成分区级 auto_update_tftp.txt：

```bash
python3 ~/.hermes/skills/devops/ingenic-adb-tftp-flash/scripts/gen_tftp_script.py \
    --project <项目> --output-dir <TFTP_DIR> rootfs system_b
```

该脚本生成的 `auto_update_tftp.txt` 可直接被 `mai_tftp` 使用，与串口 U-Boot 烧录完美兼容。选择 `rootfs system_b` 默认分区可保留 env/log/algo 等数据分区。

**⚠️ 注意：** 如果 auto_update_tftp.txt 此前是 `all` 模式（全片 NOR_ALL.bin），切到分区级烧录前必须重新生成脚本。直接用旧 `all` 脚本烧分区会擦除范围不匹配（NOR_ALL.bin 全擦 0x0-0x1000000 但分区擦 0x40000-0x250000），前者破坏 env/log 分区，后者保留。

## 4. U-Boot 其他网络命令

| 命令 | 用途 |
|------|------|
| `ping <ip>` | 测试网络连通性 |
| `tftpboot <addr> <file>` | 手动 TFTP 下载文件到内存 |
| `mai_tftp` | 设备厂商 定制：下载 auto_update_tftp.txt 并执行 |
| `setenv <var> <value>` | 设置环境变量 |
| `printenv` | 查看所有环境变量，含 `bootcmd` 和 `mtdparts` |

## 4a. NOR_ALL.bin 内部结构与 mtdparts

> ⚠️ **分区表可能已更新。** 以下是最新提交的标准布局。实际分区表以 `PRJ.h` 的 `BOOTARGS_SFCNOR_PARTITION` 为准。
> 详细的分区表（含所有变体和 <项目> 差异）见 `ingenic-adb-tftp-flash` skill 的「NOR 家族分区表」章节。

整个 NOR_ALL.bin 是连续写入 flash 的二进制大文件（16MB），内部按 `mtdparts` 分区。用 `printenv` 在 U-Boot 中可看到分区布局。

```
mtdparts=sfc0_nor:256k(boot),2368k(rootfs),5568k@0x290000(kernel_system_a),5568k@0x800000(kernel_system_b),...
system=1
```

典型 <项目> 布局：
| 分区 | 偏移 | 大小 | 内容 |
|------|------|------|------|
| boot | 0x0 | 256K | U-Boot SPL + U-Boot |
| rootfs | 0x40000 | 2368K | FIT image (kernel + dtb + squashfs) |
| kernel_system_a | 0x290000 | 5568K | FIT image (slot A, `system=0`) |
| kernel_system_b | 0x800000 | 5568K | FIT image (slot B, `system=1`) |
| algo | 0xD70000 | 1536K | 算法分区 |
| log/data | 末尾 | ~1MB | JFFS2 数据分区 |

`bootcmd` 决定从哪个 slot 启动 — 如 `sf0 read 0x80a00000 0x800000 0x600000;bootm 0x80a00000` 从 slot B 读 6MB。

## 4b. 从备选 slot 启动（烧录后 bootcmd 失败时恢复）

烧录后如果 `bootcmd` 指向的 slot 找不到内核（如手动重建 NOR_ALL.bin 时破坏了分区偏移），设备会停在 U-Boot 提示符。此时可以手动从另一个 slot 启动：

```bash
# 1) 查看布局
printenv                              # 看 bootcmd 和 mtdparts

# 2) 从备选 slot 读取内核并启动 (<项目>: slot A = 0x290000, slot B = 0x800000)
sf0 probe
sf0 read 0x80a00000 0x290000 0x600000   # 从 slot A 读 6MB
bootm 0x80a00000                        # 启动

# 或永久修复 bootcmd
setenv bootcmd 'sf0 probe;sf0 read 0x80a00000 0x290000 0x600000;bootm 0x80a00000'
saveenv
```

> ⚠️ `bootcmd` 中的读取偏移和大小来自 `mtdparts` 中对应分区的定义。先 `printenv` 确认当前位置，再决定从哪个备选 slot 读。不同项目偏移不同（<项目> 与 <项目> 不同）。

## 项目配置表

| 项目 | TFTP 目录 | 默认 U-Boot IP | Flash | 擦除范围 | 内存配置 | CMA | 串口波特率 | 进 U-Boot 方法 | U-Boot bootdelay |
|------|-----------|---------------|-------|---------|----------|-----|-----------|--------------|-----------------|
| <项目> | `<TFTP_DIR>` | 192.168.2.200 | EN25QX128A 16MB | **0x1000000**（全16MB） | mem=36M rmem=28M@0x2400000 | **8MB** | 115200（默认） | `reboot` + 持续按回车 ~12s | CONFIG_BOOTDELAY=1（~1秒窗口） |
| <项目> | `<TFTP_DIR>` | <HOST_IP>x | **EN25QX128A / ZB25VQ128** 16MB¹ | **0xf60000**（部分擦，默认）/ 0x1000000（全擦） | mem=85M rmem=43M@0x5500000 | 8MB | **921600**（`--baud 921600`，2026-07-17 用户实测纠正，非1500000） | `reboot` + 持续按回车 ~12s | CONFIG_BOOTDELAY=1 |

> ¹ <项目> flash 型号有变体：文档值为 EN25QX128A（EON），实测为 ZB25VQ128（Zbit Semiconductor）。两者均为 16MB SPI NOR，SF probe 自动识别，U-Boot 驱动兼容。

## auto_update_tftp.txt 擦除范围

**擦除范围取决于项目，不可跨项目套用：**

| 项目 | 擦除范围 | 说明 | 源文件 |
|------|---------|------|-------|
|| <项目> | `0x1000000`（全16MB） | ⚠️ 临时方案。未烧录MAC地址有bug，全擦可避免log分区残留KV数据导致SIGSEGV。后续修复后改回部分擦 | `device/soc/ingenic/pkg_tool/<项目>/auto_update_tftp.txt` |
|| <项目> | `0xf60000`（部分擦，默认） | 部分擦保留尾部 ~640K log/data。需要全擦时改为 `0x1000000` | `device/soc/ingenic/pkg_tool/<项目>/auto_update_tftp.txt` |

**坑：** <项目> 全擦是临时 bug 绕避，不是永久配置。<项目> 默认部分擦 `0xf60000`，用户明确要求"全擦"时改 `0x1000000`。不要因为 <项目> 临时需要全擦就认为 <项目> 默认也应该全擦 -- <项目> 默认保留 log/data 是正常行为，全擦仅在用户要求时切换。

## 6. 反模式

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
|| **跨项目套用擦除规则，不经确认直接修改 auto_update_tftp.txt** | 不同项目的擦除范围不同：<项目> 全擦 `0x1000000`（临时 bug 绕避），<项目> 默认部分擦 `0xf60000`。不确认就改 -> 改了还要改回来。浪费一轮烧录。 | 擦除范围是项目特定的，先确认项目需要再改。拿不准就问用户。**<项目> 全擦是临时 bug 绕避（未烧录 MAC 地址）。<项目> 默认部分擦 `0xf60000`，用户要求全擦时才改 `0x1000000`。** |
| `sf erase 0x0 0xf60000` 而非 `0x1000000`（仅 <项目>） | <项目>：log分区尾部不受擦除，旧JFFS2数据跨烧录保留。旧SDK的KV数据残留->新SDK读旧格式->SIGSEGV | <项目> 临时用全量16MB擦写 `sf erase 0x0 0x1000000`。**这是 bug 绕避，不是永久配置。** <项目> 默认用 `0xf60000`（部分擦保留log分区），不需要改。<项目> 修复后也改回部分擦。 |
| 没确认 U-Boot 提示符就执行 mai_tftp | `mai_tftp` 发到 Linux shell 会打坏终端，login 进程挂死，必须断电恢复（2026-06-17） | 确认 `<U-Boot提示符>#`/`=>` 再发 U-Boot 命令。看到 `login:` 或 `root@` 立即中止 |
| 刷完 c_mi_ipc 反复 SIGSEGV 崩溃（仅 <项目>） | log 分区残留旧 KV 数据导致。<项目> 改为 `0x1000000` 全量 16MB 擦除后问题完全消失。<项目> 无此问题（默认 `0xf60000` 即可） | <项目>：修改源文件 `device/soc/ingenic/pkg_tool/<项目>/auto_update_tftp.txt`，部分擦改为 `0x1000000` -> commit -> `make pack_firmware` -> 重烧。<项目>：默认不改。已触发时恢复：`rm -rf /data/* && reboot` |
| 改了 U-Boot 源码后只 `make INGENIC` + `make pack_firmware`，忘记 `make pack_all` | NOR_ALL.bin 未更新 U-Boot 改动 | 改 U-Boot 后 → `make INGENIC && make pack_all` |
| `reboot shutdown` 用于重启 | 内核死循环，必须物理断电恢复 | 永远只传 `reboot`，不加参数 |
| 烧录后不查 IP 直接连 ADB | DHCP 重分配，IP 变了连不上 | 切模式后重新 `ifconfig eth0` 查 IP |
| **先讲解手动步骤再执行脚本** | 用户说"烧录"后，AI 先列出 reboot → setenv → mai_tftp 等一串手工命令，而不是直接执行 auto-uboot-interrupt.py。用户纠正"你忘记技能了吗"。浪费一轮对话，让用户感觉 AI 没记住已有自动化工具。 | **听到"烧录"直接 terminal() 跑脚本。** 串口命令序列仅在脚本不可用时作为备选方案出现。技能有脚本就在 `快速参考` 第一条展示，不要跳到第3节的"手动刷机步骤"。 | | 脚本失败后直接手动 `sf erase 0 0x100000` + `sf write 0 0x1000000` → 只擦 1MB 写 16MB → NOR 未擦区域数据损坏 → U-Boot 启动区被破坏 → 设备变砖 | **技能失败时：** ①读 Usage/--help 看有没有参数能处理当前场景 ②读失败信息 ③修技能本身 ④只有技能完全不适用才创造新技能。**不要绕过技能。** |
| **试图用 ADB + dd 烧录内核代替 TFTP**（2026-07-01 <项目> 踩坑） | `flash_erase` 命令在设备上不存在（busybox 未集成 mtd-utils）。`flash_kernel.sh` 脚本尝试 `adb shell flash_erase` 失败后 fallback 到无擦除直接 dd -> NOR 旧数据和 uImage 混叠 -> MD5 不匹配 -> 重启后 kernel 仍运行旧版本。同时设备被 reboot，需重新等待启动，浪费 2 轮烧录时间。 | **烧录优先用 TFTP + U-Boot mai_tftp。** 后端（内核/驱动）改动后正确流程：`build_kernel.sh` 编译 -> `auto-uboot-interrupt.py flash` TFTP 烧录。ADB 仅适合推送用户态二进制到已运行的设备，不适用于 NOR flash 写入。如果误执行 flash_kernel.sh 把内核分区写脏了：TFTP 全量重新烧录一次即可恢复，无需担心数据残留。**注意**：设备 busybox 有 `flash_eraseall` applet（无 `flash_erase`/`flashcp`），CPSPR + 串口都失败时可用 `flash_eraseall -q /dev/mtdN && dd if=<img> of=/dev/mtdN bs=4096` 作为最后手段（见 ingenic-adb-tftp-flash skill「ADB 直写 mtd 分区」章节）。**cat 写 /dev/mtd 不可靠**（MD5 不匹配），必须用 dd。 |
| **auto-uboot-interrupt.py 在 <项目> 921600 波特率下 reboot 后未能打断 autoboot**（2026-07-15 踩坑，2026-07-17 波特率纠正为 921600，非 1500000） | 脚本 interrupt_uboot 在 reboot 后持续砸回车 12 秒，但 U-Boot bootdelay=1 秒窗口太短，reboot 到 U-Boot 启动有时间差，回车可能没覆盖到那个窗口。脚本误判打断成功（输出含 "U-Boot" 字样），继续发 mai_tftp 到了 Linux shell。autoboot 倒计时走完（"Hit any key to stop autoboot: 1 0"），设备正常启动了 Linux，TFTP 烧录根本没执行。 | ①检查串口日志确认是否真正进入 U-Boot（看 `<U-Boot提示符>#` 提示符，不要只看 "U-Boot" 字样）。②如果 autoboot 没被打断，手动串口控制：先 reboot，在倒计时窗口内手动按回车确认进入 U-Boot，再 setenv 网络 + mai_tftp。③或用 `--at-uboot` 参数（设备已在 U-Boot 时跳过打断步骤）。 |\n\n> **串口噪音处理：** 脚本内置 retry 机制——首次登录失败后自动 `killall -9 apphilogcat c_mi_ipc miio_client 2>/dev/null` 降噪再重试。手动登录时同理。如果 `killall` 命令因日志洪流（如 AIM motion detection 每 ~300ms 刷屏）无法送达 shell，改用 `paramset ohos.ctl.stop apphilogcat` 通过 init 框架停止日志服务再重试。

| 脚本运行后 terminal 输出完全为空 (0 字节、0 行) | 串口端口被上一个 session 的残留进程占用，或 pyserial 参数被污染。`stty` 重置后仍无输出时，设备可能处于半死状态（login 进程挂死或 U-Boot 中断后无响应）。 | Step 0 串口预检已自动处理 `fuser -k` + `stty` 重置 + 发 `\\r` 验证回显。如果仍无响应，物理断电重启设备。 |
| 传参 `--serial /dev/ttyUSB0` 而非 `--port /dev/ttyUSB0`（2026-07-17 踩坑） | `auto-uboot-interrupt.py` 的参数名是 `--port` 不是 `--serial`。错误参数会被 argparse 拒绝：`error: unrecognized arguments: --serial /dev/ttyUSB0`。加 `--port` 前浪费一轮修复错误。 | 记住参数名是 `--port`。查看 usage: `python3 auto-uboot-interrupt.py --help`。在使用任意 Python 脚本前先 `--help` 确认参数名，不要靠猜。已踩过坑：`h` 参数（实际是 `--help`）、`--serial`（实际是 `--port`）。 |
| `fw_setenv bootdelay` 延长 U-Boot 倒计时 | U-Boot 不读取该变量 | reboot + 持续按回车 ~12s 覆盖倒计时 |
| 改了配置文件后只做增量编译 | 文件不进入镜像 | 改配置文件后必须大编译或至少 `make pack_firmware` |
| **编译后不验证 .ko 一致性就烧录** | `make_drivers.sh` 把新模块装进 `.tmp/driver/`，但 `system_b.squashfs` 从 `.tmp/system_b/lib/modules/` 打包旧模块。设备跑着新内核 + 旧驱动，问题表现诡异（`cat /proc/version` 显示新时间戳但 bug 依旧）。 | 烧录前：`md5sum .tmp/driver/tx-isp*.ko` vs `unsquashfs system_b.img` 中的对应文件。不一致则 `cp .tmp/driver/*.ko .tmp/system_b/lib/modules/` 后重打包。 |
| **只改 output 没改 source 的 auto_update_tftp.txt** | `make pack_firmware` 从 source 复制覆盖 output，下次编译后改动丢失 | 源码 + 产物双份改。source 在 `device/soc/ingenic/pkg_tool/<项目>/auto_update_tftp.txt`（持久化），output 在 `out/image_<项目>/auto_update_tftp.txt`（立即生效）。编译前改 source 就行；编译后不改 source 只改 output 的话，下次编译会被覆盖 |
| **改了 kernel/.../arch/mips/xburst/lib/isp/ 下的 ISP 源码但实际没用上** | <项目> 的 defconfig 没使能 `CONFIG_VIDEO_TX_ISP`，内嵌 ISP 代码不会被编译。实际加载的模块来自 `drivers/t32_t33/isp/tx-isp-<平台>/`（外部模块，通过 `make_drivers.sh` 构建）。内嵌内核的 ISP 源码只用于 zeratul 平台。浪费了几轮合并工作。 | 改 ISP 驱动前先追踪编译路径：①查 `defconfig` 中 `CONFIG_VIDEO_TX_ISP` 是否使能 ②查 `init.sh` 中 `insmod` 路径 ③查 `make_drivers.sh` 中 `cd` 到哪个目录构建。 |\n| **PHY 初始化显示 SPEED:0, DUPLEX:0 就认为网络不通，中断烧录** | `mai_tftp` 首次初始化 GMAC PHY 时，SPEED:0, DUPLEX:0 是**瞬态**状态（PHY 寄存器尚未稳定或 autonegotiation 未完成），不是最终结果。GMAC 驱动会内部重试，后续（第二个 tftpboot）可正确协商到 SPEED:2 (100M), DUPLEX:2 (Full)。如果看到 SPEED:0 就 panic 或中断烧录，可能错过已经在进行的擦写操作，甚至中断 sf erase 导致 NOR 处于不一致状态。 | **等待。** `mai_tftp` 输出可能看起来断断续续——第一阶段 `tftpboot rootfs.img` 显示 SPEED:0 但仍成功下载并执行 erase+write，第二阶段 `tftpboot kernel_system_b.image` 时 PHY 已正确协商。只要看到 `sf write ... Written: OK` 和 `reset`，烧录就是完整的。用 `(python3 -c '...监控串口...')` 持续读取 90s 不要提前退出。观察到 `SPEED:0` 后继续等，不要中断。 |
| **烧录脚本输出为空（0 bytes），不断超时** | 串口 `/dev/ttyUSB0` 残留了上一个 session 的 pyserial 状态（参数污染），导致 pyserial 能 write 但 read 始终返回空。即使 `fuser -k` 杀掉旧进程，pyserial 的端口参数（timeout、波特率等）仍然不匹配。 | ⚠️ 此问题 **已修复**（2026-07-01）：`auto-uboot-interrupt.py` Step 0 已内置 `fuser -k` + `stty` 重置 + 发 `\r` 验证回显。如需绕过预检，加 `--no-precheck`。如果仍烧录输出为空，手动 `sudo stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb raw -echo -echoe -echok` 重置端口参数，然后物理断电重启设备。 |
| **手动替换 NOR_ALL.bin 中的 squashfs（不重建完整镜像）** | 把新编译的 .ko 手动复制到 staging 后，不通过 `make && make pack_firmware` 重建 NOR_ALL.bin，而是用 `dd`/python 在 NOR_ALL.bin 的固定偏移处替换 squashfs。后果：① squashfs 大小变了 → 分区边界偏移量被破坏 → 后续 FIT image 起始地址错位。② 新 squashfs 小于旧 squashfs 时，填充的 0xFF 区域被 U-Boot 当作 bootm 内核 FIT 读取 → `Wrong Image Format`。③ 设备只能从备选 slot 手动启动（见 4b），直到重新烧录正确的全量镜像。 | **只通过 build 系统重建 NOR_ALL.bin。** 流程：`cp .tmp/driver/*.ko .tmp/system_a/lib/modules/ && cp .tmp/driver/*.ko .tmp/system_b/lib/modules/ && cmake ... && make -j && make pack_firmware`。如无法运行 Docker 编译，用 `mksquashfs` 重建 squashfs 后通过 `mai_tftp` 全量烧录。**不要直接在 NOR_ALL.bin 上 patch。** | | `make pack_firmware` 不会全量重建所有分区镜像。`build_app.sh` 只执行 `make c_mi_ipc + make pack_firmware`，但 pack_firmware 可能因为依赖判断不更新 system_b.img 和 NOR_ALL.bin。产出物 `.tmp/bin/c_mi_ipc` 与 `.tmp/system_b/bin/c_mi_ipc` 时间戳不同步。 | 增量编译后，手动复制二进制到 staging 目录再执行 `make pack_all`：`cp build/applications/c_mi_ipc/c_mi_ipc out/image_<project>/.tmp/system_b/bin/ && docker run ... make pack_all`。或直接用 `build.sh` 全量编译保底。`build_app.sh` 应改为执行 `make c_mi_ipc && make pack_all` 而非 `make pack_firmware`。 |
| **用未 strip 的编译产物 MD5 对比固件内 strip 后的二进制**（2026-07-17 <项目> 踩坑） | `build/applications/c_mi_ipc/c_mi_ipc`（~47MB，含调试符号未 strip）与固件 `system_b.img` 内的 `c_mi_ipc`（~7MB，strip 后）MD5 永远不同。用 `build/` 产物对比设备二进制会误判为"pack_firmware 没打包最新产物"，浪费一轮排查。 | **对比 strip 后的 staging 二进制**：①`md5sum out/image_<项目>/.tmp/bin/c_mi_ipc`（strip 后 ~7MB）vs 设备 `adb shell md5sum /system/bin/c_mi_ipc` ②或从固件提取：`unsquashfs -f -d /tmp/sys_check out/image_<项目>/system_b.img bin/c_mi_ipc && md5sum /tmp/sys_check/bin/c_mi_ipc`。**绝不用 `build/` 目录的未 strip 产物做对比。** 判断 strip 与否看文件大小：~47MB=未 strip，~7MB=strip 后。 |
| **DIRECT 模式下 mjac_reader.c 的 delay 不生效** | mjac_reader.c 的 write retry=3、ms_delay、5ms gap 只影响 INDIRECT 模式下 c_mi_ipc 的 I2C 访问。预编译的 libmike.a（DIRECT 模式 SDK 内部开 /dev/i2c-1）和 miio_client（独立 MJAC 协议栈）的 I2C 代码不可修改，delay 完全不生效。 | 唯一能覆盖所有 I2C 访问方的方案是修改内核驱动 i2c-v12-dma-jz.c 的 i2c_jz_xfer()：在 return 前对 i2c-1 事务加 udelay(5000)。只影响 MJAC 总线，不影响传感器 i2c-0。 |
| **烧录后 /tmp 被清空，测试工具丢失**（2026-07-11） | TFTP 全片烧录重启后，`/tmp`（tmpfs）全部清空。之前 ADB push 进去的 iperf、测试脚本、工具全部丢失。除非提前考虑到，否则烧录后重新 push 需要额外 5-10 分钟，且需要 ADB 可用（见下条）。 | 烧录后的验证步骤应包含：① `adb push iperf /tmp/iperf` ② `adb push wifi_bench.sh /tmp/`。iperf 静态二进制可从编译产物的 `sd_resource_<项目>/iperf3` 获取。如果项目编译 iperf3（与主机 iperf2 不兼容），需单独编译 iperf2 静态二进制，或用 `mips-linux-gnu-strip` 缩小体积（4.7MB→1.1MB）。 |
| **WiFi + eth0 双网共存时 ADB shell 超时**（2026-07-11） | 设备同时连接 eth0（<HOST_IP>x）和 wlan0（<WIFI_SUBNET>x）时，mihomo TUN 的 `auto-route: true` iptables 规则劫持 ADB 数据包。表现：`adb connect` 成功但 `adb shell` 挂起。从设备侧 netstat 可见多个 SYN_RECV 连接。 | 症状出现时：`adb kill-server && adb connect <IP>` 刷新 ADB server 状态即可恢复。长期解决方案：检查 mihomo iptables 规则是否在 `route-exclude-address` 生效后仍有残留 conntrack 条目。临时方案：仅保持 eth0 在线时测 ADB，WiFi 测速交给串口或配通路由。 |

## 7. 烧录后验证（确认烧录生效）

> **铁律：串口看到 login: ≠ 烧录成功。** 设备从旧固件启动也会显示 login:。烧录后必须做 MD5 三方对齐验证（设备 vs 固件 vs 编译产物）。2026-07-17 实战教训：脚本监控超时退出但串口看到 login:，误判烧录成功，实际设备跑的是旧固件（uptime 16.5h 未重启，c_mi_ipc MD5 不匹配）。

烧录成功后不要假设所有组件都是新的。内核 vmlinux 和内核模块 .ko 来自两条不同的构建产线。**如果开启 `-o MSC`（MJAC 安全芯片）功能的项目，同时检查 miio_client 日志中是否有 MJAC 初始化失败。**

```bash
# MJAC 检查（Mike SDK 项目）
cat /tmp/miio_client.log | grep mjac
# 如果报错但硬件无 MJAC 芯片，属正常。
```

```bash
# 检查内核版本（在设备上）
cat /proc/version
# 确认显示最新的编译时间戳

# 检查 .ko 模块 MD5（在设备上）
md5sum /system/lib/modules/tx-isp-<平台>.ko
# 在宿主对比编译产出
md5sum out/image_<项目>/.tmp/driver/tx-isp-<平台>.ko
# 在宿主对比打包镜像中的版本
unsquashfs -ll out/image_<项目>/system_b.img lib/modules/ 2>/dev/null | grep .ko
unsquashfs -f -d /tmp/sys_check out/image_<项目>/system_b.img lib/modules/tx-isp-<平台>.ko
md5sum /tmp/sys_check/lib/modules/tx-isp-<平台>.ko

# 批量对比所有 .ko
diff <(cd .tmp/driver && md5sum *.ko | sort) <(unsquashfs -f -d /tmp/sys_check out/image_<项目>/system_b.img 2>/dev/null && cd /tmp/sys_check/lib/modules && md5sum *.ko | sort) 2>/dev/null
```

如果 device vs build-output 的 MD5 不匹配，说明 system_b squashfs 打包了旧模块。清理 staging 目录后重编：

```bash
rm -rf out/image_<项目>/.tmp/
cmake -DPROJECT_ID=<项目> .. && make -j$(nproc) && make pack_firmware
```

> ⚠️ **常见误导：** `cat /proc/version` 显示新内核时间戳 ≠ 所有模块都是新的。vmlinux 打包在 FIT image 中，.ko 打包在 system_b squashfs 中，两条产线独立。内核新 + 模块旧 = 设备跑着新内核加载旧驱动。

## 8. 烧录后设备健康检查（ADB 连接后）

烧录生效后，除验证版本/MD5 外，还应检查设备运行时健康状态。本节检查项可发现隐藏的兼容性问题（如日志分区残留、I2C 驱动缺陷、CMA 分配失败等）。

### 8.1 关键进程存活

```bash
# 检查核心进程是否全部启动
adb shell ps | grep -E "c_mi_ipc|apphilogcat|miio_client|miio_bt|adbd"
```

| 进程 | 说明 |
|------|------|
| `c_mi_ipc` | 主应用，必须存活 |
| `apphilogcat` | 日志服务 |
| `miio_client` | MIoT 通信客户端 |
| `miio_bt` | BLE 配网服务 |

### 8.2 SIGSEGV 检查

<项目> 烧录后如果 log 分区未全擦，旧 KV 数据会导致 c_mi_ipc 反复段错误。

```bash
adb shell dmesg | grep -c "Segmentation fault"
# 期望值: 0
```

仅 <项目> 有此问题（需要 `0x1000000` 全片擦写）。<项目> 保留 log 分区不影响。

### 8.3 I2C ABORT 频率检查

已知 I2C DMA 驱动缺陷修复后，ABORT 应为 **0-1 次（仅 boot 阶段传感器探测时发生）**。如果持续增长说明驱动修复未生效或仍有竞态。

```bash
adb shell dmesg | grep -c "ABORT interrupt"
# 期望值: 0-1
adb shell dmesg | grep "ABORT"
# 查看发生时间和上下文
```

- ABORT 发生在 boot 早期（~20-30s）→ 正常，传感器响应窗口未对齐
- ABORT 发生在运行期或多次发生 → 驱动问题，需检查 i2c-v12-dma-jz.c

### 8.4 dmesg ERROR 分类

dmesg 中的 `[Init][ERROR]` 分级处理：

| dmesg 日志 | 严重程度 | 说明 |
|-----------|---------|------|
| `Child process XX exit with code : 0` | ⚪ 无害 | exit code 0 是正常退出，仅日志级别标了 ERROR |
| `Can not get real path /system/etc/ohos.para` | ⚪ 无害 | <项目>/<项目> 不用 ohos 框架 |
| `ParseCfgs open cfg dir :/system/etc/init failed` | ⚪ 无害 | 同上 |
| `CPU0 RESET ERROR PC:...` | ⚪ 无害 | 每次开机都有，历史遗留信息 |
| `aic_load_fw: probe ... failed` | ⚪ 无害 | USB 枚举阶段一次性重试，后续 aic8800_fdrv 正常加载 |
| `Kernel panic` | 🔴 严重 | 烧录失败或分区溢出 |
| `Segmentation fault` | 🔴 严重 | 应用层段错误（<项目> log 分区问题） |

### 8.5 BLE/BT 状态检查

Ingenic T32 平台无 `hcitool`/`btmgmt` 等诊断工具，BLE 状态通过 sysfs + 进程状态 + 开机日志推断。

```bash
# HCI 设备基本信息
adb shell cat /sys/class/bluetooth/hci0/name
adb shell cat /sys/class/bluetooth/hci0/type
adb shell cat /sys/class/bluetooth/hci0/bus
adb shell cat /sys/class/bluetooth/hci0/address

# BLE 服务进程
adb shell ps | grep miio_bt
# 参数解释: -p <product_id> -m <BLE_MAC> -d <device_id>
# 进程存在 → BLE 栈存活

# 驱动健康
adb shell dmesg | grep -iE "aic_btusb|btusb_open"
# 期望: btusb_probe / btusb_open 各出现 1 次以上，无 error

# 内核 HCI 线程
adb shell ps | grep "\[hci0\]"
# 期望: 2 个内核线程（hci0 rx/tx）

# BLE 模式判定（从开机串口日志或 logcat 提取）
# "started miio_bt for unbound device" → 未绑定广播模式
# "started miio_bt for bound device"   → 已绑定
```

**BLE 模式判定参考：**

| 日志关键词 | 含义 |
|-----------|------|
| `started miio_bt for unbound device` | 出厂模式，BLE 广播中，等待 App 绑定 |
| `gatera_evt_handler: Device address: XX:XX:XX:XX:XX:XX` | GATT Gateway 启动 |
| `gatts_add_handle_value` / `gatts_value_set` | GATT Server 初始化完成，广播应处于活动状态 |
| `no rom version info, please check` | ⚪ 无害的版本信息缺少警告，不影响广播功能 |

### 8.6 应用日志快速扫描

```bash
# 检查应用层 fatal/error
adb shell logcat -d -s "*:E" 2>/dev/null
adb shell logcat -d | grep -iE "fatal|SIGSEGV|crash|panic" | head -20

# 检查 miio_client 日志（常见 MJAC 初始化错误）
adb shell cat /tmp/miio_client.log | grep -c "mjac_init error"
# 。
```

> **注意：** logcat 在 <项目>/<项目> 上使用 hilog 框架，部分 ERROR 级别消息是正常初始化信息。重点关注 `fatal`/`SIGSEGV`/`crash` 关键词。`mjac_init error` 是 MJAC 安全芯片初始化失败，与传感器 I2C 探测时序有关，不影响 BLE。

## 9. 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `No ethernet found` | 以太网未初始化 | `mai_tftp` 会自动初始化 GMAC |
| `Timeout` | IP/网关不在同一网段 | 检查 `ipaddr`、`serverip`、`netmask` |
脚本报 `Device mode: unknown` 或 `Failed to interrupt U-Boot` 后失败 | 设备串口输出被应用日志淹没，脚本无法识别 login 提示符。或设备已停在 U-Boot 提示符（如之前烧录中断、kernel panic 后 fallback），脚本的 Step 1 登录超时检测误判。**常见假阴性**：脚本报 `Failed to interrupt U-Boot` 但实际上设备已经在 <U-Boot提示符># 提示符下（串口可见），只是脚本没检测到 - 波特率参数 `--baud` 不匹配（<项目> 用 921600 非默认 115200，2026-07-17 纠正，非 1500000），或 Step 0/1 的状态判断超时。CMA=4MB + T32Pro ISP 驱动时 ISP/VPU 完全不启动（所有计数器为 0），也会导致设备无响应。 | **先确认设备状态：** 串口敲回车看返回。返 `<U-Boot提示符>#` -> **即使在 U-Boot！直接用 `flash --at-uboot --baud 921600` 跳过 Steps 0-1 烧录。** 返 `login:` -> 等设备完全启动后再跑脚本。若串口完全无回显，先检查 `--baud` 参数（<项目> 用 921600）。同时给 `--no-precheck` 跳过被污染串口端口的预检。确认设备在 U-Boot 但脚本三次检测不到时，可手动烧录。**注意：手动烧录前务必确认 U-Boot 提示符，`mai_tftp` 发到 Linux shell 会打坏终端。** |
| `File not found` | TFTP 目录或文件名不对 | 检查 `/etc/default/tftpd-hpa` 的 `TFTP_DIRECTORY` |
| 刷完 c_mi_ipc 反复 SIGSEGV 崩溃（仅 <项目>） | log 分区残留旧 KV 数据。<项目> 需全量 16MB 擦除 (`0x1000000`) 预防。<项目> 默认部分擦 `0xf60000` 不用改 | <项目>: 全量 16MB 擦除。已触发: `rm -rf /data/* && reboot`。修复后 `dmesg | grep -c \"Segmentation fault\"` 应为 0 |
| 刷完 <项目> 后 wlan0 无 IP，WiFi 配置丢失（2026-07-11） | <项目> 全擦或部分擦 algo 分区时被清空。工厂 env（MAC=默认）被重置，WiFi 配置存储在 algo 分区或 /data 中。wlan0 启动后 RX/TX=0，无 IP。| 烧录后检查：`adb shell ifconfig wlan0`。配网步骤。**注意** `/var/run/wpa_supplicant` 是只读，ctr_interface 必须用 `/tmp/wpa`。 |
| iperf 版本不兼容（iperf2 vs iperf3） | 主机运行 `iperf -s`（iperf2，port 5001），但设备上 push 了 iperf3 二进制。iperf2 和 iperf3 使用不兼容的协议，设备 `iperf3 -c 主机` 连接建立后无数据传输（`[ ID] Interval Transfer Bandwidth` 行缺失）。 | 确认两端用同一版本。主机：`iperf --version`（2.x），设备：`adb shell /tmp/iperf --version`。项目编译产出是 iperf3（在 `sd_resource_<项目>/iperf3`），需单独编译 iperf2 静态 MIPS 二进制或用主机的 cross-toolchain 编译。可复用的 iperf2 静态二进制在 `/tmp/iperf_mips`（4.7MB，strip 后 1.1MB）。 |
| 刷完 kernel panic `No filesystem could mount root` | rootfs 超过分区大小，溢出损坏 kernel | 打断 U-Boot → 减小 rootfs 或放大分区 → 重编重刷 |
| 全擦烧录后内核循环输出 `[env]ERROR:erase error at 0x8000.ret:-22` | factory 分区（56K）擦除对齐问题：`mtd->erasesize`（32KB BE）超出分区边界 → EINVAL → 驱动 goto RETRY 无限循环。NOR 家族（<项目>/<项目>/<项目>/<项目>/<项目>）共用 56K factory 分区均受影响。 | fix：改 `env_nor/env.c` 中 `write_to_flash()` 使用 `ENV_SECTOR_SIZE 4096` 替代 `mtd->erasesize`。。编译后验证 `md5sum out/.tmp/driver/env-flash.ko out/.tmp/system_b/lib/modules/env-flash.ko` 一致。 |
| 串口终端挂死，只有硬件回显 | 误发命令到 Linux shell 导致 login 进程死 | 看门狗复位或物理断电 |
| **烧录脚本报 exit code 1 "Login prompt not detected" 但实际烧录已成功**（两种场景） | **场景 A—全擦超时（2026-07-17 <项目> 全擦踩坑）：** `auto-uboot-interrupt.py flash --at-uboot --baud 921600` TFTP 16MB OK、sf probe OK、sf erase 开始，但擦+写耗时超脚本监控超时，脚本提前退出。U-Boot mai_tftp 在后台完成擦写+reset，实际烧录成功。<br><br>**场景 B—部分擦 + 固件串口刷屏（2026-07-17 实测）：** 部分擦 `0xef0000`（~15.6MB）erase 仅 ~36s 即完成，write 正常。设备重启进新固件，但 **c_mi_ipc 在 Linux 启动后立即往串口输出日志**（ISP/VPU/Motor 初始化、视频推流 ~1s/25 帧），串口刷屏掩盖了 `login:` 提示符。脚本监控到 c_mi_ipc 日志但找不到 `login:`，超时报 exit code 1。**实际烧录已成功** — c_mi_ipc 正常运行，视频推流、马达校准、感光检测均可从串口日志确认。<br><br>**共同验证：** ①等 60-90s 后串口敲回车看 login: ②串口日志中出现新固件内核/应用启动信息（ISP build 时间戳、c_mi_ipc 日志时间戳）即为成功 ③`adb kill-server; adb connect <新IP>:5555` 后 `cat /proc/uptime` → 应 < 120s。**不要因 exit code 1 重烧**——可能打断进行中的擦写。 | **脚本 exit code 1 ≠ 烧录失败。** 看到 mai_tftp 阶段输出 `sf probe` / `sf erase ... Erased: OK` / `Bytes transferred = 16777216` 等成功标志后，即使脚本报 "Boot verification failed"，烧录大概率已成功。验证：①等 60-90s 串口看 login: ②串口日志中新固件内核启动信息（ISP build 时间戳）③`adb shell cat /proc/uptime` < 120s ④MD5 三方对齐。不要因 exit code 1 重烧。 |
| **全擦烧录后设备用默认静态 IP，主机无法 ADB 连接**（2026-07-17 <项目> 全擦踩坑） | 全擦（0x1000000）清空 env 分区后，设备 boot 时无 DHCP 配置，eth0 使用固件内置默认静态 IP（<项目> = 192.168.5.100/24，网关 192.168.5.1）。主机在 <HOST_IP>x 网段，与设备 192.168.5.x 不在同一网段 -> ping 不通 -> ADB offline -> 无法通过 ADB 验证。串口日志可见 `eth cfg: IFACE=eth0 IP=192.168.5.100 MASK=255.255.255.0 GW=192.168.5.1`。 | 全擦后需通过**串口**配置网络或等待 DHCP。串口登录后：`ifconfig eth0 <主机同网段IP> netmask <mask>` 临时配 IP，或检查 DHCP 服务是否可达。部分擦（0xf60000）保留 env 不受影响。注意：全擦后 env 分区被清，U-Boot 也用默认环境变量（无 saveenv，每次断电需 `env default -a` 重置）。 |
| **烧录后 ADB 连到旧设备而非新烧录设备**（2026-07-17 <项目> 踩坑） | 烧录后直接 `adb connect <HOST_IP>`（旧设备 WiFi IP），旧设备 uptime 17.5h、旧内核、旧 MD5。误判烧录失败，实际新设备在另一个 IP（<HOST_IP>，通过串口配的 eth0）。旧设备通过 wlan0 持有 WiFi IP 不会自动消失，ADB server 缓存了连接。 | **烧录后先 `adb kill-server` 断开所有旧连接**，通过串口确认新设备 IP 后再 `adb connect <新IP>`。验证身份：①`adb shell cat /proc/uptime` 应 <120s（刚重启）②`adb shell cat /proc/version` 时间戳应匹配本次编译 ③MD5 三方对齐。 |
| 脚本报 `Device mode: unknown`，串口完全无输出，但 ADB 在线且 `reboot` 返回 `Input/output error`（2026-07-17 <项目> 踩坑） | c_mi_ipc 崩溃后 init 框架处于异常状态：`/sbin/reboot` 系统调用返回 EIO（init 无法处理 SIGTERM），SysRq 被锁定（`Permission denied`），但 adbd 用户态进程仍存活 → 设备可 ADB 连接但无法软件重启。`reboot` 和 `echo b > /proc/sysrq-trigger` 均无效。串口 UART 驱动可能未初始化或终端层挂死，完全无输出。 | 唯一解法：**物理断电重启**。拔电源 → 等待 5 秒 → 重新上电 → 等 ~30-45s 启动完成 → 串口应有 U-Boot 输出 → 再跑脚本。不要试图用 ADB 恢复（`killall -9`、`busybox reboot`、`echo b > /proc/sysrq-trigger` 均无效）。识别标志：`adb shell "cat /proc/uptime"` 可执行但 `adb shell /sbin/reboot` 返回 `Input/output error`。
