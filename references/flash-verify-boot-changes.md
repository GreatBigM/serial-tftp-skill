# 烧录后验证：boot 序列变更确认

修改了内核 config、init.sh 或 flash 擦除范围后，烧录完成时设备已在运行新固件。以下方法确认变更实际生效，无需 ADB（串口可读）。

## 1. 内核 config 变更验证

### JFFS2_SUMMARY

```bash
# 在串口输出中搜索 dmesg 的 jffs2 行
dmesg | grep jffs2
# 未启用 SUMMARY:
#   jffs2: version 2.2.  © 2001-2006 Red Hat, Inc.
# 已启用 SUMMARY:
#   jffs2: version 2.2. (SUMMARY)  © 2001-2006 Red Hat, Inc.
```

烧录过程中内核日志会打印在串口上，也可以登录后 `dmesg | grep jffs2` 确认。

```bash
# 内核版本 + 编译时间
cat /proc/version
# Linux version 3.10.14__isvp_goat_1.0__ (user@host) ... #2 PREEMPT Thu Jun 25 09:33:30 UTC 2026
# 确认时间戳对应最新 build
```

## 2. init.sh 流程变更验证

### JFFS2 挂载在 KO 加载之后

观察串口输出中关键事件的先后顺序：

```
# 1) KO 加载 → 可见 tnpu/audio/tx-isp/sensor 的 probe 日志
# 2) JFFS2 挂载 → 如果 /data 分区为空，出现 "Format data partition...""
#    此时擦除进度条在 KO 日志之后出现
# 3) 内存整理 → 无日志（sync + drop_caches + compact_memory 静默执行）
# 4) c_mi_ipc 启动 → workmode 服务启动日志
```

如果在 `Format data partition...` 之前看到了 tnpu/audio/tx-isp 的 probe 日志，说明 init.sh 的 JFFS2 已移到 KO 之后，顺序正确。

### 内存整理（静默）

`sync; echo 3 > /proc/sys/vm/drop_caches; echo 1 > /proc/sys/vm/compact_memory` 不产生日志。
可以登录后检查执行效果：

```bash
cat /proc/sys/vm/drop_caches   # 总是 0，写后立即复位
cat /proc/sys/vm/compact_memory  # 总是 0，写后立即复位
```

确认 init.sh 包含了这 3 行即可——运行时不可观测但有效。

## 3. auto_update_tftp.txt 擦除范围验证

### 烧录日志

在 `mai_tftp` 输出中检查：

```
>> sf erase 0x0 0x1000000     # ✅ 全 16MB 擦除
# 而非:
>> sf erase 0x0 0xef0000      # ❌ 只擦 14.94MB，log 分区残留
```

### 烧录后 /data 为空

全擦后首次启动 log 分区被擦除，init.sh 会执行：

```
Format data partition...
```

如果没出现这行，说明 /data 分区数据未被清除（0xef0000 场景）。

## 4. 总检查清单

| 检查项 | 命令/观察点 | 通过标准 |
|--------|------------|---------|
| JFFS2 SUMMARY | `dmesg \| grep jffs2` | 显示 `jffs2: version 2.2. (SUMMARY)` |
| JFFS2 挂载顺序 | 串口日志中 KO probe 出现在 `Format data` 之前 | KO 日志先于 JFFS2 格式化/挂载 |
| 内存整理 | init.sh 内容确认 | 包含 `sync; drop_caches; compact_memory` |
| 全量擦除 | mai_tftp 输出 | `sf erase 0x0 0x1000000` |
| /data 已清 | 串口日志 | 首次启动出现 `Format data partition...` |
| 内核时间戳 | `cat /proc/version` | 与 `ls -l out/image_hm6801/hm6801_NOR_ALL.bin` 时间一致 |
