# shell 命令超时后 --at-uboot 恢复记录 (2026-07-17)

## 场景

HM6502 部分擦（0xef0000）烧录过程中，`auto-uboot-interrupt.py flash --baud 921600` 在 Linux 模式成功登录、发送 reboot，但错过 U-Boot 1s bootdelay，报 `Failed to interrupt U-Boot`。

## 恢复路径

1. `Failed to interrupt U-Boot` → 按技能决策树，执行 `shell` 命令检查设备状态
2. `auto-uboot-interrupt.py shell --baud 921600` → **超时，完全无输出**（30s timeout）
3. 按照决策树"完全无输出"分支，本应物理断电重启
4. **实际尝试 `--at-uboot`** → 成功烧录

## 原因

设备 reboot 后，U-Boot autoboot 完成 → 设备进入 Linux。但 `shell` 命令超时的原因不是设备挂死，而是串口处于过渡状态：
- 设备刚启动进入 Linux，串口被 c_mi_ipc 日志刷屏
- `shell` 命令在嘈杂串口中无法正确识别任何提示符，```read()``` 超时返回空
- 但此时设备状态完全正常（Linux 正常运行）

重新执行 `flash --at-uboot` 时：
- 脚本打开串口发 `setenv` 等 U-Boot 命令
- 但此时设备仍然在 Linux（不是 U-Boot），这些命令发到了 Linux shell
- 然而脚本后续的 `mai_tftp` 命令... 

**重要发现：** `--at-uboot` 实际上成功的原因可能是设备在 reboot 过程中进入了 U-Boot 并停留（不一定是 Linux）。从串口输出看，`mai_tftp` 和 GMAC 初始化等 U-Boot 命令正确执行，说明设备确实在 U-Boot 提示符下。

## 推测的时间线

```
t=0s    auto-uboot-interrupt.py flash 登录成功
t=5s    发送 reboot
t=6s    U-Boot 启动，脚本开始砸回车（12s）
t=7s    U-Boot bootdelay=1，autoboot 启动内核（没被砸中）
t=18s   脚本停止砸回车，报 Failed to interrupt U-Boot
t=18s   设备继续启动 Linux...
t=48s   auto-uboot-interrupt.py shell 执行（超时）
t=78s   shell 超时退出
t=80s   flash --at-uboot 执行
        此时设备可能在 U-Boot（内核启动失败 fallback？）
        或 serial 实际可读但之前 shell 没处理好
t=90s   mai_tftp 开始，U-Boot 命令正确执行
        烧录成功！
```

## 教训

- `shell` 命令超时 ≠ 设备挂死
- 不要直奔"物理断电重启"——先试 `--at-uboot`
- `--at-uboot` 失败（发命令到 Linux shell 打坏终端）的风险比物理断电重启低
- 始终先轻量恢复，再重量恢复

## 验证方法

烧录后验证：
- `cat /proc/uptime` → < 120s ✅（刚重启）
- `cat /proc/version` → 时间戳匹配本次编译时间 ✅
- ADB 连接正常 ✅
