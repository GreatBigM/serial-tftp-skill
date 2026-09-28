# Changelog
## 2.0.4 (2026-09-28)

### Changed

- 回灌本机 Hermes 副本的实测修正：reboot 压测三禁 + auto-uboot-interrupt 网络回读核对门禁（flash-gate 09-11）+ flash_config 烧录门禁 6a/6b/6c
- 版本 2.0.3 → 2.0.4


本文件记录版本历史。版本号定义在 SKILL.md frontmatter 的 `version` 字段（单一真相源）。

## 2.0.3 (2026-09-28)

### Added（故障速查补两条——业务槽串口"有回显但命令不执行"）

- **有回显但命令不执行**：业务槽（OpenHarmony/Android init 侧）getty 会消失，键盘字符仍有回显但命令不落；
  该 boot 往往同时 eth0/adbd 不在网 ⇒ 只能重启恢复。
- **反复 login 失败后彻底无 shell**：顶到 init 的 respawn 限额。提示符出现时**一次**登录
  （实测 root + 空密码直接进），别反复重试——实测 ~8 次失败后本 boot 再无 getty。
  （与"getty 提示符被日志洪流淹没 → 多试几次 CR"是两回事：前者是**登录尝试**次数，后者是**CR 唤醒**。）

## 2.0.2 (2026-09-24)

### Fixed（真 bug：IP 冲突预检从上线起就是空转的）

- **`scripts/auto-uboot-interrupt.py` IP 冲突预检写的是字面反斜杠+r，不是回车**：
  `ser.write(f"ping {ipaddr}\\r".encode())` —— f-string 里 `\\r` 求值成**反斜杠和 r 两个可打印字符**，
  U-Boot 的 hush 只在收到 CR 时才把整行交给解析器，于是：
  ① 预检**从未真的 ping 过**（“IP 被占用”永远报不出来，而报错引导里还让人“先查 IP 冲突”→ 把人往沟里带）；
  ② 文本堆在控制台输入缓冲里，直到下一条真 CR 被一起结清，现场表现
  `PRJ009# ping 172.17.151.118\rping 172.17.151.118\rping 172.17.151.6` 粘成一行、
  预检残渣还会被紧随其后的验证/命令吃掉（烧录偶发失败、靠 ping 重试自愈）。
  （2026-09-17 现场记录 → 2026-09-24 定位，见 qwiki `hm6502_wifi/20260917-redline-310-vs-515-ab-result.md` §6）
- **新增 `uboot_cmd(ser, cmd, timeout=10)` 统一出口**：写前 `reset_input_buffer()`、真正的 `\r` 只在这里拼、
  读回以提示符 `#` 为界而不是固定 `sleep 3`。`check_ip_conflict()` 与 `ping_verify()` 全部改走它。
  纪律：**今后任何写 U-Boot 的地方都走这个函数**（同类笔误不会再出现）。
- 判据收紧：成功只看 U-Boot 的 `is alive` 行（失败行 `host X is not alive` 不含该子串，不误判）；
  `retries=1` 的“最多 2 次尝试”语义写明；冲突提示补 `--no-ping` 逃生门（跳过含预检在内的网络预检）。
- 顺手清掉 `ping_verify()` 开头的死代码（`ip = serverip.rstrip(...)` 下一行就被 `ip = serverip` 覆盖）。
- 版本 2.0.1 → 2.0.2

## 2.0.1 (2026-09-23)

### Added（工作副本回灌，09-17/09-22 实机踩坑）

- 设备 shell 转义：**反斜杠须双写**（`\n`→`\\n`、`"`→`\42`、空格→`\040`），单写静默写错内容
- 设备 shell 吞双引号 → 主机侧卡在 `> ` 续行（脱出方式）+ `base64 -d` 静默 0 字节
- **busybox ash 不展开重定向目标里的 glob**（报错带未展开星号是识别特征）+ 设备工具清单（无 `head`/`tail`/`iw`/`iwpriv`）+ debugfs 需手挂、phy 号随重载变 ⇒ 路径写 glob
- 工作副本另有「烧录门禁与高频坑」段（09-12 补），一并回灌

## 2.0.0 (2026-08-29)

### Changed（定位调整：skill 归属于 agent，无人通道）

- **移除全局命令入口**：install.sh 不再 `ln -sf` 到 `~/.local/bin/serial-tftp`；不再注册 PATH
- **SKILL.md「终端直连 / 便捷入口」章节改为「脚本入口（skill 目录内，不全局注册）」**：所有调用都走 `<skill_dir>/scripts/`，agent 专属
- **wrapper 脚本定位更新**：`scripts/serial-tftp` 保留在 skill 目录内作为 agent 可选统一入口，用法改为 `<skill_dir>/scripts/serial-tftp ...`
- 版本 1.9.1 → 2.0.0

### Changed（审查修复）

- **终端直连命令改为统一 CLI 入口**：README 无 AI 终端示例从 `python3 ~/.hermes/skills/serial-tftp/scripts/...` 改为 `serial-tftp setup/config/flash`（安装脚本自动建 `~/.local/bin/serial-tftp` 链接，去掉对 Hermes 安装路径的硬编码；手动复制安装的兜底说明同步）
- 版本 1.7.0 → 1.8.0

## 1.7.0 (2026-08-18)

### Added

- **ZCode 安装目标**：`install.sh` 支持 ZCode（探测 `~/.zcode` → 安装到 `~/.zcode/skills/serial-tftp`，CLI 入口 `serial-tftp` 同步链到 `~/.local/bin/`），README 补 `--target zcode` 示例，发布页一键命令即可装到 ZCode

## 1.6.0 (2026-08-05)

### Added（烧录参考资料并入，2026-08-05 skill 审计）
- **14 个烧录参考资料从 ingenic-basic-tftp-flash 并入** `references/`：post-flash-md5-verification（烧录后 MD5 三方对齐铁律）、hm6502-full-erase-flash（全擦实录）、hm6502-partial-erase-flash-at-uboot-recovery（部分擦除+U-Boot 恢复）、hm6502-flash-timing-zb25vq128（timing 与 ZB25VQ128 变体）、tftp-flash-baud-uboot-recovery（波特率+打断恢复）、20260717-shell-timeout-recovery、bricked-nor-recovery（变砖恢复）、nor-all-bin-layout-recovery、flash-network-diagnosis-anti-pattern、flash-verify-boot-changes、flashing-concurrent-prevention、build-output-staleness-verification、post-flash-wifi-reconnect、skill-failure-handling
- SKILL.md 参考资料段同步列出全部 16 个 references
- 无关调试类资料（i2c/mjac/isp 等 12 个）转存 qwiki 项目知识库
- 版本 1.5.0 → 1.6.0

## 1.5.0 (2026-08-03)

### Changed（参考分层 A 模式对齐）
- **坑内容从 SKILL.md 移入 `references/troubleshooting.md`**：失败恢复速查 / 各步骤失败处理 / 反模式表 / IP 冲突根因——SKILL.md 只留干净主流程，坑按需查阅（参考分层定稿，见 hermes-skill-gen v1.3.0）
- SKILL.md 五步图失败处理改一行导航（指向 troubleshooting.md）；IP 冲突预检括号原因移除（根因归 references）
- 版本 1.4.0 → 1.5.0

## 1.4.0 (2026-08-01)

### Fixed（HM6502 真机实践复盘，三轮 LOOP 优化）
- **IP 冲突预检**：配网后 ping 设备自身 IP，通 = 被占用 → 中止并给排查路径（根因：设备 IP 与局域网设备冲突导致 TFTP T T T T 反复失败）
- **打断 U-Boot 提示符探测化**：不再硬编码 `<项目>#`（真实设备是 PRJ009# 匹配不上），改正则匹配行尾 # 或 =>
- **静默窗口打断**：有输出时不发回车，静默 ≥0.3s 才砸——避免和 mai_tftp 重试循环的 T 输出打架
- **失败恢复提示细化**：mai_tftp 循环（静默窗口 Ctrl+C）/ IP 冲突（ip neigh 排查）/ 打断失败三场景具体路径
- SKILL.md 流程铁律同步：IP 冲突预检 + 提示符探测 + 失败恢复速查

### Changed
- 版本 1.3.0 → 1.4.0

## 1.2.0 (2026-08-01)

### Added
- **serial_compat.py：pyserial 兼容层（标准库 termios 实现，零依赖）**——环境无 pyserial 时自动 fallback，无需 pip install
- 6 个脚本 import 统一改为 try/except fallback（有 pyserial 用 pyserial，无则用标准库）
- 解决协作者环境差异：py3 必有 + pyserial 可能缺失的场景全覆盖

### Changed
- 版本 1.1.0 → 1.2.0

## 1.1.0 (2026-08-01)

### Added
- **统一命令入口 `serial-tftp`**（scripts/serial-tftp wrapper）：版本门卫（py3 检测在 Python 解析前拦截 py2-only 环境，友好提示不崩溃）+ 子命令分派（flash/setup/config/cmd/capture/reboot-capture/stress/shell）
- install.sh 安装 wrapper 到 ~/.local/bin/serial-tftp
- py3 版本检测：flash_config.py 顶部 sys.version_info < 3.6 拦截（3.0-3.5 提示）

### Changed
- README/SKILL.md：使用方式主推 `serial-tftp` 命令入口，依赖明确 Python 3.6+

## 1.0.0 (2026-08-01)

### Added
- 初始发布：serial-tftp 单技能（串口交互 + TFTP 刷机五步流程）
- 由 serial-debug + serial-tftp 两技能收敛合并（消除重叠）
- 顶部新增「AI 替你完成」使用哲学头节 + AI 交互约定（agent 走参数路径，不用管道喂 stdin）
- setup 交互式参数设定向导：逐项输入+校验，回车接受默认值，q 取消，取消零副作用
- flash 预检失败自动引导：参数缺失 → 询问是否进入交互设定（isatty 分界）
- 脱敏：prj009# → <项目>#，进程名加"按设备调整"说明
- scripts: auto-uboot-interrupt.py / flash_config.py / serial_cmd.py / capture_boot_log.py / reboot_capture.py / reboot-stress.py
- references/serial-console-notes.md 串口交互经验

## 1.9.0 (2026-08-28)

### Added（并入 serial-debug）

- 新增「串口调试（非烧录场景）」章节：发 CR 判模式铁律、盲打登录、命令执行模式、常见操作、故障速查
- 并入 serial-debug 的脚本 `serial_login_ip.py` 与 19 个串口调试 references
- description 更新为「串口交互 + TFTP 刷机一站式」；triggers 补串口调试/盲打登录/波特率等
- 版本 1.8.0 → 1.9.0

## 1.9.1 (2026-08-28)

### Added

- install.sh 新增 pi 安装目标（探测 `~/.pi/agent` → 安装到 `~/.pi/agent/skills/<skill>`，pi 自动发现）
- 版本 1.9.0 → 1.9.1
