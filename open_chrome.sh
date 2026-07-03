#!/bin/bash
# 用远程调试端口启动 Chrome（让牧云野能连上来操控）
# 用法: bash open_chrome.sh
#   可用 CHROME=/path/to/chrome bash open_chrome.sh 覆盖浏览器路径

SESSION_DIR="$HOME/.chrome-ga-session"

# 跨平台探测 Chrome/Chromium 可执行文件（可用 CHROME=... 覆盖）
detect_chrome() {
    if [ -n "${CHROME:-}" ]; then echo "$CHROME"; return 0; fi
    local candidates=(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        "$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        "/Applications/Chromium.app/Contents/MacOS/Chromium"
    )
    for c in "${candidates[@]}"; do
        [ -x "$c" ] && { echo "$c"; return 0; }
    done
    for c in google-chrome google-chrome-stable chromium chromium-browser; do
        command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return 0; }
    done
    return 1
}
CHROME="$(detect_chrome)" || {
    echo "❌ 未找到 Chrome/Chromium。请安装，或用 CHROME=/path/to/chrome bash open_chrome.sh"
    exit 1
}

# 只杀掉本项目启动的调试实例（按专用 user-data-dir 精确匹配，不影响你的正式浏览器）
pkill -f -- "--user-data-dir=$SESSION_DIR" 2>/dev/null || true
sleep 1

# 启动 Chrome（带调试端口 + 全新的用户数据目录以避免影响你的正式浏览器）
"$CHROME" \
  --remote-debugging-port=9222 \
  --user-data-dir="$SESSION_DIR" \
  --no-first-run \
  --no-default-browser-check \
  --disable-features=TranslateUI \
  --disable-sync \
  --disable-features=IsolateOrigins,site-per-process \
  &

echo "✅ Chrome 已启动（调试端口 9222，路径: $CHROME）"
echo "   牧云野可以连上来操控浏览器了"
echo ""
echo "   关闭: pkill -f -- '--user-data-dir=$SESSION_DIR'"
