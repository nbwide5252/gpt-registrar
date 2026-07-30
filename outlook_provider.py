"""
Apple Email (appleemail.top) Outlook邮箱Provider
支持账号池管理
"""
import sys
import io
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

import requests
import time
import re
import logging
import random
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class OutlookAccount:
    """Outlook账号"""
    def __init__(self, email: str, password: str, client_id: str, refresh_token: str):
        self.email = email
        self.password = password
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.in_use = False
        self.last_used = 0

    def __str__(self):
        return f"{self.email} (client_id={self.client_id[:20]}...)"


class OutlookAccountPool:
    """Outlook账号池"""

    def __init__(self, pool_file: str = "outlook_pool.txt"):
        self.pool_file = pool_file
        self.accounts: List[OutlookAccount] = []
        self._load_accounts()

    def _load_accounts(self):
        """从文件加载账号"""
        try:
            with open(self.pool_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = line.split('----')
                    if len(parts) != 4:
                        logger.warning(f"账号格式错误，跳过: {line[:50]}...")
                        continue

                    email, password, client_id, refresh_token = parts
                    account = OutlookAccount(
                        email=email.strip(),
                        password=password.strip(),
                        client_id=client_id.strip(),
                        refresh_token=refresh_token.strip()
                    )
                    self.accounts.append(account)

            logger.info(f"[Outlook池] 加载 {len(self.accounts)} 个账号")

        except FileNotFoundError:
            logger.warning(f"[Outlook池] 文件不存在: {self.pool_file}")
            self.accounts = []

    def get_account(self) -> Optional[OutlookAccount]:
        """获取一个可用账号"""
        available = [a for a in self.accounts if not a.in_use]

        if not available:
            logger.error("[Outlook池] 无可用账号")
            return None

        # 随机选择一个
        account = random.choice(available)
        account.in_use = True
        account.last_used = time.time()

        logger.info(f"[Outlook池] 分配账号: {account.email}")
        return account

    def release_account(self, account: OutlookAccount):
        """释放账号"""
        account.in_use = False
        logger.info(f"[Outlook池] 释放账号: {account.email}")


class AppleEmailProvider:
    """AppleEmail.top Outlook邮箱服务Provider"""

    def __init__(self, api_url: str = "https://www.appleemail.top", account_pool: OutlookAccountPool = None):
        self.api_url = api_url.rstrip("/")
        self.account_pool = account_pool
        self.current_account: Optional[OutlookAccount] = None
        self._seen_mail_ids = set()

        # 兼容auth_flow接口
        self.last_persona = None
        self._outlook_creds = None
        self.outlook_exhausted = False

    def create_mailbox(self) -> str:
        """分配一个Outlook邮箱"""
        if not self.account_pool:
            raise RuntimeError("[AppleEmail] 未配置账号池")

        account = self.account_pool.get_account()
        if not account:
            raise RuntimeError("[AppleEmail] 账号池已耗尽")

        self.current_account = account
        self._seen_mail_ids = set()

        logger.info(f"[AppleEmail] 使用邮箱: {account.email}")
        return account.email

    def wait_for_otp(
        self,
        email_addr: str,
        timeout: int = 180,
        issued_after=None
    ) -> str:
        """等待并提取邮箱OTP验证码"""
        if not self.current_account:
            raise RuntimeError("[AppleEmail] 未分配邮箱账号")

        deadline = time.time() + timeout
        logger.info(f"[AppleEmail] 等待OTP -> {email_addr} (timeout={timeout}s)")

        # 记录开始时间，只处理之后的邮件
        start_time = time.time()
        logger.debug(f"[AppleEmail] 只处理 {time.strftime('%H:%M:%S', time.localtime(start_time))} 之后的邮件")

        poll_count = 0
        last_mail_id = None  # 记录上一次的邮件ID

        while time.time() < deadline:
            poll_count += 1

            try:
                mail = self._get_latest_mail()

                if not mail:
                    logger.debug(f"[AppleEmail] 轮询 #{poll_count} - 无邮件")
                    time.sleep(3)
                    continue

                # 使用subject作为唯一标识
                subject = mail.get("subject", "")
                mail_id = f"{subject}_{mail.get('send', '')}"

                # 如果邮件ID和上次相同，说明没有新邮件
                if mail_id == last_mail_id:
                    logger.debug(f"[AppleEmail] 轮询 #{poll_count} - 无新邮件")
                    time.sleep(3)
                    continue

                last_mail_id = mail_id
                logger.info(f"[AppleEmail] 轮询 #{poll_count} - 发现新邮件: {subject[:50]}")

                # 检查是否是OpenAI相关邮件（通过主题和发件人）
                sender = mail.get("from", "").lower()
                subject_lower = subject.lower()
                logger.debug(f"[AppleEmail] 发件人: {sender if sender else '(空)'}")

                # 判断是否是OpenAI邮件
                is_openai_mail = False

                # 方式1: 检查发件人
                if sender and ("openai" in sender or "noreply" in sender):
                    is_openai_mail = True
                    logger.debug(f"[AppleEmail] 通过发件人识别为OpenAI邮件")

                # 方式2: 检查主题关键词（即使发件人为空）
                openai_keywords = [
                    "chatgpt", "openai", "verification", "verify your email",
                    "temporary login code", "your code", "confirm your email"
                ]
                if not is_openai_mail and any(kw in subject_lower for kw in openai_keywords):
                    is_openai_mail = True
                    logger.debug(f"[AppleEmail] 通过主题识别为OpenAI邮件")

                # 过滤：跳过非OpenAI邮件
                if not is_openai_mail:
                    logger.warning(
                        f"[AppleEmail] 跳过非OpenAI邮件 (subject={subject[:40]}, from={sender[:30] if sender else '空'})"
                    )
                    time.sleep(3)
                    continue

                # 提取OTP
                body_html = mail.get("body", "") or mail.get("html", "")
                body_text = mail.get("text", "")

                combined = f"{subject}\n{body_html}\n{body_text}"
                otp = self._extract_otp(combined)

                if otp:
                    logger.info(
                        f"[AppleEmail] ✅ OTP={otp} from subject=\"{subject[:50]}\" sender={sender[:30] if sender else '(空)'} (poll={poll_count})"
                    )
                    return otp

                logger.warning(
                    f"[AppleEmail] OpenAI邮件未匹配到OTP (subject={subject[:50]})"
                )

            except Exception as e:
                logger.warning(f"[AppleEmail] 轮询异常（继续重试）: {e}")

            time.sleep(3)

        raise TimeoutError(f"[AppleEmail] 等待OTP超时 {timeout}s for {email_addr}")

    def _get_latest_mail(self) -> Optional[Dict]:
        """获取最新一封邮件"""
        if not self.current_account:
            raise RuntimeError("[AppleEmail] 未分配邮箱账号")

        # 优先查询INBOX
        for mailbox in ["INBOX", "Junk"]:
            try:
                resp = requests.post(
                    f"{self.api_url}/api/mail-new",
                    json={
                        "refresh_token": self.current_account.refresh_token,
                        "client_id": self.current_account.client_id,
                        "email": self.current_account.email,
                        "mailbox": mailbox,
                        "response_type": "json"
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=15
                )

                if resp.status_code == 200:
                    result = resp.json()
                    if result and result.get("code") == 200 and result.get("success"):
                        mail_data = result.get("data", {})
                        if mail_data:
                            return mail_data

            except Exception as e:
                logger.debug(f"[AppleEmail] 查询{mailbox}失败: {e}")
                continue

        return None

    def _extract_otp(self, text: str) -> str:
        """从邮件中提取6位验证码"""
        if not text:
            return ""

        # 强模式：关键字附近的6位数字
        strong_patterns = [
            r'(?:code|验证码|verification(?:\s+code)?|verify|one[-\s]*time\s+code)[^\d]{0,120}(\d{6})',
            r'-->\s*(\d{6})\s*<!--',
            r'>\s*(\d{6})\s*<',
        ]

        for pattern in strong_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        # 弱模式：所有6位数字，排除干扰
        for match in re.finditer(r'\d{6}', text):
            code = match.group(0)
            idx = match.start()

            prev = text[idx-1] if idx > 0 else ''
            next_char = text[idx+6] if idx+6 < len(text) else ''

            ctx = text[max(0, idx-80):min(len(text), idx+120)].lower()

            # 排除干扰
            if prev == '#':  # 颜色
                continue
            if 'http' in ctx or 'href=' in ctx or 'sendgrid' in ctx:  # URL
                continue
            if 'color:' in ctx or 'font-' in ctx or 'css' in ctx:  # CSS
                continue
            if re.search(r'[a-z]', prev, re.I) or re.search(r'[a-z]', next_char, re.I):  # 紧邻字母
                continue

            return code

        # 兜底
        match = re.search(r'\b(\d{6})\b', text)
        if match:
            code = match.group(1)
            if f't={code}' not in text and f'x={code}' not in text:
                return code

        return ""

    def cleanup(self):
        """清理资源"""
        if self.current_account and self.account_pool:
            self.account_pool.release_account(self.current_account)
            self.current_account = None


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 创建测试账号池文件
    test_pool = "outlook_pool_test.txt"
    with open(test_pool, 'w', encoding='utf-8') as f:
        f.write("# Outlook账号池\n")
        f.write("# 格式: 邮箱----密码----client_id----refresh_token\n")
        f.write("KoenJayson2253@outlook.com----tw591648----9e5f94bc-e8a4-4e73-b8be-63364c29d753----M.C545_SN1.0.U.MsaArtifacts.-Cl9OUlLXRCLIbMlfGZwlS0SrpHcX2vNEJl2Db62UdvimBNfROWWbVXdeGN0sQZeFnBwSafMvvXU7BaRqA2FgPtUvOGWzOTUOxJTNefVbjevw*F7UWF92b2CJgMfbqQIRSpxnyXsXVyo3hXsGh78KVPhTTkrE24*cGOzOQ4BmHVpMNIaYOObwfZQ!XSJQvs8wa9ULoBRPV4DanQOTTnA0BonjurrZhjfmAWzfSPrp9ccVt6QafPfjvO3LaBVRvZTNc1Ds78JHvUA5341As2QNNXOPb1lWanGme8Eez75h4Zpqyqn4VKp6PuJOKqRZba77XjHQuCwZDNXzV6PMM5jOQmHA692BZITmuhMkLj5PIxgfPu!uIFD19fCD!PpgNzROm1SpyOX3FCa5O1!p4kAP5WE58AYE2YN3uvLXfSX!zxt6Ox66kZy*UEaj0EQRH44AXw$$\n")

    print("\n" + "="*70)
    print(" Apple Email Provider 测试")
    print("="*70)
    print()

    # 创建账号池
    pool = OutlookAccountPool(test_pool)

    # 创建Provider
    provider = AppleEmailProvider(account_pool=pool)

    try:
        # 测试分配邮箱
        email = provider.create_mailbox()
        print(f"\n✅ 分配邮箱: {email}")
        print(f"   Client ID: {provider.current_account.client_id[:30]}...")
        print()

        # 测试获取最新邮件
        print("测试获取最新邮件...")
        mail = provider._get_latest_mail()
        if mail:
            print(f"✅ 获取到邮件:")
            print(f"   主题: {mail.get('subject', 'N/A')[:50]}")
            print(f"   ID: {str(mail.get('id', ''))[:30]}...")
        else:
            print("ℹ️  收件箱为空")

        print()
        print("="*70)
        print("✅ 测试通过！")
        print("="*70)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        provider.cleanup()
