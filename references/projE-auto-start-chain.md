# <项目E> Auto-Start Chain & Disabling c_mi_ipc

## Init Chain (debug mode)

```
init.sh → workmode=debug
  → factory.cfg: "param:workmode=debug"
    → cmd: "system /system/bin/start_user_process.sh"  (WiFi/BT drivers)
    → cmd: "trigger mi_ipc_init"
      → mi_ipc.cfg: job "mi_ipc_init" → cmd: "start mi_ipc_start"
        → mi_ipc_start service: run_c_mi_ipc.sh → c_mi_ipc
```

## Why mi_ipc.cfg disabled=1 doesn't work alone

`disabled: 1` on the **service** prevents auto-start, but `trigger mi_ipc_init` is a **job trigger** from factory.cfg that issues `start mi_ipc_start` — this bypasses the disabled flag.

## Correct way to disable c_mi_ipc auto-start

1. **mi_ipc.cfg**: add `"disabled": 1` to the service (prevents other triggers)
2. **factory_<项目E>.cfg**: remove `"trigger mi_ipc_init"` from debug/user/unknown mode jobs

Source files:
- `test/factory_test/factory/factory_<项目E>.cfg` → copied to `init_cfg/factory.cfg` during build
- `applications/c_mi_ipc/etc/mi_ipc.cfg` → copied to `init_cfg/mi_ipc.cfg` during build

Build mechanism: CMakeLists copies `factory_${PROJECT_ID}.cfg` → `${SMART_INIT_CFG_PATH}/factory.cfg`

## miio_client start chain

miio_client is NOT started by any service_cfg. It's started by wifi_start.sh (part of OT_SDK), which is triggered by c_mi_ipc during initialization. When c_mi_ipc is disabled, miio_client won't start either.

## adbd auto-start

adbd auto-starts during boot via init system (not via init.sh). No explicit `adbd &` in init.sh. After flash, adbd is available on port 5555 after network comes up.
