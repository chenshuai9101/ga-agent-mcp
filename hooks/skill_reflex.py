#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ga-agent 肌肉记忆反射 hook (Claude Code UserPromptSubmit)

每当用户提交一条消息，本 hook 拿这句话去匹配 memory/L3_skills/ 里已结晶的 Skill；
命中就把对应 SOP 作为 additionalContext 注入，让 Claude "条件反射"般想起过去的做法
——无需 Claude 主动检索，也无需等下一个会话。

匹配逻辑集中在 crystallizer/skill_matcher.py（hook 与 MCP server 共用同一真相）。
本文件只是薄薄的 fail-safe 外壳：读 stdin JSON → 调 find_skills → 输出注入 JSON。

设计红线：
- 纯标准库，用系统 python3 即可，不依赖 skill 的 .venv。
- 绝不阻断：任何异常都静默 exit 0，不影响用户正常提问。
"""
import sys
import os
import json

# 相对定位共享模块目录（去硬编码，可移植）
_HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
_CRYSTALLIZER_DIR = os.path.normpath(os.path.join(_HOOK_DIR, "..", "crystallizer"))
if _CRYSTALLIZER_DIR not in sys.path:
    sys.path.insert(0, _CRYSTALLIZER_DIR)


def main():
    try:
        from skill_matcher import find_skills, render_injection
    except Exception:
        return  # 模块缺失就别干预

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return

    matches = find_skills(prompt)
    if not matches:
        return

    injected = render_injection(matches)
    if not injected:
        return

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": injected,
        }
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 反射永远不该阻断主流程
    sys.exit(0)
