# 烧录后设备变砖恢复方法（NOR flash 损坏）

## 场景

手动在 U-Boot 中执行了错误的 erase+write 操作（如 `sf erase 0 0x100000` 只擦 1MB + `sf write 0 0x1000000` 写 16MB），导致 NOR flash 中 U-Boot 启动区损坏，设备串口无输出。

## 恢复步骤

### 方法 1：重新上电后快速打断

1. 物理断电 → 重新上电
2. 立即在串口持续发送回车（覆盖 U-Boot 的 ~1s bootdelay）
3. 如果看到 `PRJ009#` 提示符 → 用 `--at-uboot` 参数全量烧录：
   ```bash
   python3 auto-uboot-interrupt.py flash --at-uboot
   ```
4. 如果无输出 → 尝试用串口按 Ctrl+C 或 Ctrl+D（Ingenic T32 SoC 可能从 BootROM 回退）

### 方法 2：检查 BootROM 模式

Ingenic T32 SoC 可能有 USB BootROM 模式（需拉特定 GPIO 进下载模式）：
- 查阅 SoC datasheet 确认 BOOT_SEL pin 配置
- 如果支持 USB boot，可用 Ingenic USB boot tool 下载 U-Boot 到 RAM 后再写回 NOR

### 方法 3：SPI Flash 编程器

如果前两种方法都无效：
1. 拆下 NOR flash 芯片（EN25QX128A 等）
2. 用 SPI Flash 编程器（CH341A 等）写入完整的 NOR_ALL.bin（16MB）
3. 焊回芯片

## 预防

- 永远使用 `auto-uboot-interrupt.py flash` 脚本（自动全擦 16MB + 写 16MB）
- 永远不要手动输入 `sf erase` + `sf write` 命令
- 如果脚本失败 → 读脚本文档 → 用正确参数重试 → 修脚本 → **不绕过**
- 避免用 NFS 或 tftp 启动设备替代烧录（非持久化）
