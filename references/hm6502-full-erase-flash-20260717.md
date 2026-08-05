# 全擦烧录完整实录（2026-07-17 HM6502）

## 背景

OpenSpec change `zero-copy-yuv-to-ai` 需要烧录新固件验证。设备此前 c_mi_ipc 崩溃后处于半死状态（reboot 返回 I/O error），物理断电重新上电后停在 U-Boot（PRJ009#）。

## 波特率纠正

skill 原记录 HM6502 串口波特率 1500000（1.5M），**实际为 921600**。

| 波特率 | 串口输出 |
|--------|---------|
| 1500000 | 全乱码（`\r` 后返回不可读字符，`tcsetattr: Inappropriate ioctl`） |
| 921600 | 清晰可读（U-Boot 启动日志、mai_tftp 输出、Linux login 提示符） |

用户纠正："波特率921600"。已同步修正 SKILL.md（项目配置表、踩坑记录、排障表）和 `references/tftp-flash-baud-uboot-recovery.md`。

## 烧录命令

```bash
python3 scripts/auto-uboot-interrupt.py flash --baud 921600 --at-uboot
```

设备已在 U-Boot（PRJ009#），用 `--at-uboot` 跳过登录+reboot 步骤。

## 烧录过程（串口日志关键节点）

```
# 1. 网络初始化（mai_tftp 自动）
SPEED:2, DUPLEX:2          # PHY 协商成功 100M Full
Link is up in FULL DUPLEX mode
Link is with 100M Speed

# 2. TFTP 下载固件
TFTP from server 172.17.151.6; our IP address is 172.17.150.200
Filename 'hm6502_NOR_ALL.bin'.
Loading: ##########################...（16MB）
2 MiB/s
done
Bytes transferred = 16777216 (1000000 hex)    # 16MB 下载完成

# 3. Flash 操作
sf probe                     # 检测到 EN25QX128A 16MB
sf erase 0x0 0x1000000       # 全片擦除 16MB -- 这里脚本监控超时了
```

## 脚本假阴性：exit code 1 但烧录成功

脚本在 `sf erase 0x0 0x1000000` 后报：
```
[+] Flash monitoring ended
[*] Verifying flash...
[-] Login prompt not detected within timeout
[-] Step 3: Boot verification failed
```
exit code = 1。

**但实际烧录成功**。证据：设备随后正常启动新固件，串口日志可见：
```
[    7.544922] <TNPU> Alloc 0x2ec000 from CMA for tnpu pool.
[    7.551061] <TNPU> Successful insmod, version=0x20108.
[    8.507336] ISP driver's version is H20260708a
     tx-isp-probe ok (fw:H20260708a drv:H20260608a build:Jul 16 2026 15:34:34)
[    8.705676] [env] User and User Back OK!
70mai login:
```

根因：全片 16MB erase+write 耗时长于脚本的 post-flash 监控超时。脚本提前退出，但 U-Boot 的 mai_tftp 继续完成擦写 + reset。

**教训**：脚本 exit code 1 ≠ 烧录失败。看到 mai_tftp 阶段 `sf probe` / TFTP `done` / `Bytes transferred = 16777216` 后，即使脚本报 "Boot verification failed"，烧录大概率已成功。等 60-90s 后串口敲回车验证 login: 提示符。

## 全擦后网络问题

全擦（0x1000000）清空 env 分区后，设备无 DHCP 配置，使用固件内置默认静态 IP：

```
eth cfg: IFACE=eth0 IP=192.168.5.100 MASK=255.255.255.0 GW=192.168.5.1
```

主机在 172.17.151.x 网段，设备在 192.168.5.x 网段，不在同一网段 -> ping 不通 -> ADB 无法连接。

需通过串口登录后手动配置网络，或等待 DHCP 服务可达。

## 验证清单（全擦后）

1. 串口敲回车确认 `70mai login:` 出现（烧录成功标志）
2. 串口登录（root + 空密码）
3. `ifconfig eth0` 确认 IP（可能为默认 192.168.5.100）
4. 配置网络：`ifconfig eth0 <主机同网段IP> netmask 255.255.255.0` 或等待 DHCP
5. 主机 `adb connect <设备IP>:5555`
6. `adb shell cat /proc/uptime` 确认 uptime 很小（几十秒，刚重启）
7. 等 60-90s 让 c_mi_ipc 启动
8. `adb shell ps | grep c_mi_ipc` 确认主程序存活
