#!/usr/bin/env python3
"""
牧云野 Generic Agent MCP Server
=================================
轻量级 MCP 服务器，提供 10 个原子工具。
实现 GenericAgent 核心思想：最小工具集 + 分层记忆 + 技能结晶。

安装：
    pip install -r requirements.txt
    playwright install chromium

运行：
    python mcp_ga_server.py

用法（在 OpenClaw 中配置为 MCP server）：
    在 .openclaw.toml 或配置中加入：
    [[mcp_servers]]
    name = "ga-agent"
    command = "python"
    args = ["/path/to/mcp_ga_server.py"]
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
import re
import subprocess
import shutil
import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from io import BytesIO

# ─── MCP SDK ───────────────────────────────────────────────────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool, TextContent, ImageContent, EmbeddedResource,
    CallToolResult, ListToolsResult,
)

# ─── Optional imports (graceful fallback) ──────────────────────────────────────
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Playwright is loaded lazily to speed up startup when not needed


# ═══════════════════════════════════════════════════════════════════════════════
#                          MEMORY SYSTEM (L0-L4)
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent.resolve()
MEMORY_DIR = SCRIPT_DIR / "memory"
L3_SKILLS_DIR = MEMORY_DIR / "L3_skills"
L4_ARCHIVE_DIR = MEMORY_DIR / "L4_archive"


def ensure_memory_dirs():
    """Ensure all memory directories exist."""
    for d in [MEMORY_DIR, L3_SKILLS_DIR, L4_ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def read_memory_file(name: str) -> str:
    """Read a memory file, returning empty string if not found."""
    path = MEMORY_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def write_memory_file(name: str, content: str):
    """Write to a memory file."""
    path = MEMORY_DIR / name
    path.write_text(content, encoding="utf-8")


def update_insight_index(changes: str):
    """Update L1 insight index with new pointers."""
    current = read_memory_file("L1_insight_index.txt")
    lines = current.split("\n")
    # Keep only comment lines as header (blank lines are re-inserted below,
    # so they don't accumulate over repeated calls)
    header = [l for l in lines if l.startswith("#")]
    entries = [l for l in lines if not l.startswith("#") and l.strip()]

    for change in changes.strip().split("\n"):
        if change and change not in entries:
            entries.append(change)

    # Enforce ≤ 25 lines
    if len(entries) > 25:
        entries = entries[-25:]

    result = "\n".join(header + [""] + entries) + "\n"
    write_memory_file("L1_insight_index.txt", result)


def load_global_memory() -> str:
    """Load L1 + L2 into a context block for system prompt injection."""
    l1 = read_memory_file("L1_insight_index.txt")
    l2 = read_memory_file("L2_global_facts.txt")
    parts = []
    if l1:
        parts.append(f"[L1 洞察索引]\n{l1}")
    if l2:
        parts.append(f"[L2 全局事实]\n{l2}")
    return "\n\n".join(parts) if parts else ""


def log_session(task_name: str, summary: str, key_info: str = ""):
    """Append to L4 session archive."""
    date = datetime.now().strftime("%Y-%m-%d_%H-%M")
    safe_name = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", task_name)[:40]
    filename = f"{date}_{safe_name}.md"
    content = (
        f"# Session: {task_name}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## Summary\n{summary}\n\n"
        f"## Key Info\n{key_info}\n"
    )
    (L4_ARCHIVE_DIR / filename).write_text(content, encoding="utf-8")


def crystallize_skill(task_name: str, trigger_phrase: str, key_steps: str,
                      prerequisites: str = "", code_template: str = ""):
    """Crystallize a completed task into a reusable L3 skill.
    
    Creates a markdown SOP in L3_skills/ that can be directly invoked
    next time the user says the same trigger phrase.
    """
    safe_name = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", task_name)[:40]
    path = L3_SKILLS_DIR / f"{safe_name}.md"
    
    # Don't overwrite existing skills
    if path.exists():
        return f"Skill '{task_name}' already exists. Skipping."
    
    content = (
        f"# Skill: {task_name}\n"
        f"Trigger: 「{trigger_phrase}」\n"
        f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## Prerequisites\n{prerequisites or 'None'}\n\n"
        f"## Key Steps\n{key_steps}\n\n"
    )
    if code_template:
        content += f"## Code Template\n```python\n{code_template}\n```\n"
    
    path.write_text(content, encoding="utf-8")

    # Update L1 index
    update_insight_index(f"skills/{safe_name} ← {trigger_phrase}")

    # L4 归档：结晶即留下会话痕迹，保证记忆闭环
    log_session(task_name, f"crystallized skill 「{trigger_phrase}」", key_steps)

    return f"✅ Skill '{task_name}' crystallized! Next time user says '【{trigger_phrase}】', auto-load this skill."


def find_skill_for_query(query: str) -> Optional[tuple[str, str]]:
    """Fuzzy-match a user query against crystallized skills.
    Returns (skill_name, content) if match found."""
    query_lower = query.lower()
    candidates = []
    
    for f in sorted(L3_SKILLS_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        name = f.stem
        
        # Extract trigger phrase
        m = re.search(r"Trigger.*?[：:]\s*「(.+?)」", content)
        trigger = m.group(1) if m else name
        
        # Simple keyword matching
        trigger_words = set(re.findall(r"\w+", trigger.lower()))
        query_words = set(re.findall(r"\w+", query_lower))
        overlap = len(trigger_words & query_words)
        
        if overlap > 0 or trigger.lower() in query_lower:
            candidates.append((overlap, name, content))
    
    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1], candidates[0][2]
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#                           TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

class BrowserManager:
    """Manages a Playwright browser instance (lazy init)."""
    
    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._lazy_initialized = False
    
    async def ensure_browser(self):
        """Lazy-initialize browser on first use."""
        if self._lazy_initialized and self._page:
            try:
                # Quick health check
                _ = await self._page.title()
                return
            except Exception:
                pass  # Browser died, restart
        
        self._lazy_initialized = True
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            
            # Try to connect to existing Chrome instance first
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    "http://localhost:9222"
                )
                self._context = self._browser.contexts[0] if self._browser.contexts else (
                    await self._browser.new_context()
                )
            except Exception:
                # Launch new browser
                self._browser = await self._playwright.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--allow-running-insecure-content",
                    ],
                )
                self._context = await self._browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                )
                # Stealth: override navigator.webdriver
                await self._context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                    window.chrome = { runtime: {} };
                """)
            
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
    
    async def navigate(self, url: str):
        """Navigate to a URL."""
        await self.ensure_browser()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return await self.page_info()
    
    async def page_info(self) -> dict:
        """Get current page info."""
        await self.ensure_browser()
        return {
            "url": self._page.url,
            "title": await self._page.title(),
        }
    
    async def get_content(self, text_only: bool = False, max_chars: int = 15000) -> str:
        """Get page content (simplified)."""
        await self.ensure_browser()
        
        if text_only:
            content = await self._page.evaluate("document.body.innerText")
        else:
            # Simplified HTML extraction via JS
            content = await self._page.evaluate("""
                () => {
                    // Remove scripts, styles, nav, footer, aside
                    const removals = document.querySelectorAll(
                        'script, style, nav, footer, aside, .sidebar, .ad, iframe'
                    );
                    for (const el of removals) el.remove();
                    
                    // Get main content
                    const main = document.querySelector('main, article, [role="main"]') || document.body;
                    return main.innerText.substring(0, 30000);
                }
            """)
        
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n... [truncated]"
        return content.strip()
    
    async def execute_js(self, script: str) -> Any:
        """Execute JavaScript in the browser."""
        await self.ensure_browser()
        result = await self._page.evaluate(script)
        return result
    
    async def get_tabs(self) -> list[dict]:
        """Get all open tabs/pages."""
        await self.ensure_browser()
        tabs = []
        for i, page in enumerate(self._context.pages):
            try:
                tabs.append({
                    "id": str(i),
                    "url": page.url[:80],
                    "title": await page.title(),
                    "active": page == self._page,
                })
            except Exception:
                tabs.append({"id": str(i), "url": "(closed)", "title": "(closed)"})
        return tabs
    
    async def switch_tab(self, tab_id: str):
        """Switch to a specific tab by ID."""
        await self.ensure_browser()
        pages = self._context.pages
        try:
            idx = int(tab_id)
            if 0 <= idx < len(pages):
                self._page = pages[idx]
                await self._page.bring_to_front()
                return {"status": "success", "tab": tab_id}
        except (ValueError, IndexError):
            pass
        return {"status": "error", "msg": f"Invalid tab ID: {tab_id}"}
    
    async def screenshot(self) -> Optional[bytes]:
        """Take a screenshot, returns PNG bytes."""
        await self.ensure_browser()
        return await self._page.screenshot(type="png")
    
    async def close(self):
        """Close browser."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            await self._playwright.stop()


class CodeRunner:
    """Runs Python and shell code with timeout and safety."""
    
    @staticmethod
    async def run(code: str, type_: str = "python", timeout: int = 60) -> dict:
        """Execute code and return result."""
        if type_ in ("python", "py"):
            return await CodeRunner._run_python(code, timeout)
        elif type_ in ("bash", "sh", "shell"):
            return await CodeRunner._run_shell(code, timeout)
        else:
            return {"status": "error", "msg": f"Unsupported type: {type_}"}
    
    @staticmethod
    async def _run_python(code: str, timeout: int) -> dict:
        """Execute Python code in a subprocess."""
        # Write to temp file
        fd, tmp_path = tempfile.mkstemp(suffix=".ga.py", prefix="ga_run_")
        os.close(fd)
        
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write("import sys\n")
                f.write("import json\n")
                f.write("from pathlib import Path\n\n")
                f.write(code)
            
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-X", "utf8", "-u", tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                stdout, stderr = await proc.communicate()
                return {
                    "status": "timeout",
                    "stdout": stdout.decode("utf-8", errors="replace")[-5000:] if stdout else "",
                    "stderr": f"[Timeout] Execution exceeded {timeout}s",
                }
            
            return {
                "status": "success" if proc.returncode == 0 else "error",
                "stdout": stdout.decode("utf-8", errors="replace")[-5000:] if stdout else "",
                "stderr": stderr.decode("utf-8", errors="replace")[-2000:] if stderr else "",
                "exit_code": proc.returncode,
            }
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    
    @staticmethod
    async def _run_shell(code: str, timeout: int) -> dict:
        """Execute shell command."""
        shell = "bash" if sys.platform != "win32" else "powershell"
        shell_flag = "-c" if shell == "bash" else "-Command"
        
        proc = await asyncio.create_subprocess_exec(
            shell, shell_flag, code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return {
                "status": "timeout",
                "stdout": stdout.decode("utf-8", errors="replace")[-5000:] if stdout else "",
                "stderr": f"[Timeout] Shell execution exceeded {timeout}s",
            }
        
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "stdout": stdout.decode("utf-8", errors="replace")[-5000:] if stdout else "",
            "stderr": stderr.decode("utf-8", errors="replace")[-2000:] if stderr else "",
            "exit_code": proc.returncode,
        }


class FileOps:
    """File operations: read, write, patch."""
    
    @staticmethod
    def read(path: str, start: int = 1, count: int = 200,
             keyword: str = None, show_linenos: bool = True) -> str:
        """Read a file with flexible options."""
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total = len(lines)
        result_lines = []
        
        if keyword:
            kw_lower = keyword.lower()
            match_start = None
            for i, line in enumerate(lines):
                if kw_lower in line.lower():
                    match_start = max(0, i - count // 3)
                    break
            if match_start is None:
                return f"Keyword '{keyword}' not found. Showing first {count} lines:\n"
            start_line = match_start + 1
            selected = lines[match_start:match_start + count]
        else:
            start_line = max(1, start)
            selected = lines[start_line - 1:start_line - 1 + count]
        
        for i, line in enumerate(selected):
            line_num = start_line + i
            # Truncate long lines
            if len(line) > 8000:
                line = line[:8000] + " ... [TRUNCATED]\n"
            if show_linenos:
                result_lines.append(f"{line_num:6d}|{line.rstrip()}")
            else:
                result_lines.append(line.rstrip())
        
        header = f"[FILE] {total} lines" + (f" | showing {len(selected)}" if len(selected) < total else "") + "\n"
        return header + "\n".join(result_lines)
    
    @staticmethod
    def write(path: str, content: str, mode: str = "overwrite") -> dict:
        """Write/create/append to a file."""
        path = os.path.abspath(os.path.expanduser(path))
        
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            if mode == "overwrite":
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {"status": "success", "msg": f"Written {len(content)} bytes to {os.path.basename(path)}", "bytes": len(content)}
            elif mode == "append":
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
                return {"status": "success", "msg": f"Appended {len(content)} bytes to {os.path.basename(path)}"}
            elif mode == "prepend":
                old = ""
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        old = f.read()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content + old)
                return {"status": "success", "msg": f"Prepended {len(content)} bytes to {os.path.basename(path)}"}
            else:
                return {"status": "error", "msg": f"Unknown mode: {mode}"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}
    
    @staticmethod
    def patch(path: str, old_content: str, new_content: str) -> dict:
        """Replace exact text in a file."""
        path = os.path.abspath(os.path.expanduser(path))
        
        if not os.path.exists(path):
            return {"status": "error", "msg": "File not found"}
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            count = content.count(old_content)
            if count == 0:
                return {"status": "error", "msg": "old_content not found in file"}
            if count > 1:
                return {"status": "error", "msg": f"Found {count} matches, need unique match. Provide more context."}
            
            content = content.replace(old_content, new_content)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return {"status": "success", "msg": "Patch applied successfully"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}


class WebFetch:
    """Simple web fetching (no browser needed)."""
    
    @staticmethod
    def fetch(url: str, max_chars: int = 15000) -> dict:
        """Fetch URL and extract text content."""
        if not HAS_REQUESTS:
            return {"status": "error", "msg": "requests not installed"}
        
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
                )
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            
            if HAS_BS4:
                soup = BeautifulSoup(resp.text, "lxml")
                # Remove non-content elements
                for tag in soup(["script", "style", "nav", "footer", "aside", "iframe"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            else:
                text = resp.text[:max_chars]
            
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n... [truncated]"
            
            return {
                "status": "success",
                "url": url,
                "content": text,
                "content_type": resp.headers.get("content-type", ""),
            }
        except Exception as e:
            return {"status": "error", "msg": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
#                             MCP SERVER
# ═══════════════════════════════════════════════════════════════════════════════

server = Server("ga-agent")

# Global state
browser = BrowserManager()
code_runner = CodeRunner()
file_ops = FileOps()
web_fetcher = WebFetch()


def _tool(name: str, desc: str, properties: dict, required: list = None) -> Tool:
    """Helper to create a Tool definition."""
    return Tool(
        name=name,
        description=desc,
        inputSchema={
            "type": "object",
            "properties": properties,
            "required": required or [],
        }
    )


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools — 10 atomic operations."""
    return [
        # ── Code Execution ──
        _tool(
            "code_run",
            "Execute Python or shell code. Prefer Python for complex operations. "
            "Use shell for system commands. Multi-call for independent tasks.",
            {
                "code": {"type": "string", "description": "Code to execute"},
                "type": {
                    "type": "string",
                    "enum": ["python", "bash", "shell"],
                    "description": "Code type (default: python)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 60)",
                },
            },
            required=["code"],
        ),
        
        # ── Browser: Navigate ──
        _tool(
            "web_navigate",
            "Open a URL in the browser. First call launches a real browser window "
            "(retains login sessions). Use web_scan to read content.",
            {
                "url": {"type": "string", "description": "URL to open"},
            },
            required=["url"],
        ),
        
        # ── Browser: Scan ──
        _tool(
            "web_scan",
            "Get simplified content from current browser page, or list all open tabs. "
            "Use tabs_only=true to just list tabs without reading content (saves tokens).",
            {
                "tabs_only": {"type": "boolean", "description": "Only return tabs list"},
                "switch_tab_id": {
                    "type": "string",
                    "description": "Switch to this tab before scanning",
                },
                "text_only": {
                    "type": "boolean",
                    "description": "Text-only extraction (no HTML)",
                },
            },
        ),
        
        # ── Browser: Execute JS ──
        _tool(
            "web_execute_js",
            "Execute arbitrary JavaScript in the current browser page. "
            "Full control: click elements, fill forms, extract data, scroll, etc. "
            "Prefer this over web_scan when you need specific data.",
            {
                "script": {"type": "string", "description": "JavaScript code to execute"},
                "switch_tab_id": {"type": "string", "description": "Switch tab first"},
            },
            required=["script"],
        ),
        
        # ── Browser: Screenshot ──
        _tool(
            "web_screenshot",
            "Take a screenshot of the current browser page. Good for visual tasks "
            "or when text extraction misses important visual info.",
            {},
        ),
        
        # ── Simple Web Fetch (no browser) ──
        _tool(
            "web_fetch",
            "Fetch a URL without launching a browser. Fast, low overhead. "
            "Use for API responses, simple pages, or data extraction. "
            "For interactive pages (login forms, JS-heavy), use web_navigate + web_scan instead.",
            {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters to return (default: 15000)",
                },
            },
            required=["url"],
        ),
        
        # ── File Operations ──
        _tool(
            "file_read",
            "Read a file with optional line range or keyword search. "
            "Always read before editing to get latest content.",
            {
                "path": {"type": "string", "description": "File path (absolute or relative)"},
                "start": {"type": "integer", "description": "Start line (1-based)"},
                "count": {"type": "integer", "description": "Number of lines (default: 200)"},
                "keyword": {"type": "string", "description": "Search keyword"},
                "show_linenos": {"type": "boolean", "description": "Show line numbers"},
            },
            required=["path"],
        ),
        _tool(
            "file_write",
            "Create, overwrite, append, or prepend to a file. "
            "Use overwrite for new files, patch for modifications.",
            {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to write"},
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append", "prepend"],
                    "description": "Write mode (default: overwrite)",
                },
            },
            required=["path", "content"],
        ),
        _tool(
            "file_patch",
            "Surgically replace exact text in a file. old_content must be unique. "
            "Fails if 0 or 2+ matches found — prevents ambiguity. "
            "For large changes, use file_write with mode=overwrite.",
            {
                "path": {"type": "string", "description": "File path"},
                "old_content": {"type": "string", "description": "Exact text to replace"},
                "new_content": {"type": "string", "description": "Replacement text"},
            },
            required=["path", "old_content", "new_content"],
        ),
        
        # ── Memory & Skill Crystallization ──
        _tool(
            "memory_crystallize",
            "CRITICAL: Call at the END of every completed task. "
            "Crystallizes the execution path into a reusable L3 skill. "
            "Next time user says the trigger phrase, the skill auto-loads.",
            {
                "task_name": {"type": "string", "description": "Short, descriptive name"},
                "trigger_phrase": {
                    "type": "string",
                    "description": "Natural language phrase that triggers this skill",
                },
                "key_steps": {
                    "type": "string",
                    "description": "Key steps: preconditions, logic, success criteria",
                },
                "prerequisites": {
                    "type": "string",
                    "description": "Dependencies, configs, or environment needs",
                },
                "code_template": {
                    "type": "string",
                    "description": "Optional reusable code snippet",
                },
            },
            required=["task_name", "trigger_phrase", "key_steps"],
        ),
        _tool(
            "memory_update",
            "Write important facts to L2 global memory or update L1 insight index. "
            "Use for: learned user preferences, environment facts, paths, configs, "
            "or anything the agent should remember across sessions.",
            {
                "layer": {
                    "type": "string",
                    "enum": ["L1_index", "L2_facts"],
                    "description": "L1 = navigation index (≤25 entries), L2 = detailed facts",
                },
                "content": {"type": "string", "description": "Content to remember"},
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite entire file (default: false = append)",
                },
            },
            required=["layer", "content"],
        ),
        _tool(
            "agent_state",
            "Get current state: loaded skills, recent sessions, memory usage. "
            "Diagnostic tool to understand what the agent knows.",
            {
                "what": {
                    "type": "string",
                    "enum": ["skills", "memory", "recent", "all"],
                    "description": "What to query (default: all)",
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    """Handle tool calls."""
    try:
        result = await _dispatch_tool(name, arguments)
        
        # Handle text results
        if isinstance(result, str):
            return CallToolResult(content=[TextContent(type="text", text=result)])
        
        # Handle dict results
        if isinstance(result, dict):
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return CallToolResult(content=[TextContent(type="text", text=text)])
        
        # Handle bytes (screenshot)
        if isinstance(result, bytes):
            b64 = base64.b64encode(result).decode("ascii")
            return CallToolResult(content=[
                ImageContent(type="image", data=b64, mimeType="image/png")
            ])
        
        return CallToolResult(content=[TextContent(type="text", text=str(result))])
    
    except Exception as e:
        import traceback
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {e}\n{traceback.format_exc()}")]
        )


async def _dispatch_tool(name: str, args: dict) -> Any:
    """Dispatch to the right tool implementation."""
    
    # ── Code Execution ──
    if name == "code_run":
        return await code_runner.run(
            code=args.get("code", ""),
            type_=args.get("type", "python"),
            timeout=args.get("timeout", 60),
        )
    
    # ── Browser: Navigate ──
    elif name == "web_navigate":
        info = await browser.navigate(args["url"])
        return {"status": "success", "info": info}
    
    # ── Browser: Scan ──
    elif name == "web_scan":
        tabs_only = args.get("tabs_only", False)
        switch_tab = args.get("switch_tab_id")
        
        if switch_tab:
            await browser.switch_tab(switch_tab)
        
        tabs = await browser.get_tabs()
        
        if tabs_only:
            return {"tabs": tabs, "count": len(tabs), "status": "success"}
        
        content = await browser.get_content(
            text_only=args.get("text_only", False)
        )
        return {
            "tabs": tabs,
            "page": await browser.page_info(),
            "content": content,
            "status": "success",
        }
    
    # ── Browser: Execute JS ──
    elif name == "web_execute_js":
        switch_tab = args.get("switch_tab_id")
        if switch_tab:
            await browser.switch_tab(switch_tab)
        
        js_result = await browser.execute_js(args["script"])
        return {
            "status": "success",
            "result": js_result,
        }
    
    # ── Browser: Screenshot ──
    elif name == "web_screenshot":
        return await browser.screenshot()
    
    # ── Simple Web Fetch ──
    elif name == "web_fetch":
        result = web_fetcher.fetch(
            url=args["url"],
            max_chars=args.get("max_chars", 15000),
        )
        return result
    
    # ── File Operations ──
    elif name == "file_read":
        return file_ops.read(
            path=args["path"],
            start=args.get("start", 1),
            count=args.get("count", 200),
            keyword=args.get("keyword"),
            show_linenos=args.get("show_linenos", True),
        )
    
    elif name == "file_write":
        return file_ops.write(
            path=args["path"],
            content=args["content"],
            mode=args.get("mode", "overwrite"),
        )
    
    elif name == "file_patch":
        return file_ops.patch(
            path=args["path"],
            old_content=args["old_content"],
            new_content=args["new_content"],
        )
    
    # ── Memory & Skills ──
    elif name == "memory_crystallize":
        result = crystallize_skill(
            task_name=args["task_name"],
            trigger_phrase=args["trigger_phrase"],
            key_steps=args["key_steps"],
            prerequisites=args.get("prerequisites", ""),
            code_template=args.get("code_template", ""),
        )
        log_session(
            task_name=args["task_name"],
            summary=args["key_steps"][:200],
            key_info=args.get("prerequisites", ""),
        )
        
        # Also add to L2 facts
        current_l2 = read_memory_file("L2_global_facts.txt")
        entry = f"- skill/{args['task_name']}: invoked by「{args['trigger_phrase']}」\n"
        if entry not in current_l2:
            write_memory_file("L2_global_facts.txt", current_l2 + entry)
        
        return result
    
    elif name == "memory_update":
        layer = args["layer"]
        content = args["content"]
        overwrite = args.get("overwrite", False)
        
        if layer == "L1_index":
            if overwrite:
                write_memory_file("L1_insight_index.txt", content)
            else:
                update_insight_index(content)
            return {"status": "success", "msg": "L1 insight index updated"}
        
        elif layer == "L2_facts":
            if overwrite:
                write_memory_file("L2_global_facts.txt", content)
            else:
                current = read_memory_file("L2_global_facts.txt")
                write_memory_file("L2_global_facts.txt", current + "\n" + content)
            return {"status": "success", "msg": "L2 global facts updated"}
    
    elif name == "agent_state":
        what = args.get("what", "all")
        result = {}
        
        if what in ("skills", "all"):
            skills = sorted(L3_SKILLS_DIR.glob("*.md"))
            result["skills"] = [
                {"name": f.stem, "content": f.read_text(encoding="utf-8")[:200]}
                for f in skills
            ]
            result["skill_count"] = len(skills)
        
        if what in ("memory", "all"):
            l1 = read_memory_file("L1_insight_index.txt")
            l2 = read_memory_file("L2_global_facts.txt")
            result["memory"] = {
                "L1_lines": len(l1.split("\n")) if l1 else 0,
                "L2_lines": len(l2.split("\n")) if l2 else 0,
                "L3_skills": len(list(L3_SKILLS_DIR.glob("*.md"))),
                "L4_sessions": len(list(L4_ARCHIVE_DIR.glob("*.md"))),
            }
        
        if what in ("recent", "all"):
            archives = sorted(L4_ARCHIVE_DIR.glob("*.md"), reverse=True)[:5]
            result["recent_sessions"] = [
                f.stem for f in archives
            ]
        
        return result
    
    return {"status": "error", "msg": f"Unknown tool: {name}"}


# ═══════════════════════════════════════════════════════════════════════════════
#                                  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    ensure_memory_dirs()
    
    # Check if L0 meta rules exist, create default if not
    l0_path = MEMORY_DIR / "L0_meta_rules.txt"
    if not l0_path.exists():
        l0_path.write_text(
            "# L0 元规则 — 不可违抗\n"
            "1. 无行动，不记忆：写入记忆的信息必须源自成功的工具调用结果\n"
            "2. 每次任务完成后必须调用 memory_crystallize 结晶为 Skill\n"
            "3. 问用户前，先尝试所有工具组合至少 3 次\n"
            "4. 禁止一次性写入大段未经验证的信息到记忆\n"
            "5. 用户喜好与习惯必须记入 L2 global_facts\n"
            "6. 每次启动时检查 L3_skills/ 中是否有匹配当前需求的 Skill\n",
            encoding="utf-8",
        )
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
