# GPT 自动注册机 - Docker VPS 版

## 前提条件
- VPS 已安装 Docker 和 docker-compose
- zhidexiu.com 域名邮箱 Worker 已部署
- HeroSMS / SMSBower API Key

## 快速启动

bash
# 传到 VPS
scp -r gpt-vps root@你的VPS:/opt/gpt-registrar

# SSH 登录 VPS
cd /opt/gpt-registrar

# 编辑 SMS Key
nano sms_providers_config.json

# 构建并启动
docker compose up -d

# 进入菜单
docker exec -it gpt-registrar python3 deploy/menu.py


## 菜单功能
`
 1. 批量注册 ChatGPT 账号   - 自动上传 Sub2
 2. 单次注册               - 可选手动上传
 3. 恢复已有 Token
 4. 上传 Token 到 Sub2
 5. 账号健康检查
 6. SMS 余额查询
 w. WARP VPN 管理          - 容器内不影响宿主机
 8. 配置管理
 9. 环境检查
`

## 目录说明
- outputs/tokens/  - Token 文件（宿主机可读）
- logs/           - 日志
- sms_providers_config.json - SMS 配置
- sub2_config.json - Sub2 配置
