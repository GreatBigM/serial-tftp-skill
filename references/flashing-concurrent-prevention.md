# 烧录并发冲突预防

## 场景

启动烧录脚本之前，检查到已有烧录/python3 进程占用串口 `/dev/ttyUSB0`。

## 风险

`auto-uboot-interrupt.py` 默认 Step 0 会 `fuser -k /dev/ttyUSB0` 杀掉所有占用串口的进程。如果已有一个正在执行 `mai_tftp` 的烧录进程，kill 它会：
1. 中断正在进行的 `sf erase`（NOR 处于半擦除状态，扇区数据随机）
2. `sf write` 写到半截断开，NOR 数据损坏（新数据 + 旧数据混叠）
3. 设备可能变砖（U-Boot 启动区损坏）

## 检查方法

执行烧录前先查串口占用进程：

```bash
fuser /dev/ttyUSB0 2>&1          # 显示占用 PID
ps aux | grep ttyUSB0             # 显示进程详情
ps aux | grep auto-uboot          # 检查是否烧录脚本
```

## 判断与处理

| 检测结果 | 判断 | 操作 |
|----------|------|------|
| 无进程占用 | 安全 | 直接跑脚本 |
| 有进程占用但运行时长 < 30s | 可能刚启动 | 确认进程是否在烧录中；是则串口观察输出等待完成 |
| 有进程占用且运行时长 > 2min | 可能正在擦写 | **一定不要 kill！** 串口观察确认 mai_tftp 是否在执行。等待进程自然退出 |
| 有进程占用但进程已挂起（D 状态） | 异常 | 物理断电重启设备，`fuser -k` 清理残留后再跑 |

## 进程起止时间判断

```bash
ps -o lstart= -p <PID>    # 进程启动时间（精确到秒）
stat -c %Y /proc/<PID>    # PID 的创建时间戳（epoch）
echo "进程已运行秒数: $(( $(date +%s) - $(stat -c %Y /proc/<PID>) ))"
```

## 无法读取输出时如何判断烧录状态

如果烧录进程已在运行（占用了串口）但 stdout/stderr 被管道路由到外部 shell（Hermes 未跟踪），无法直接读取输出：

1. 检查进程文件描述符：`ls -la /proc/<PID>/fd/` — 确认 fd 3 指向 `/dev/ttyUSB0`（串口连接正常）
2. 检查进程运行时长：短 < 2min → 烧录中；长 > 3min（16MB 全擦）→ 接近完成
3. 等待进程自然退出而不是用 `fuser -k` 终止
4. 进程退出后直接检查串口有无 `login:` 提示符确认结果