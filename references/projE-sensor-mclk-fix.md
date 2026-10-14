# <项目E> os08f10 传感器 MCLK 配置修复记录

## 问题

rtsp_demo 调用 `IMP_ISP_AddSensor()` 后，传感器驱动 `os08f10_attr_check()` 中 `info->mclk` 收到的值既不等于 `TISP_SENSOR_MCLK0=0` 也不等于 `TISP_SENSOR_MCLK1=1`，进入 `default:` 分支后未初始化指针 → kernel Oops。

## 根因

### 应用层

`rtsp_demo/main.c` 中 `SENSOR_MCLK` 定义为频率值 `24000000`（24MHz），但 `IMPSensorInfo.mclk` 字段类型为枚举 `IMPISPSensorMCLK`，期望值是 `IMPISP_SENSOR_MCLK0=0`。

**修复：** `#define SENSOR_MCLK IMPISP_SENSOR_MCLK0`

### 内核驱动层

`kernel/linux/drivers/t32_t33/sensors/os08f10/PRJ009/os08f10.c` 的 `os08f10_attr_check()` 函数中，MCLK switch 的 `default:` 分支只打印错误信息但不初始化 `sclka` 和 `sensor->mclk`，后续代码用未初始化指针调用 `os08f10_clk_set()` → kernel Oops。

**修复：**
```c
struct clk *sclka = NULL;  // 初始化为 NULL

switch (info->mclk) {
    case TISP_SENSOR_MCLK0:
        // ... 正常路径
        break;
    case TISP_SENSOR_MCLK1:
        // ... 正常路径
        break;
    default:
        ISP_WARNING("Have no this MCLK Source(info->mclk=%d), "
                     "fallback to MCLK0\n", info->mclk);
        // fallback to MCLK0
        sclka = devm_clk_get(&client->dev, SEN_MCLK);
        sensor->mclk = devm_clk_get(&client->dev, SEN_BCLK);
        set_sensor_mclk_function(0);
        break;
}
if (IS_ERR_OR_NULL(sclka)) {
    ISP_ERROR("sclka acquisition failed\n");
    goto err_get_mclk;
}
```

## 验证方法

1. 编译 `sensor_os08f10_PRJ009.ko`
2. 推送到设备：`adb push sensor_os08f10_PRJ009.ko /tmp/`
3. 加载：`rmmod sensor_os08f10_PRJ009; insmod /tmp/sensor_os08f10_PRJ009.ko`
4. 运行 rtsp_demo，检查 dmesg：
   - ❌ 旧版: `Have no this MCLK Source!!!` + kernel Oops
   - ✅ 新版: `set sensor mclk(0) gpio` + `fallback to MCLK0`（无 Oops）
5. 确认 pipeline 出帧：`cat /proc/jz/isp/isp-m0 | grep frameNum`

## 附加注意

- `info->mclk` 在 SDK 驱动（drv:H20260608a）中能正常工作，在基线驱动（drv:H20260603a）中不匹配 — 可能涉及 libimp.a 和内核驱动之间的结构体布局 ABI 兼容性。
- 完整烧录固件后（含修复版 sensor .ko），第一次启动时传感器 probe 正常，无 Oops。
