#!/usr/bin/env python3
"""
ga-agent MCP 客户端 — 牧云野通过 exec 调用的桥梁
===================================================
用法：
    python3 mcp_client.py list                          # 列出工具
    python3 mcp_client.py call <tool> '<json_args>'     # 调用工具
    python3 mcp_client.py crystal <name> <trigger> <steps>  # 结晶
    python3 mcp_client.py snapshot                      # 记忆状态

示例：
    python3 mcp_client.py call web_fetch '{"url":"https://example.com"}'
    python3 mcp_client.py call code_run '{"code":"print(42)","type":"python"}'
    python3 mcp_client.py call web_navigate '{"url":"https://news.ycombinator.com"}'
    python3 mcp_client.py call web_scan '{"text_only":true}'
    python3 mcp_client.py crystal "HN_digest" "抓HN头条" "1. fetch 2. parse 3. output"
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ─── 路径 ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
VENV_PYTHON = SCRIPT_DIR / ".venv" / "bin" / "python"
MCP_SERVER = SCRIPT_DIR / "mcp_ga_server.py"


def _resolve_python() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    # 优先当前解释器，再回退到常见名称（不再硬编码 homebrew 路径）
    candidates = [sys.executable, "python3.13", "python3.12", "python3.11",
                  "python3.10", "python3", "python"]
    for p in candidates:
        if not p:
            continue
        try:
            r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and "3." in (r.stdout + r.stderr):
                return p
        except Exception:
            continue
    return "python3"


def _mcp_call(method: str, params: dict = None) -> dict:
    """Send one MCP request via a fresh server instance (sequential protocol)."""
    python = _resolve_python()
    
    try:
        proc = subprocess.Popen(
            [python, str(MCP_SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
        )
    except Exception as e:
        return {"status": "error", "msg": f"Failed to start server: {e}"}
    
    def _send(line: str) -> str:
        """Send a line and read the response."""
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        # Wait briefly for output
        time.sleep(0.3)
        return proc.stdout.readline()
    
    try:
        # Step 1: Initialize handshake
        init = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "ga-client", "version": "1.0"},
            },
        })
        resp1 = _send(init)
        if not resp1:
            stderr = proc.stderr.read() if proc.stderr else ""
            return {"status": "error", "msg": f"No init response. stderr: {stderr[:500]}"}
        
        data1 = json.loads(resp1)
        if "error" in data1:
            return {"status": "error", "msg": f"Init failed: {data1['error']}"}
        
        # Step 2: Send actual method call
        req = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": method,
            "params": params or {},
        })
        resp2 = _send(req)
        
        if not resp2:
            # Try to read more
            time.sleep(1)
            resp2 = proc.stdout.readline()
        
        if not resp2:
            stderr = proc.stderr.read() if proc.stderr else ""
            return {"status": "error", "msg": f"No response. stderr: {stderr[:500]}"}
        
        data2 = json.loads(resp2)
        if "error" in data2:
            return {"status": "error", "msg": str(data2["error"])}
        
        return {"status": "success", "result": data2.get("result", {})}
    
    except json.JSONDecodeError as e:
        return {"status": "error", "msg": f"JSON error: {e}"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _handle_result(result: dict):
    """Pretty-print MCP result."""
    if result["status"] != "success":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    
    content = result["result"].get("content", [])
    for c in content:
        if c.get("type") == "text":
            text = c["text"]
            try:
                parsed = json.loads(text)
                print(json.dumps(parsed, indent=2, ensure_ascii=False))
            except (json.JSONDecodeError, TypeError):
                print(text)
        elif c.get("type") == "image":
            print(f"[Image: {c.get('mimeType', 'img')} {len(c.get('data', ''))} bytes]")


def _quick_crystal(task_name: str, trigger: str, steps: str,
                   prerequisites: str = "", code: str = "") -> dict:
    """Crystallize skill (direct file write, no MCP needed)."""
    safe_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', task_name)[:60]
    skills_dir = SCRIPT_DIR / "memory" / "L3_skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    path = skills_dir / f"{safe_name}.md"
    
    if path.exists():
        return {"status": "exists", "msg": f"Skill '{task_name}' already exists", "path": str(path)}
    
    content = (
        f"# Skill: {task_name}\n"
        f"Trigger: 「{trigger}」\n"
        f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## Prerequisites\n{prerequisites or 'None'}\n\n"
        f"## Key Steps\n{steps}\n\n"
    )
    if code:
        content += f"## Code Template\n```python\n{code}\n```\n"
    path.write_text(content, encoding="utf-8")

    # Update L1 index（与 mcp_ga_server.update_insight_index 保持一致：用 "\n" 连接）
    index_path = SCRIPT_DIR / "memory" / "L1_insight_index.txt"
    entry = f"skills/{safe_name} ← {trigger}"
    default_header = [
        "# L1 洞察索引 — 极简导航（≤25 行）",
        "# 格式：能力关键词 → 具体位置",
    ]
    if index_path.exists():
        lines = index_path.read_text(encoding="utf-8").split("\n")
        header = [l for l in lines if l.startswith("#")] or default_header
        entries = [l for l in lines if not l.startswith("#") and l.strip()]
    else:
        header, entries = default_header, []
    if entry not in entries:
        entries.append(entry)
    if len(entries) > 25:
        entries = entries[-25:]
    index_path.write_text("\n".join(header + [""] + entries) + "\n", encoding="utf-8")

    # L4 归档：与 server 端 crystallize 闭环一致，留下会话痕迹
    arch_dir = SCRIPT_DIR / "memory" / "L4_archive"
    arch_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    (arch_dir / f"{stamp}_{safe_name}.md").write_text(
        f"# Session: {task_name}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## Summary\ncrystallized skill 「{trigger}」\n\n"
        f"## Key Steps\n{steps}\n",
        encoding="utf-8",
    )

    return {"status": "success", "msg": f"✅ Skill '{task_name}' 已结晶！下次说「{trigger}」直接复用", "path": str(path)}


def _snapshot() -> dict:
    """Memory system snapshot."""
    skills_dir = SCRIPT_DIR / "memory" / "L3_skills"
    arch_dir = SCRIPT_DIR / "memory" / "L4_archive"
    index_path = SCRIPT_DIR / "memory" / "L1_insight_index.txt"
    
    l1 = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    l3_skills = list(skills_dir.glob("*.md")) if skills_dir.exists() else []
    l4_sessions = list(arch_dir.glob("*.md")) if arch_dir.exists() else []
    
    skills_list = []
    for s in l3_skills:
        content = s.read_text(encoding="utf-8", errors="replace")
        title = ""
        trigger = ""
        for line in content.split("\n"):
            if line.startswith("# Skill:"):
                title = line.replace("# Skill:", "").strip()
            m = re.search(r"「(.+?)」", line)
            if m:
                trigger = m.group(1)
        skills_list.append({"name": s.stem, "title": title, "trigger": trigger})
    
    return {
        "l1_entries": len([l for l in l1.split("\n") if l.strip() and not l.startswith("#")]),
        "l3_skills": len(l3_skills),
        "l4_sessions": len(l4_sessions),
        "skills": skills_list[:20],
        "notes": "浏览器工具web_navigate/scan/execute_js/screenshot每次调用启动新实例，不保留标签页状态。需要连续浏览器操作时告诉我，我用单次会话一次完成。"
    }


# ═══════════════════════════════════════════════════════════════════════════════
#                                    CLI
# ═══════════════════════════════════════════════════════════════════════════════

def print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return
    
    cmd = sys.argv[1]
    
    # ── list: 列出工具 ──
    if cmd == "list":
        result = _mcp_call("tools/list")
        if result["status"] == "success":
            tools = result["result"].get("tools", [])
            print(f"✅ ga-agent MCP — {len(tools)} 个工具\n")
            for t in tools:
                desc = t.get("description", "")[:70]
                print(f"  🛠️  {t['name']}")
                print(f"     {desc}...")
                print()
        else:
            print_json(result)
    
    # ── call: 调用工具 ──
    elif cmd == "call":
        if len(sys.argv) < 3:
            print("用法: python3 mcp_client.py call <tool_name> '<json_args>'")
            return
        tool_name = sys.argv[2]
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        _handle_result(_mcp_call("tools/call", {"name": tool_name, "arguments": args}))
    
    # ── crystal: 结晶 ──
    elif cmd == "crystal":
        if len(sys.argv) < 5:
            print("用法: mcp_client.py crystal <task_name> <trigger> <steps> [prerequisites] [code]")
            return
        print_json(_quick_crystal(sys.argv[2], sys.argv[3], sys.argv[4],
                                  sys.argv[5] if len(sys.argv) > 5 else "",
                                  sys.argv[6] if len(sys.argv) > 6 else ""))
    
    # ── snapshot: 记忆状态 ──
    elif cmd == "snapshot":
        print_json(_snapshot())
    
    else:
        print(f"未知命令: {cmd}")
        print(__doc__.strip())


if __name__ == "__main__":
    main()
