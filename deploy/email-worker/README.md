# 部署指南 - Cloudflare Worker 域名邮箱

## 前置条件

1. Cloudflare 账号 (你已经有)
2. zhidexiu.com 在 Cloudflare 上管理 (你已经有)
3. Node.js 已安装

## 第一步: 安装 Wrangler CLI

```bash
npm install -g wrangler
wrangler login
# 浏览器会打开 Cloudflare 登录确认
```

## 第二步: 创建 KV 命名空间

```bash
cd deploy/email-worker
wrangler kv:namespace create ZHDX_MAIL
```

输出类似:
```
🌀 Creating namespace with title "zhidexiu-mail-ZHDX_MAIL"
✨ Success!
Add the following to your wrangler.toml:
[[kv_namespaces]]
binding = "MAIL_KV"
id = "abc123def456"
```

把输出的 `id` 值复制到 `wrangler.toml` 中替换。

## 第三步: 获取 Zone ID

1. 打开 https://dash.cloudflare.com/
2. 选择 zhidexiu.com
3. 在右侧面板找到 "Zone ID"
4. 复制到 `wrangler.toml` 的 `zone_id`

## 第四步: 部署 Worker

```bash
cd deploy/email-worker
wrangler deploy
```

输出类似:
```
✨ Success! Your Worker was successfully deployed
  https://zhidexiu-mail.xxxx.workers.dev
```

记下这个 Workers.dev 域名。

## 第五步: 设置 Email Routing

1. 打开 https://dash.cloudflare.com/ → zhidexiu.com
2. 左侧菜单 → Email → Email Routing
3. 点击 "Enable Email Routing" (如果还没启用)
4. 在 "Routes" 页:
   - "Catch-all" 或 "Custom Addresses"
   - 设置 `*@zhidexiu.com` → 发送到 Worker
   - 选择你刚部署的 `zhidexiu-mail` Worker
5. 等待 DNS 生效 (1-5 分钟)

## 第六步: 验证

```bash
# 检查 Worker 是否在线
curl https://zhidexiu-mail.xxxx.workers.dev/api/health

# 发一封测试邮件到 test@zhidexiu.com
# 然后检查
curl "https://zhidexiu-mail.xxxx.workers.dev/api/inbox?email=test@zhidexiu.com"
```

## 第七步: 配置 Python 注册机

编辑 `config.py` 或 `.env`:

```python
# 使用 zhidexiu.com 域名邮箱
MAIL_PROVIDER = "cloudflare"
CF_MAIL_DOMAIN = "zhidexiu.com"
CF_MAIL_API_URL = "https://zhidexiu-mail.xxxx.workers.dev"
# 不需要 TOKEN - Worker 是公开读的
```

## 注意事项

- Worker 免费计划每天 10 万次请求，足够注册使用
- KV 免费 1GB 存储，邮件 7 天自动过期
- 邮件的原始内容存在 KV 中，不要用于敏感信息