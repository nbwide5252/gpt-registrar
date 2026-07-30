#!/usr/bin/env python3
"""
海鸥GPT自动注册机 - VPS 后端管理菜单
============================================
Debian VPS 终端操作台
启动: python3 deploy/menu.py  或  gpt
"""
import os, sys, json, time, subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
TOKENS_DIR = OUTPUTS_DIR / "tokens"
LOGS_DIR = BASE_DIR / "logs"
DEPLOY_DIR = BASE_DIR / "deploy"

R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"
B = "\033[94m"; M = "\033[95m"; C = "\033[96m"
W = "\033[97m"; N = "\033[0m"; BLD = "\033[1m"
DIM = "\033[2m"; CLS = "\033[H\033[J"

DASH = "\u2500"
CHECK = "\u2714"
CROSS = "\u2716"
WARN = "\u26a0"
ARROW = "\u25b6"

def err(msg): print(f" {R}{CROSS} {msg}{N}")
def ok(msg): print(f" {G}{CHECK} {msg}{N}")
def warn(msg): print(f" {Y}{WARN} {msg}{N}")
def header(t):
    w = 56
    sep = DASH * w
    print("")
    print(f" {C}{sep}{N}")
    print(f" {BLD}{Y}  {t}{N}")
    print(f" {C}{sep}{N}")
    print("")

def press():
    input(f"\n {DIM}按 Enter 返回菜单...{N}")

# ========== Config ==========
def load_env():
    cfg = {}
    env_f = DEPLOY_DIR / ".env"
    if env_f.exists():
        for line in env_f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip("'\"")
            os.environ[k.strip()] = v.strip().strip("'\"")
    # Cloudflare mail from config.py
    try:
        sys.path.insert(0, str(BASE_DIR))
        import config as cf
        cfg["CF_MAIL_API_URL"] = getattr(cf, "CF_MAIL_API_URL", cfg.get("CF_MAIL_API_URL",""))
        cfg["CF_MAIL_ADMIN_TOKEN"] = getattr(cf, "CF_MAIL_ADMIN_TOKEN", cfg.get("CF_MAIL_ADMIN_TOKEN",""))
        cfg["CF_MAIL_DOMAIN"] = getattr(cf, "CF_MAIL_DOMAIN", cfg.get("CF_MAIL_DOMAIN",""))
    except: pass
    cfg_f = BASE_DIR / "config.json"
    if cfg_f.exists():
        try:
            j = json.loads(cfg_f.read_text(encoding="utf-8"))
            cfg["HEROSMS_API_KEY"] = j.get("heroSmsApiKey","")
        except: pass
    s2 = BASE_DIR / "sub2_config.json"
    if s2.exists():
        try:
            cfg["SUB2"] = json.loads(s2.read_text(encoding="utf-8")).get("sub2api",{})
        except: pass
    return cfg

def check_env():
    issues = []
    cfg = load_env()
    sms_f = BASE_DIR / "sms_providers_config.json"
    has_smsbower = has_herosms = False
    if sms_f.exists():
        try:
            j = json.loads(sms_f.read_text(encoding="utf-8"))
            for n,p in j.get("sms_providers",{}).items():
                if p.get("api_key"):
                    if n=="smsbower": has_smsbower=True
                    elif n=="herosms": has_herosms=True
        except: pass
    if has_smsbower: ok("SMSBower")
    else: issues.append("SMSBower 未配置")
    if has_herosms: ok("HeroSMS")
    else: issues.append("HeroSMS 未配置")
    if not has_smsbower and not has_herosms:
        issues.append("CROSS 未配置任何 SMS 平台")
    d = cfg.get("CF_MAIL_DOMAIN","")
    if d: ok("Cloudflare: " + d)
    else: issues.append("Cloudflare 邮箱未配置")
    s2 = cfg.get("SUB2",{})
    if s2.get("url"): ok("Sub2: " + s2["url"] + " 分组:" + s2.get("default_group","?"))
    else: issues.append("Sub2 未配置（可选）")
    for mod, name in [("curl_cffi","curl-cffi"), ("playwright","playwright")]:
        try:
            __import__(mod)
            ok(name)
        except ImportError:
            issues.append(name + " 未安装")
    return issues

# ========== Sub2 group helper ==========
def list_sub2_groups(url, email, password):
    try:
        from sub2api_uploader import Sub2AdminClient
        client = Sub2AdminClient(url, email, password, "")
        client.login()
        data = client.request_json("/api/v1/admin/groups/all")
        groups = data if isinstance(data, list) else data.get("items", data.get("data", []))
        return groups
    except Exception as e:
        warn("获取分组失败: " + str(e))
        return []

def select_sub2_group():
    cfg = load_env()
    s2 = cfg.get("SUB2", {})
    url = s2.get("url", "") or os.environ.get("SUB2_URL", "")
    email = s2.get("email", "") or os.environ.get("SUB2_EMAIL", "")
    password = s2.get("password", "") or os.environ.get("SUB2_PASSWORD", "")
    default_group = s2.get("default_group", "") or os.environ.get("SUB2_GROUP", "chatgpt1")

    if not url or not email:
        print("  Sub2 未配置，请填写（只需一次）:")
        url = input("  Sub2 URL [https://ai.zhidexiu.com]: ").strip() or "https://ai.zhidexiu.com"
        email = input("  管理员邮箱 [ppu281285@gmail.com]: ").strip() or "ppu281285@gmail.com"
        password = input("  密码: ").strip() or "kuan0709"
        default_group = input("  分组名 [chatgpt1]: ").strip() or "chatgpt1"
        import json as _j2
        _j2.dump({"sub2api": {"url": url, "email": email, "password": password, "default_group": default_group}}, open(str(BASE_DIR / "sub2_config.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        ok("Sub2 配置已保存")
        return {"url": url, "email": email, "password": password, "group": default_group}

    print("  Sub2: " + url + "  分组: " + default_group)
    ch = input("  更改分组? [y/N]: ").strip().lower()
    if ch == "y":
        groups = list_sub2_groups(url, email, password)
        if groups:
            print("  可用分组:")
            for i, g in enumerate(groups, 1):
                print("    " + str(i) + ". " + g.get("name", "ID:" + str(g.get("id","?"))))
            idx2 = input("  编号 (Enter=保持): ").strip()
            if idx2 and idx2.isdigit():
                i3 = int(idx2) - 1
                if 0 <= i3 < len(groups):
                    default_group = groups[i3].get("name", default_group)
        else:
            c2 = input("  输入分组名: ").strip()
            if c2: default_group = c2

    return {"url": url, "email": email, "password": password, "group": default_group}
def auto_set_warp_location(country_code):
    """根据接码国家自动匹配 IP 地区"""
    import json as _j
    map_file = BASE_DIR / "country_ip_map.json"
    if not map_file.exists():
        return
    try:
        mapping = _j.loads(map_file.read_text(encoding="utf-8"))
        info = mapping.get(country_code)
        if not info:
            return
        region = info.get("region", "?")
        warp_loc = info.get("warp_location", "")
        warp_name = info.get("name", "")
        print(f"  IP 匹配: {warp_name} ({region})")
        os.environ["WARP_LOCATION"] = warp_loc
        # 尝试设置 WARP 位置 (WARP+ / Zero Trust)
        if warp_loc:
            import subprocess as _sp
            try:
                _sp.run(["warp-cli", "set-custom-endpoint", ""], timeout=5, capture_output=True)
            except:
                pass
    except:
        pass

def action_setup_wizard():
    Q=lambda t,d='':input(chr(27)+'[93m?'+chr(27)+'[0m '+t+((chr(27)+'[2m['+d+']'+chr(27)+'[0m')if d else '')+': ').strip()or d
    S=lambda t:print(chr(10)+'  '+chr(27)+'[1m'+chr(27)+'[93m'+t+chr(27)+'[0m')
    L=lambda:print('  '+chr(27)+'[96m'+'='*44+chr(27)+'[0m')
    D=lambda t:print('  '+chr(27)+'[2m'+t+chr(27)+'[0m')
    G=lambda t:print('  '+chr(27)+'[92m\u2714 '+t+chr(27)+'[0m')
    W=lambda t:print('  '+chr(27)+'[93m\u26a0 '+t+chr(27)+'[0m')

    S('首次配置向导 - 只需一次')
    L()
    S('步骤 1/4: 域名邮箱 + SMS 平台')
    L()
    print()
    D('检查 zhidexiu.com 域名邮箱 Worker...')
    import json,subprocess,requests as req
    worker='https://zhidexiu-mail.ppu2812859729.workers.dev'
    try:
        r=req.get(worker+'/api/health',timeout=10)
        if r.status_code==200:G('域名邮箱 Worker 在线')
        else:W('Worker 异常: '+str(r.status_code))
    except Exception as e:W('Worker 连接失败: '+str(e))

    D('配置 SMS 接码平台...')
    print()
    f=BASE_DIR/'sms_providers_config.json'
    j=json.loads(f.read_text(encoding='utf-8'))if f.exists()else{'sms_providers':{}}
    pvs=j.setdefault('sms_providers',{})
    if'smsbower'not in pvs:pvs['smsbower']={'enabled':True,'api_key':'','service_code':'dr','priority':1}
    if'herosms'not in pvs:pvs['herosms']={'enabled':True,'api_key':'','service_code':'dr','priority':2}
    for n in['smsbower','herosms']:
        p=pvs[n];k=p.get('api_key','')
        if k and len(k)>4 and chr(0x4f60)not in k:G(n+': 已配置')
        else:
            nk=Q('请输入 '+n+' API Key')
            if nk:p['api_key']=nk
            else:W(n+': 跳过')
    cur=j.get('max_price',0.03)
    inp=Q('最高单价 ($/SMS)',str(cur))
    try:j['max_price']=abs(float(inp))if inp else cur
    except:j['max_price']=cur
    f.write_text(json.dumps(j,indent=2,ensure_ascii=False),encoding='utf-8')

    print()
    D('自动测试 SMS 连通性...')
    any_ok=False
    try:
        from multi_sms_provider import SMSBowerProvider,HeroSMSProvider as HSP
        for n,pv in pvs.items():
            if not pv.get('api_key')or chr(0x4f60)in pv.get('api_key',''):continue
            prov=SMSBowerProvider(pv['api_key'],pv.get('service_code','dr'))if n=='smsbower'else HSP(pv['api_key'],pv.get('service_code','dr'))
            try:
                bal=prov.get_balance()
                if bal is not None:
                    mp=j['max_price'];est=int(bal/mp)if mp>0 else 0
                    G(n+' 连通成功! 余额: $'+str(round(bal,2))+' (约'+str(est)+'个)')
                    any_ok=True
                cl=prov.get_countries_with_prices()
                if cl:
                    cheap=[c for c in cl if c['price']<=j['max_price']]
                    if cheap:
                        os.environ['SMS_COUNTRY']=cheap[0]['code']
                        print('  最便宜: 代码'+cheap[0]['code']+' $'+str(cheap[0]['price'])+'/次')
            except Exception as e:W(n+' 测试失败: '+str(e))
    except:pass

    if not any_ok:
        W('没有可用的 SMS 平台')
        input('  '+chr(27)+'[2m按 Enter 返回...'+chr(27)+'[0m')
        return

    print()
    S('选择接码国家')
    D('注册成功的国家会自动匹配 IP 地区')
    try:
        found=[]
        for n,pv in pvs.items():
            if not pv.get('api_key')or chr(0x4f60)in pv.get('api_key',''):continue
            prov=SMSBowerProvider(pv['api_key'],pv.get('service_code','dr'))if n=='smsbower'else HSP(pv['api_key'],pv.get('service_code','dr'))
            cl=prov.get_countries_with_prices()
            if cl:found=[c for c in cl if c['price']<=j['max_price']][:15];break
        if found:
            print()
            for i,c in enumerate(found,1):
                tag=chr(27)+'[92m\u2714'+chr(27)+'[0m'if i==1 else''
                print('  '+str(i).rjust(2)+'. '+c['code'].rjust(4)+'  $'+str(c['price'])+tag)
            sel=Q('选择编号','1').strip()
            if sel and sel.isdigit():
                idx=int(sel)-1
                if 0<=idx<len(found):os.environ['SMS_COUNTRY']=found[idx]['code']
        else:print('  无可用国家')
    except:pass
    input(chr(10)+'  '+chr(27)+'[2m按 Enter 继续...'+chr(27)+'[0m')

    S('步骤 2/4: Sub2 面板 (可选)')
    L()
    D('注册完自动上传 Token 到 Sub2')
    print()
    s2f=BASE_DIR/'sub2_config.json'
    s2=json.loads(s2f.read_text(encoding='utf-8')).get('sub2api',{})if s2f.exists()else{}
    if s2.get('url'):G('已配置: '+s2.get('url','?'))
    if Q('更改','n').lower()=='y' or not s2.get('url'):
        if not s2.get('url'):
            u=Q('Sub2 地址')
            if u:
                e=Q('管理员邮箱')
                pw=Q('密码')
                g=Q('分组名','chatgpt1')or'chatgpt1'
                s2={'url':u,'email':e,'password':pw,'default_group':g}
                s2f.write_text(json.dumps({'sub2api':s2},indent=2,ensure_ascii=False),encoding='utf-8')
    input(chr(10)+'  '+chr(27)+'[2m按 Enter 继续...'+chr(27)+'[0m')

    S('步骤 3/4: WARP VPN (可选)')
    L()
    D('WARP 提供干净 IP')
    uw=Q('安装并启动 WARP','n').lower()
    if uw=='y':
        D('正在安装 WARP (约1分钟)...')
        ret=subprocess.run(['bash',str(DEPLOY_DIR/'install_warp.sh')])
        if ret.returncode==0:
            G('WARP 安装成功')
            D('正在启动代理模式...')
            subprocess.run(['warp-cli','set-mode','proxy'],timeout=10)
            subprocess.run(['warp-cli','registration','new'],timeout=10)
            D('正在连接 WARP 网络...')
            r2=subprocess.run(['warp-cli','connect'],timeout=15)
            if r2.returncode==0:os.environ['WARP_PROXY']='socks5://127.0.0.1:40000';G('WARP 连接成功')
            else:W('WARP 连接失败')
        else:W('WARP 安装失败')
    input(chr(10)+'  '+chr(27)+'[2m按 Enter 继续...'+chr(27)+'[0m')

    S('配置完成 - 自动开始注册')
    L()
    print('  '+chr(27)+'[92m邮箱'+chr(27)+'[0m '+chr(27)+'[2m\u2192'+chr(27)+'[0m zhidexiu.com')
    print('  '+chr(27)+'[92mSMS'+chr(27)+'[0m  '+chr(27)+'[2m\u2192'+chr(27)+'[0m 最高\$'+str(j.get('max_price',0.03)))
    print('  '+chr(27)+'[92mSub2'+chr(27)+'[0m '+chr(27)+'[2m\u2192'+chr(27)+'[0m '+(s2.get('url','未配置')if s2 else'未配置'))
    print('  '+chr(27)+'[92mWARP'+chr(27)+'[0m '+chr(27)+'[2m\u2192'+chr(27)+'[0m '+('已启用'if uw=='y' else'未启用'))
    print()
    n=Q('注册数量','5')
    os.environ['BATCH_COUNT']=str(int(n))
    os.environ['SUB2_URL']=s2.get('url','')if s2 else''
    os.environ['SUB2_GROUP']=s2.get('default_group','')if s2 else''
    os.environ['SUB2_EMAIL']=s2.get('email','')if s2 else''
    os.environ['SUB2_PASSWORD']=s2.get('password','')if s2 else''
    os.environ['WARP_ROTATE']='5'
    print()
    D('自动开始批量注册 + Sub2上传...')
    try:
        from batch_register_and_upload import main as batch_main
        batch_main()
    except Exception as e:W('注册失败: '+str(e))
    G('下次直接按 1 批量注册')
    input(chr(10)+'  '+chr(27)+'[2m按 Enter 返回...'+chr(27)+'[0m')


def action_batch_register():
    header("批量注册 ChatGPT 账号")
    try:
        import json
        mp = 0.03
        f = BASE_DIR / "sms_providers_config.json"
        if f.exists():
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
                mp = float(j.get("max_price", 0.03))
            except:
                pass
        os.environ["SMS_MAX_PRICE"] = str(mp)
        count = int(input("  注册数量 (默认 1): ").strip() or "1")
        if count < 1:
            count = 1
        from multi_sms_provider import HeroSMSProvider, SMSBowerProvider
        j2 = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        found = []
        for n,p in j2.get("sms_providers",{}).items():
            if not p.get("api_key"):
                continue
            if n == "smsbower":
                prov = SMSBowerProvider(p["api_key"], p.get("service_code","dr"))
            else:
                prov = HeroSMSProvider(p["api_key"], p.get("service_code","dr"))
            cl = prov.get_countries_with_prices()
            if cl:
                found = [c for c in cl if c["price"] <= mp][:15]
                if found:
                    break
        country = os.environ.get("SMS_COUNTRY", "52")
        if found:
            print("  可用国家 (价格限: $" + str(mp) + "):")
            for i,c in enumerate(found, 1):
                print("    " + str(i).rjust(2) + "  " + c["code"].rjust(4) + "  $" + str(c["price"]))
            sel = input("  编号 (1-" + str(len(found)) + ", Enter=最便宜): ").strip()
            if sel and sel.isdigit():
                i2 = int(sel) - 1
                if 0 <= i2 < len(found):
                    country = found[i2]["code"]
            else:
                country = found[0]["code"]
                print("  自动选: 代码 " + found[0]["code"] + " - $" + str(found[0]["price"]))
        else:
            print("  没有价格<=" + str(mp) + "的国家，用默认")
        sub2_cfg = select_sub2_group()
        print("")
        print(ARROW + " 开始注册 " + str(count) + " 个账号，SMS: " + country + "，Sub2: " + ("启用" if sub2_cfg else "禁用"))
        print("")
        os.environ["SMS_COUNTRY"] = country
        auto_set_warp_location(country)
        os.environ["BATCH_COUNT"] = str(count)
        if sub2_cfg:
            os.environ["SUB2_URL"] = sub2_cfg["url"]
            os.environ["SUB2_EMAIL"] = sub2_cfg["email"]
            os.environ["SUB2_PASSWORD"] = sub2_cfg["password"]
            os.environ["SUB2_GROUP"] = sub2_cfg["group"]
        sys.path.insert(0, str(BASE_DIR))
        from batch_register_and_upload import main as batch_main
        batch_main()
        ok("批量注册完成")
    except KeyboardInterrupt:
        warn("已中断")
    except Exception as e:
        err("注册失败: " + str(e))
    press()


def action_single_register():
    header("单次注册")
    sys.path.insert(0, str(BASE_DIR))
    try:
        from full_registration_token import full_registration_with_token
        import asyncio, json
        country = os.environ.get("SMS_COUNTRY", "52")
        result = asyncio.run(full_registration_with_token(sms_country=country))
        if result:
            ok("注册成功")
            up = input("  \u4e0a\u4f20\u5230 Sub2 \u9762\u677f\uff1f[Y/n]: ").strip().lower()
            if up in ("", "y", "yes"):
                sub2_cfg = select_sub2_group()
                if sub2_cfg:
                    from sub2api_uploader import Sub2AdminClient
                    client = Sub2AdminClient(sub2_cfg["url"], sub2_cfg["email"], sub2_cfg["password"], sub2_cfg["group"])
                    try:
                        token_files = sorted(TOKENS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
                        if token_files:
                            for f in token_files:
                                try:
                                    token_data = json.loads(f.read_text(encoding="utf-8"))
                                    if token_data.get("access_token") or token_data.get("token"):
                                        client.create_account(token_data)
                                        ok(f"\u5df2\u4e0a\u4f20: {f.stem}")
                                        break
                                except: pass
                    except Exception as e:
                        err(f"Sub2 \u4e0a\u4f20\u5931\u8d25: {e}")
        else:
            err("注\u518c\u5931\u8d25")
    except Exception as e:
        err("失\u8d25: " + str(e))
    press()

def action_recover():
    header("恢复已有账号 Token")
    files = list(TOKENS_DIR.glob("*.json")) if TOKENS_DIR.exists() else []
    files = [f for f in files if "backup" not in f.name]
    if not files:
        files = list(OUTPUTS_DIR.glob("*.json"))
        files = [f for f in files if "backup" not in f.name]
    if not files:
        err("未找到 Token 文件"); press(); return
    print("  找到 " + str(len(files)) + " 个 Token 文件\n")
    for i, f in enumerate(files[:10], 1):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            e = d.get("email", "?")
            print("  " + str(i).rjust(2) + ". " + f.stem + "  [" + e + "]")
        except:
            print("  " + str(i).rjust(2) + ". " + f.name)
    print()
    sel = input("  选择: 1.全部重新获取  2.上传Sub2  3.导出JSON\n  > ").strip()
    sys.path.insert(0, str(BASE_DIR))
    if sel == "1":
        try:
            from recover_tokens import main as r
            r()
        except: pass
    elif sel == "2":
        from sub2api_uploader import MainUploader
        MainUploader().run()
    elif sel == "3":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = OUTPUTS_DIR / ("accounts_export_" + ts + ".json")
        accs = []
        for f in files:
            try: accs.append(json.loads(f.read_text(encoding="utf-8")))
            except: pass
        out.write_text(json.dumps(accs, indent=2, ensure_ascii=False), encoding="utf-8")
        ok("导出: " + str(out))
    press()

def action_upload_sub2():
    header("上传 Token 到 Sub2 面板")
    sub2_cfg = select_sub2_group()
    if not sub2_cfg:
        press(); return
    sys.path.insert(0, str(BASE_DIR))
    try:
        from sub2api_uploader import Sub2AdminClient
        client = Sub2AdminClient(sub2_cfg["url"], sub2_cfg["email"], sub2_cfg["password"], sub2_cfg["group"])
        client.login()
        group_ids = client.get_groups()
        ok("分组ID: " + str(group_ids))
        files = list(TOKENS_DIR.glob("*.json")) if TOKENS_DIR.exists() else []
        files = [f for f in files if "backup" not in f.name]
        if not files:
            err("未找到 Token 文件")
        else:
            print("\n  找到 " + str(len(files)) + " 个账号，开始上传...\n")
            success = 0
            for f in files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    client.create_account(data)
                    success += 1
                    print("  " + CHECK + " " + f.stem)
                except Exception as e:
                    print("  " + CROSS + " " + f.stem + ": " + str(e))
            ok("上传完成: " + str(success) + "/" + str(len(files)))
    except Exception as e:
        err("上传失败: " + str(e))
    press()

def action_health():
    header("账号健康检查")
    files = list(TOKENS_DIR.glob("*.json")) if TOKENS_DIR.exists() else []
    files = [f for f in files if "backup" not in f.name]
    if not files:
        err("未找到 Token 文件"); press(); return
    h, d = 0, 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("access_token") or data.get("token"): h += 1
            else: d += 1
        except: d += 1
    print("\n  " + CHECK + " 健康: " + str(h) + "  |  " + CROSS + " 异常: " + str(d) + "  |  总计: " + str(len(files)))
    press()

def action_sms_balance():
    header("SMS 余额查询")
    sys.path.insert(0, str(BASE_DIR))
    f = BASE_DIR / "sms_providers_config.json"
    if not f.exists(): err("未找到 sms_providers_config.json"); press(); return
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
        for name, p in cfg.get("sms_providers",{}).items():
            api_key = p.get("api_key","")
            if not api_key: print("  " + name + ": 未配置"); continue
            print("  查询 " + name + "...", end=" ")
            if name == "smsbower":
                from multi_sms_provider import SMSBowerProvider
                bal = SMSBowerProvider(api_key, p.get("service_code","dr")).get_balance()
            elif name == "herosms":
                from multi_sms_provider import HeroSMSProvider
                bal = HeroSMSProvider(api_key, p.get("service_code","dr")).get_balance()
            else: bal = "?"
            if isinstance(bal, (int, float)):
                print("$" + str(bal))
            else:
                print(str(bal))
    except Exception as e: err("查询失败: " + str(e))
    press()

def action_stats():
    header("注册统计")
    files = list(TOKENS_DIR.glob("*.json")) if TOKENS_DIR.exists() else []
    files = [f for f in files if "backup" not in f.name]
    today = 0
    for f in files:
        mt = datetime.fromtimestamp(f.stat().st_mtime)
        if mt.date() == datetime.now().date():
            today += 1
    print("  总注册: " + str(len(files)))
    print("  今日: " + str(today))
    if files:
        print("\n  最近 5 个:")
        for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            mt = datetime.fromtimestamp(f.stat().st_mtime)
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                em = d.get("email","?")
            except: em = "?"
            print("   * " + f.stem + "  [" + em + "]  " + mt.strftime("%m-%d %H:%M"))
    press()

def action_config():
    while True:
        header("配置管理")
        print("  1. 查看当前配置")
        print("  2. 编辑 SMS 配置 (sms_providers_config.json)")
        print("  3. 编辑 Cloudflare 邮箱 (config.py)")
        print("  4. 编辑 Sub2 配置 (sub2_config.json)")
        print("  5. 编辑 .env 文件")
        print("  6. 编辑 Outlook 邮箱池 (outlook_pool.txt)")
        print("  7. 部署指南 - 域名邮箱 Worker (README)")
        print("  8. 运行环境检查")
        print("  0. 返回")
        sel = input("\n  选择: ").strip()
        if sel == "1":
            cfg = load_env()
            print("\n  Cloudflare: " + str(cfg.get("CF_MAIL_DOMAIN","未设置")))
            s2 = cfg.get("SUB2",{})
            print("  Sub2: " + str(s2.get("url","未配置")) + "  分组: " + str(s2.get("default_group","?")))
            print("  配置文件位置: " + str(BASE_DIR))
            press()
        elif sel == "2": subprocess.run(["nano", str(BASE_DIR/"sms_providers_config.json")])
        elif sel == "3": subprocess.run(["nano", str(BASE_DIR/"config.py")])
        elif sel == "4": subprocess.run(["nano", str(BASE_DIR/"sub2_config.json")])
        elif sel == "5":
            env_f = DEPLOY_DIR / ".env"
            if not env_f.exists():
                t = "# CF Mail\nCF_MAIL_API_URL=\nCF_MAIL_ADMIN_TOKEN=\nCF_MAIL_DOMAIN=\n\n# SMS\nSMS_COUNTRY=52\n\n# Sub2\nSUB2_URL=\nSUB2_EMAIL=\nSUB2_PASSWORD=\nSUB2_GROUP=chatgpt1\n"
                env_f.write_text(t, encoding="utf-8")
            subprocess.run(["nano", str(env_f)])
        elif sel == "6":
            pool_f = BASE_DIR / "outlook_pool.txt"
            if not pool_f.exists():
                pool_f.write_text("# Outlook邮箱池，每行: email:password:client_id:refresh_token\n", encoding="utf-8")
            subprocess.run(["nano", str(pool_f)])
        elif sel == "7":
            readme = DEPLOY_DIR / "email-worker" / "README.md"
            if readme.exists():
                print(readme.read_text(encoding="utf-8"))
                press()
            else:
                err("README.md not found")
                press()
        elif sel == "8":
            issues = check_env()
            if issues:
                print("\n " + Y + "发现 " + str(len(issues)) + " 个问题:" + N)
                for i in issues: print("   " + i)
            else: print("\n " + G + "所有检查通过!" + N)
            press()
        elif sel == "0": break

def action_warp():
    """WARP 管理"""
    while True:
        warp_on = os.environ.get("WARP_PROXY", "") != ""
        status_str = G + "已启用" + N if warp_on else R + "已禁用" + N

        header("WARP VPN 管理")
        print("  Cloudflare WARP — VPS机房IP被封时使用")
        print(f"  状态: {status_str}  (socks5://127.0.0.1:40000)")
        print()
        print("  1. 安装 WARP")
        print("  2. 启动 WARP (代理模式)")
        print("  3. 停止 WARP")
        print("  4. 查看状态")
        print("  5. 启用 WARP 代理 (注册走WARP)")  
        print("  6. 禁用 WARP 代理 (注册走VPS直连)")
        print("  7. 设置每 N 个账号换 IP")
        print("  0. 返回")
        print()
        sel = input("  选择: ").strip()
        if sel == "1":
            subprocess.run(["bash", str(DEPLOY_DIR / "install_warp.sh")])
            press()
        elif sel == "2":
            subprocess.run(["warp-cli", "set-mode", "proxy"], timeout=10)
            subprocess.run(["warp-cli", "connect"], timeout=10)
            os.environ["WARP_PROXY"] = "socks5://127.0.0.1:40000"
            ok("WARP 已启动 (代理模式)")
            press()
        elif sel == "3":
            subprocess.run(["warp-cli", "disconnect"], timeout=10)
            os.environ["WARP_PROXY"] = ""
            ok("WARP 已停止")
            press()
        elif sel == "4":
            subprocess.run(["warp-cli", "status"], timeout=10)
            press()
        elif sel == "5":
            os.environ["WARP_PROXY"] = "socks5://127.0.0.1:40000"
            ok("WARP 代理已启用，注册走WARP")
            press()
        elif sel == "6":
            os.environ["WARP_PROXY"] = ""
            ok("WARP 代理已禁用，注册走VPS直连")
            press()
        elif sel == "7":
            n = input("  每几个账号换一次IP (0=不换): ").strip()
            if n.isdigit():
                os.environ["WARP_ROTATE"] = n
                ok(f"每 {n} 个账号换一次IP")
            press()
        elif sel == "0":
            break


    header("Shell 模式 (exit 返回)")
    os.chdir(str(BASE_DIR))
    while True:
        try:
            cmd = input(" " + G + "gpt>" + N + " ").strip()
            if cmd.lower() in ("exit","quit","q","back","返回"):
                break
            if not cmd: continue
            subprocess.run(cmd, shell=True)
        except KeyboardInterrupt: break
        except Exception as e: err(str(e))

def show_banner():
    tok_count = len(list(TOKENS_DIR.glob("*.json"))) if TOKENS_DIR.exists() else 0
    cfg = load_env()
    cf_domain = cfg.get("CF_MAIL_DOMAIN","未配置") or "未配置"
    s2 = cfg.get("SUB2",{})
    s2_info = s2.get("url","X") if s2 else "X"
    sep = DASH * 54
    print(CLS, end="")
    print(" " + C + sep + N)
    print(" " + C + "|" + N + "  " + BLD + Y + "海鸥 GPT 自动注册机 - VPS 后端管理终端" + N + "  " + C + "|" + N)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(" " + C + "|" + N + "  " + DIM + now_str + N + "                    " + C + "|" + N)
    print(" " + C + sep + N)
    print()
    print("  邮箱: " + cf_domain + "  |  Token: " + str(tok_count) + "  |  Sub2: " + s2_info)
    print()

def main():
    menu_items = [
        ("--- 注册操作 ---", ["1","2","c"]),
        ("--- Token 管理 ---", ["3","4","5"]),
        ("--- 系统管理 ---", ["6","7","8","9","w"]),
    ]
    actions = {
        "1": ("批量注册 ChatGPT 账号", action_batch_register),
        "2": ("单次注册（手动模式）", action_single_register),
        "c": ("首次配置向导", action_setup_wizard),
        "3": ("恢复已有 Token", action_recover),
        "4": ("上传 Token 到 Sub2", action_upload_sub2),
        "5": ("账号健康检查", action_health),
        "6": ("SMS 余额查询", action_sms_balance),
        "7": ("注册统计", action_stats),
        "8": ("配置管理", action_config),
        "9": ("环境检查", lambda: (header("环境检查"), check_env(), press())),
        "w": ("WARP VPN 管理", action_warp),
        "0": ("退出 / Shell", action_shell),
    }

    while True:
        show_banner()
        for title, keys in menu_items:
            print("  " + W + "  " + title + N)
            for k in keys:
                label, _ = actions[k]
                print("  " + B + " " + k + "." + N + " " + label)
            print()
        print("  " + DIM + "快捷: gpt, gpt-config, gpt-balance" + N)
        print()
        sel = input(" " + Y + ARROW + " 选择 [0-9]: " + N).strip()
        if sel in actions:
            _, fn = actions[sel]
            try:
                fn()
            except KeyboardInterrupt:
                continue
            except Exception as e:
                err("异常: " + str(e))
                press()
        else:
            err("无效选择")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n " + G + "感谢使用!" + N)
    except Exception as e:
        print("\n " + R + "程序异常: " + str(e) + N)
        sys.exit(1)
