# GPT Registrator v3.0

ChatGPT 自动注册机 - VPS Docker 一键部署

## 功能
- 域名邮箱收验证码（Cloudflare Worker）
- SMSBower / HeroSMS 双平台接码
- 完整注册流程 + Token 获取
- 自动上传 Sub2 面板
- 防风控（指纹轮换 + 随机延迟）
- WARP IP 轮换（10分钟）

## 一键部署
`ash
bash <(curl -fsSL https://raw.githubusercontent.com/nbwide5252/gpt-registrar/main/deploy.sh)
`

## 快捷命令
| 命令 | 说明 |
|------|------|
| gpt | 打开菜单 |
| gpt batch 10 | 批量注册10个 |
| gpt status | 容器状态 |
| gpt balance | SMS余额 |
| gpt stats | Token统计 |

## 配置向导
首次运行自动弹出5步引导：SMS → 邮箱 → 国家 → 数量 → Sub2

## 卸载
`ash
bash <(curl -fsSL https://raw.githubusercontent.com/nbwide5252/gpt-registrar/main/uninstall.sh)
`
