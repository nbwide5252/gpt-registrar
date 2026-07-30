"""Service adapters with curl_cffi TLS fingerprinting."""
from __future__ import annotations

import os
import logging
import time
from dataclasses import dataclass
from typing import Any

# Try curl_cffi first
try:
    from curl_cffi.requests import Session as CffiSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import httpx

from .fingerprint import generate_fingerprint


@dataclass
class Phone:
    """SMS phone number."""
    number: str
    activation_id: str = ""
    country: str = ""
    meta: dict[str, Any] | None = None


@dataclass
class Inbox:
    """Email inbox."""
    email: str
    password: str
    token: str = ""
    address_id: str = ""


class HttpService:
    """HTTP client with TLS fingerprinting (curl_cffi)."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._fingerprint = generate_fingerprint()
        self.logger.info(
            f"指纹: impersonate={self._fingerprint['impersonate']} "
            f"screen={self._fingerprint['screen']} lang={self._fingerprint['lang']}"
        )

    def client(self, proxy_url: str = "", headers: dict[str, str] | None = None):
        """Create HTTP client with TLS fingerprinting."""

        if HAS_CURL_CFFI:
            # Use curl_cffi with impersonate
            session = CffiSession(impersonate=self._fingerprint["impersonate"])
            session.trust_env = False

            # Set proxy
            if proxy_url:
                if proxy_url.startswith("socks5://"):
                    proxy_url = "socks5h://" + proxy_url[len("socks5://"):]
                session.proxies = {"https": proxy_url, "http": proxy_url}
            else:
                session.proxies = {"https": "", "http": ""}

            # Set headers
            default_headers = {
                "User-Agent": self._fingerprint["user_agent"],
                "Accept-Language": self._fingerprint["lang_full"],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            if headers:
                default_headers.update(headers)

            session.headers.update(default_headers)

            self.logger.info(f"✅ 使用 curl_cffi (impersonate={self._fingerprint['impersonate']})")
            return session

        else:
            # Fallback to httpx
            default_headers = {
                "User-Agent": self._fingerprint["user_agent"],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": self._fingerprint["lang_full"],
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            if headers:
                default_headers.update(headers)

            self.logger.warning("⚠️  curl_cffi 不可用，降级到 httpx")
            return httpx.Client(
                proxy=proxy_url or None,
                headers=default_headers,
                timeout=60,
                follow_redirects=True,
            )


class SmsService:
    """SMS service adapter (HeroSMS)."""

    def __init__(self, settings: dict[str, Any], logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self.base_url = "https://hero-sms.com/stubs/handler_api.php"

        # Support both api_key and api_key_env
        self.api_key = settings.get("api_key") or ""
        if not self.api_key:
            api_key_env = settings.get("api_key_env", "")
            if api_key_env:
                self.api_key = os.getenv(api_key_env, "")

    def acquire(self, service: str = "dr", country: int = 31, **opts: Any) -> Phone:
        self.logger.info("sms.acquire service=%s country=%s", service, country)

        params = {
            "api_key": self.api_key,
            "action": "getNumber",
            "service": service,
            "country": country,
        }

        operator = opts.get("operator")
        if operator:
            params["operator"] = operator

        if HAS_CURL_CFFI:
            session = CffiSession()
            response = session.get(self.base_url, params=params, timeout=30)
        else:
            import httpx
            response = httpx.get(self.base_url, params=params, timeout=30)

        response.raise_for_status()
        text = response.text.strip()

        if text.startswith("ACCESS_NUMBER"):
            parts = text.split(":")
            if len(parts) >= 3:
                activation_id = parts[1]
                phone_number = parts[2]
                self.logger.info("sms.acquire ok phone=%s activation_id=%s", phone_number, activation_id)
                return Phone(number=phone_number, activation_id=activation_id)

        raise RuntimeError(f"sms.acquire failed: {text}")

    def get_code(self, phone: Phone, timeout: int = 60) -> str:
        start = time.time()
        while time.time() - start < timeout:
            params = {
                "api_key": self.api_key,
                "action": "getStatus",
                "id": phone.activation_id,
            }

            if HAS_CURL_CFFI:
                session = CffiSession()
                response = session.get(self.base_url, params=params, timeout=30)
            else:
                import httpx
                response = httpx.get(self.base_url, params=params, timeout=30)

            response.raise_for_status()
            text = response.text.strip()

            if text.startswith("STATUS_OK"):
                code = text.split(":")[1] if ":" in text else text[10:]
                self.logger.info("sms.get_code ok code=%s", code)
                return code

            if text == "STATUS_CANCEL":
                raise RuntimeError("sms.get_code cancelled")

            time.sleep(5)

        raise TimeoutError(f"sms.get_code timeout after {timeout}s")

    def release(self, phone: Phone, success: bool = True):
        self.logger.info("sms.release phone=%s success=%s", phone.number, success)

        status = "6" if success else "8"
        params = {
            "api_key": self.api_key,
            "action": "setStatus",
            "status": status,
            "id": phone.activation_id,
        }

        try:
            if HAS_CURL_CFFI:
                session = CffiSession()
                session.get(self.base_url, params=params, timeout=10)
            else:
                import httpx
                httpx.get(self.base_url, params=params, timeout=10)
        except Exception:
            pass


class EmailService:
    """Email service adapter (CloudMail)."""

    def __init__(self, settings: dict[str, Any], logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self.base_url = str(settings.get("base_url", "")).rstrip("/")
        self.admin_email = settings.get("admin_email") or ""
        self.admin_password = settings.get("admin_password") or ""
        self.admin_token = settings.get("admin_token") or ""
        self.domains = settings.get("domains") or []

    def acquire(self, service: str = "chatgpt", **opts: Any) -> Inbox:
        self.logger.info("email.acquire service=%s", service)

        if not self.base_url:
            email = f"test{int(time.time())}@example.com"
            self.logger.info("email.acquire ok (mock) email=%s", email)
            return Inbox(email=email, password="TestPass123!")

        if not self.admin_token:
            self.admin_token = self._login()

        import random
        domain = random.choice(self.domains) if self.domains else "example.com"
        name = f"user{int(time.time() * 1000)}"
        suffix = f"@{domain}" if not domain.startswith("@") else domain
        email = f"{name}{suffix}"
        password = f"Pass{random.randint(100000, 999999)}!"

        if HAS_CURL_CFFI:
            session = CffiSession()
            response = session.post(
                f"{self.base_url}/api/user/add",
                json={
                    "email": email,
                    "suffix": suffix,
                    "password": password,
                    "type": 1,
                },
                headers={
                    "Authorization": self.admin_token,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        else:
            import httpx
            response = httpx.post(
                f"{self.base_url}/api/user/add",
                json={
                    "email": email,
                    "suffix": suffix,
                    "password": password,
                    "type": 1,
                },
                headers={
                    "Authorization": self.admin_token,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

        response.raise_for_status()

        if HAS_CURL_CFFI:
            login_response = session.post(
                f"{self.base_url}/api/login",
                json={"email": email, "password": password},
                timeout=30,
            )
        else:
            login_response = httpx.post(
                f"{self.base_url}/api/login",
                json={"email": email, "password": password},
                timeout=30,
            )

        login_response.raise_for_status()
        login_data = login_response.json()

        if isinstance(login_data, dict) and "data" in login_data:
            token = login_data["data"].get("token", "")
        else:
            token = login_data.get("token", "")

        self.logger.info("email.acquire ok email=%s", email)
        return Inbox(email=email, password=password, token=token, address_id="")

    def _login(self) -> str:
        self.logger.info("email.login start")

        if HAS_CURL_CFFI:
            session = CffiSession()
            response = session.post(
                f"{self.base_url}/api/login",
                json={"email": self.admin_email, "password": self.admin_password},
                timeout=30,
            )
        else:
            import httpx
            response = httpx.post(
                f"{self.base_url}/api/login",
                json={"email": self.admin_email, "password": self.admin_password},
                timeout=30,
            )

        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and "data" in data:
            token = data["data"].get("token", "")
        else:
            token = data.get("token", "")

        if not token:
            raise RuntimeError(f"CloudMail login failed: no token in response {data}")

        self.logger.info("email.login ok")
        return token

    def get_code(self, inbox: Inbox, timeout: int = 180) -> str:
        start = time.time()
        while time.time() - start < timeout:
            # Implementation omitted for brevity
            time.sleep(10)
        raise TimeoutError("email.get_code timeout")

    def release(self, inbox: Inbox, success: bool = True):
        self.logger.info("email.release email=%s success=%s", inbox.email, success)


class CaptchaService:
    """Captcha service adapter."""

    def __init__(self, settings: dict[str, Any], logger: logging.Logger):
        self.settings = settings
        self.logger = logger

    def solve(self, challenge: dict[str, Any]) -> str:
        self.logger.info("captcha.solve provider=none")
        return ""


class ProxyService:
    """Proxy service adapter."""

    def __init__(self, settings: dict[str, Any], logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self.provider = settings.get("provider", "none")

    def acquire(self, target: str = "", **opts: Any) -> dict[str, str]:
        self.logger.info("proxy.acquire provider=%s target=%s", self.provider, target)

        if self.provider == "static":
            return {"proxy_url": self.settings.get("static_url", "")}

        return {}

    def release(self, route: dict[str, str], success: bool = True):
        pass

    def failure(self, route: dict[str, str], reason: str = ""):
        self.logger.info("proxy.failure reason=%s", reason)


def build_services(config: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    """Build all services."""
    return {
        "http": HttpService(logger),
        "sms": SmsService(config.get("sms", {}), logger),
        "email": EmailService(config.get("email", {}), logger),
        "captcha": CaptchaService(config.get("captcha", {}), logger),
        "proxy": ProxyService(config.get("proxy", {}), logger),
    }
