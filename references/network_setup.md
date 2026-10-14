# <项目A> 开发环境网络配置

> 开发时设备通过有线直连宿主机，需要配同网段 IP + 网关 + DNS

## 宿主机

```bash
# 给宿主网口加一个同网段 IP（如果还没配）
sudo ip addr add <IP-1>/23 dev enp2s0
```

## 设备端（串口）

```bash
# 登录 root，密码为空
ifconfig eth0 <IP-2> netmask 255.255.254.0 up
route add default gw <IP-3>
echo "nameserver 223.5.5.5" > /etc/resolv.conf
adbd &
```

## 验证

```bash
ping <IP-2>         # 宿主机→设备通
adb connect <IP-2>:5555
adb shell ping baidu.com    # 设备能出外网
```

## 常见问题

| 问题 | 原因 | 处理 |
|------|------|------|
| ping 不通 | 不同网段 | `ip addr add` 配同网段 |
| ADB 连不上 | adbd 没启动 | 串口 `adbd &` |
| DNS 失败 | 无 resolv.conf + 无默认网关 | 上面两条都要配，缺一不可 |
| 重启后丢失 | 运行时配置不持久 | 每次重启重配 |
| DHCP 改 IP | c_mi_ipc 的 start_lan.sh 启动 udhcpc | 开发版已注释掉该行 |
