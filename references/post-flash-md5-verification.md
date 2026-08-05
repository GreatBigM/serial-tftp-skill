# 烧录后 MD5 三方对齐验证（铁律）

> 2026-07-17 实战教训：烧录脚本报"监控超时"但串口看到 login:，甜妞误判烧录成功。
> 实际设备跑的是旧固件（c_mi_ipc 时间戳 Jul 3，uptime 16.5h 未重启）。
> 烧录根本没生效 -- 要么 erase/write 未完成，要么设备从旧固件启动。

## 核心原则

**串口看到 `login:` ≠ 烧录成功。** 设备从旧固件启动也会显示 login:。
**脚本报"监控超时" ≠ 烧录失败。** 全擦 16MB erase 耗时长，脚本 monitoring 线程先退出，erase/write 可能仍在进行或已完成。

唯一可靠的验证方法：**MD5 三方对齐**。

## 三方对齐验证步骤

烧录后 ADB 连上设备，执行以下对比（三方 MD5 必须完全一致）：

```bash
# 1. 设备上的 c_mi_ipc
adb shell md5sum /system/bin/c_mi_ipc

# 2. 固件 NOR_ALL.bin 内的 c_mi_ipc（unsquashfs 提取）
unsquashfs -f -d /tmp/sys_check out/image_<project>/system_b.img bin/c_mi_ipc
md5sum /tmp/sys_check/bin/c_mi_ipc

# 3. staging 产物（strip 后，~7MB）
md5sum out/image_<project>/.tmp/bin/c_mi_ipc
```

> ⚠️ **绝不用 `build/` 目录的未 strip 产物做对比**：`build/applications/c_mi_ipc/c_mi_ipc`（~47MB，含调试符号）与固件内 strip 后的二进制（~7MB）MD5 永远不同。判断 strip 与否看文件大小。staging 产物在 `out/image_<project>/.tmp/bin/c_mi_ipc`（strip 后）。

| 位置 | MD5 | 说明 |
|------|-----|------|
| 设备 /system/bin/c_mi_ipc | A | 设备实际运行的 |
| 固件 system_b.img 内 | B | 打包进固件的 |
| 编译产物 build/.../c_mi_ipc | C | 源码编译出的 |

- **A = B = C**：烧录成功，固件打包正确
- **A ≠ B**：烧录未生效（设备跑旧固件），需重新烧录
- **B ≠ C**：固件打包不完整（pack_firmware 未更新 system_b.img），需 `make pack_firmware` 重打包
- **A ≠ B 且 B ≠ C**：两个问题都有，先修打包再重烧

## 烧录真正成功的辅助判据

MD5 之外，以下信号可辅助判断（但不能替代 MD5）：

1. **设备 uptime 重置**：烧录后设备会 reset 重启，`cat /proc/uptime` 应为几十秒（不是几万秒）。uptime 未变 = 设备没重启 = 烧录没生效
2. **串口看到烧录阶段完整输出**：`sf erase` -> `sf write` -> `Written: OK` -> `reset`，缺任一环节都不可信
3. **c_mi_ipc 时间戳**：`ls -la /system/bin/c_mi_ipc`，时间戳应与编译时间吻合

## 全镜像级 MD5 对齐（NOR_ALL.bin → 设备 φlash）

对于全片烧录（NOR_ALL.bin），最简单的验证是直接比对烧录前后 NOR_ALL.bin 的 MD5 是否一致。烧录过程中文件不改变，**烧录前后 NOR_ALL.bin MD5 相同 = TFTP 传输无损坏**。但这不能证明 `sf write` 写入到 flash 是否正确。

**更严格的验证：从 NOR_ALL.bin 提取分区 MD5，与设备 φlash 和编译产物三方对齐。**

步骤：
```bash
# 0. 预先确认 NOR_ALL.bin 和 system_b.img 的 MD5（烧录前记录）
md5sum hm6502_NOR_ALL.bin
md5sum system_b.img

# 1. 从 NOR_ALL.bin 提取 system_b 分区
#    分区偏移和大小从 kernel cmdline 的 mtdparts 获取。
#    以 HM6502 为例：
#    mtdparts=sfc0_nor:256k(boot),2368k(rootfs),5568k@0x290000(kernel_system_a),
#              4157440@0x974100(system_b),...
#                                ↑偏移     ↑大小
OFFSET=$((0x974100))
SIZE=4157440
dd if=hm6502_NOR_ALL.bin bs=1 skip=$OFFSET count=$SIZE of=/tmp/system_b_from_nor.bin 2>/dev/null
md5sum /tmp/system_b_from_nor.bin
# 预期 == md5sum system_b.img

# 2. 设备端通过串口/ADB 读取 mtdblock3（system_b）
adb shell dd if=/dev/mtdblock3 bs=$SIZE count=1 2>/dev/null | md5sum
# 或通过串口：
# cat /dev/mtdblock3 | md5sum
# 预期 == md5sum system_b.img

# 3. 三方对齐
echo "build artifact:  $(md5sum system_b.img)"
echo "from NOR_ALL:   $(md5sum /tmp/system_b_from_nor.bin)"
echo "from device:     $(adb shell dd if=/dev/mtdblock3 2>/dev/null | md5sum)"
# 三者一致 = 烧录成功 ✅
```

**注意：** mtdblock 设备号从 mtdparts 顺序确定。HM6502 分区映射：
| mtd | 分区 | 偏移 (hex) | 大小 |
|-----|------|-----------|------|
| mtd0 | boot | 0x0 | 256K |
| mtd1 | rootfs | 0x40000 | 2368K |
| mtd2 | kernel_system_a | 0x290000 | 5568K |
| **mtd3** | **system_b** | **0x974100** | **4157440** |
| mtd4 | algo | 0xD70000 | 1536K |

此布局在不同项目间不同，HM6502 与 HM6801 的 system_b 偏移不同。以设备 `/proc/mtd` 的实际输出为准。

**快速检查脚本（设备侧，通过串口执行）：**
```bash
# 串口查看完整 mtd 分区表
cat /proc/mtd
# 读取 system_b 并计算 MD5（注意：adb 不可用时，串口无法直接获取 MD5）
# 建议先查 IP 后 adb connect，再执行
```

## 固件产物一致性预检（烧录前）

烧录前确认固件 NOR_ALL.bin 内的 c_mi_ipc 与编译产物一致，避免烧了不一致的固件：

```bash
# 提取固件中的 c_mi_ipc 并比对
unsquashfs -f -d /tmp/fw_check out/image_<project>/system_b.img bin/c_mi_ipc 2>/dev/null
md5sum /tmp/fw_check/bin/c_mi_ipc
md5sum out/image_<project>/.tmp/bin/c_mi_ipc
# 不一致 -> make pack_firmware 重打包 -> 再比对 -> 一致才烧录
```

## 子 agent 参数错误的处理

delegate 子 agent 用了错误参数（如波特率 1500000 而非 921600）时，进程会持续运行不报错（pyserial 能 write 但 read 返回乱码/空）。甜妞不能被动等待子 agent 超时返回，应主动检查：
- `fuser /dev/ttyUSB0` 确认串口被占用
- `ps aux | grep auto-uboot` 确认脚本在跑
- 如果脚本运行超过 3 分钟仍无进展，主动 kill 并用正确参数重派

## 2026-07-17 完整案例

| 阶段 | 操作 | 结果 | 教训 |
|------|------|------|------|
| 烧录#1 | delegate --baud 1500000 | 串口全乱码，tcsetattr 失败 | 波特率错误 |
| 烧录#2 | delegate --baud 921600 | TFTP 下载成功，sf erase 开始，脚本监控超时退出 | 误判为烧录成功（因串口看到 login:） |
| 验证 | ADB 连 172.17.151.122 | 连上但 c_mi_ipc 未运行，MD5 不匹配，uptime 16.5h | 烧录实际未生效 |
| 根因 | -- | 设备从旧固件启动，erase/write 可能未完成或 reset 后未从新固件引导 | 缺 MD5 验证步骤 |

正确流程：烧录脚本退出后，**立即 MD5 三方对齐**，不一致则重新烧录，不做任何后续验证。
