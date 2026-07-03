#!/bin/bash
# 用远程调试端口启动 Chrome（让牧云野能连上来操控）
# 用法: bash open_chrome.sh

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 杀掉已有 Chrome 实例
pkill -f "Google Chrome.*remote-debugging-port" 2>/dev/null || true
sleep 1

# 启动 Chrome（带调试端口 + 全新的用户数据目录以避免影响你的正式浏览器）
"$CHROME" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-ga-session" \
  --no-first-run \
  --no-default-browser-check \
  --disable-features=TranslateUI \
  --disable-sync \
  --disable-features=IsolateOrigins,site-per-process \
  &

echo "✅ Chrome 已启动（调试端口 9222）"
echo "   牧云野可以连上来操控浏览器了"
echo ""
echo "   关闭: pkill -f 'chrome-ga-session'"
