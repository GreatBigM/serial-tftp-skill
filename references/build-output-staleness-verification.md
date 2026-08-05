# 构建产物一致性验证

## 背景

HM6502/HM6801 的增量编译可能产生 **内核 vmlinux 新 + 模块 .ko 旧** 的不一致状态。原因：`make_drivers.sh` 把编译的新 .ko 放入 `.tmp/driver/`，但 `system_b.squashfs` 从 `.tmp/system_b/lib/modules/` 打包。两个目录来源不同（`make modules_install` vs `make_drivers.sh`），可能用到不同批次的编译产物。

## 验证命令

```bash
# 在宿主对比三处 MD5
echo "=== Build output (driver/) ==="
md5sum out/image_hm6502/.tmp/driver/tx-isp-PRJ009.ko

echo "=== Staging (system_b/) ==="
md5sum out/image_hm6502/.tmp/system_b/lib/modules/tx-isp-PRJ009.ko

echo "=== Packed (system_b.img) ==="
unsquashfs -f -d /tmp/sys_check out/image_hm6502/system_b.img lib/modules/tx-isp-PRJ009.ko 2>/dev/null
md5sum /tmp/sys_check/lib/modules/tx-isp-PRJ009.ko

echo "=== Device ==="
adb shell md5sum /system/lib/modules/tx-isp-PRJ009.ko
```

## 修复方法

driver/ 和 system_b/ 不一致时，手动复制再重打包：

```bash
cp -f out/image_<项目>/.tmp/driver/*.ko out/image_<项目>/.tmp/system_b/lib/modules/
# 删除 dangling symlink（指向 docker 内路径的 link 在宿主机无效）
rm -f out/image_<项目>/.tmp/system_b/lib/modules/lockd.ko
rm -f out/image_<项目>/.tmp/system_b/lib/modules/nfs*.ko
rm -f out/image_<项目>/.tmp/system_b/lib/modules/sunrpc.ko
# 重建 squashfs + NOR
mksquashfs out/image_<项目>/.tmp/system_b/ out/image_<项目>/.tmp/system_b.squashfs -noappend -comp xz
cp out/image_<项目>/.tmp/system_b.squashfs out/image_<项目>/system_b.img
docker run --rm -v /mnt/data/项目:/workspace smart:latest bash -c 'cd /workspace/build && make pack_all'
```

## 彻底预防

清空 `out/image_<项目>/` 后全量编译，确保没有任何旧产物残留。
