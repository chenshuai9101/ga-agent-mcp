#!/usr/bin/env python3
"""
技能结晶器 — 从任务中提取可复用 Skill
========================================
此脚本可在任务执行后被调用，从执行日志中自动提炼 Skill。

用法：
    python crystallize.py --task "任务名" --log <file> [--output <dir>]

功能：
    - 从执行日志中提取关键步骤
    - 自动生成 SOP 文档
    - 更新 L1 索引
    - 支持"查询→匹配 Skill"的语义搜索
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 默认路径
BASE_DIR = Path(__file__).parent.parent
SKILLS_DIR = BASE_DIR / "memory" / "L3_skills"
INDEX_FILE = BASE_DIR / "memory" / "L1_insight_index.txt"
FACTS_FILE = BASE_DIR / "memory" / "L2_global_facts.txt"
ARCHIVE_DIR = BASE_DIR / "memory" / "L4_archive"


def query_skills(query: str) -> list[dict]:
    """查询已有技能，返回匹配结果（按相关度排序）"""
    if not SKILLS_DIR.exists():
        return []
    
    query_lower = query.lower()
    query_words = set(re.findall(r'[\w\u4e00-\u9fff]+', query_lower))
    results = []
    
    for f in sorted(SKILLS_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8", errors="replace")
        
        # Extract metadata
        name = f.stem
        title = re.search(r"# Skill:\s*(.+)", content)
        title = title.group(1) if title else name
        trigger = re.search(r"Trigger.*?「(.+?)」", content)
        trigger = trigger.group(1) if trigger else ""
        
        # Scoring
        score = 0
        content_lower = content.lower()
        
        # Trigger phrase match (highest weight)
        if trigger and trigger.lower() in query_lower:
            score += 10
        elif trigger:
            trigger_words = set(re.findall(r'[\w\u4e00-\u9fff]+', trigger.lower()))
            score += len(trigger_words & query_words) * 3
        
        # Title match
        if title and title.lower() in query_lower:
            score += 5
        
        # Content keyword match
        score += len(query_words & set(re.findall(r'[\w\u4e00-\u9fff]+', content_lower)))
        
        if score > 0:
            results.append({
                "name": name,
                "title": title,
                "trigger": trigger,
                "score": score,
                "content": content[:500],
            })
    
    results.sort(key=lambda x: -x["score"])
    return results


def list_skills() -> list[dict]:
    """列出所有技能库"""
    if not SKILLS_DIR.exists():
        return []
    
    skills = []
    for f in sorted(SKILLS_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8", errors="replace")
        title = re.search(r"# Skill:\s*(.+)", content)
        trigger = re.search(r"Trigger.*?「(.+?)」", content)
        created = re.search(r"Created:\s*(.+)", content)
        skills.append({
            "name": f.stem,
            "title": title.group(1) if title else f.stem,
            "trigger": trigger.group(1) if trigger else "",
            "created": created.group(1) if created else "",
            "size": len(content),
        })
    
    return skills


def create_skill(task_name: str, trigger_phrase: str, key_steps: str,
                 prerequisites: str = "", code_template: str = "",
                 category: str = "general") -> str:
    """创建技能文件"""
    safe_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', task_name)[:60]
    path = SKILLS_DIR / f"{safe_name}.md"
    
    # Don't overwrite
    if path.exists():
        return f"⚠️ Skill '{task_name}' 已存在，跳过（如需覆盖请手动删除 {path}）"
    
    content = (
        f"# Skill: {task_name}\n"
        f"Trigger: 「{trigger_phrase}」\n"
        f"Category: {category}\n"
        f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## Prerequisites\n{prerequisites or '无'}\n\n"
        f"## Key Steps\n{key_steps}\n\n"
    )
    if code_template:
        content += f"## Code Template\n```python\n{code_template}\n```\n"
    
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    
    # Update L1 index
    _update_index(f"skills/{safe_name} ← {trigger_phrase}")
    
    # Log to L4
    _log_archive(task_name, trigger_phrase, key_steps[:200])
    
    return f"✅ Skill '{task_name}' 结晶成功！触发词「{trigger_phrase}」"


def _update_index(entry: str):
    """更新 L1 索引"""
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(
            "# L1 洞察索引 — 极简导航（≤25 行）\n"
            "# 格式：能力关键词 → 具体位置\n\n",
            encoding="utf-8",
        )
    
    lines = INDEX_FILE.read_text(encoding="utf-8").split("\n")
    # Keep header
    header = [l for l in lines if l.startswith("#") or not l.strip()]
    entries = [l for l in lines if not l.startswith("#") and l.strip()]
    
    if entry not in entries:
        entries.append(entry)
    
    # Enforce ≤ 25 lines
    if len(entries) > 25:
        entries = entries[-25:]
    
    INDEX_FILE.write_text("\n".join(header + [""] + entries) + "\n", encoding="utf-8")


def _log_archive(task_name: str, trigger: str, summary: str):
    """写入 L4 会话归档"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d_%H-%M")
    safe_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', task_name)[:40]
    
    content = (
        f"# Session: {task_name}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Trigger: {trigger}\n\n"
        f"## Summary\n{summary}\n"
    )
    (ARCHIVE_DIR / f"{date}_{safe_name}.md").write_text(content, encoding="utf-8")


def memory_stats() -> dict:
    """获取记忆系统统计"""
    stats = {}
    
    l1 = INDEX_FILE.read_text(encoding="utf-8") if INDEX_FILE.exists() else ""
    l2 = FACTS_FILE.read_text(encoding="utf-8") if FACTS_FILE.exists() else ""
    l3 = list(SKILLS_DIR.glob("*.md")) if SKILLS_DIR.exists() else []
    l4 = list(ARCHIVE_DIR.glob("*.md")) if ARCHIVE_DIR.exists() else []
    
    stats["L1索引行数"] = len([l for l in l1.split("\n") if l.strip() and not l.startswith("#")])
    stats["L2事实行数"] = len([l for l in l2.split("\n") if l.strip() and not l.startswith("#")])
    stats["L3技能数"] = len(l3)
    stats["L4会话数"] = len(l4)
    stats["总记忆体积"] = sum(len(p.read_bytes()) for p in l3 + l4) + len(l1) + len(l2)
    
    if l3:
        stats["技能列表"] = [f.stem for f in l3]
    
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generic Agent 技能结晶器")
    parser.add_argument("--query", help="查询已有技能")
    parser.add_argument("--list", action="store_true", help="列出所有技能")
    parser.add_argument("--stats", action="store_true", help="记忆系统统计")
    parser.add_argument("--create", nargs=5, metavar=("NAME", "TRIGGER", "STEPS", "PREQ", "CODE"),
                        help="创建新技能")
    
    args = parser.parse_args()
    
    if args.query:
        results = query_skills(args.query)
        if results:
            print(f"找到 {len(results)} 个匹配技能：\n")
            for r in results:
                print(f"  [{r['score']}分] {r['title']}")
                print(f"        触发词：{r['trigger']}")
                print(f"        文件：{r['name']}.md")
                print()
        else:
            print("未找到匹配技能")
    
    elif args.list:
        skills = list_skills()
        if skills:
            print(f"\n📚 技能库（共 {len(skills)} 个）\n")
            for s in skills:
                print(f"  {s['name']}")
                print(f"    Title: {s['title']}")
                print(f"    Trigger: {s['trigger']}")
                print(f"    Created: {s['created']}")
                print()
        else:
            print("技能库为空")
    
    elif args.stats:
        stats = memory_stats()
        print("\n📊 记忆系统状态\n")
        for k, v in stats.items():
            if isinstance(v, list):
                print(f"  {k}:")
                for item in v:
                    print(f"    - {item}")
            else:
                print(f"  {k}: {v}")
    
    elif args.create:
        name, trigger, steps, preq, code = args.create
        result = create_skill(name, trigger, steps, preq, code)
        print(result)
    
    else:
        parser.print_help()
