"""
完整OpenAI注册+获取Token
全新手写版本，支持多平台SMS和Token保存
"""
import asyncio
import random
import secrets
import string
import json
import base64
import hashlib
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, parse_qs
from curl_cffi.requests import AsyncSession, Session
from cloudflare_mail_provider import CloudflareMailProvider
from registrar.fingerprint import generate_fingerprint
from sentinel import get_sentinel_token
import logging

logging.basicConfig(level=logging.INFO)

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

USED_OTPS = set()


def load_sms_config():
    """加载SMS多平台配置"""
    config_file = Path("sms_providers_config.json")
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def create_multi_sms_service():
    """创建多平台SMS服务"""
    config = load_sms_config()

    if not config:
        logging.warning("未找到sms_providers_config.json，使用默认HeroSMS配置")
        from sms_service import HeroSMSService
        return HeroSMSService(api_key="f5ebbcdA48f70A3d3950631A44ce9b5e")

    providers_config = config.get("sms_providers", {})
    max_price = None
    if config.get("price_filter_enabled", False):
        max_price = config.get("max_price")
        if max_price is not None:
            logging.info(f"💰 已启用价格筛选: 最高 ${max_price:.4f}")

    provider_list = []
    for name, cfg in providers_config.items():
        if not cfg.get("enabled"):
            continue
        api_key = cfg.get("api_key")
        service_code = cfg.get("service_code", "dr")
        priority = cfg.get("priority", 99)
        if not api_key:
            continue
        if name == "herosms":
            from multi_sms_provider import HeroSMSProvider
            provider_list.append((priority, HeroSMSProvider(api_key, service_code)))
        elif name == "smsbower":
            from multi_sms_provider import SMSBowerProvider
            provider_list.append((priority, SMSBowerProvider(api_key, service_code)))

    if not provider_list:
        raise ValueError("没有启用的SMS平台")

    provider_list.sort(key=lambda x: x[0])
    providers = [p for _, p in provider_list]
    from multi_sms_provider import MultiProviderSMS
    return MultiProviderSMS(providers, max_price=max_price)


def generate_datadog_headers():
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    return {
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    }


def generate_password():
    """生成随机强密码"""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(chars) for _ in range(16))
    return password


async def full_registration_with_token(sms_country: str = "52"):
    """
    完整注册流程 + 获取Token

    Args:
        sms_country: SMS接码国家代码（默认52=泰国）

    Returns:
        Token数据字典，失败返回None
    """
    mail_provider = CloudflareMailProvider()
    test_email = mail_provider.create_mailbox()
    registration_success = False

    try:
        print("⏳ 初始化SMS接码服务...")
        sms_service = create_multi_sms_service()

        if hasattr(sms_service, 'providers'):
            platforms = [p.provider_name for p in sms_service.providers]
            print(f"✅ 已加载 {len(platforms)} 个平台: {', '.join(platforms)}")
        else:
            print(f"✅ 使用单平台模式")

        print(f"\n{'='*70}")
        print(f"🚀 完整注册流程 + Token获取")
        print(f"邮箱: {test_email}")
        print(f"SMS国家: {sms_country}")
        print(f"{'='*70}\n")

        fp = generate_fingerprint()

        # WARP SOCKS5 proxy
        proxy_url = os.environ.get("WARP_PROXY", "")
        if not proxy_url:
            import json as _json
            try:
                with open("config.json", "r", encoding="utf-8") as _f:
                    _cfg = _json.load(_f)
                if _cfg.get("proxyHost") and _cfg.get("proxyPort"):
                    _host = _cfg["proxyHost"]
                    _port = _cfg["proxyPort"]
                    proxy_url = f"socks5://{_host}:{_port}"
            except:
                pass
        if proxy_url:
            print(f"  Proxy: {proxy_url}")
            session = AsyncSession(impersonate=fp["impersonate"], proxies={"http": proxy_url, "https": proxy_url})
            sync_session = Session(impersonate=fp["impersonate"], proxies={"http": proxy_url, "https": proxy_url})
        else:
            session = AsyncSession(impersonate=fp["impersonate"])
            sync_session = Session(impersonate=fp["impersonate"])

        # PKCE
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')

        client_id = "app_EMoamEEZ73f0CkXaXp7hrann"
        redirect_uri = "http://localhost:1455/auth/callback"
        state = secrets.token_hex(16)

        params = {
            "client_id": client_id,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile offline_access",
            "state": state,
            "prompt": "login",
            "codex_cli_simplified_flow": "true",
            "id_token_add_organizations": "true"
        }

        auth_url = f"https://auth.openai.com/oauth/authorize?{urlencode(params)}"

        # 步骤1: OAuth初始化
        print("步骤1: OAuth初始化")
        resp = await session.get(auth_url, timeout=30, allow_redirects=True)
        device_id = session.cookies.get("oai-did", "")
        print(f"Device ID: {device_id}\n")

        # 步骤2: Sentinel
        print("步骤2: Sentinel Token")
        sentinel = get_sentinel_token(
            sync_session, device_id=device_id, flow="authorize_continue",
            user_agent=fp["user_agent"], sec_ch_ua=fp["sec_ch_ua"],
            screen=fp["screen"], lang=fp["lang"], lang_full=fp["lang_full"]
        )
        print(f"Token: {sentinel[:50] if sentinel else 'None'}...\n")

        # 步骤3: 提交邮箱
        print("步骤3: 提交邮箱")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "https://auth.openai.com/",
            "Origin": "https://auth.openai.com",
            "oai-device-id": device_id,
            **generate_datadog_headers()
        }
        if sentinel and len(sentinel) > 100:
            headers["openai-sentinel-token"] = sentinel

        auth_resp = await session.post(
            "https://auth.openai.com/api/accounts/authorize/continue",
            headers=headers,
            json={"username": {"value": test_email, "kind": "email"}, "screen_hint": "signup"},
            timeout=30
        )
        print(f"Status: {auth_resp.status_code}\n")

        if auth_resp.status_code != 200:
            print(f"❌ 提交邮箱失败")
            return None

        print("⏳ 等待3秒...")
        await asyncio.sleep(3)

        # 步骤4: 设置密码
        print("步骤4: 设置密码")
        password = generate_password()
        print(f"密码: {password}")

        pw_headers = {**headers, "Referer": "https://auth.openai.com/create-account/password"}
        pw_resp = await session.post(
            "https://auth.openai.com/api/accounts/user/register",
            headers=pw_headers,
            json={"password": password, "username": test_email},
            timeout=30
        )
        print(f"Status: {pw_resp.status_code}\n")

        if pw_resp.status_code != 200:
            print(f"❌ 密码注册失败")
            return None

        # 步骤5: 发送邮箱OTP
        print("步骤5: 发送邮箱OTP")
        otp_send_resp = await session.post(
            "https://auth.openai.com/api/accounts/email-otp/send",
            headers={**headers, "Referer": "https://auth.openai.com/email-verification"},
            json={},
            timeout=30
        )
        print(f"Status: {otp_send_resp.status_code}\n")

        if otp_send_resp.status_code != 200:
            print(f"❌ 发送OTP失败")
            return None

        # 步骤6: 获取OTP
        print("步骤6: 获取邮箱OTP")
        otp = None
        try:
            temp = mail_provider.wait_for_otp(test_email, timeout=120)
            if temp and temp not in USED_OTPS:
                otp = temp
                USED_OTPS.add(otp)
        except Exception as e:
            print(f"⚠️ 获取OTP失败: {e}")

        if not otp:
            print(f"❌ 未收到OTP")
            return None

        print(f"OTP: {otp}\n")

        # 步骤7: 验证OTP
        print("步骤7: 验证邮箱OTP")
        otp_resp = await session.post(
            "https://auth.openai.com/api/accounts/email-otp/validate",
            headers={**headers, "Referer": "https://auth.openai.com/email-verification"},
            json={"code": otp},
            timeout=30
        )
        print(f"Status: {otp_resp.status_code}\n")

        if otp_resp.status_code != 200:
            print(f"❌ OTP验证失败: {otp_resp.status_code}")
            try:
                error_data = otp_resp.json()
                print(f"   错误详情: {error_data}")
            except:
                print(f"   响应: {otp_resp.text[:200]}")
            return None

        # 步骤8: SMS验证
        print("步骤8: SMS验证")
        phone = None
        sms_success = False

        # 重试计数：只计算验证码相关的失败
        verification_attempts = 0
        max_verification_attempts = 5

        while verification_attempts < max_verification_attempts:
            verification_attempts += 1
            print(f"\n验证尝试 #{verification_attempts}/{max_verification_attempts}")

            if verification_attempts > 1:
                await asyncio.sleep(3)

            try:
                phone_info = sms_service.get_number(country=sms_country)
            except Exception as e:
                print(f"❌ 获取号码失败: {e}")
                verification_attempts -= 1  # 不计入尝试次数
                await asyncio.sleep(3)
                continue

            if not phone_info:
                print(f"❌ 无可用号码，等待后重试...")
                verification_attempts -= 1  # 不计入尝试次数
                await asyncio.sleep(5)
                continue

            phone = phone_info.number
            print(f"Phone: {phone}")

            # 为SMS操作获取新的sentinel token
            print("获取新的Sentinel Token...")
            sentinel_sms = get_sentinel_token(
                session, device_id=device_id, flow="add_phone",
                user_agent=fp["user_agent"], sec_ch_ua=fp["sec_ch_ua"],
                screen=fp["screen"], lang=fp["lang"], lang_full=fp["lang_full"]
            )

            # 准备SMS请求的headers
            sms_headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "https://auth.openai.com/add-phone",
                "Origin": "https://auth.openai.com",
                "oai-device-id": device_id,
                **generate_datadog_headers()
            }
            if sentinel_sms and len(sentinel_sms) > 100:
                sms_headers["openai-sentinel-token"] = sentinel_sms

            sms_resp = await session.post(
                "https://auth.openai.com/api/accounts/add-phone/send",
                headers=sms_headers,
                json={"phone_number": phone},
                timeout=30
            )
            print(f"SMS发送: {sms_resp.status_code}")

            if sms_resp.status_code != 200:
                print(f"❌ SMS发送失败: {sms_resp.status_code}")
                try:
                    error_data = sms_resp.json()
                    print(f"   错误详情: {error_data}")
                except:
                    print(f"   响应: {sms_resp.text[:200]}")

                # 取消号码
                print(f"   正在取消号码...")
                try:
                    cancel_success = sms_service.cancel_number(phone_info.id)
                    if cancel_success:
                        print(f"   ✅ 号码已取消，余额已退还")
                    else:
                        print(f"   ⚠️  取消失败")
                except Exception as e:
                    print(f"   ⚠️  取消异常: {e}")

                # SMS发送失败（400/403等）不计入验证尝试次数
                # 因为这是OpenAI拒绝该号码，不是验证失败
                verification_attempts -= 1
                print(f"   💡 号码被拒绝，不计入尝试次数，继续换号")
                continue

            print("等待SMS验证码（20秒）...")
            sms_code = sms_service.get_code(phone_info.id, timeout=20)

            if not sms_code:
                print(f"❌ 未收到验证码（计入尝试次数）")
                print(f"   正在取消号码并退款...")

                # 尝试取消号码
                cancel_success = False
                try:
                    cancel_success = sms_service.cancel_number(phone_info.id)
                    if cancel_success:
                        print(f"   ✅ 号码已取消，余额已退还")
                    else:
                        print(f"   ⚠️  取消失败（可能已过取消期限）")
                except Exception as e:
                    print(f"   ⚠️  取消异常: {e}")

                # 未收到验证码：这是真正的失败，计入尝试次数
                continue

            print(f"✅ SMS: {sms_code}")

            # 准备验证请求的headers
            validate_headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "https://auth.openai.com/phone-verification",
                "Origin": "https://auth.openai.com",
                "oai-device-id": device_id,
                **generate_datadog_headers()
            }

            validate_resp = await session.post(
                "https://auth.openai.com/api/accounts/phone-otp/validate",
                headers=validate_headers,
                json={"code": sms_code},
                timeout=30
            )
            print(f"SMS验证: {validate_resp.status_code}")

            if validate_resp.status_code == 200:
                print("✅ SMS验证成功!\n")
                sms_success = True
                break
            else:
                print(f"❌ SMS验证失败: {validate_resp.status_code}（计入尝试次数）")
                # 验证失败：这是真正的失败，计入尝试次数
                continue

        if not sms_success:
            print(f"\n❌ SMS验证失败，已尝试 {verification_attempts} 次")
            return None

        # 步骤8.5: 创建账户
        print("步骤8.5: 创建账户（填写用户信息）")
        names = ["James Smith", "John Johnson", "Robert Williams", "Michael Brown",
                 "William Davis", "David Miller", "Richard Wilson", "Joseph Moore"]
        name = random.choice(names)
        birthdate = f"{random.randint(1985, 2000)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
        print(f"姓名: {name}, 生日: {birthdate}")

        # 获取create_account的Sentinel Token
        sentinel_create = get_sentinel_token(
            session, device_id=device_id, flow="create_account",
            user_agent=fp["user_agent"], sec_ch_ua=fp["sec_ch_ua"],
            screen=fp["screen"], lang=fp["lang"], lang_full=fp["lang_full"]
        )

        # 调用create_account API
        create_resp = await session.post(
            "https://auth.openai.com/api/accounts/create_account",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "https://auth.openai.com/about-you",
                "Origin": "https://auth.openai.com",
                "oai-device-id": device_id,
                "openai-sentinel-token": sentinel_create,
                **generate_datadog_headers()
            },
            json={"name": name, "birthdate": birthdate},
            timeout=30
        )

        print(f"Status: {create_resp.status_code}")

        if create_resp.status_code != 200:
            print(f"❌ 创建账户失败")
            try:
                error_data = create_resp.json()
                print(f"   错误详情: {error_data}")
            except:
                print(f"   响应: {create_resp.text[:200]}")
            return None

        # 🔑 关键：获取 continue_url
        create_data = create_resp.json()
        continue_url = create_data.get("continue_url", "")
        print(f"Continue URL: {continue_url[:100]}...\n")

        if not continue_url:
            print("❌ 未获取到continue_url")
            return None

        # 步骤9: 获取callback URL
        print("步骤9: 跟随重定向获取OAuth callback")

        # 首先提取workspace_id（关键步骤！）
        workspace_id = None
        try:
            import json
            auth_session_cookie = session.cookies.get("oai-client-auth-session", "")
            if auth_session_cookie:
                print("尝试从cookie提取workspace_id...")
                parts = auth_session_cookie.split(".")
                for part in parts[:2]:
                    if part:
                        try:
                            payload_b64 = part + "=" * (-len(part) % 4)
                            payload_str = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
                            payload_json = json.loads(payload_str)
                            workspace_id = (
                                payload_json.get("workspace_id") or
                                payload_json.get("workspace", {}).get("id") or
                                (payload_json.get("workspaces", [{}])[0].get("id") if payload_json.get("workspaces") else None)
                            )
                            if workspace_id:
                                print(f"✅ 提取到workspace_id: {workspace_id}\n")
                                break
                        except:
                            pass
        except Exception as e:
            print(f"⚠️ 提取workspace_id失败: {e}\n")

        # 从 continue_url 开始跟随重定向链
        current = continue_url
        callback_url = None
        workspace_selected = False  # 只选择一次workspace

        for i in range(20):
            if i % 5 == 0:
                print(f"跟随重定向 #{i+1}...")

            # 检查是否到达callback
            if redirect_uri in current and "code=" in current:
                callback_url = current
                print(f"✅ 找到callback!\n")
                break

            # 检查是否是error页面
            if "/error" in current:
                print(f"❌ 重定向到错误页面")
                # 尝试解析error payload
                try:
                    if "payload=" in current:
                        payload_b64 = current.split("payload=")[1].split("&")[0]
                        payload_b64 += "=" * (-len(payload_b64) % 4)
                        error_json = json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
                        print(f"错误详情: {error_json}")
                except:
                    pass
                break

            try:
                # 关键：检查是否是codex/consent页面，需要POST选择workspace
                if not workspace_selected and "/codex/consent" in current and workspace_id:
                    print(f"检测到codex/consent页面，POST选择workspace...")
                    workspace_resp = await session.post(
                        "https://auth.openai.com/api/accounts/workspace/select",
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "Referer": current,
                            "Origin": "https://auth.openai.com",
                            "oai-device-id": device_id,
                            **generate_datadog_headers()
                        },
                        json={"workspace_id": workspace_id},
                        timeout=30
                    )
                    print(f"Status: {workspace_resp.status_code}")
                    workspace_selected = True  # 标记已选择

                    if workspace_resp.status_code == 200:
                        ws_data = workspace_resp.json()
                        next_url = ws_data.get("continue_url", "")
                        if next_url:
                            print(f"✅ 获取到continue_url\n")
                            current = next_url if next_url.startswith("http") else f"https://auth.openai.com{next_url}"
                            await asyncio.sleep(0.5)
                            continue
                    else:
                        print(f"⚠️ workspace选择失败\n")

                # 尝试GET当前URL
                resp = await session.get(current, timeout=30, allow_redirects=False)

                # 检查重定向
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    if location:
                        # 检查重定向目标是否是callback
                        if redirect_uri in location and "code=" in location:
                            callback_url = location
                            print(f"✅ 找到callback!\n")
                            break
                        # 继续跟随
                        current = location if location.startswith("http") else f"https://auth.openai.com{location}"
                    else:
                        print(f"❌ 重定向但无Location")
                        break
                elif resp.status_code == 200:
                    # 200响应：可能是包含自动跳转的HTML页面
                    print(f"200响应，检查页面内容...")

                    # 尝试从HTML中查找可能的跳转URL
                    try:
                        html_content = resp.text

                        # 检查是否有callback code在URL中（虽然是200，但可能已经到了callback页面）
                        if redirect_uri in resp.url and "code=" in resp.url:
                            callback_url = str(resp.url)
                            print(f"✅ 在200响应的URL中找到callback!")
                            break

                        # 查找JavaScript跳转
                        js_redirect = re.search(r'window\.location\s*=\s*[\'"]([^\'"]+)[\'"]', html_content)
                        if not js_redirect:
                            js_redirect = re.search(r'window\.location\.href\s*=\s*[\'"]([^\'"]+)[\'"]', html_content)
                        if not js_redirect:
                            js_redirect = re.search(r'window\.location\.replace\([\'"]([^\'"]+)[\'"]\)', html_content)

                        if js_redirect:
                            next_url = js_redirect.group(1)
                            print(f"找到JavaScript跳转: {next_url[:80]}...")
                            current = next_url if next_url.startswith("http") else f"https://auth.openai.com{next_url}"
                            await asyncio.sleep(0.5)
                            continue

                        # 查找meta refresh
                        meta_refresh = re.search(r'<meta[^>]*http-equiv=[\'"]refresh[\'"][^>]*content=[\'"]0;\s*url=([^\'"]+)[\'"]', html_content, re.IGNORECASE)
                        if meta_refresh:
                            next_url = meta_refresh.group(1)
                            print(f"找到meta refresh: {next_url[:80]}...")
                            current = next_url if next_url.startswith("http") else f"https://auth.openai.com{next_url}"
                            await asyncio.sleep(0.5)
                            continue
                    except:
                        pass

                    # 如果都没找到，可能真的到达终点了
                    print(f"未找到跳转，停止")
                    break
                else:
                    print(f"状态码 {resp.status_code}，停止")
                    break

            except Exception as e:
                print(f"⚠️ 跟随重定向异常: {e}")
                break

            await asyncio.sleep(0.5)

        # 检查是否成功获取callback_url
        if not callback_url:
            print("\n❌ 未获取到callback code")
            print("   可能原因:")
            print("   1. workspace_id提取失败")
            print("   2. 重定向链中断")
            print("   3. 需要额外的验证步骤\n")
            return None

        # 步骤10: 交换Token
        if callback_url and "code=" in callback_url:
            print("步骤10: 交换Token")

            parsed = urlparse(callback_url)
            query = parse_qs(parsed.query)
            auth_code = query.get("code", [None])[0]

            if auth_code:
                print(f"Code: {auth_code[:30]}...\n")

                token_resp = await session.post(
                    "https://auth.openai.com/oauth/token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "client_id": client_id,
                        "code": auth_code,
                        "code_verifier": code_verifier,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri
                    },
                    timeout=30
                )

                print(f"Token交换: {token_resp.status_code}")

                if token_resp.status_code == 200:
                    tokens = token_resp.json()
                    print("✅ Token获取成功!\n")

                    # 保存Token
                    outputs_dir = Path("outputs/tokens")
                    outputs_dir.mkdir(parents=True, exist_ok=True)

                    email_prefix = test_email.split('@')[0]
                    filename = f"codex-{email_prefix}-free.json"
                    full_filename = outputs_dir / filename

                    # 解析account_id
                    account_id = ""
                    expires_at = 0
                    access_token = tokens.get("access_token", "")
                    if access_token:
                        try:
                            parts = access_token.split('.')
                            if len(parts) > 1:
                                payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
                                payload_str = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
                                payload = json.loads(payload_str)
                                auth_info = payload.get("https://api.openai.com/auth", {})
                                account_id = auth_info.get("chatgpt_account_id", "")
                                expires_at = int(payload.get("exp") or 0)
                        except:
                            pass

                    # 保存文件
                    with open(full_filename, 'w', encoding='utf-8') as f:
                        json.dump({
                            "email": test_email,
                            "password": password,
                            "phone": phone,
                            "account_id": account_id,
                            "access_token": tokens.get("access_token", ""),
                            "refresh_token": tokens.get("refresh_token", ""),
                            "id_token": tokens.get("id_token", ""),
                            "expires_in": tokens.get("expires_in", 0),
                            "expires_at": expires_at,
                            "expired": datetime.fromtimestamp(expires_at, timezone.utc).isoformat().replace("+00:00", "Z") if expires_at else "",
                            "type": "free",
                            "client_id": client_id,
                            "created_at": datetime.now().isoformat()
                        }, f, indent=2, ensure_ascii=False)

                    print(f"✅ Token已保存: {full_filename}\n")

                    # 追加到汇总
                    summary_file = Path("outputs/accounts_summary.txt")
                    with open(summary_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n{'='*70}\n")
                        f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"邮箱: {test_email}\n")
                        f.write(f"密码: {password}\n")
                        f.write(f"手机: {phone}\n")
                        f.write(f"Account ID: {account_id}\n")
                        f.write(f"文件: {filename}\n")

                    registration_success = True
                    return tokens

        print("\n✅ 注册成功（未获取Token）")
        registration_success = True
        return {"email": test_email, "password": password, "phone": phone}

    finally:
        # 关闭 HTTP sessions
        try:
            sync_session.close()
        except:
            pass
        try:
            await session.close()
        except:
            pass
        if registration_success:
            print(f"💾 邮箱 {test_email} 已永久使用")
        else:
            if mail_provider:
                try:
                    mail_provider.release(test_email)
                    print(f"♻️ 邮箱 {test_email} 已释放")
                except:
                    pass


if __name__ == "__main__":
    result = asyncio.run(full_registration_with_token(sms_country="52"))
    if result:
        print("\n🎉 注册完成!")
    else:
        print("\n❌ 注册失败")
