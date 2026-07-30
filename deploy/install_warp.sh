#!/bin/bash
# ============================================
# Cloudflare WARP 安装脚本 - Debian VPS
# ============================================
# 给 VPS 装 WARP 获取干净 IP，解决机房IP被OpenAI封的问题
# 用法: bash deploy/install_warp.sh
# 需要 root 权限

set -e

echo "============================================"
echo "  Cloudflare WARP 安装"
echo "============================================"

# 检查 root
if [ "$EUID" -ne 0 ]; then
    echo "请用 root 运行: sudo bash deploy/install_warp.sh"
    exit 1
fi

echo "[1/5] 添加 Cloudflare 仓库..."

# 导入 GPG 密钥
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg 2>/dev/null || true

# 添加仓库
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -sc 2>/dev/null || echo 'bookworm') main" | tee /etc/apt/sources.list.d/cloudflare-client.list > /dev/null 2>/dev/null || {
    # 如果 lsb_release 失败，用 bookworm (Debian 12)
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ bookworm main" > /etc/apt/sources.list.d/cloudflare-client.list
}

echo "[2/5] 安装 cloudflare-warp..."
apt-get update -qq 2>/dev/null
apt-get install -y -qq cloudflare-warp 2>/dev/null || {
    echo "  尝试备用安装方式..."
    # 如果仓库不行，直接下载 deb
    wget -q https://github.com/cloudflare/cloudflare-warp/releases/latest/download/cloudflare-warp-stable-linux-amd64.deb -O /tmp/warp.deb 2>/dev/null || {
        echo "  WARP 安装失败，使用 wgcf 模式..."
        WGCF_MODE=1
    }
    if [ -z "$WGCF_MODE" ]; then
        dpkg -i /tmp/warp.deb 2>/dev/null || apt-get install -f -y -qq
    fi
}

if [ -z "$WGCF_MODE" ] && command -v warp-cli &>/dev/null; then
    echo "[3/5] 注册 WARP..."
    warp-cli registration new 2>/dev/null || true

    echo "[4/5] 连接 WARP..."
    warp-cli connect 2>/dev/null || true
    sleep 3

    echo "[5/5] 检查状态..."
    warp-cli status 2>/dev/null || true

    echo ""
    echo "============================================"
    echo "  WARP 安装完成!"
    echo "============================================"
    echo ""
    echo "  设置 SOCKS5 代理模式（只让注册走 WARP）:"
    echo "    warp-cli set-mode proxy           设置代理模式"
    echo "    warp-cli connect                   连接"
    echo "    代理地址: socks5://127.0.0.1:40000"
    echo "    然后在 config.json 中配置: proxyHost=127.0.0.1, proxyPort=40000"
    echo ""
    echo "  管理命令:"
    echo "    warp-cli status         查看状态"
    echo "    warp-cli connect        连接"
    echo "    warp-cli disconnect     断开"
    echo "    warp-cli registration new  重新注册"
else
    echo ""
    echo "[备用方案] 使用 wgcf 安装 WireGuard WARP..."
    echo "  确保先安装: apt install -y wireguard resolvconf"
    echo "  然后: wget https://github.com/ViRb3/wgcf/releases/latest/download/wgcf_2.2.22_linux_amd64 -O /usr/local/bin/wgcf"
    echo "  详情: https://github.com/ViRb3/wgcf"
fi

echo ""
echo "提示: WARP 连接后 VPS 所有流量走 WARP 出口"
echo "  如果只需要注册走 WARP，请配置 socks5 代理指向 127.0.0.1:40000"
echo "  然后在 config.json 中填写代理"