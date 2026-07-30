from curl_cffi.requests import AsyncSession, Session
import random as _random_obj

class AntiFraud:
    _SAFARI = [
        {'ua':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.3 Safari/605.1.15','imp':'safari15_3'},
        {'ua':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15','imp':'safari15_5'},
        {'ua':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15','imp':'safari16_0'},
        {'ua':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15','imp':'safari17_0'},
    ]
    _SCREENS=['1440x900','1512x982','1728x1117','2560x1440','1920x1080']
    _LANGS=['en-US,en;q=0.9','en-US,en;q=0.9,zh-CN;q=0.8','en-GB,en;q=0.9','en-US,en;q=0.9,ja;q=0.8']

    @staticmethod
    def delay(min_s=0.5,max_s=3.0):
        import asyncio,time
        t=_random_obj.uniform(min_s,max_s)
        def sync_delay():time.sleep(t)
        async def async_delay():await asyncio.sleep(t)
        return sync_delay,async_delay,t

    @staticmethod
    def random_fingerprint():
        s=_random_obj.choice(AntiFraud._SAFARI)
        sc=_random_obj.choice(AntiFraud._SCREENS)
        l=_random_obj.choice(AntiFraud._LANGS)
        return {'impersonate':s['imp'],'user_agent':s['ua'],'screen':sc,'lang':l.split(',')[0],'lang_full':l,'sec_ch_ua':'','sec_ch_ua_platform':'','sec_ch_ua_mobile':''}

    @staticmethod
    def lock_ip():
        import os
        os.environ['WARP_LOCK']='1'
        return'IP locked for this session'

    @staticmethod
    def unlock_ip():
        import os
        os.environ['WARP_LOCK']=''
        return'IP unlocked'

    @staticmethod
    def warmup_session(session,email):
        try:
            import asyncio
            async def _warm():
                await asyncio.sleep(_random_obj.uniform(5,15))
                try:
                    r=await session.get('https://chatgpt.com/',timeout=15,allow_redirects=True)
                    if r.status_code==200:
                        pass
                except:pass
            try:
                loop=asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_warm())
                else:
                    asyncio.run(_warm())
            except:pass
        except:pass
