import requests,os,json,time
class Notifier:
    def __init__(self):
        self.token=os.environ.get('TG_BOT_TOKEN','')
        self.chat_id=os.environ.get('TG_CHAT_ID','')
        self.enabled=bool(self.token and self.chat_id)
        if self.enabled:print('Telegram通知已启用')
    def send(self,msg):
        if not self.enabled:return
        try:
            requests.post(f'https://api.telegram.org/bot{self.token}/sendMessage',json={'chat_id':self.chat_id,'text':msg,'parse_mode':'HTML'},timeout=10)
        except:pass
    def reg_ok(self,email,phone,cost,ok,total):
        self.send(f'<b>\u2705 注册成功</b>\n\u90ae\u7bb1: {email}\n\u7535\u8bdd: {phone}\n\u8d39\u7528: \u00a4{cost:.4f}\n\u8fdb\u5ea6: {ok}/{total}')
    def reg_fail(self,reason,ok,total):
        self.send(f'<b>\u274c 注册失败</b>\n\u539f\u56e0: {reason}\n\u8fdb\u5ea6: {ok}/{total}')
    def batch_done(self,ok,fail,cost,elapsed):
        rate=ok/(ok+fail)*100 if(ok+fail)>0 else 0
        m=int(elapsed//60);s=int(elapsed%60)
        self.send(f'<b>\ud83c\udf89 批量完成</b>\n\u6210\u529f: {ok}\n\u5931\u8d25: {fail}\n\u6210\u672c: \u00a4{cost:.2f}\n\u6210\u529f\u7387: {rate:.1f}%\n\u8017\u65f6: {m}\u5206{s}\u79d2')
