#!/bin/bash
# 牧云野 Generic Agent — 一键安装脚本
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# 动态探测 Python 解释器（可用 PYTHON=... 覆盖）。要求 3.10+
detect_python() {
    if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return 0; fi
    for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$c" >/dev/null 2>&1 \
           && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)' 2>/dev/null; then
            command -v "$c"; return 0
        fi
    done
    return 1
}
PYTHON="$(detect_python)" || { echo "❌ 未找到 Python 3.10+，请先安装，或用 PYTHON=/path/to/python ./install.sh"; exit 1; }
echo "🚀 牧云野 Generic Agent MCP Server 安装中... (Python: $PYTHON)"
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

# L0 meta rules（须与 mcp_ga_server.py main() 中的默认模板保持一致）
if [ ! -f "$DIR/memory/L0_meta_rules.txt" ]; then
    cat > "$DIR/memory/L0_meta_rules.txt" << 'EOF'
# L0 元规则 — 不可违抗
1. 无行动，不记忆：写入记忆的信息必须源自成功的工具调用结果
2. 每次任务完成后必须调用 memory_crystallize 结晶为 Skill
3. 问用户前，先尝试所有工具组合至少 3 次
4. 禁止一次性写入大段未经验证的信息到记忆
5. 用户喜好与习惯必须记入 L2 global_facts
6. 每次启动时检查 L3_skills/ 中是否有匹配当前需求的 Skill
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

# 4. 注册"肌肉记忆反射" hook 到 Claude Code 全局配置（幂等，带备份）
echo "→ 注册肌肉记忆反射 hook (Claude Code UserPromptSubmit)..."
"$PYTHON" - "$DIR" << 'PYEOF'
import json, os, shutil, sys
dir_ = sys.argv[1]
settings = os.path.expanduser("~/.claude/settings.json")
os.makedirs(os.path.dirname(settings), exist_ok=True)
if os.path.exists(settings):
    shutil.copy(settings, settings + ".bak")   # 备份
    try:
        data = json.load(open(settings, encoding="utf-8"))
    except Exception:
        data = {}
else:
    data = {}
cmd = "python3 %s/hooks/skill_reflex.py" % dir_
ups = data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
exists = any(
    h.get("type") == "command" and "skill_reflex.py" in h.get("command", "")
    for entry in ups for h in entry.get("hooks", [])
)
if exists:
    print("  已存在，跳过（幂等）")
else:
    ups.append({"hooks": [{"type": "command", "command": cmd}]})
    json.dump(data, open(settings, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("  ✔ 已写入 %s（备份 .bak）" % settings)
print("  💡 下次新开 Claude Code 会话即自动生效")
PYEOF

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
echo "     command = \"$DIR/.venv/bin/python\""
echo '     args = ["'"${DIR}"'/mcp_ga_server.py"]'
echo ""
echo "  4. 查看技能库状态："
echo '     python "'"$DIR"'/crystallizer/crystallize.py" --stats'
echo ""
echo "  🧠→⚡ 肌肉记忆反射：已注册为 Claude Code UserPromptSubmit hook，"
echo "     每次提问自动召回匹配的 L3 skill。停用：删掉 ~/.claude/settings.json"
echo "     里 hooks.UserPromptSubmit 中含 skill_reflex.py 的那条。"
echo ""
echo "🎯 然后说人话就能操控了！"
