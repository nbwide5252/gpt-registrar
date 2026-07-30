"""
Sub2API正确的上传实现

基于 new注册机_干净版 项目的sub2Admin.js
"""
import json
import base64
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import requests


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    """解码JWT payload"""
    if not token:
        return {}

    try:
        parts = token.split('.')
        if len(parts) < 2:
            return {}

        payload_b64 = parts[1]
        # 补齐padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_str = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
        return json.loads(payload_str)
    except Exception as e:
        print(f"⚠️ 解析JWT失败: {e}")
        return {}


def build_credentials_from_token(token_data: Dict[str, Any]) -> Dict[str, Any]:
    """从token数据构建credentials"""
    access_token = token_data.get("access_token", "")
    id_token = token_data.get("id_token", "")

    access_claims = decode_jwt_payload(access_token)
    id_claims = decode_jwt_payload(id_token)

    profile = access_claims.get("https://api.openai.com/profile", {})
    auth = access_claims.get("https://api.openai.com/auth") or id_claims.get("https://api.openai.com/auth", {})

    # 优先使用明确的时间戳，其次使用 access token 自带的 exp。
    expires_at = int(token_data.get("expires_at") or access_claims.get("exp") or 0)
    if token_data.get("expired"):
        try:
            expired = str(token_data["expired"]).replace("Z", "+00:00")
            expires_at = int(datetime.fromisoformat(expired).timestamp())
        except (TypeError, ValueError):
            pass

    if not expires_at:
        expires_at = int(time.time()) + 863999  # 默认10天

    return {
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token", ""),
        "id_token": id_token,
        "expires_at": expires_at,
        "email": token_data.get("email") or id_claims.get("email") or profile.get("email", ""),
        "chatgpt_account_id": token_data.get("account_id") or auth.get("chatgpt_account_id", ""),
        "chatgpt_user_id": auth.get("chatgpt_user_id") or auth.get("user_id") or access_claims.get("sub", ""),
        "organization_id": auth.get("organization_id", ""),
        "plan_type": token_data.get("plan_type") or auth.get("chatgpt_plan_type") or token_data.get("type") or "free",
        "client_id": token_data.get("client_id", "app_EMoamEEZ73f0CkXaXp7hrann"),
    }


class Sub2AdminClient:
    """Sub2API管理员客户端"""

    def __init__(self, url: str, email: str, password: str, group_name: str = "codex-auto"):
        self.url = url.rstrip('/')
        self.email = email
        self.password = password
        self.group_name = group_name
        self.token = None

    def request_json(self, api_path: str, method: str = "GET", body: Dict = None) -> Any:
        """发送JSON请求"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        url = f"{self.url}{api_path}"

        try:
            if method == "POST":
                resp = requests.post(url, headers=headers, json=body, timeout=30)
            elif method == "PUT":
                resp = requests.put(url, headers=headers, json=body, timeout=30)
            else:
                resp = requests.get(url, headers=headers, timeout=30)

            text = resp.text

            # 尝试解析JSON
            try:
                data = json.loads(text) if text else {}
            except:
                data = {"raw": text}

            if not resp.ok:
                if resp.status_code == 423 and isinstance(data, dict) and data.get("code") == "ADMIN_COMPLIANCE_ACK_REQUIRED":
                    raise Exception(
                        "Sub2API 管理员尚未完成合规确认。请登录 Sub2API 管理后台，"
                        "按弹窗阅读并确认当前版本后重试"
                    )
                raise Exception(f"SUB2API {api_path} HTTP {resp.status_code}: {json.dumps(data)[:500]}")

            # 处理 {code: 0, data: ...} 格式
            if isinstance(data, dict) and "code" in data:
                code = data.get("code")
                if code == 0:
                    return data.get("data", data)
                else:
                    message = data.get("message") or data.get("msg") or data.get("error") or json.dumps(data)[:500]
                    raise Exception(f"SUB2API {api_path} 失败: {message}")

            return data

        except Exception as e:
            raise Exception(f"请求失败 {api_path}: {e}")

    def login(self) -> str:
        """登录并获取token"""
        if self.token:
            return self.token

        print(f"  登录到: {self.url}")
        print(f"  账号: {self.email}")

        data = self.request_json(
            "/api/v1/auth/login",
            method="POST",
            body={"email": self.email, "password": self.password}
        )

        # 尝试多种token字段名
        token = data.get("access_token") or data.get("accessToken") or data.get("token")

        if not token:
            raise Exception("登录响应缺少 access_token")

        self.token = token
        print(f"  ✅ 登录成功")
        return token

    def get_groups(self) -> List[int]:
        """获取目标分组的ID列表"""
        print(f"  获取分组: {self.group_name}")

        data = self.request_json("/api/v1/admin/groups/all")

        # 兼容多种返回格式
        groups = []
        if isinstance(data, list):
            groups = data
        elif isinstance(data, dict):
            groups = data.get("items") or data.get("data") or []

        # 查找匹配的分组
        matched = [g for g in groups if g.get("name") == self.group_name or str(g.get("id")) == self.group_name]

        if not matched:
            # 列出所有可用分组
            available = [g.get("name", str(g.get("id"))) for g in groups]
            raise Exception(f"找不到分组 '{self.group_name}'。可用分组: {', '.join(available)}")

        group_ids = [int(g["id"]) for g in matched if g.get("id")]
        print(f"  ✅ 分组ID: {group_ids}")
        return group_ids

    def find_existing_account(self, email: str) -> Dict:
        """查找是否已存在相同邮箱的账号"""
        if not email:
            return None

        email_lower = email.lower()

        # 尝试多种API路径
        paths = [
            "/api/v1/admin/accounts?limit=500",
            "/api/v1/admin/accounts?page=1&page_size=500",
            "/api/v1/admin/accounts",
        ]

        for api_path in paths:
            try:
                data = self.request_json(api_path)

                # 兼容多种返回格式
                accounts = []
                if isinstance(data, list):
                    accounts = data
                elif isinstance(data, dict):
                    accounts = data.get("items") or data.get("records") or data.get("accounts") or data.get("data") or []

                # 查找匹配的账号
                for acc in accounts:
                    creds = acc.get("credentials", {})
                    acc_email = (creds.get("email") or acc.get("email") or acc.get("name") or "").lower()

                    if acc_email == email_lower or email_lower in acc_email:
                        return acc

            except:
                # 继续尝试下一个路径
                pass

        return None

    def validate_openai_token(self, credentials):
        try:
            at = credentials.get("access_token", "")
            if not at: return
            r = requests.get("https://chatgpt.com/backend-api/codex/models",
                headers={"Authorization": "Bearer " + at, "Accept": "application/json"},
                params={"client_version": "0.144.1"}, timeout=10)
            if r.status_code == 401:
                print("  Token expired, trying upload anyway")
            elif r.ok:
                print("  Token valid")
            else:
                print(f"  Token pre-check HTTP {r.status_code}")
        except Exception as e:
            print(f"  Token pre-check failed: {e}")

def create_account(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建账号"""
        # 1. 构建并验证 credentials
        credentials = build_credentials_from_token(token_data)

        if not credentials.get("access_token"):
            raise Exception("缺少 access_token，不能添加到 SUB2API")

        print("  验证 OpenAI token...")
        self.validate_openai_token(credentials)
        print("  Token 有效")

        # 2. 登录并获取分组ID
        self.login()
        group_ids = self.get_groups()

        email = credentials.get("email") or token_data.get("email", "")

        # 4. 检查是否已存在
        print(f"  检查账号: {email}...")
        existing = self.find_existing_account(email)

        if existing:
            account_id = existing.get("id")
            if not account_id:
                raise Exception(f"同邮箱账号已存在，但响应缺少账号 ID: {email}")
            print(f"  账号已存在，原位更新 OAuth 凭据: ID={account_id}")
            updated = self.request_json(
                f"/api/v1/admin/accounts/{account_id}/apply-oauth-credentials",
                method="POST",
                body={
                    "type": "oauth",
                    "credentials": credentials,
                    "extra": {"email": email, "source": "token-recovery"},
                },
            )
            self.request_json(
                f"/api/v1/admin/accounts/{account_id}",
                method="PUT",
                body={"group_ids": group_ids, "status": "active"},
            )
            print(f"  已更新账号并归入分组: {group_ids}")
            return {"updated": True, "account": updated, "email": email}

        # 5. 创建账号
        account_name = f"{email or 'codex'}-{int(time.time())}"

        body = {
            "name": account_name,
            "platform": "openai",
            "type": "oauth",
            "credentials": credentials,
            "extra": {
                "email": email,
                "auth_provider": "chatgpt2api",
                "source": "improved-registrar",
                "openai_oauth_responses_websockets_v2_enabled": False,
                "openai_oauth_responses_websockets_v2_mode": "off",
                "privacy_mode": "training_off",
            },
            "group_ids": group_ids,
            "concurrency": 10,
            "priority": 1,
            "rate_multiplier": 1,
            "auto_pause_on_expired": True,
        }

        print(f"  创建账号: {account_name}...")

        # 尝试两种API路径
        candidates = [
            "/api/v1/admin/accounts",
            "/api/v1/admin/openai/accounts",
        ]

        for api_path in candidates:
            try:
                account = self.request_json(api_path, method="POST", body=body)
                print(f"  ✅ 创建成功")
                return {"account": account, "accountName": account_name, "email": email, "endpoint": api_path}
            except Exception as e:
                last_error = e

        raise last_error


def upload_token_to_sub2(token_data: Dict[str, Any], url: str, email: str, password: str, group_name: str = "codex-auto") -> bool:
    """上传单个token到Sub2API"""
    try:
        client = Sub2AdminClient(url, email, password, group_name)
        result = client.create_account(token_data)

        if result.get("skipped"):
            return True  # 已存在也算成功

        return True

    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False


if __name__ == "__main__":
    # 测试
    print("这是Sub2API上传模块，请使用 upload_to_sub2.py 运行")
