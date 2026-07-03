#!/bin/bash
# 牧云野 Generic Agent — 一键安装脚本
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-/opt/homebrew/bin/python3.12}"
echo "🚀 牧云野 Generic Agent MCP Server 安装中..."
echo ""

# 1. Install Python dependencies into venv
echo "→ 创建虚拟环境并安装依赖..."
"$PYTHON" -m venv "$DIR/.venv"
source "$DIR/.venv/bin/activate"
pip install -q -r "$DIR/requirements.txt"
echo "  依赖安装完成"

# 2. Install Playwright browser
echo "→ 安装 Playwright 浏览器..."
playwright install chromium 2>&1 | tail -3
echo "  浏览器安装完成"

# 3. Initialize memory directories
echo "→ 初始化记忆系统..."
mkdir -p "$DIR/memory/L3_skills" "$DIR/memory/L4_archive"

# L0 meta rules
if [ ! -f "$DIR/memory/L0_meta_rules.txt" ]; then
    cat > "$DIR/memory/L0_meta_rules.txt" << 'EOF'
# L0 元规则 — 不可违抗
1. 无行动，不记忆：写入记忆的信息必须源自成功的工具调用结果
2. 每次任务完成后必须结晶为 Skill
3. 问用户前，先尝试所有工具组合至少 3 次
4. 用户喜好与习惯必须记入 L2 global_facts
5. 接到任务先查 L3_skills 是否有匹配的 Skill
EOF
fi

# L1 insight index
if [ ! -f "$DIR/memory/L1_insight_index.txt" ]; then
    cat > "$DIR/memory/L1_insight_index.txt" << 'EOF'
# L1 洞察索引 — 极简导航（≤25 行）
# 格式：能力关键词 → 具体位置

EOF
fi

# L2 global facts
if [ ! -f "$DIR/memory/L2_global_facts.txt" ]; then
    cat > "$DIR/memory/L2_global_facts.txt" << 'EOF'
# L2 全局事实库
# 环境配置和长期知识

EOF
fi

echo ""
echo "✅ 安装完成！"
echo ""
echo "使用方法："
echo ""
echo "  1. 激活环境："
echo '     source "'"$DIR"'/.venv/bin/activate"'
echo ""
echo "  2. 启动 MCP Server："
echo '     python "'"$DIR"'/mcp_ga_server.py"'
echo ""
echo "  3. 在 OpenClaw 中注册 MCP server："
echo "     [[mcp_servers]]"
echo '     name = "ga-agent"'
echo "     command = \"$PYTHON\""
echo '     args = ["'"${DIR}"'/mcp_ga_server.py"]'
echo ""
echo "  4. 查看技能库状态："
echo '     python "'"$DIR"'/crystallizer/crystallize.py" --stats'
echo ""
echo "🎯 然后说人话就能操控了！"
