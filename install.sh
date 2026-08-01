#!/usr/bin/env bash
# serial-tftp-skill 一键安装脚本
# 用法: curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/GreatBigM/serial-tftp-skill.git"
SKILL_NAME="serial-tftp"
DEST="${HOME}/.hermes/skills/${SKILL_NAME}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "==> 克隆仓库（--depth 1）..."
git clone --depth 1 "${REPO_URL}" "${TMP}/repo" >/dev/null 2>&1 || {
    echo "❌ 克隆失败，请检查网络或仓库地址"; exit 1; }

echo "==> 安装 ${SKILL_NAME} ..."
mkdir -p "${HOME}/.hermes/skills"
if [ -d "${DEST}" ]; then
    BAK="${DEST}.bak.$(date +%Y%m%d%H%M%S)"
    echo "    检测到已有安装，备份到 ${BAK}"
    mv "${DEST}" "${BAK}"
fi

mkdir -p "${DEST}"
cp "${TMP}/repo/SKILL.md" "${DEST}/"
cp -r "${TMP}/repo/scripts" "${DEST}/"
if [ -d "${TMP}/repo/references" ]; then
    cp -r "${TMP}/repo/references" "${DEST}/"
fi

# 清理 __pycache__
find "${DEST}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "✅ 安装完成: ${DEST}"
echo "   新会话自动加载；当前会话执行 /reload-skills 生效"
echo ""
echo "首次使用请设定参数:"
echo "   python3 ${DEST}/scripts/auto-uboot-interrupt.py config ipaddr <设备IP>"
echo "   python3 ${DEST}/scripts/auto-uboot-interrupt.py config serverip <主机IP>"
echo "   python3 ${DEST}/scripts/auto-uboot-interrupt.py config tftp-dir <TFTP目录>"
#!/usr/bin/env bash
# serial-tftp-skill 一键安装脚本（串口 + TFTP 烧录技能集）
# 用法:
#   安装全部: curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash
#   安装单个: curl -fsSL https://raw.githubusercontent.com/GreatBigM/serial-tftp-skill/main/install.sh | bash -s -- serial-dev-console
# 等价于手动复制，不经过 hermes skills install 的安全扫描
set -euo pipefail

REPO_URL="https://github.com/GreatBigM/serial-tftp-skill.git"
SKILLS_DIR="${HOME}/.hermes/skills"
SKILLS=("serial-dev-console" "ingenic-basic-tftp-flash")

# 参数：可选指定单个技能名
TARGET="${1:-}"
if [ -n "$TARGET" ]; then
    case " ${SKILLS[*]} " in
        *" $TARGET "*) SKILLS=("$TARGET") ;;
        *) echo "❌ 未知技能: $TARGET（可选: ${SKILLS[*]}）"; exit 1 ;;
    esac
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "==> 克隆仓库（--depth 1）..."
git clone --depth 1 "${REPO_URL}" "${TMP}/repo" >/dev/null 2>&1 || {
    echo "❌ 克隆失败，请检查网络或仓库地址"; exit 1; }

for skill in "${SKILLS[@]}"; do
    DEST="${SKILLS_DIR}/${skill}"
    echo ""
    echo "==> 安装 ${skill} ..."
    mkdir -p "${SKILLS_DIR}"
    if [ -d "${DEST}" ]; then
        BAK="${DEST}.bak.$(date +%Y%m%d%H%M%S)"
        echo "    检测到已有安装，备份到 ${BAK}"
        mv "${DEST}" "${BAK}"
    fi
    mkdir -p "${DEST}"
    cp "${TMP}/repo/${skill}/SKILL.md" "${DEST}/"
    if [ -d "${TMP}/repo/${skill}/scripts" ]; then
        cp -r "${TMP}/repo/${skill}/scripts" "${DEST}/"
    fi
    echo "    ✅ ${skill} 已安装"
done

echo ""
echo "✅ 安装完成！新会话自动加载；当前会话执行 /reload-skills 生效"
echo ""
echo "已安装技能:"
for skill in "${SKILLS[@]}"; do
    echo "  - ${skill}"
done
