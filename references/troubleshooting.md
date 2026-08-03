# 烧录排障参考（troubleshooting）

> 排障参考：烧录失败/异常时按需查阅，非必读。主流程见 SKILL.md。
> 定位：坑（排障经验）——遇问题查，不占主文档（参考分层 A 模式）。

## 失败恢复速查

| 症状 | 处理 |
|------|------|
| 卡 mai_tftp 重试循环（Loading: T T 反复） | 等静默 ≥1.5s 窗口连发 Ctrl+C，回提示符后重跑 |
| TFTP 持续 T T T T | 先查 IP 冲突（`ip neigh show | grep <IP>`），占用则换空闲 IP |
| 打断失败 | 敲回车看状态：`<名字>#` → `--at-uboot`；`login:` → 等启动完；无响应 → 断电 |

## 各步骤失败恢复

| 步骤 | 失败处理 |
|------|---------|
| Step 0 环境预检 | 按提示修复：restart tftpd-hpa / 设 IP / 检查目录 |
| Step 1 串口无响应 | 物理断电 / 检查串口线 |
| Step 2 打断失败 | 敲回车看状态：U-Boot# → `--at-uboot`；login → 重跑；无响应 → 断电 |
| Step 3 TFTP 超时 | 检查网线/IP/目录 → `--at-uboot` 重试 |
| Step 4 启动超时 | 等 60-90s，**不要重烧** |

## 反模式

| 反模式 | 正确做法 |
|--------|---------|
| 没确认 U-Boot 就发 mai_tftp | 确认提示符再发 |
| 跨项目套擦除范围 | 先确认项目 |
| exit 1 就重烧 | 等 60-90s 确认 |
| 先讲步骤再跑脚本 | 直接跑脚本 |
| 烧完 adb connect 旧 IP | 串口查新 IP |
| 用 `\n` 作行终止符 | 用 `\r` |

## 根因备注

- **IP 冲突是 TFTP T T T T 首要原因**：烧录前 ping 设备自身 IP，通 = 被占用 → 换空闲 IP
- **打断 U-Boot 只认交互提示符**（行尾 `#` 或 `=>`），不认 "U-Boot" banner；`CONFIG_BOOTDELAY=1`（~1s），reboot 后持续砸回车，边砸边读避免缓冲溢出
- **烧录后 /tmp 清空**：必须重推 iperf3 + wpa.conf + 测试脚本，WiFi 配网重做
