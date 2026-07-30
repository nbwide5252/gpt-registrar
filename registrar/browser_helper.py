"""Hybrid browser helper - use puppeteer-real-browser to bypass Cloudflare."""
import subprocess
import json
import time
from pathlib import Path
from typing import Any


class BrowserHelper:
    """Use Node.js + puppeteer-real-browser to bypass Cloudflare."""

    def __init__(self, chrome_path: str = ""):
        self.chrome_path = chrome_path or "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

    def get_cookies(self, url: str = "https://chatgpt.com/", timeout: int = 30) -> dict[str, str]:
        """Launch browser, get cookies, then close."""

        # Create temporary Node.js script using puppeteer-real-browser
        script_content = """
const {{ connect }} = require('puppeteer-real-browser');

(async () => {{
    const {{ browser, page }} = await connect({{
        headless: false,
        turnstile: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
        executablePath: '{self.chrome_path.replace("\\", "\\\\")}'
    }});

    try {{
        console.log('Navigating to {url}...');
        await page.goto('{url}', {{ waitUntil: 'domcontentloaded', timeout: {timeout * 1000} }});

        // Wait for Cloudflare to pass
        await new Promise(resolve => setTimeout(resolve, 3000));

        const cookies = await page.cookies();
        console.log('COOKIES_START');
        console.log(JSON.stringify(cookies));
        console.log('COOKIES_END');

        await browser.close();
    }} catch (error) {{
        console.error('Error:', error.message);
        try {{ await browser.close(); }} catch(e) {{}}
        process.exit(1);
    }}
}})();
"""

        # Write script
        script_file = Path(__file__).parent.parent / "temp_get_cookies.js"
        script_file.write_text(script_content, encoding="utf-8")

        try:
            # Run Node.js script
            result = subprocess.run(
                ["node", str(script_file)],
                capture_output=True,
                text=True,
                timeout=timeout + 10,
                cwd=str(Path(__file__).parent.parent),
            )

            # Parse cookies
            output = result.stdout
            stderr = result.stderr

            if "COOKIES_START" in output:
                start = output.index("COOKIES_START") + len("COOKIES_START\n")
                end = output.index("COOKIES_END")
                cookies_json = output[start:end].strip()
                cookies_list = json.loads(cookies_json)

                # Convert to dict
                cookies_dict = {c["name"]: c["value"] for c in cookies_list}

                # Log cookies count
                print(f"[BrowserHelper] Got {len(cookies_dict)} cookies from {url}")
                for name in list(cookies_dict.keys())[:5]:
                    print(f"  - {name}: {cookies_dict[name][:20]}...")

                return cookies_dict

            # Show error details
            error_msg = f"stdout={output[:500]} stderr={stderr[:500]}"
            raise RuntimeError(f"Failed to get cookies: {error_msg}")

        finally:
            # Clean up
            if script_file.exists():
                script_file.unlink()

    def get_session_with_cookies(self, url: str = "https://chatgpt.com/") -> dict[str, Any]:
        """Get cookies and return as dict for httpx."""
        cookies = self.get_cookies(url)
        return {
            "cookies": cookies,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
