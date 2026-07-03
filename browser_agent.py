#!/usr/bin/env python3
"""
浏览器一站式工具 — 在同一个 MCP 会话中完成导航+扫描+JS执行
用于需要连续浏览器操作的场景（一次 exec 完成多步）
"""
import json, subprocess, sys, time
sys.path.insert(0, '.')
from mcp_client import _resolve_python, MCP_SERVER

def send(proc, req):
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)

def recv(proc):
    return proc.stdout.readline()

def browser_task(actions: list) -> dict:
    """执行一系列浏览器操作，返回最终结果"""
    python = _resolve_python()
    proc = subprocess.Popen(
        [python, str(MCP_SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=0,
    )
    
    try:
        # Init
        send(proc, {"jsonrpc":"2.0","id":1,"method":"initialize",
                     "params":{"protocolVersion":"2025-11-25","capabilities":{},
                               "clientInfo":{"name":"ga-browser","version":"1"}}})
        recv(proc)
        
        results = []
        for i, action in enumerate(actions):
            req = {"jsonrpc":"2.0","id":i+2,"method":"tools/call",
                   "params":{"name":action["tool"],"arguments":action.get("args",{})}}
            send(proc, req)
            resp = recv(proc)
            if resp:
                data = json.loads(resp)
                results.append({"tool": action["tool"], "result": data})
            else:
                results.append({"tool": action["tool"], "error": "no response"})
        
        return {"status": "success", "results": results}
    finally:
        try: proc.terminate(); proc.wait(timeout=3)
        except: proc.kill()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 browser_agent.py '<json_actions>'")
        print('例: python3 browser_agent.py \'[{"tool":"web_navigate","args":{"url":"https://taobao.com"}},{"tool":"web_scan","args":{"text_only":true}}]\'')
        sys.exit(0)
    
    actions = json.loads(sys.argv[1])
    result = browser_task(actions)
    print(json.dumps(result, indent=2, ensure_ascii=False))
