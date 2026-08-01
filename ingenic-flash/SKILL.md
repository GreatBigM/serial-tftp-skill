---
name: ingenic-flash
description: 君正 T32 NOR 烧录 — auto-uboot TFTP 自动烧录 + 手动 U-Boot 备选，含故障速查
category: devops
metadata:
  hermes:
    triggers: [烧录, flash, NOR, TFTP, uboot, mai_tftp, 刷机]
---

# 君正 T32 NOR 烧录

## 标准烧录流程

### 1. TFTP 就绪

```bash
systemctl status tftpd-hpa
# 如 /mnt/data 重挂载过 → sudo systemctl restart tftpd-hpa
```

TFTP 目录: `<TFTP_DIR>`，端口 69

### 2. 自动烧录（首选）

```bash
python3 <skill_dir>/scripts/auto-uboot-interrupt.py flash --baud 921600
```

脚本自动: reboot → 打断 U-Boot → TFTP 下载 NOR_ALL.bin → SF erase+write → reset
耗时 ~80s

### 3. 手动烧录（备选，自动脚本失败时）

```
# U-Boot 提示符下:
setenv ipaddr <HOST_IP>
setenv netmask 255.255.255.0
setenv serverip <HOST_IP>6
mai_tftp
```

### 4. 烧录后验证

```
[ ] cat /proc/uptime < 60s（确认新启动）
[ ] 等 40s 让设备完全启动（日志洪流消退）
[ ] 串口登录 + 查 DHCP IP
```

## 故障速查（if-X-then-Y）

### 烧录后设备不启动
```
IF 串口 60s 无输出
THEN 断电重上电 → 重试烧录
```

### auto-uboot-interrupt 不进 TFTP
```
IF CPSPR 连续失败
THEN 断电重上电 → 手动 U-Boot 打断 → setenv + mai_tftp
```

### TFTP File not found
```
IF TFTP 下载报 File not found
THEN systemctl restart tftpd-hpa（/mnt/data 重挂载导致句柄过期）
```

### 烧录后验证失败
```
IF uptime > 60s
THEN 烧录失败（设备没重启，还是旧固件）→ 重试
```

### NOR_ALL.bin 不存在
```
IF out/image_<项目>/ 无 NOR_ALL.bin
THEN 需先编译: bash ~/qwiki/projects/_toolkit/compile/build.sh <项目>
```

### 分区表漂移
```
IF 烧录后 FIT 签名验证失败
THEN 核对 gen_tftp_script.py PARTITIONS 与 PRJ.h mtdparts 是否一致
     优先用 NOR_ALL.bin 全量烧录（不受分区表影响）
```
