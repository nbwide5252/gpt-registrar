import os,json,time,asyncio
from pathlib import Path
from datetime import datetime

BASE_DIR=Path(__file__).resolve().parent
OUTPUTS=BASE_DIR/'outputs'
SUCCESS_FILE=OUTPUTS/'success_rate.json'
COST_FILE=OUTPUTS/'cost_log.json'

class CostTracker:
    def __init__(self):
        OUTPUTS.mkdir(parents=True,exist_ok=True)
        self.cost=0.0
        self.stats={'ok':0,'fail':0,'countries':{}}
        self.start_time=time.time()
        if SUCCESS_FILE.exists():
            try:self.stats=json.loads(SUCCESS_FILE.read_text(encoding='utf-8'))
            except:pass
    def track(self,ok,country='',cost=0):
        if ok: self.stats['ok']+=1; self.cost+=cost
        else: self.stats['fail']+=1
        if country:
            if country not in self.stats['countries']:self.stats['countries'][country]={'ok':0,'fail':0}
            self.stats['countries'][country]['ok'if ok else'fail']+=1
        SUCCESS_FILE.write_text(json.dumps(self.stats,indent=2,ensure_ascii=False),encoding='utf-8')
    def get_best_country(self,countries):
        best=None;best_score=999
        for c in countries:
            r=self.stats['countries'].get(c['code'],{'ok':0,'fail':0})
            total=r['ok']+r['fail']
            sr=r['ok']/total if total>0 else 1.0
            score=c['price']/sr if sr>0 else c['price']*10
            if score<best_score:best_score=score;best=c['code']
        return best or (countries[0]['code']if countries else'52')
    def summary(self):
        elapsed=time.time()-self.start_time
        m=int(elapsed//60);s=int(elapsed%60)
        total=self.stats['ok']+self.stats['fail']
        rate=self.stats['ok']/total*100 if total>0 else 0
        return f'OK:{self.stats[chr(111)+chr(107)]} FAIL:{self.stats[chr(102)+chr(97)+chr(105)+chr(108)]} Rate:{rate:.0f}% Cost: Time:{m}m{s}s'

class WarpRotator:
    def __init__(self,interval=5):self.interval=interval;self.count=0
    def rotate(self):
        self.count+=1
        if self.interval>0 and self.count%self.interval==0:
            import subprocess as sp
            try:sp.run(['warp-cli','disconnect'],timeout=10,capture_output=True);time.sleep(2);sp.run(['warp-cli','connect'],timeout=15,capture_output=True)
            except:pass

async def batch_enhanced(count,sms_country,sub2_url=None,sub2_email=None,sub2_pwd=None,group='chatgpt1',rotate=5):
    from batch_register_and_upload import register_and_upload_one,Sub2AdminClient
    tracker=CostTracker()
    rotator=WarpRotator(rotate)
    sub2_client=None
    if sub2_url and sub2_email:
        try:sub2_client=Sub2AdminClient(sub2_url,sub2_email,sub2_pwd,group)
        except:pass
    i=0
    while tracker.stats['ok']<count:
        i+=1;rotator.rotate()
        print(f'\\n  Reg {i}: ok={tracker.stats[chr(111)+chr(107)]}/{count}')
        result=await register_and_upload_one(sms_country=sms_country,sub2_client=sub2_client,index=i,total=count)
        tracker.track(result,sms_country)
    print(f'\\n  {tracker.summary()}')
    return tracker.stats
