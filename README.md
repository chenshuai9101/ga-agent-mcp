# 🎯 牧云野 Generic Agent — 说人话操控一切

> 受 GenericAgent (13K⭐) 启发，提炼核心思想：
> **最小工具集 + 分层记忆 + 技能结晶 = 越用越强的电脑管家**

## ✨ 一句话

**你说人话，它干活。干完自动记住，下次不用再教。**

## 🚀 快速上手

```bash
cd /path/to/ga-agent
chmod +x install.sh && ./install.sh
```

### 启动浏览器操控能力

```bash
# 用系统 Chrome（绕过淘宝/京东等反爬检测）
bash open_chrome.sh

# 运行 MCP server
source .venv/bin/activate
python mcp_ga_server.py
```

### 测试

```bash
# 列出工具
python mcp_client.py list

# 抓 HN 头条
python mcp_client.py call web_fetch '{"url":"https://news.ycombinator.com/","max_chars":5000}'

# 查看记忆状态
python mcp_client.py snapshot

# 浏览淘宝（需要先运行 open_chrome.sh）
python browser_agent.py '[{"tool":"web_navigate","args":{"url":"https://s.taobao.com/search?q=儿童服装"}},{"tool":"web_execute_js","args":{"script":"new Promise(r=>setTimeout(r,3000)).then(()=>document.body.innerText.substring(0,2000))"}}]'
```

## 🧠 核心机制

### 12 个工具 = 无限可能

| 工具 | 能力 | 适用场景 |
|------|------|---------|
| `code_run` | 执行 Python/Shell 代码 | 跑脚本/算数据 |
| `web_navigate` | 打开浏览器 | 逛网页；需配合 `open_chrome.sh` 用系统 Chrome 绕过反爬 |
| `web_scan` | 读取网页内容 | 提取页面信息 |
| `web_execute_js` | 注入 JS 完全操控浏览器 | 点击/填表单/提取数据 |
| `web_screenshot` | 截图 | 看页面长什么样 |
| `web_fetch` | 快速拉取页面（无浏览器） | API/静态页面 |
| `file_read/write/patch` | 文件操作三件套 | 读写改文件 |
| `memory_crystallize` | ✅ 任务→Skill 结晶 | 每次完成可复现任务后调用 |
| `memory_update` | 记住用户偏好/配置 | 跨会话持久化 |
| `agent_state` | 查技能库/记忆状态 | 诊断 |

### 5 层记忆系统（L0→L4）

```
L0 元规则     → 不可违抗的行为红线
L1 洞察索引   → ≤25 行的极简导航
L2 全局事实   → 环境配置 + 用户偏好（跨会话）
L3 技能库     → 从任务中自动结晶的可复用 Skill ← ★核心
L4 会话归档   → 历史任务回顾
```

### 技能结晶流程

```
用户第一次说：「帮我监控这个股票」
  → 你执行：装库→写脚本→配置定时任务→验证
  → 自动结晶为 L3 Skill
  → 通知用户："已记住，下次说 '监控股票' 就行"

用户第二次说：「帮我监控那个股票」
  → 你查 Skill：发现已结晶 → 直接调用 → 改参数
  → 不需要重新推理
```

越用，L3 技能库越大，Agent 越懂你。

## 🛠️ 文件说明

```
ga-agent/
├── mcp_ga_server.py         ← ★ MCP 服务器（核心，12个工具）
├── mcp_client.py            ← ★ 牧云野通过 exec 调用的 CLI 桥梁
├── browser_agent.py         ← 一站式浏览器工具（多步连续操作）
├── open_chrome.sh           ← 启动系统 Chrome + CDP 调试端口
├── skills/ga-agent/SKILL.md ← ★ 操控指南（教我怎么做你的管家）
├── crystallizer/crystallize.py ← 技能结晶器 CLI
├── memory/
│   ├── L0_meta_rules.txt    ← 6 条不可违抗的元规则
│   ├── L1_insight_index.txt ← 洞察导航（≤25 行）
│   ├── L2_global_facts.txt  ← 记住你是谁、环境信息
│   ├── L3_skills/           ← ⏳ 技能库（用起来自动填满）
│   └── L4_archive/          ← 会话归档日志
├── install.sh               ← 一键安装脚本
└── requirements.txt         ← Python 依赖
```

## ⚠️ 注意事项

### 国内电商反爬（淘宝/京东等）
系统 Playwright 启动的 Chromium 浏览器会被识别为自动化工具。
**解决方案**：运行 `bash open_chrome.sh` 启动系统 Chrome，
MCP server 会自动检测 localhost:9222 并连上系统 Chrome，
利用你真实 Chrome 的指纹绕过反爬检测。

### 浏览器状态
每次 `exec` 调用会启动新的 MCP server 进程，浏览器状态不持久。
- 普通操作（抓网页/查 API）：用 `mcp_client.py call web_fetch`，无状态要求
- 浏览器操作（淘宝搜索/登录）：用 `browser_agent.py` 一次性完成多步操作

## 📦 依赖

- Python 3.10+
- Playwright
- MCP SDK
- Pillow / requests / beautifulsoup4 / lxml

## ☕ 支持项目

如果这个项目对你有帮助，欢迎请喝杯咖啡 ☕

<img src="assets/donate.jpg" width="200" alt="捐赠二维码">

## 许可证

MIT
