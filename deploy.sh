#!/bin/bash
set -e
REPO_URL=https://github.com/nbwide5252/gpt-registrar.git
INSTALL_DIR=/opt/gpt-registrar

echo === GPT v2.3.0 ===

[ $EUID -ne 0 ] && echo Need root && exit 1

command -v git >/dev/null 2>&1 && echo git: ok || { apt-get update -qq && apt-get install -y -qq git; }
command -v docker >/dev/null 2>&1 && echo docker: ok || { curl -fsSL https://get.docker.com | bash; }

if [ -d $INSTALL_DIR/.git ]; then
    cd $INSTALL_DIR
    echo Current: $(cat VERSION 2>/dev/null || echo unknown)
    git fetch origin 2>/dev/null
    L=$(git rev-parse HEAD);R=$(git rev-parse origin/main)
    if [ "$L" != "$R" ]; then
        echo Upgrading...
        git reset --hard origin/main 2>/dev/null
git clean -fd 2>/dev/null
git pull origin main
        docker compose down 2>/dev/null;docker compose up -d --build 2>/dev/null || docker-compose up -d --build
        echo Upgraded to $(cat VERSION)
    else
        echo Already latest
        docker compose up -d 2>/dev/null || docker-compose up -d || true
    fi
else
    git clone $REPO_URL $INSTALL_DIR && cd $INSTALL_DIR
    docker compose up -d --build 2>/dev/null || docker-compose up -d --build
fi

cp gpt.sh /usr/local/bin/gpt 2>/dev/null && chmod +x /usr/local/bin/gpt
echo === v$(cat VERSION) Ready ===
echo "  gpt           Menu"
echo "  gpt batch 10  Register 10"