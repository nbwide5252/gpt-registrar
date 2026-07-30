import os,json,time,random as _r
from datetime import datetime

class AntiDetect:
    _PROFILES = [
        {'ua':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15','imp':'safari17_0','screen':'1728x1117','lang':'en-US,en;q=0.9','platform':'MacIntel'},
        {'ua':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15','imp':'safari16_0','screen':'1512x982','lang':'en-US,en;q=0.9,zh-CN;q=0.8','platform':'MacIntel'},
        {'ua':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36','imp':'chrome124','screen':'1920x1080','lang':'en-US,en;q=0.9','platform':'Win32'},
        {'ua':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36','imp':'chrome126','screen':'2560x1440','lang':'en-GB,en;q=0.9','platform':'Win32'},
        {'ua':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36','imp':'chrome125','screen':'1920x1080','lang':'en-US,en;q=0.9,ja;q=0.8','platform':'Linux x86_64'},
    ]

    @staticmethod
    def random_profile():
        p=_r.choice(AntiDetect._PROFILES)
        w,h=map(int,p['screen'].split('x'))
        return {
            'impersonate':p['imp'],'user_agent':p['ua'],
            'screen':p['screen'],'viewport_width':w,'viewport_height':h,
            'lang':p['lang'].split(',')[0],'lang_full':p['lang'],
            'platform':p['platform'],'sec_ch_ua':'',
            'sec_ch_ua_platform':'','sec_ch_ua_mobile':''
        }

    @staticmethod
    def human_delay(fast=False):
        import time,math
        if fast:mu,sigma=0.5,0.3
        else:mu,sigma=2.0,1.0
        t=max(0.2,abs(_r.lognormvariate(mu,sigma)))
        return t

    @staticmethod
    def referer_chain(step):
        chain={
            'init':'https://www.google.com/',
            'login':'https://chatgpt.com/auth/login',
            'signup':'https://auth.openai.com/create-account',
            'verify':'https://auth.openai.com/email-verification',
            'phone':'https://auth.openai.com/add-phone',
            'complete':'https://auth.openai.com/authorize'
        }
        return chain.get(step,'https://auth.openai.com/')

    @staticmethod
    def ordered_headers(fp,step):
        return {
            'User-Agent':fp['user_agent'],
            'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language':fp['lang_full'],
            'Accept-Encoding':'gzip, deflate, br',
            'Referer':AntiDetect.referer_chain(step),
            'Origin':'https://auth.openai.com',
            'DNT':'1',
            'Connection':'keep-alive',
            'Sec-Fetch-Dest':'empty',
            'Sec-Fetch-Mode':'cors',
            'Sec-Fetch-Site':'same-origin',
        }

    @staticmethod
    def fingerprint_headers(fp):
        import base64,hashlib
        return {
            'User-Agent':fp['user_agent'],
            'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language':fp['lang_full'],
            'Accept-Encoding':'gzip, deflate, br',
            'DNT':'1',
            'Upgrade-Insecure-Requests':'1',
            'Cache-Control':'max-age=0',
        }
