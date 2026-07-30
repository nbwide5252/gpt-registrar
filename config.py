"""
配置 - 域名邮箱 + SMS
"""
import os

MAIL_PROVIDER = "cloudflare"
CF_MAIL_DOMAIN = "zhidexiu.com"
CF_MAIL_API_URL = "https://zhidexiu-mail.ppu2812859729.workers.dev"

os.environ["MAIL_PROVIDER"] = MAIL_PROVIDER
os.environ["CF_MAIL_DOMAIN"] = CF_MAIL_DOMAIN
os.environ["CF_MAIL_API_URL"] = CF_MAIL_API_URL

HEROSMS_API_KEY = "f5ebbcdA48f70A3d3950631A44ce9b5e"
os.environ["HEROSMS_API_KEY"] = HEROSMS_API_KEY

print("配置已加载")
print("  邮箱: zhidexiu.com (cloudflare)")
print("  Worker: https://zhidexiu-mail.ppu2812859729.workers.dev")
