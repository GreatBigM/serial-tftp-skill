# <项目A> 串口参数

- 波特率: 115200
- 登录: 用户 `root`，密码**分固件版本**：旧版空密码（直接回车），新版 `root`/`root`。先用空密码尝试，失败后用 `root`/`root` 重试
- busybox 缺: `head`, `which`, `strings`, `getprop`, `uname`, `nohup`
- adbd: **当前固件无 adbd**。`adbd &` 命令不存在。ADB 连接尝试会超时（10s）。串口是唯一可靠通道。
- 内核 3.10: AF_ALG 无 `ALG_SET_OP`/`ALG_SET_IV`，write=encrypt, IV prepend to data
- **kexec**：`reboot` 命令跳过 U-Boot 直接重启内核。如需打断 U-Boot 必须用 `echo b > /proc/sysrq-trigger` 触发硬件复位，或物理按复位键

## 日志洪流防御（关键）

设备启动后多个进程往串口输出：
- `apphilogcat` — 日志转发守护进程（init 管理）
- `c_mi_ipc` — 主应用进程（IPCMain/MikeInit 日志直接输出到 console）
- `miio_client` — 米家客户端
- `mai_log_service` — 日志服务

**只杀 apphilogcat 不够** — c_mi_ipc 也会直接输出日志。

```python
# 必须杀全部四个进程
s.write(b"killall -9 apphilogcat mai_log_service miio_client c_mi_ipc 2>/dev/null\r")
# init 会在 1-2s 内重启这些进程，需立即采集数据
```

## DHCP 限制

多轮重启（约 2-3 次）后 DHCP 不再分配 IP。必须设置静态 IP：

```bash
ifconfig eth0 <IP-1> netmask 255.255.240.0 up
```
不需要 `down` 先。不要同时运行 `udhcpc`。

## 相关 skill

- `<项目A>-stress-test` — 重启压力测试脚本和指南
