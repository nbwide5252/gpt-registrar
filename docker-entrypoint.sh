#!/bin/bash
set -e
echo ============================================
echo  GPT 自动注册机 - Docker 容器启动
echo ============================================
cd /app

# Start dbus for WARP
if ! pgrep -x dbus-daemon > /dev/null 2>&1; then
    mkdir -p /run/dbus
    dbus-daemon --system 2>/dev/null || true
fi

if command -v warp-cli &>/dev/null; then
    echo [WARP] 启动代理模式...
    nohup warp-svc > /dev/null 2>&1 &
    sleep 3
    warp-cli set-mode proxy 2>/dev/null || true
    warp-cli registration new 2>/dev/null && echo [WARP] 注册成功 || echo [WARP] 已注册过
    warp-cli connect 2>/dev/null
    sleep 2
    export WARP_PROXY=socks5://127.0.0.1:40000
    echo [WARP] 代理已启动
fi

python3 deploy/menu.py
warp-cli disconnect 2>/dev/null || true
