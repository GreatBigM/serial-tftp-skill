# MIPS 预编译二进制反汇编指南

## 适用场景
分析嵌入式设备中的预编译二进制（如 miio_client、libmike.a 等），
追踪函数调用链、理解 RPC 消息处理逻辑、定位错误路径。

## 工具链

```bash
# 安装 MIPS 交叉 binutils（Ubuntu）
sudo apt-get install binutils-mips-linux-gnu

# 使用
mips-linux-gnu-objdump -d binary.elf
mips-linux-gnu-readelf -a binary.elf
```

## 分析流程

### 1. 确认二进制类型
```bash
file miio_client
# ELF 32-bit LSB executable, MIPS, MIPS32 rel2, dynamically linked, stripped
```

`stripped` = 无符号表，函数名只能从字符串推断。

### 2. 找关键字符串
```bash
strings -t x miio_client | grep -i "error\|did not int\|response_dinfo"
#   e60f4 [E] %s: did not int (%s,%d)
```

输出格式：文件偏移 + 字符串内容。

### 3. 字符串地址转虚拟地址 (VA)
```bash
# .rodata section info:
# 12 .rodata: VA 0x4d4460, file offset 0xd4460
# 字符串在文件偏移 0xe60f4
# VA = 0x4d4460 + (0xe60f4 - 0xd4460) = 0x4e60f4
```

### 4. 查找代码中对字符串的引用
在 PIC 代码中，字符串通过 GP-relative 寻址：

```bash
# 查找 addiu 指令中的低 16 位匹配
# 0x60f4 = 24820
mips-linux-gnu-objdump -d binary | grep "60f4" | head -10
# 47fe54: addiu a0,s5,24820  → 引用 [E] did not int
```

### 5. 反汇编关键函数
```bash
mips-linux-gnu-objdump -d binary \
  --start-address=0x47fc00 --stop-address=0x47ff00
```

### 6. 查找函数符号（动态链接时）
```bash
mips-linux-gnu-nm -D miio_client | grep i2c
# 004cf85c T arch_i2c_write
# 004cf8cc T arch_i2c_read
```

`-D` = dynamic symbols，只显示导出/导入符号。

### 7. 追踪 GOT 调用
PIC 代码调外部函数：
```
lw t9, -26892(gp)    # 从 GOT 加载函数指针
jalr t9               # 间接调用
```

GOT 偏移 → 查 `.got` section：
```bash
mips-linux-gnu-readelf -r binary | grep <offset>
```

## MIPS 反汇编快速参考

### 函数调用约定 (o32 ABI)
| 寄存器 | 用途 |
|--------|------|
| a0-a3  | 参数 1-4 |
| v0-v1  | 返回值 |
| t0-t9  | 临时 |
| s0-s8  | 保存寄存器（Callee-saved）|
| gp     | 全局指针 (PIC) |
| sp     | 栈指针 |
| ra     | 返回地址 |

### 常见指令
| 指令 | 含义 |
|------|------|
| `lw rt, offset(rs)` | Load Word |
| `sw rt, offset(rs)` | Store Word |
| `addiu rt, rs, imm` | Add Immediate Unsigned |
| `lui rt, imm` | Load Upper Immediate |
| `jalr rs` | Jump and Link Register |
| `bal offset` | Branch and Link (PC-relative call) |
| `beqz rs, offset` | Branch if EQual Zero |
| `bnez rs, offset` | Branch if Not Equal Zero |
| `jr ra` | Jump Register (return) |
| `move rd, rs` | 伪指令: `addu rd, rs, zero` |

### PIC 函数入口样板
```asm
lui gp, 0xa           # 加载 GOT 高 16 位
addiu gp, gp, 8184    # gp = GOT 基地址
addu gp, gp, t9       # gp = t9 + GOT 偏移 (PC-relative)
```

### 日志打印模式
MIPS 预编译二进制中日志函数遵循固定模式：
```asm
# 1. arch_printf_begin — 开始日志
bal arch_printf_begin

# 2. log_printf_ex — 打印带行号的日志
li a3, 1717           # 行号
addiu a2, ..., XX     # 参数字符串/数据
addiu a1, ..., YY     # 格式参数
addiu a0, ..., ZZ     # 格式字符串 "[E] ..."
bal log_printf_ex

# 3. arch_printf_end — 结束日志
bal arch_printf_end
```

## 常见坑

| 坑 | 说明 |
|----|------|
| 找 `lui 0x4e` 匹配太多 | 高 16 位重复率高，用低 16 位 `addiu` 匹配更精确 |
| GOT 偏移是负数 | `lw t9, -29632(gp)` — 用 2's complement: `0x73C0` |
| `bal` 目标 = PC + offset × 4 | MIPS 分支延迟槽，目标地址要 /4 再乘 |
| `nop` 在分支后 | 延迟槽指令，CPU 先执行再跳转 |
