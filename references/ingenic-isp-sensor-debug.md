# Ingenic T32 ISP/Sensor Debugging

> Collected from <项目E> (os08f10 sensor, T32 SoC, 64MB DDR, NOR 16MB)

## RTSP Demo MCLK Crash

### Symptom

rtsp_demo runs through full pipeline:
```
System OK → FSensor OK → FS OK → Encoder OK → Streams enabled
```
Then ~25-30s later exits cleanly (SIGHUP via ADB). This is actually normal — ADB shell sends SIGHUP to background processes when the shell session closes. Use **serial console** instead of ADB to start persistent daemons.

### Kernel Oops: "Unable to handle kernel paging request"

**Error chain in dmesg:**
```
[os08f10_attr_check:1103] Have no this MCLK Source!!!
[os08f10_attr_check:1113] MCLK configuration failed!!!
[i2c_jz_irq] I2C transfer error, ABORT interrupt
[tx_isp_subdev_sensor_ops_register_sensor] g_chip_ident failed after retry
[lib_tx_isp_sensor_get_input] no active sensor for vinum 0
CPU 0 Unable to handle kernel paging request at virtual address XXXXXXXX
Oops[#1]
```

**Root cause:** `SENSOR_MCLK` defined as frequency value `24000000` (24MHz in Hz) in user-space rtsp_demo code, but the IMP API expects the enum `IMPISP_SENSOR_MCLK0 = 0`.

```c
// WRONG — this is a frequency in Hz
#define SENSOR_MCLK         24000000

// RIGHT — use the IMP enum
#define SENSOR_MCLK         IMPISP_SENSOR_MCLK0
```

The old Ingenic SDK ISP driver (drv:H20260608a) tolerated the wrong value. The server-baseline ISP driver (drv:H20260603a) enforces strict enumeration checks.

**Key lesson:** Always check that `IMPSensorInfo.mclk` is set to one of `IMPISP_SENSOR_MCLK0/1/2` (0/1/2), never a raw frequency.

### ISP Driver Sync Pitfalls

When syncing ISP driver source from Ingenic SDK (`arch/mips/xburst/lib/isp/PRJ009/`) to project's external module (`drivers/t32_t33/isp/tx-isp-PRJ009/`):

| File | Critical? | Notes |
|------|-----------|-------|
| **`board/platform.c`** | **YES** | SDK removes 4 IRQ resources (VIC/LDC/ISP/IVDC). **Keep IRQ resources** — sensor MCLK clock config fails without them. |
| `tx_isp_funcs.c` | Safe | SDK adds `memcpy` before return on `access_ok` failure. Bug fix, safe to keep. |
| `tx_isp_device.c` | Check | SDK removes `ispdev->refcnt = 1`. May affect module state tracking. |
| `src/tx_isp_fs.c` | Check | Compare carefully. |
| `include/lib_base.h` | No | Only firmware version string diff. |
| `include/tx-isp-device.h` | No | Only driver version string diff. |

### libimp.a Linking with uclibc

SDK's `libimp.a` references `__fputc_unlocked` which is a **glibc internal symbol** not present in uclibc. This causes link errors:

```
libimp.a(isp_tseries.c.o): undefined reference to `__fputc_unlocked'
```

Two solutions:

**A — Provide a stub (for uclibc):**
```c
#include <stdio.h>
int __fputc_unlocked(int c, FILE *f) { return fputc(c, f); }
```
Compile and link this stub before `libimp.a`.

**B — Use glibc libimp.a + glibc dynamic linker:**
```bash
# Link against glibc version
gcc ... -limpp -lrt -lm -ldl -lpthread
# Binary needs glibc .so.6 etc at runtime — device must have glibc or symlinks.
```

### Disabling c_mi_ipc for RTSP Testing

`mi_ipc.cfg` `"console" : 0` only disables console output — it does **NOT** prevent the service from starting.

**Reliable way to stop c_mi_ipc:**
```bash
touch /data/disable_c_mi_ipc    # run_c_mi_ipc.sh checks this file
killall c_mi_ipc                 # init won't restart it
```

Or remove the service registration from init.sh entirely.

### ADB SIGHUP vs Serial Shell

| Shell type | Background process survives? |
|------------|------------------------------|
| ADB shell | ❌ No — SIGHUP kills bg processes when ADB closes |
| Serial console (+ `&`) | ✅ Yes — persistent session |

To run a long-lived daemon without SIGHUP:
- Use serial console: `cmd < /dev/null > /tmp/log 2>&1 &`
- Or use init: `paramset ohos.ctl.start <service_name>`
