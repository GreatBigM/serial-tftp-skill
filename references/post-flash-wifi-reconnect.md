# 烧录后 WiFi 手动重连

> 部分擦（0xef0000）烧录后，WiFi 配置在 /data 中保留但 wpa_supplicant 不自动启动。需手动操作。

## 触发场景

- 烧录后 eth0 ADB 在线但 wlan0 无 IP
- `ifconfig wlan0` 显示 `UP BROADCAST MULTICAST` 但无 `inet addr`
- `/data/wpa_supplicant.conf` 存在且有有效 SSID/PSK
- WiFi 驱动已加载（dmesg 有 `aic8800_fdrv` 注册成功）

## 一键恢复

```bash
adb shell '
killall wpa_supplicant 2>/dev/null
rm -rf /tmp/wpa_supplicant
mkdir -p /tmp/wpa_supplicant
ifconfig wlan0 up
wpa_supplicant -D nl80211 -i wlan0 -c /data/wpa_supplicant.conf -B
sleep 2
udhcpc -i wlan0 -b -A 3
'
```

> ⚠️ ctrl_interface 必须是 `/tmp/wpa_supplicant`（`/var/run/wpa_supplicant` 是只读 squashfs）

## 验证

```bash
adb shell ifconfig wlan0          # 应有 inet addr
adb shell ping -c 2 <网关IP>      # 确认连通
```

## 2026-07-17 实测

- 设备：HM6502，部分擦 0xef0000 烧录，WiFi SSID=znetx 5GHz 802.11ac
- 烧录后 wlan0 无 IP，`/data/wpa_supplicant.conf` 配置完好
- 手动启动 wpa_supplicant + udhcpc → 获取 10.10.10.207，ping 3-9ms
- iperf3 WiFi 测速：TX 70.5 Mbps / RX 75.5 Mbps
