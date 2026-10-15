# <项目E> rmem Pool Management

## rmem Layout (<项目E>, 64MB DRAM)

```
bootargs: mem=42496K@0x0 rmem=23040K@0x2980000
  → Linux: 41.5 MB
  → rmem:  22.5 MB (多媒体保留)
```

## isp_memopt Parameter

ISP 驱动参数，控制 ISP 内部 rmem 缓冲用量。在 init.sh 中通过 insmod 传入：

| 值 | ISP rmem 占用 (4K) | 说明 |
|----|-------------------|------|
| 0x7 | ~10 MB | 高质量，当前生产配置 |
| 0x5 | ~7 MB | 官方默认值，省 ~3MB rmem |

官方文档建议范围 [0x0, 0x5] 或 [0x10, 0x15]。默认 0x5。0x7=0x5+0x2（额外优化）。

切换方式：
```sh
insmod tx-isp-<项目E>.ko isp_memopt=0x5 ...
```

## Diagnostics

```bash
# View rmem pools and usage
cat /tmp/continuous_mem_info

# Each pool entry shows:
#   addr: virtual address
#   size: bytes allocated
#   used: 1=in use, 0=idle
#   reuse: IDLE/CAUTION/UNUSABLE
```

## Pool Lifecycle

- `IMP_System_MemPoolRequest(poolId, size, name)` — creates pool IN rmem, BEFORE IMP_System_Init
- `IMP_System_MemPoolFree(poolId)` — frees pool, must be called in cleanup
- **Pools PERSIST across process exits** — if app crashes, pool leaks until reboot
- IMP_FrameSource_SetPool / IMP_Encoder_SetPool bind channels to existing pools by ID

## Encoder Pool Requirements (H265, Ingenic T32)

| Resolution | Pool Size Needed | Pool ID |
|-----------|-----------------|---------|
| 4K (3840×2160) | ~14 MB | 0 |
| 1080p (1920×1080) | ~8 MB | 0 |
| 480P (832×480) | ~1 MB | 1 |

## rmem Budget (<项目E> 4K)

```
rmem 22.5 MB
├── ISP internal (isp_memopt=0x7)  ~10 MB
├── OSD pool                        0.5 MB
├── ISP tuning OSD                  0.24 MB
├── Encoder pool 0 (H265 4K)       ~14 MB ← 超配!
└── Encoder pool 1 (H265 480P)     ~1 MB
                                 = ~25.7 MB > 22.5 MB
```

**Issue**: 4K H265 encoding needs 14MB pool 0, but ISP needs ~10MB. Total 24MB > 22.5MB rmem.
Workaround: Use 1080p H265 (encoder needs ~8MB, ISP needs ~3MB → fits).

## Pool Leak Pattern

When app crashes (SegFault, Abort):
1. MemPoolRequest allocates pool from rmem
2. Process dies before MemPoolFree
3. Pool persists — consuming rmem permanently
4. Next run: MemPoolRequest fails or ISP starved
5. Only reboot clears leaked pools

**Fix**: add signal handler calling cleanup, or always call MemPoolFree in all exit paths.
