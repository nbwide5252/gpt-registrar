"""
Cloudflare Worker 域名邮箱 Provider
====================================
对接部署在 Cloudflare Workers 上的邮件接收服务。
通过 Worker API 获取 OpenAI 验证码。

配置 (config.py 或环境变量):
    MAIL_PROVIDER = "cloudflare"
    CF_MAIL_DOMAIN = "zhidexiu.com"
    CF_MAIL_API_URL = "https://zhidexiu-mail.xxx.workers.dev"
"""
import sys
import io
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

import os
import time
import re
import json
import logging
import secrets
import string
import requests
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class CloudflareMailProvider:
    """
    Cloudflare Worker 域名邮箱客户端
    
    使用流程:
        1. 创建实例 (自动配置域名和API地址)
        2. create_mailbox() - 生成随机邮箱地址
        3. 用邮箱地址注册 OpenAI
        4. wait_for_otp() - 轮询 Worker API 获取验证码
        5. release() - 清理收件箱
    """

    def __init__(self, domain: str = "", api_url: str = ""):
        """
        Args:
            domain: 邮箱域名 (如 zhidexiu.com)
            api_url: Cloudflare Worker API 地址
        """
        self.domain = domain or os.environ.get("CF_MAIL_DOMAIN", "zhidexiu.com")
        self.api_url = (api_url or os.environ.get("CF_MAIL_API_URL", "")).rstrip("/")
        self.current_email = ""
        self._seen_ids = set()

        if not self.api_url:
            logger.warning("[CFMail] CF_MAIL_API_URL 未设置")

    def _random_name(self, prefix: str = "gpt") -> str:
        """生成随机邮箱前缀"""
        chars = string.ascii_lowercase + string.digits
        suffix = ''.join(secrets.choice(chars) for _ in range(8))
        return f"{prefix}{suffix}"

    def create_mailbox(self, prefix: str = "gpt") -> str:
        """
        生成一个新的域名邮箱地址
        
        Returns:
            完整邮箱地址 (如 gptx3k9m2@zhidexiu.com)
        """
        name = self._random_name(prefix)
        self.current_email = f"{name}@{self.domain}"
        self._seen_ids = set()
        logger.info(f"[CFMail] 生成邮箱: {self.current_email}")
        return self.current_email

    def wait_for_otp(
        self,
        email_addr: str = "",
        timeout: int = 120,
        issued_after: float = None
    ) -> str:
        """
        等待并提取 OpenAI 邮箱验证码
        
        轮询 Worker API 直到收到验证码邮件或超时。
        
        Args:
            email_addr: 邮箱地址 (默认用 self.current_email)
            timeout: 超时秒数
            issued_after: 忽略这个时间之前的邮件 (时间戳)
            
        Returns:
            验证码字符串 (6位数字)
            
        Raises:
            TimeoutError: 超时未收到验证码
            RuntimeError: API 错误
        """
        email = email_addr or self.current_email
        if not email:
            raise RuntimeError("[CFMail] 未设置邮箱地址，请先调用 create_mailbox()")

        deadline = time.time() + timeout
        start_time = issued_after or time.time()
        poll_count = 0
        last_id = None

        logger.info(f"[CFMail] 等待 OTP -> {email} (timeout={timeout}s)")

        while time.time() < deadline:
            poll_count += 1
            try:
                resp = requests.get(
                    f"{self.api_url}/api/inbox",
                    params={"email": email},
                    timeout=15
                )
                if resp.status_code != 200:
                    logger.debug(f"[CFMail] 轮询 #{poll_count} - HTTP {resp.status_code}")
                    time.sleep(3)
                    continue

                data = resp.json()
                emails = data.get("emails", [])

                if not emails:
                    logger.debug(f"[CFMail] 轮询 #{poll_count} - 无邮件")
                    time.sleep(3)
                    continue

                # 找新邮件
                for mail in reversed(emails):
                    mail_id = mail.get("id", "")
                    if mail_id == last_id or mail_id in self._seen_ids:
                        continue
                    if mail_id:
                        self._seen_ids.add(mail_id)
                    
                    last_id = mail_id
                    subject = mail.get("subject", "")
                    raw = mail.get("raw", "")
                    from_addr = mail.get("from", "").lower()
                    body = (subject + " " + (raw or "")).lower()

                    # 判断是否是 OpenAI 邮件
                    is_openai = (
                        "openai" in from_addr or
                        "chatgpt" in from_addr or
                        "noreply" in from_addr or
                        any(kw in subject.lower() for kw in ["verification", "verify", "code", "otp", "openai", "chatgpt"])
                    )
                    if not is_openai:
                        logger.debug(f"[CFMail] 跳过非 OpenAI 邮件: {subject[:40]}")
                        continue

                    # 提取验证码
                    otp = self._extract_otp(raw or "")
                    if otp:
                        logger.info(f"[CFMail] 验证码: {otp} (来自: {subject[:50]})")
                        return otp
                    else:
                        logger.info(f"[CFMail] 找到 OpenAI 邮件但未提取到验证码: {subject[:50]}")
                        # 可能是第二封验证码邮件，继续等

                time.sleep(3)

            except requests.Timeout:
                logger.debug(f"[CFMail] 轮询 #{poll_count} 超时")
                time.sleep(3)
            except Exception as e:
                logger.debug(f"[CFMail] 轮询 #{poll_count} 错误: {e}")
                time.sleep(3)

        raise TimeoutError(f"[CFMail] 等待验证码超时 ({timeout}s): {email}")

    def _extract_otp(self, raw_text: str) -> Optional[str]:
        """从邮件原文中提取6位数字验证码"""
        if not raw_text:
            return None

        # 多种验证码模式
        patterns = [
            r'(?:verification|code|otp|is|code:)\s*(\d{6})',
            r'(\d{6})\s*(?:is your|验证码|确认码)',
            r'(?:>|:|\s)(\d{6})(?:<|\s|\.|$)',
            r'您的验证码[：:]\s*(\d{6})',
            r'验证码[：:]\s*(\d{6})',
        ]

        for pattern in patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def get_mails(self, email_addr: str = "") -> List[Dict]:
        """获取某邮箱的所有邮件"""
        email = email_addr or self.current_email
        if not email:
            return []
        try:
            resp = requests.get(
                f"{self.api_url}/api/inbox",
                params={"email": email},
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json().get("emails", [])
        except Exception as e:
            logger.warning(f"[CFMail] 获取邮件失败: {e}")
        return []

    def release(self, email_addr: str = ""):
        """清理收件箱"""
        email = email_addr or self.current_email
        if not email:
            return
        try:
            requests.delete(
                f"{self.api_url}/api/inbox",
                params={"email": email},
                timeout=10
            )
            logger.info(f"[CFMail] 已清理: {email}")
        except Exception as e:
            logger.debug(f"[CFMail] 清理失败: {e}")

    def health_check(self) -> bool:
        """检查 Worker 是否在线"""
        try:
            resp = requests.get(f"{self.api_url}/api/health", timeout=10)
            return resp.status_code == 200
        except:
            return False


# ── 兼容 outlook_provider 接口 ──
class CloudflareMailAdapter:
    """
    适配器: 将 CloudflareMailProvider 包装成
    与 outlook_provider.AppleEmailProvider 兼容的接口
    """
    
    def __init__(self, domain: str = "", api_url: str = ""):
        self.provider = CloudflareMailProvider(domain, api_url)
        self.current_account = None
        self.last_email = ""

    def create_mailbox(self) -> str:
        email = self.provider.create_mailbox()
        # 构建一个兼容的 account 对象
        class FakeAccount:
            def __init__(self, email):
                self.email = email
                self.password = ""
                self.in_use = True
        self.current_account = FakeAccount(email)
        self.last_email = email
        return email

    def wait_for_otp(self, email_addr: str = "", timeout: int = 120, issued_after=None) -> str:
        return self.provider.wait_for_otp(email_addr or self.last_email, timeout, issued_after)

    def get_mails(self, email_addr: str = ""):
        return self.provider.get_mails(email_addr or self.last_email)

    def release(self, email_addr: str = ""):
        self.provider.release(email_addr or self.last_email)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    p = CloudflareMailProvider()
    print(f"Worker 在线: {p.health_check()}")
    email = p.create_mailbox()
    print(f"生成邮箱: {email}")