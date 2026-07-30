"""ChatGPT Registration Flow - Full Protocol Implementation.

Based on gpt-outlook-register project's proven approach.
"""
from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlencode

from registrar.result import Result


def register(ctx):
    """Main registration flow - Correct OAuth initialization sequence."""

    # Step 1: Acquire phone number
    phone = ctx.run_step(
        "sms acquire",
        lambda: ctx.sms.acquire(
            service=ctx.settings.get("sms_service", "dr"),
            country=ctx.settings.get("phone_country", 73),
        )
    )

    # Step 2: Acquire proxy
    route = ctx.run_step(
        "proxy acquire",
        lambda: ctx.proxy.acquire(target="chatgpt", account=phone.number)
    )

    try:
        # Step 3: Initialize HTTP client with curl_cffi + fingerprint
        http_client = ctx.http.client(proxy_url=route.get("proxy_url", ""))

        # Step 4: Get CSRF token from ChatGPT (CRITICAL!)
        csrf_token = ctx.run_step(
            "get csrf token",
            lambda: get_csrf_token(ctx, http_client)
        )

        # Step 5: Get OAuth authorization URL (CRITICAL!)
        auth_url = ctx.run_step(
            "get auth url",
            lambda: get_auth_url(ctx, http_client, csrf_token)
        )

        # Step 6: Initialize OAuth session and get device_id (CRITICAL!)
        device_id = ctx.run_step(
            "init oauth session",
            lambda: init_oauth_session(ctx, http_client, auth_url)
        )

        # Step 7: Get sentinel token
        sentinel_token = ctx.run_step(
            "get sentinel",
            lambda: get_sentinel_token_for_signup(ctx, http_client, device_id)
        )

        # Step 8: Start phone signup
        signup_session = ctx.run_step(
            "phone signup",
            lambda: authorize_continue_signup(
                ctx, http_client, phone, device_id, sentinel_token
            )
        )

        # Step 9: Wait for SMS code
        sms_code = ctx.run_step(
            "wait sms",
            lambda: ctx.sms.get_code(phone, timeout=60)
        )

        # Step 10: Verify phone
        session = ctx.run_step(
            "verify phone",
            lambda: verify_phone_otp(
                ctx, http_client, signup_session, sms_code
            )
        )

        # Step 11: Create account (set password)
        account_created = ctx.run_step(
            "create account",
            lambda: register_password(
                ctx, http_client, session, device_id, sentinel_token
            )
        )

        # Step 10: Complete session
        result = ctx.run_step(
            "complete session",
            lambda: complete_auth_session(ctx, http_client, account_created)
        )

        # Release phone on success
        ctx.sms.release(phone, success=True)
        ctx.proxy.release(route, success=True)

        return result

    except Exception as e:
        ctx.logger.error(f"Registration failed: {e}")
        ctx.sms.release(phone, success=False)
        ctx.proxy.release(route, success=False)
        raise


def get_csrf_token(ctx, client) -> str:
    """Get CSRF token from ChatGPT - Step 1 of correct OAuth flow."""
    ctx.logger.info("Getting CSRF token from ChatGPT...")

    fp = ctx.http._fingerprint

    headers = {
        "Accept": "application/json",
        "Referer": "https://chatgpt.com/auth/login",
        "User-Agent": fp["user_agent"],
    }

    response = client.get(
        "https://chatgpt.com/api/auth/csrf",
        headers=headers,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to get CSRF token: {response.status_code}")

    csrf_token = response.json().get("csrfToken", "")

    if not csrf_token:
        raise RuntimeError("CSRF token not found in response")

    ctx.logger.info(f"CSRF token obtained: {csrf_token[:20]}...")

    return csrf_token


def get_auth_url(ctx, client, csrf_token: str) -> str:
    """Get OAuth authorization URL - Step 2 of correct OAuth flow."""
    ctx.logger.info("Getting OAuth authorization URL...")

    fp = ctx.http._fingerprint

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Referer": "https://chatgpt.com/auth/login",
        "Origin": "https://chatgpt.com",
        "User-Agent": fp["user_agent"],
    }

    data = {
        "csrfToken": csrf_token,
        "callbackUrl": "https://chatgpt.com/",
        "json": "true",
    }

    response = client.post(
        "https://chatgpt.com/api/auth/signin/openai",
        headers=headers,
        data=data,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to get auth URL: {response.status_code}")

    auth_url = response.json().get("url", "")

    if not auth_url:
        raise RuntimeError("Auth URL not found in response")

    ctx.logger.info(f"Auth URL obtained: {auth_url[:80]}...")

    return auth_url


def init_oauth_session(ctx, client, auth_url: str) -> str:
    """Initialize OAuth session and get device_id - Step 3 of correct OAuth flow."""
    ctx.logger.info("Initializing OAuth session...")

    fp = ctx.http._fingerprint

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://chatgpt.com/auth/login",
        "User-Agent": fp["user_agent"],
    }

    response = client.get(
        auth_url,
        headers=headers,
        allow_redirects=True
    )

    ctx.logger.info(f"OAuth init status: {response.status_code}")
    ctx.logger.info(f"Final URL: {response.url}")

    # Extract device_id from cookies
    device_id = ""
    try:
        cookies_dict = dict(client.cookies)
        device_id = cookies_dict.get("oai-did", "")
        ctx.logger.info(f"Cookies after OAuth init: {list(cookies_dict.keys())[:10]}")
    except Exception as e:
        ctx.logger.warning(f"Failed to get cookies: {e}")

    # Fallback: extract from HTML
    if not device_id:
        import re
        m = re.search(r'oai-did["\s:=]+([a-f0-9-]{36})', response.text)
        if m:
            device_id = m.group(1)

    # Last resort: generate
    if not device_id:
        import uuid
        device_id = str(uuid.uuid4())
        ctx.logger.warning(f"Generated device_id: {device_id}")

    ctx.logger.info(f"Device ID: {device_id}")

    return device_id


def init_session(ctx, client) -> tuple[str, str]:
    """Initialize session and get device_id - SIMPLIFIED VERSION."""

    # Skip chatgpt.com entirely - go direct to auth.openai.com!
    ctx.logger.info("Initializing session at auth.openai.com...")

    # Visit create-account page to get oai-did cookie
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://auth.openai.com/",
    }

    response = client.get(
        "https://auth.openai.com/create-account",
        headers=headers,
        allow_redirects=True
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to access create-account: {response.status_code}")

    ctx.logger.info(f"create-account page status: {response.status_code}")

    # Extract device_id from cookies (oai-did)
    device_id = ""

    try:
        cookies_dict = dict(client.cookies)
        device_id = cookies_dict.get("oai-did", "")
        ctx.logger.info(f"Cookies: {list(cookies_dict.keys())[:10]}")
    except Exception as e:
        ctx.logger.warning(f"Failed to get cookies: {e}")

    # Fallback: extract from HTML
    if not device_id:
        import re
        m = re.search(r'oai-did["\s:=]+([a-f0-9-]{36})', response.text)
        if m:
            device_id = m.group(1)

    # Last resort: generate
    if not device_id:
        import uuid
        device_id = str(uuid.uuid4())
        ctx.logger.warning(f"Generated device_id: {device_id}")

    ctx.logger.info(f"Device ID: {device_id}")

    # No CSRF token needed for direct auth.openai.com flow
    csrf_token = ""

    return device_id, csrf_token


def get_sentinel_token_for_signup(ctx, client, device_id: str) -> str:
    """Get sentinel token for signup flow."""
    from registrar.sentinel import get_sentinel_token

    # Get fingerprint from HttpService
    fp = ctx.http._fingerprint

    # CRITICAL: Use a SEPARATE client for sentinel to avoid cookie conflicts!
    # When we request sentinel token from sentinel.openai.com, it sets cookies
    # on that domain which conflict with auth.openai.com cookies.
    # Solution: Create a temporary client just for sentinel, then discard it.
    from curl_cffi.requests import Session
    sentinel_client = Session(impersonate=fp['impersonate'])

    ctx.logger.info("Getting sentinel token (using separate client)...")

    token = get_sentinel_token(
        sentinel_client,  # Use separate client!
        device_id=device_id,
        flow="authorize_continue",  # NOT username_password_create!
        user_agent=fp["user_agent"],
        screen=fp["screen"],
        lang=fp["lang"],
        lang_full=fp["lang_full"],
    )

    # Close the sentinel client to ensure no cookie leakage
    try:
        sentinel_client.close()
    except:
        pass

    if not token:
        raise RuntimeError("Failed to get sentinel token")

    ctx.logger.info(f"Sentinel token obtained: {len(token)} bytes")

    return token


def authorize_continue_signup(
    ctx, client, phone, device_id: str, sentinel_token: str
) -> dict[str, Any]:
    """Submit phone number for signup."""

    ctx.logger.info("Submitting phone number...")

    # Get fingerprint for headers
    fp = ctx.http._fingerprint

    # Build headers - CRITICAL: include oai-device-id!
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://auth.openai.com",
        "Referer": "https://auth.openai.com/create-account",
        "User-Agent": fp["user_agent"],
        "Accept-Language": fp["lang_full"],
        "openai-sentinel-token": sentinel_token,
        "oai-device-id": device_id,
    }

    # Add Datadog headers
    import random
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    trace_hex = format(int(trace_id), "016x")
    parent_hex = format(int(parent_id), "016x")
    headers.update({
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    })

    # Submit phone
    payload = {
        "username": {
            "value": f"+{phone.number}",
            "kind": "phone_number"
        },
        "screen_hint": "signup"
    }

    response = client.post(
        "https://auth.openai.com/api/accounts/authorize/continue",
        json=payload,
        headers=headers,
    )

    ctx.logger.info(f"authorize/continue status={response.status_code}")
    ctx.logger.info(f"authorize/continue response={response.text[:500]}")

    if response.status_code != 200:
        raise RuntimeError(f"authorize/continue failed: {response.status_code} {response.text[:500]}")

    data = response.json()

    # Check response
    page = data.get("page", {})
    page_type = page.get("type", "")

    if page_type != "phone_otp_verification":
        raise RuntimeError(f"Unexpected page_type: {page_type}")

    ctx.logger.info("Phone submitted, waiting for OTP")

    return {
        "device_id": device_id,
        "phone": phone.number,
        "page_data": data,
    }


def verify_phone_otp(
    ctx, client, session: dict[str, Any], code: str
) -> dict[str, Any]:
    """Verify phone with OTP code."""

    device_id = session.get("device_id", "")

    # Get fingerprint for headers
    fp = ctx.http._fingerprint

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://auth.openai.com",
        "Referer": "https://auth.openai.com/create-account",
        "User-Agent": fp["user_agent"],
        "Accept-Language": fp["lang_full"],
        "oai-device-id": device_id,
    }

    # Add Datadog headers
    import random
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    trace_hex = format(int(trace_id), "016x")
    parent_hex = format(int(parent_id), "016x")
    headers.update({
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    })

    ctx.logger.info(f"Verifying phone OTP: {code}")

    response = client.post(
        "https://auth.openai.com/api/accounts/phone-otp/validate",
        json={"code": code},
        headers=headers,
    )

    ctx.logger.info(f"verify_phone_otp status={response.status_code}")
    ctx.logger.info(f"verify_phone_otp response={response.text[:500]}")

    if response.status_code != 200:
        raise RuntimeError(f"verify_phone_otp failed: {response.status_code} {response.text[:500]}")

    data = response.json()

    # Check for continue_url or next step
    page = data.get("page", {})
    page_type = page.get("type", "")

    ctx.logger.info(f"Phone verified, page_type={page_type}")

    return {
        **session,
        "verified": True,
        "verify_data": data,
    }


def register_password(
    ctx, client, session: dict[str, Any], device_id: str, sentinel_token: str
) -> dict[str, Any]:
    """Register account with password."""

    # Generate password from phone
    password = f"Pass{session['phone'][:8]}!"

    # Get fingerprint for headers
    fp = ctx.http._fingerprint

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://auth.openai.com",
        "Referer": "https://auth.openai.com/create-account",
        "User-Agent": fp["user_agent"],
        "Accept-Language": fp["lang_full"],
        "oai-device-id": device_id,
    }

    # Add Datadog headers
    import random
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    trace_hex = format(int(trace_id), "016x")
    parent_hex = format(int(parent_id), "016x")
    headers.update({
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    })

    ctx.logger.info(f"Creating account with password")

    response = client.post(
        "https://auth.openai.com/api/accounts/password-continue",
        json={"password": password},
        headers=headers,
    )

    ctx.logger.info(f"register_password status={response.status_code}")
    ctx.logger.info(f"register_password response={response.text[:500]}")

    if response.status_code != 200:
        raise RuntimeError(f"register_password failed: {response.status_code} {response.text[:500]}")

    data = response.json()

    ctx.logger.info("Account created with password")

    return {
        **session,
        "password": password,
        "registered": True,
        "register_data": data,
    }


def complete_auth_session(ctx, client, session: dict[str, Any]) -> Result:
    """Complete authentication and get session token."""

    ctx.logger.info("Completing auth session...")

    # Extract session_token from cookies
    session_token = ""
    try:
        cookies_dict = dict(client.cookies)
        session_token = cookies_dict.get("__Secure-next-auth.session-token", "")
        ctx.logger.info(f"Cookies available: {list(cookies_dict.keys())[:10]}")
    except Exception as e:
        ctx.logger.warning(f"Failed to get cookies: {e}")

    # Try to get access_token from register_data
    access_token = ""
    register_data = session.get("register_data", {})
    if isinstance(register_data, dict):
        # Look for access_token in response
        access_token = register_data.get("access_token", "")

        # Or try to get from redirect URL
        redirect_url = register_data.get("redirect_url", "")
        if redirect_url:
            ctx.logger.info(f"Redirect URL: {redirect_url[:100]}...")

    # If no session_token, try to get it via /api/auth/session
    if not session_token:
        ctx.logger.info("Attempting to get session via /api/auth/session")
        try:
            fp = ctx.http._fingerprint
            session_resp = client.get(
                "https://chatgpt.com/api/auth/session",
                headers={"User-Agent": fp["user_agent"]},
                timeout=30
            )
            if session_resp.status_code == 200:
                session_data = session_resp.json()
                access_token = session_data.get("accessToken", access_token)
                ctx.logger.info(f"Session API response: {str(session_data)[:200]}")
        except Exception as e:
            ctx.logger.warning(f"Failed to get session: {e}")

    ctx.logger.info(f"Session token: {session_token[:30] if session_token else 'N/A'}...")
    ctx.logger.info(f"Access token: {access_token[:30] if access_token else 'N/A'}...")

    # Build result
    result = Result(ok=True)
    result.account = {
        "phone": f"+{session['phone']}",
        "password": session.get("password", "")
    }
    result.email = ""
    result.password = session.get("password", "")
    result.phone = f"+{session['phone']}"
    result.artifacts = {
        "device_id": session.get("device_id", ""),
        "session_token": session_token,
        "access_token": access_token,
    }

    return result
