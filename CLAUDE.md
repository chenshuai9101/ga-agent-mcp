# CLAUDE.md — ga-agent-mcp 编码与协作指南

## 项目定位
牧云野 Generic Agent — MCP Server + 5层记忆系统 + 技能结晶引擎。
核心差异化：技能结晶（自动将任务转化为可复用 SOP）+ 肌肉反射 Hook。

## 架构要点
- **MCP Server**: mcp_ga_server.py（12 个工具）
- **技能结晶**: crystallizer/crystallize.py + skill_matcher.py
- **Hook**: hooks/skill_reflex.py（Claude Code UserPromptSubmit）
- **记忆系统**: memory/L0-L4

## 贡献指南
1. 修改前先开 Issue 讨论
2. 保持 MCP 协议兼容性
3. 新增工具需同时更新 mcp_client.py 的列表
4. 技能结晶流程不可破坏向后兼容

## 发布流程
1. 修改 README.md 同步更新
2. git add + commit + push
3. 打 tag 发布 Release
