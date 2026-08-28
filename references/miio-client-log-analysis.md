# miio_client 日志分析参考

HM6502 miio_client 行为模式，基于 5 小时/9.8 万行日志分析。

## Timer 精度

1 秒周期定时器 (D0) 的行为分布：

| 延迟范围 | 占比 | 含义 |
|---------|------|------|
| ≤1005ms | 24% | 准时 |
| 1006-1020ms | 33% | 轻微抖动 |
| 1021-1050ms | 40% | 偏慢 2-5%，最常见 |
| 1051-1100ms | 2.4% | 明显延迟 |
| >1100ms | 0.3% | 严重延迟（最差 3318ms） |

## WiFi 重连模式

- miio_client 每秒重试连接 wpa_supplicant
- 全部失败（`connect error` / `open failed`）— 正常，设备未配网
- 5 小时内行为无退化

## MJAC 检测

搜索 `mjac` 关键词在 miio_client 日志中：
- 仅 2 行相关日志（通常出现在设备首次启动时）
- 内容: `mjac_i2c: /dev/i2c-1` — MJAC 在 i2c-1 总线
- `did not int` — MJAC 未初始化（硬件缺失时正常）

## 崩溃

- miio_client 可被 init 自动重启（PID 变化）
- 分析：检查不同 PID 数量判断重启次数
