"""
Hybrid Registration Flow - FINAL VERSION
Browser initialization + Protocol for everything else
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


async def init_session_with_browser(ctx) -> dict[str, str]:
    """
    Use browser to initialize session and get cookies.
    This is the ONLY part that uses browser!
    """
    ctx.logger.info("🌐 Initializing session with browser...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )

        try:
            page = await browser.new_page()

            # Set user agent
            fp = ctx.http._fingerprint
            await page.set_extra_http_headers({
                'User-Agent': fp['user_agent'],
                'Accept-Language': fp['lang_full'],
            })

            ctx.logger.info("Visiting create-account page...")

            # Navigate to create-account
            await page.goto(
                'https://auth.openai.com/create-account',
                wait_until='networkidle',
                timeout=30000
            )

            ctx.logger.info("Page loaded, extracting cookies...")

            # Get all cookies
            cookies = await page.context.cookies()

            # Convert to dict
            cookie_dict = {}
            for c in cookies:
                cookie_dict[c['name']] = c['value']

            device_id = cookie_dict.get('oai-did', '')

            ctx.logger.info(f"Device ID: {device_id}")
            ctx.logger.info(f"Cookies obtained: {list(cookie_dict.keys())}")

            return cookie_dict

        finally:
            await browser.close()


def register_hybrid(ctx):
    """
    Hybrid registration flow:
    - Browser: Session initialization (get cookies)
    - Protocol: Everything else (sentinel, phone, OTP)
    """
    from registrar.result import Result

    # ===== PHASE 1: Browser Initialization =====
    ctx.logger.info("=" * 60)
    ctx.logger.info("PHASE 1: Browser Initialization")
    ctx.logger.info("=" * 60)

    try:
        cookies = asyncio.run(init_session_with_browser(ctx))
    except Exception as e:
        ctx.logger.error(f"Browser init failed: {e}")
        raise RuntimeError(f"Browser initialization failed: {e}")

    device_id = cookies.get('oai-did', '')
    if not device_id:
        raise RuntimeError("Failed to get device_id from browser")

    # ===== PHASE 2: Switch to Protocol =====
    ctx.logger.info("\n" + "=" * 60)
    ctx.logger.info("PHASE 2: Protocol (Sentinel + Phone + OTP)")
    ctx.logger.info("=" * 60)

    client = ctx.http.client

    # Import cookies to curl_cffi session
    for name, value in cookies.items():
        # Set for both domains
        client.cookies.set(name, value, domain='.openai.com')
        client.cookies.set(name, value, domain='auth.openai.com')

    ctx.logger.info(f"✅ Imported {len(cookies)} cookies to protocol session")

    # Get sentinel token (PROTOCOL)
    ctx.logger.info("\n[Step 1/4] Getting sentinel token...")

    from registrar.sentinel import get_sentinel_token

    fp = ctx.http._fingerprint

    sentinel_token = get_sentinel_token(
        client,
        device_id=device_id,
        flow="authorize_continue",
        user_agent=fp["user_agent"],
        screen=fp["screen"],
        lang=fp["lang"],
        lang_full=fp["lang_full"],
    )

    if not sentinel_token:
        raise RuntimeError("Failed to get sentinel token")

    ctx.logger.info(f"✅ Sentinel token: {len(sentinel_token)} bytes")

    # Submit phone (PROTOCOL)
    phone = ctx.phone

    ctx.logger.info(f"\n[Step 2/4] Submitting phone: +{phone.number}")

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
        timeout=30,
    )

    ctx.logger.info(f"Response status: {response.status_code}")

    if response.status_code != 200:
        ctx.logger.error(f"Response: {response.text[:500]}")
        raise RuntimeError(f"Phone signup failed: {response.status_code}")

    try:
        data = response.json()
    except:
        ctx.logger.error(f"Response is not JSON: {response.text[:300]}")
        raise RuntimeError("Response is not JSON")

    # Check page type
    page = data.get("page", {})
    page_type = page.get("type", "")

    ctx.logger.info(f"Page type: {page_type}")

    if page_type != "phone_otp_verification":
        ctx.logger.error(f"Unexpected page type: {page_type}")
        ctx.logger.error(f"Full response: {json.dumps(data, indent=2)[:500]}")
        raise RuntimeError(f"Unexpected page_type: {page_type}")

    ctx.logger.info("✅ Phone submitted successfully!")

    # Wait for OTP (PROTOCOL)
    ctx.logger.info(f"\n[Step 3/4] Waiting for OTP...")

    try:
        code = phone.wait_code(timeout=120)
    except Exception as e:
        ctx.logger.error(f"Failed to get OTP: {e}")
        raise

    ctx.logger.info(f"✅ Got OTP: {code}")

    # Verify OTP (PROTOCOL)
    ctx.logger.info(f"\n[Step 4/4] Verifying OTP...")

    response = client.post(
        "https://auth.openai.com/api/accounts/authorize/continue",
        json={"code": code},
        headers=headers,
        timeout=30,
    )

    if response.status_code != 200:
        ctx.logger.error(f"OTP verification failed: {response.status_code}")
        ctx.logger.error(f"Response: {response.text[:500]}")
        raise RuntimeError(f"OTP verification failed: {response.status_code}")

    ctx.logger.info("✅ OTP verified!")

    try:
        data = response.json()
        ctx.logger.info(f"Response: {json.dumps(data, indent=2)[:300]}")
    except:
        pass

    # ===== SUCCESS =====
    ctx.logger.info("\n" + "=" * 60)
    ctx.logger.info("🎉 REGISTRATION SUCCESSFUL! 🎉")
    ctx.logger.info("=" * 60)

    result = Result(ok=True)
    result.account = {"phone": f"+{phone.number}"}
    result.phone = f"+{phone.number}"
    result.artifacts = {
        "device_id": device_id,
        "cookies": cookies,
    }

    return result
