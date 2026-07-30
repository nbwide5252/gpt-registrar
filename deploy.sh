#!/bin/bash
set -e
REPO_URL="https://github.com/nbwide5252/gpt-registrar.git"
INSTALL_DIR="/opt/gpt-registrar"

echo "=== GPT v2.1.0 ==="

[ "" -ne 0 ] && echo "Need root" && exit 1

command -v git &>/dev/null && echo "git: ok" || { echo "installing git..."; apt-get update -qq && apt-get install -y -qq git; }

command -v docker &>/dev/null && echo "docker: ok" || { echo "installing docker..."; curl -fsSL https://get.docker.com | bash; }

if [ -d "/.git" ]; then
    cd "" && git pull origin main 2>/dev/null || true
else
    git clone "" "" && cd ""
fi

echo "building..."
docker compose up -d --build 2>/dev/null || docker-compose up -d --build || docker compose up -d

cp gpt.sh /usr/local/bin/gpt 2>/dev/null && chmod +x /usr/local/bin/gpt

echo "Done! Run: gpt"