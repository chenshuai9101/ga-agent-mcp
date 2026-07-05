#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_matcher —— ga-agent 肌肉记忆的单一匹配真相
=================================================

把用户的一句话去模糊匹配 memory/L3_skills/ 里已结晶的 Skill，命中就返回其 SOP。
hook（hooks/skill_reflex.py）与 MCP server（mcp_ga_server.py 的 skill_find 工具）
共用本模块，避免两套逻辑跑偏。

对中文友好（这是原 find_skill_for_query 用 \\w+ 分词失效的修正）：
- 触发词按 / 、 , 空白 等切分成关键词；
- 打分：整词命中 3 分；ASCII 词元(hn/cdp/chrome)子串 2 分；中文 bigram 每个 1 分；
- 总分 ≥ threshold(默认 2) 才算命中，滤掉单个常见 bigram 的噪音。

纯标准库，可用系统 python3 直接跑，不依赖项目 .venv。
"""
import os
import re
from typing import Optional

# 缺省 L3 目录：相对本文件 crystallizer/ → ../memory/L3_skills（去硬编码，可移植）
_DEFAULT_L3_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memory", "L3_skills")
)

MIN_KEYWORD_LEN = 2       # 关键词至少 2 字符（过滤 "的""a" 噪音）
DEFAULT_THRESHOLD = 2     # 总分达到此值才算命中
DEFAULT_MAX_RESULTS = 2   # 并列命中最多返回几条

SPLIT_RE = re.compile(r"[/／、,，|；;\s]+")           # 触发词切分符
TRIGGER_RE = re.compile(r"Trigger.*?[：:]\s*「(.+?)」")  # 提取 Trigger: 「...」
ASCII_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
CJK_RUN_RE = re.compile(r"[一-鿿]{2,}")


def cjk_bigrams(s: str) -> set:
    """从连续中文片段取二元组，如 '抓hn头条' -> {'头条'}。"""
    grams = set()
    for run in CJK_RUN_RE.findall(s):
        for i in range(len(run) - 1):
            grams.add(run[i:i + 2])
    return grams


def extract_keywords(trigger: str) -> list:
    kws = []
    for tok in SPLIT_RE.split(trigger):
        tok = tok.strip()
        if len(tok) >= MIN_KEYWORD_LEN:
            kws.append(tok.lower())
    return kws


def match_keyword(prompt_lower: str, prompt_bigrams: set, kw: str):
    """对单个触发关键词打分，返回 (points, label|None)。"""
    if kw in prompt_lower:
        return 3, kw
    pts = 0
    matched = []
    for tok in ASCII_TOKEN_RE.findall(kw):
        if tok in prompt_lower:
            pts += 2
            matched.append(tok)
    shared = cjk_bigrams(kw) & prompt_bigrams
    if shared:
        pts += len(shared)
        matched.extend(sorted(shared))
    return (pts, "+".join(matched)) if pts else (0, None)


def score_skill(prompt_lower: str, prompt_bigrams: set, trigger: str, name: str):
    """对一个 skill 打总分，返回 (score, hits)。"""
    kws = extract_keywords(trigger) or extract_keywords(name)
    total = 0
    hits = []
    for k in kws:
        pts, label = match_keyword(prompt_lower, prompt_bigrams, k)
        if pts:
            total += pts
            hits.append(label)
    return total, hits


def _extract_trigger(content: str, name: str) -> str:
    m = TRIGGER_RE.search(content)
    return m.group(1) if m else name


def find_skills(prompt: str,
                l3_dir: Optional[str] = None,
                threshold: int = DEFAULT_THRESHOLD,
                max_results: int = DEFAULT_MAX_RESULTS) -> list:
    """匹配 prompt 与 L3 skills。返回 [{score, name, content, hits}, ...]（按分降序）。

    出错/无匹配一律返回 []，调用方无需 try（保证 fail-safe）。
    """
    if not prompt or not prompt.strip():
        return []
    l3_dir = l3_dir or _DEFAULT_L3_DIR
    if not os.path.isdir(l3_dir):
        return []

    prompt_lower = prompt.lower()
    prompt_bigrams = cjk_bigrams(prompt_lower)
    candidates = []
    try:
        files = sorted(f for f in os.listdir(l3_dir) if f.endswith(".md"))
    except OSError:
        return []

    for fn in files:
        path = os.path.join(l3_dir, fn)
        try:
            content = open(path, encoding="utf-8").read()
        except OSError:
            continue
        name = fn[:-3]
        trigger = _extract_trigger(content, name)
        score, hits = score_skill(prompt_lower, prompt_bigrams, trigger, name)
        if score >= threshold:
            candidates.append({"score": score, "name": name,
                               "content": content, "hits": hits})

    candidates.sort(key=lambda c: -c["score"])
    if not candidates:
        return []
    top = candidates[0]["score"]
    return [c for c in candidates if c["score"] == top][:max_results]


def render_injection(matches: list) -> str:
    """把匹配结果渲染成注入上下文的文案。matches 为空返回 ''。"""
    if not matches:
        return ""
    blocks = []
    for m in matches:
        blocks.append(
            f"【已结晶 Skill：{m['name']}】(命中关键词: {', '.join(m['hits'])})\n"
            f"{m['content'].strip()}"
        )
    return (
        "以下是 ga-agent 记忆库中与当前请求相关的、你过去已结晶的可复用 SOP "
        "（肌肉记忆反射召回）。如果适用，请优先按其步骤执行，可按需微调参数；"
        "完成后若产生了新的可复现流程，记得调用 ga-agent 的 memory_crystallize 结晶。\n\n"
        + "\n\n---\n\n".join(blocks)
    )


# ─── self-test：python3 skill_matcher.py ────────────────────────────────────────
if __name__ == "__main__":
    import sys
    cases = [
        ("帮我抓一下HN头条整理个摘要", True),
        ("淘宝老是反爬，用系统Chrome连一下", True),
        ("帮我做个CDP连接调试", True),
        ("今天天气怎么样", False),
        ("帮我写个快速排序", False),
        ("", False),
    ]
    l3 = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_L3_DIR
    print(f"L3 目录: {l3}")
    ok = 0
    for prompt, expect_hit in cases:
        matches = find_skills(prompt, l3_dir=l3)
        hit = bool(matches)
        mark = "✔" if hit == expect_hit else "✘"
        if hit == expect_hit:
            ok += 1
        names = ",".join(m["name"] for m in matches) or "(无)"
        print(f"  {mark} 期望命中={expect_hit!s:5} 实际={hit!s:5} -> {names:20} | {prompt[:20]}")
    print(f"\n{ok}/{len(cases)} 通过")
    sys.exit(0 if ok == len(cases) else 1)
