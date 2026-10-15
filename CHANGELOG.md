# Changelog

本文件记录版本历史。版本号定义在 SKILL.md frontmatter 的 `version` 字段（单一真相源）。

## 2.0.10 (2026-10-15)

### Changed
- pre-push 的 CHANGELOG 同步名单注释补 `assets/`（与正则实际枚举一致）——九仓该文件文本归一

- 版本 2.0.9 → 2.0.10

## 2.0.9 (2026-10-15)

### Fixed
- **厂商名残留清零（S2）**：脚本注释与 references 共 18 处第三方品牌名（设备登录提示符里的 `<厂商>` 字样）统一泛化——
  串口提示符匹配改用通用前缀（`root@` + `login:`，与本仓既有脚本 `auto-uboot-interrupt.py` 同口径），
  注释写「现场 fix」，示例写 `<设备主机名>`。**匹配行为不变**：`root@` 覆盖「已登录」提示符、`login:` 覆盖「未登录」提示符，
  二者在该设备上与原子面量等价（原字面量本身就是 `login:` 的子串），且不会误匹配 `Login incorrect`；已逐行复核。
- **人名/昵称残留（S4）**：`references/post-flash-md5-verification.md` 两处同事昵称改为「操作者」/「执行者」。
  此类无法正则枚举的标识（人名、厂商 SDK 名、内部技能名）在本机未跟踪名单 `scripts/publish-deny.local` 内维护，闸门一并扫。
- **死链（S3）**：`references/ingenic-serial-boot-login.md` 六处「详见某已并入技能」改指仓内文件
  （连接建立 → `references/serial-debug-diagnostics.md`，命令执行 → `references/command-execution-patterns.md`，
  ADB SIGHUP → `references/ingenic-isp-sensor-debug.md`，ADB 降级 → 本文 §六）；删除指向未发布内部技能的一行「相关技能」；
  三份 references 的 frontmatter `name` 改回与文件名一致（原为已并入的旧技能名），并去掉 `debug-playbook` 引用。
- **文档与实现相反（S1）**：SKILL.md 称发布闸门「仅发布仓内，不随安装下发」，而 `install.sh` 整目录拷 `scripts/`
  ⇒ 实为随装下发 ⇒ 口径改为「随 `scripts/` 一并安装，仅供本仓维护者使用，日常烧录不涉及」。
- **CHANGELOG 版本链错位（S6）**：混在 2.0.0 条目内的「1.7.0 → 1.8.0」变更独立成 `## 1.8.0 (2026-08-18)` 条目，
  放到 1.9.0 之后（保持新→旧降序）；2.0.0 条目只留 1.9.1 → 2.0.0 一段。

### Changed
- **README 目录结构数量词（S5）**：`scripts/` 行由「9 个可运行脚本」改为「9 个运行脚本 + 发布闸门 publish-check.py 与 hooks/」，
  与 S1 处置口径一致。
- 版本 2.0.8 → 2.0.9

## 2.0.8 (2026-10-15)

### Fixed
- **脱敏回潮清理（新版闸门首次扫出）**：历史条目、references 与脚本注释里残留的提示符代号统一换 `<项目E>`；
  内网网段改写为 `<宿主网段>` / `<设备网段>`；例子里的真代号换成形态写法（`HM####` 这类）。
- **README 目录结构块与实际严重不符**：references 只列 1 个（实际 34 个）、scripts 只列 6 个（实际 9 个）、
  未列 CHANGELOG.md ⇒ 改为概述 + 指向 SKILL.md 的清单，并补实际脚本项与 CHANGELOG.md。
- **密码口径冲突（会导致盲打登录失败）**：SKILL.md 四处「密码为空」与 `references/` 的「分固件版本」互相矛盾 ⇒
  统一为「先试空密码（旧固件），失败再试 `root`/`root`（新固件）」，正文与注释同步。
- **「双写」约定指向不存在的目录**：旧文写「与 `~/.pi/agent/skills/serial-tftp/` 同源双份，改动须双写」，
  该目录在本机不存在 ⇒ 改为按 install.sh 的 pi 目标安装（`bash install.sh --target pi`）。
- **死链**：删除指向不存在技能的「相关 skill」段（重启压力测试已在本仓 `scripts/reboot-stress.py` + SKILL.md 表内）。
- **占位符过度折叠**：波特率表 / 项目配置表两行项目名此前都成同一个 `<项目>`（两行不可区分）⇒ 按仓内
  references 的项目记录还原为 `<项目E>` / `<项目A>`。
- **CHANGELOG 结构**：`1.9.0` / `1.9.1` 两段从 `1.0.0` 之后上移到 `2.0.0` 之前（保持新→旧降序）；
  「本文件记录版本历史…」说明行移到 H1 之后。

### Changed
- 版本 2.0.7 → 2.0.8

## 2.0.7 (2026-10-15)

### Fixed
- **发布闸门 publish-check.py 三个洞同批修**（脱敏反复回潮的根因之一：闸门对真实标识零防护却一直报「干净」）：
  ① 代号正则大小写不敏感（旧版只认小写，大写写法如 `HM####` 整体漏）；
  ② 白名单改为**按匹配项豁免**（旧版 `if any(a in line for a in ALLOW): continue` 是整行豁免——一行里出现
  `<项目A>` 就给同行的真名背书；且原 7 个词对 12 条 pattern 全部零命中 = 纯死豁免）；
  ③ 词边界改用显式字符类（`\b` 在 str 模式下 `\w` 含汉字 ⇒「项目hm####」这类中文常见写法漏检，
  加不加空格决定报不报）。另补 PRJ0## / 裸数字代号 / MAC 连字符 / 凭据变体（`token=`、`Bearer`、中文『密码』后接冒号）/
  邮箱 六类形态。
- **`--self-test` 样本按已知缺陷类别扩容**（原 15 条只覆盖「正常裸值」一档，上述六类一条样本都没有）；
  自检与扫描共用同一份判定口径（`line_hits`），不再各写一套造成假绿。
- **`scripts/hooks/pre-push` 在推送路径上先跑 `--self-test`**（规则表被改坏时不得静默通过）；
  CHANGELOG 名单统一为超集（SKILL / SCHEMA / install.sh / templates / references / scripts，9 仓文本自此一致）；
  基点改为 `origin/main → gitee/main → 根提交` 三级回落（旧版无 `origin/main` 时回落到 `HEAD~1`，
  多笔提交一起推会只看最后一笔）。
- **新增本机私用名单 `scripts/publish-deny.local`**（gitignore、不进仓）：人名 / 昵称 / 厂商 SDK 名 /
  内部 skill 名这类**无法正则枚举、也不该写进发布仓**的标识，在本机未跟踪文件里逐行列真名，闸门自动一并扫。

### 说明
- 口径全文见 `scripts/publish-check.py` 文件头（已知边界：长 hash 折行、全角句点 IP 不识别；该文件自身在
  `SKIP_FILES` 内，改它时需人工核对）。9 仓共用同一份闸门（md5 一致）——改一处必须批量同步。
- 版本 2.0.6 → 2.0.7

## 2.0.6 (2026-10-14)

### Fixed（install.sh 两处 + 发布闸门，与 qwiki-skill 同款）

- **`--target hermes,claude`（空格形式）从未生效**：解析只认 `--target=`，空格形式把值吞成空串后落进"非交互 = 装全部"分支——而 README / 用法行 / 脚本头部**三处文档全写的空格形式**。现两种形式都支持，且 `--target` 缺参数时直接报错退出（不再静默装全部）。
- **备份落在 skills 扫描根之内**：旧版备份写成 `<skills>/<name>.bak.<时间戳>`，而 agent 按「含 SKILL.md 的目录」发现技能、不看目录名 ⇒ 备份被当成**第二个同名技能**加载（重名歧义下静默跳过其一）。现备份落 `<tool 根>/skills-backup/`（扫描根之外），README 与脚本尾注同步。
- **挂上 pre-push 闸门（脱敏 + CHANGELOG 同步）**：`scripts/publish-check.py`（扫项目代号 / 内网 IP / MAC / 长 hash / 凭据 / 本机路径，自带 `--self-test`）+ `scripts/hooks/pre-push`；启用一次 `git config core.hooksPath scripts/hooks`。理由与脱敏规则同源：**靠人记必然回潮**，检查要做成"推送时自动拦"而不是"记得手动跑"。CHANGELOG 闸门名单 = SKILL.md / install.sh / scripts/ / references/。
- **脱敏：全量清理项目代号 / 内网 IP / MAC / 内网路径**（闸门首扫命中后执行）——正文、references、脚本注释与默认值一并处理：项目代号 → `<项目A>`…`<项目F>`（**大小写不敏感**，大写写法一并换）；IP / MAC → `<IP-n>` / `<MAC-n>`（**文件内编号唯一**，保住句内多机对比关系）；内网代码树路径 → `<代码树>/`，本机家目录 → `<用户目录>/`；**脚本里的功能性默认值改为环境变量**（`TFTP_PROJECTS` / `DEVICE_IP` / `TFTP_GATEWAY`，未给时报错或显式跳过，不再写死内网值）；9 个文件名含代号的 references 改名（真名 → `projA-*` / `projE-*`），SKILL.md 引用清单同步。历史不回改（已公开的收不回，force push 也不行），本次只保证往后版本不再含。
- 版本 2.0.5 → 2.0.6

## 2.0.5 (2026-09-30)

### Changed

- 支持文件清单补全：`## 参考资料` 补 15 条（串口调试类，此前只落盘未登记）、`## 串口工具` 表补 3 个脚本（flash_config / serial_login_ip / serial_compat）
- 引用率 25/43 → 43/43
- 版本 2.0.4 → 2.0.5

## 2.0.4 (2026-09-28)

### Changed

- 回灌本机 Hermes 副本的实测修正：reboot 压测三禁 + auto-uboot-interrupt 网络回读核对门禁（flash-gate 09-11）+ flash_config 烧录门禁 6a/6b/6c
- 版本 2.0.3 → 2.0.4

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
  `<项目E># ping <IP-1>\rping <IP-1>\rping <IP-2>` 粘成一行、
  预检残渣还会被紧随其后的验证/命令吃掉（烧录偶发失败、靠 ping 重试自愈）。
  （2026-09-17 现场记录 → 2026-09-24 定位，见 qwiki `<项目A>_wifi/20260917-redline-310-vs-515-ab-result.md` §6）
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

## 1.9.1 (2026-08-28)

### Added

- install.sh 新增 pi 安装目标（探测 `~/.pi/agent` → 安装到 `~/.pi/agent/skills/<skill>`，pi 自动发现）
- 版本 1.9.0 → 1.9.1

## 1.9.0 (2026-08-28)

### Added（并入 serial-debug）

- 新增「串口调试（非烧录场景）」章节：发 CR 判模式铁律、盲打登录、命令执行模式、常见操作、故障速查
- 并入 serial-debug 的脚本 `serial_login_ip.py` 与 19 个串口调试 references
- description 更新为「串口交互 + TFTP 刷机一站式」；triggers 补串口调试/盲打登录/波特率等
- 版本 1.8.0 → 1.9.0

## 1.8.0 (2026-08-18)

### Changed（审查修复）

- **终端直连命令改为统一 CLI 入口**：README 无 AI 终端示例从 `python3 ~/.hermes/skills/serial-tftp/scripts/...` 改为 `serial-tftp setup/config/flash`（安装脚本自动建 `~/.local/bin/serial-tftp` 链接，去掉对 Hermes 安装路径的硬编码；手动复制安装的兜底说明同步）
- 版本 1.7.0 → 1.8.0

## 1.7.0 (2026-08-18)

### Added

- **ZCode 安装目标**：`install.sh` 支持 ZCode（探测 `~/.zcode` → 安装到 `~/.zcode/skills/serial-tftp`，CLI 入口 `serial-tftp` 同步链到 `~/.local/bin/`），README 补 `--target zcode` 示例，发布页一键命令即可装到 ZCode

## 1.6.0 (2026-08-05)

### Added（烧录参考资料并入，2026-08-05 skill 审计）
- **14 个烧录参考资料从 ingenic-basic-tftp-flash 并入** `references/`：post-flash-md5-verification（烧录后 MD5 三方对齐铁律）、<项目A>-full-erase-flash（全擦实录）、<项目A>-partial-erase-flash-at-uboot-recovery（部分擦除+U-Boot 恢复）、<项目A>-flash-timing-zb25vq128（timing 与 ZB25VQ128 变体）、tftp-flash-baud-uboot-recovery（波特率+打断恢复）、20260717-shell-timeout-recovery、bricked-nor-recovery（变砖恢复）、nor-all-bin-layout-recovery、flash-network-diagnosis-anti-pattern、flash-verify-boot-changes、flashing-concurrent-prevention、build-output-staleness-verification、post-flash-wifi-reconnect、skill-failure-handling
- SKILL.md 参考资料段同步列出全部 16 个 references
- 无关调试类资料（i2c/mjac/isp 等 12 个）转存 qwiki 项目知识库
- 版本 1.5.0 → 1.6.0

## 1.5.0 (2026-08-03)

### Changed（参考分层 A 模式对齐）
- **坑内容从 SKILL.md 移入 `references/troubleshooting.md`**：失败恢复速查 / 各步骤失败处理 / 反模式表 / IP 冲突根因——SKILL.md 只留干净主流程，坑按需查阅（参考分层定稿，见 hermes-skill-gen v1.3.0）
- SKILL.md 五步图失败处理改一行导航（指向 troubleshooting.md）；IP 冲突预检括号原因移除（根因归 references）
- 版本 1.4.0 → 1.5.0

## 1.4.0 (2026-08-01)

### Fixed（<项目A> 真机实践复盘，三轮 LOOP 优化）
- **IP 冲突预检**：配网后 ping 设备自身 IP，通 = 被占用 → 中止并给排查路径（根因：设备 IP 与局域网设备冲突导致 TFTP T T T T 反复失败）
- **打断 U-Boot 提示符探测化**：不再硬编码 `<项目>#`（真实设备是 `<项目E>#` 匹配不上），改正则匹配行尾 # 或 =>
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
- 脱敏：提示符真名 → `<项目>#`，进程名加"按设备调整"说明
- scripts: auto-uboot-interrupt.py / flash_config.py / serial_cmd.py / capture_boot_log.py / reboot_capture.py / reboot-stress.py
- references/serial-console-notes.md 串口交互经验