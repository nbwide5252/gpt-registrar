import os,json,time,asyncio
from pathlib import Path
from datetime import datetime,timedelta

BASE_DIR=Path(__file__).resolve().parent
OUTPUTS=BASE_DIR/'outputs'
SUCCESS_FILE=OUTPUTS/'success_rate.json'
COST_FILE=OUTPUTS/'cost_log.json'

class SmartRotator:
    def __init__(self):
        OUTPUTS.mkdir(parents=True,exist_ok=True)
        self.stats={'countries':{}}
        self.current=''
        self.switch_time=0
        self.start_date=str(datetime.now().date())
        if SUCCESS_FILE.exists():
            try:self.stats=json.loads(SUCCESS_FILE.read_text(encoding='utf-8'))
            except:pass
        if'start_date'in self.stats:self.start_date=self.stats['start_date']
        else:self.stats['start_date']=self.start_date

    def mode(self):
        d1=datetime.strptime(self.start_date,'%Y-%m-%d').date()
        days=(datetime.now().date()-d1).days
        return('smart'if days>=3 else'learn'),days

    def get_top(self,n=5):
        scored=[]
        for code,r in self.stats.get('countries',{}).items():
            total=r.get('ok',0)+r.get('fail',0)
            if total>=3:scored.append((r.get('ok',0)/total,code))
        scored.sort(reverse=True)
        return[c for _,c in scored[:n]]

    def next_country(self,countries):
        codes=[c['code']for c in countries]
        mode,days=self.mode()
        if mode=='smart':
            top=self.get_top()
            valid=[c for c in top if c in codes]
            if valid:
                if self.current not in valid:self.current=valid[0]
                else:
                    idx=valid.index(self.current)
                    self.current=valid[(idx+1)%len(valid)]
                return self.current
        if time.time()-self.switch_time>600 or not self.current:
            if self.current and self.current in codes:
                idx=codes.index(self.current)
                self.current=codes[(idx+1)%len(codes)]
            else:self.current=codes[0]
            self.switch_time=time.time()
        return self.current or codes[0]

    def track(self,country,ok):
        c=self.stats['countries']
        if country not in c:c[country]={'ok':0,'fail':0}
        if ok:c[country]['ok']+=1
        else:c[country]['fail']+=1
        SUCCESS_FILE.write_text(json.dumps(self.stats,indent=2,ensure_ascii=False),encoding='utf-8')

    def match_ip(self,country_code):
        try:
            with open(BASE_DIR/'country_ip_map.json')as f:m=json.load(f)
            if country_code in m:
                import subprocess as sp
                sp.run(['warp-cli','disconnect'],timeout=10,capture_output=True)
                time.sleep(2)
                sp.run(['warp-cli','connect'],timeout=15,capture_output=True)
                return True
        except:pass
        return False

    def summary(self):
        mode,days=self.mode()
        lines=[mode.upper()+' mode - Day '+str(days)]
        items=sorted(self.stats.get('countries',{}).items(),key=lambda x:x[1].get('ok',0)/max(1,x[1].get('ok',0)+x[1].get('fail',0)),reverse=True)
        for code,r in items:
            total=r.get('ok',0)+r.get('fail',0)
            rate=r.get('ok',0)/total*100 if total>0 else 0
            lines.append('  '+code+': '+str(r.get('ok',0))+'/'+str(total)+' ('+str(int(rate))+'%)')
        return chr(10).join(lines)

class CostTracker:
    def __init__(self):
        self.cost=0.0
        self.start=time.time()
        if COST_FILE.exists():
            try:self.cost=json.loads(COST_FILE.read_text(encoding='utf-8')).get('total',0.0)
            except:pass
    def add(self,c=0):self.cost+=c
    def summary(self):
        m=int((time.time()-self.start)//60)
        return'Cost: $'+str(round(self.cost,2))+' Time: '+str(m)+'m'

class WarpRotator:
    def __init__(self):self.last=0
    def rotate(self,force=False):
        now=time.time()
        if force or now-self.last>600:
            import subprocess as sp
            try:sp.run(['warp-cli','disconnect'],timeout=10,capture_output=True);time.sleep(2);sp.run(['warp-cli','connect'],timeout=15,capture_output=True)
            except:pass
            self.last=now

async def batch_enhanced(count,sms_country,sub2_url=None,sub2_email=None,sub2_pwd=None,group='chatgpt1'):
    from batch_register_and_upload import register_and_upload_one,Sub2AdminClient
    rotator=SmartRotator()
    warp=WarpRotator()
    tracker=CostTracker()

    countries=[]
    try:
        from multi_sms_provider import SMSBowerProvider,HeroSMSProvider as HSP
        cfg_file=BASE_DIR/'sms_providers_config.json'
        j=json.loads(cfg_file.read_text(encoding='utf-8'))if cfg_file.exists()else{}
        for n,p in j.get('sms_providers',{}).items():
            if not p.get('api_key'):continue
            prov=SMSBowerProvider(p['api_key'],p.get('service_code','dr'))if n=='smsbower'else HSP(p['api_key'],p.get('service_code','dr'))
            cl=prov.get_countries_with_prices()
            if cl:
                mp=float(j.get('max_price',0.03))
                countries=[c for c in cl if c['price']<=mp];break
    except:countries=[{'code':sms_country,'price':0}]
    if not countries:countries=[{'code':sms_country,'price':0}]

    sub2_client=None
    if sub2_url and sub2_email:
        try:sub2_client=Sub2AdminClient(sub2_url,sub2_email,sub2_pwd,group)
        except:pass

    i=0;ok=0;mode,days=rotator.mode()
    print('Mode: '+mode.upper()+' Day '+str(days))
    if mode=='learn':print('Collecting data for 3 days, then auto-switch to top 5 countries')
    while ok<count:
        i+=1
        best=rotator.next_country(countries)
        is_new=rotator.switch_time>time.time()-10
        rotator.match_ip(best)
        warp.rotate(force=is_new)
        print('  Reg '+str(i)+': country='+best+' ok='+str(ok)+'/'+str(count))
        result=await register_and_upload_one(sms_country=best,sub2_client=sub2_client,index=i,total=count)
        rotator.track(best,result)
        if result:ok+=1
        tracker.add()
    print(chr(10)+rotator.summary())
    print(tracker.summary())
    return{'ok':ok,'cost':tracker.cost}
