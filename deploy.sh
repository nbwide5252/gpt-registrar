#!/bin/bash
set -e
# ============================================
# GPT自动注册机 - 一键部署脚本
# 用法: bash <(curl -fsSL https://raw.githubusercontent.com/nbwide5252/gpt-registrar/main/deploy.sh)
# ============================================

REPO_URL="https://github.com/nbwide5252/gpt-registrar.git"
INSTALL_DIR="/opt/gpt-registrar"

# Colors
R="\033[91m"; G="\033[92m"; Y="\033[93m"; C="\033[96m"; N="\033[0m"; BLD="\033[1m"

echo -e "\n ${C}================================================${N}"
echo -e " ${BLD}${Y}  海鸥GPT自动注册机 - 一键部署${N}"
echo -e " ${C}================================================${N}\n"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e " ${R}✖ 请用 root 运行: sudo bash deploy.sh${N}"
    exit 1
fi

# Check git
if ! command -v git &>/dev/null; then
    echo -e " ${Y}安装 git...${N}"
    apt-get update -qq && apt-get install -y -qq git
fi

# Check Docker
if ! command -v docker &>/dev/null; then
    echo -e " ${Y}安装 Docker...${N}"
    curl -fsSL https://get.docker.com | bash
fi

# Clone
echo -e " ${Y}下载项目...${N}"
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR" && git pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Build and run
echo -e " ${Y}构建 Docker 镜像...${N}"
docker compose up -d --build

echo -e "\n ${G}================================================${N}"
echo -e " ${BLD}部署完成!${N}"
echo -e " ${G}================================================${N}"
echo -e ""
echo -e "  进入菜单:"
echo -e "    docker exec -it gpt-registrar python3 deploy/menu.py"
echo -e ""
echo -e "  查看日志:"
echo -e "    docker logs -f gpt-registrar"
echo -e ""
echo -e "  配置 SMS:"
echo -e "    nano $INSTALL_DIR/sms_providers_config.json"
echo -e ""