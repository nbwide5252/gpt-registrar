"""
批量注册 + 自动上传到Sub2API

每注册成功一个账号，立即上传到Sub2面板
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 导入注册模块
from full_registration_token import full_registration_with_token

# 导入上传模块
from sub2api_uploader import Sub2AdminClient

# 导入智能国家解析器
from country_resolver import CountryResolver


def configure_console():
    """避免 Windows GBK 控制台因 emoji 输出中断业务流程。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


configure_console()


def load_sub2_config():
    """加载Sub2配置"""
    config_file = Path("sub2_config.json")
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f).get("sub2api", {})
    return {}


def save_sub2_config(url, email, password, group_name):
    """保存Sub2配置"""
    config = {
        "sub2api": {
            "url": url,
            "email": email,
            "password": password,
            "default_group": group_name
        }
    }
    with open("sub2_config.json", 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


async def register_and_upload_one(
    sms_country: str,
    sub2_client: Sub2AdminClient = None,
    index: int = 1,
    total: int = 1
):
    """
    注册一个账号并立即上传

    Args:
        sms_country: 接码国家代码
        sub2_client: Sub2客户端（如果为None则不上传）
        index: 当前是第几个
        total: 总共要注册几个
    """
    print(f"\n{'='*70}")
    print(f"📝 开始注册第 {index}/{total} 个账号")
    print(f"{'='*70}\n")

    try:
        # 1. 注册并获取Token
        tokens = await full_registration_with_token(sms_country=sms_country)

        if not tokens:
            print(f"\n❌ 第 {index} 个账号注册失败\n")
            return False

        # 2. 读取刚生成的token文件
        tokens_dir = Path("outputs/tokens")
        token_files = sorted(tokens_dir.glob("codex-*-free.json"), key=os.path.getmtime, reverse=True)

        if not token_files:
            print(f"\n❌ 未找到生成的token文件\n")
            return False

        # 获取最新的token文件
        latest_token_file = token_files[0]

        with open(latest_token_file, 'r', encoding='utf-8') as f:
            token_data = json.load(f)

        email = token_data.get("email", "unknown")

        # 3. 如果配置了Sub2，立即上传
        if sub2_client:
            print(f"\n{'='*70}")
            print(f"📤 上传到Sub2API")
            print(f"{'='*70}\n")

            try:
                result = sub2_client.create_account(token_data)

                if result.get("updated"):
                    print(f"\n✅ 第 {index} 个账号 {email} 已更新到Sub2\n")
                elif result.get("skipped"):
                    print(f"\n⚠️ 第 {index} 个账号 {email} 已存在Sub2中\n")
                else:
                    print(f"\n✅ 第 {index} 个账号 {email} 上传成功！\n")

                return True

            except Exception as e:
                print(f"\n❌ 第 {index} 个账号 {email} 上传失败: {e}\n")
                print(f"   账号已注册成功，token已保存，可稍后手动上传\n")
                return False
        else:
            print(f"\n✅ 第 {index} 个账号 {email} 注册成功！（未配置Sub2上传）\n")
            return True

    except Exception as e:
        print(f"\n❌ 第 {index} 个账号处理失败: {e}\n")
        return False


async def batch_register_and_upload(
    count: int,
    sms_country: str,
    sub2_url: str = None,
    sub2_email: str = None,
    sub2_password: str = None,
    group_name: str = "codex-auto",
    warp_rotate_interval: int = 0
):
    """
    批量注册并上传

    Args:
        count: 注册数量
        sms_country: 接码国家代码
        sub2_url: Sub2 URL（可选）
        sub2_email: Sub2管理员邮箱（可选）
        sub2_password: Sub2管理员密码（可选）
        group_name: Sub2分组名称
    """
    print(f"\n{'='*70}")
    print(f"🚀 批量注册 + 自动上传")
    print(f"{'='*70}")
    print(f"  数量: {count} 个")
    print(f"  国家: {sms_country}")

    # 初始化Sub2客户端
    sub2_client = None
    if sub2_url and sub2_email and sub2_password:
        print(f"  Sub2: {sub2_url}")
        print(f"  分组: {group_name}")
        sub2_client = Sub2AdminClient(sub2_url, sub2_email, sub2_password, group_name)
    else:
        print(f"  Sub2: 未配置，仅注册不上传")

    print(f"{'='*70}\n")

    # 统计
    success_count = 0
    failed_count = 0
    attempt_count = 0

    start_time = datetime.now()

    # 循环直到成功注册指定数量
    while success_count < count:
        attempt_count += 1

        print(f"\n{'='*70}")
        print(f"📝 尝试第 {attempt_count} 次注册 (已成功 {success_count}/{count})")
        print(f"{'='*70}\n")

        success = await register_and_upload_one(
            sms_country=sms_country,
            sub2_client=sub2_client,
            index=success_count + 1,
            total=count
        )

        if success:
            success_count += 1
            print(f"\n✅ 成功注册第 {success_count}/{count} 个账号")
        else:
            failed_count += 1
            print(f"\n❌ 本次尝试失败 (已失败 {failed_count} 次)")

        # 如果还没达到目标数量，等待后继续
        if success_count < count:
            print(f"\n⏳ 等待5秒后继续...\n")
            await asyncio.sleep(5)

    # 总结
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print(f"\n{'='*70}")
    print(f"🎉 批量任务完成！")
    print(f"{'='*70}")
    print(f"  🎯 目标: {count} 个")
    print(f"  ✅ 成功: {success_count} 个")
    print(f"  ❌ 失败: {failed_count} 次尝试")
    print(f"  📊 总尝试: {attempt_count} 次")
    print(f"  📈 成功率: {success_count/attempt_count*100:.1f}%")
    print(f"  ⏱️ 耗时: {int(duration//60)}分{int(duration%60)}秒")
    print(f"  📁 Token保存在: outputs/tokens/")

    if sub2_client:
        print(f"  🌐 访问Sub2: {sub2_url}")
        print(f"  📊 查看分组: {group_name}")

    print(f"{'='*70}\n")


def main():
    print("\n" + "="*70)
    print("🌍 批量注册 + 自动上传到Sub2API")
    print("="*70 + "\n")

    # Auto-load from env (set by menu.py)
    env_url = os.environ.get('SUB2_URL', '')
    env_group = os.environ.get('SUB2_GROUP', '')
    if env_url and env_group:
        sub2_cfg = {'url': env_url, 'group': env_group}
        sub2_cfg['email'] = os.environ.get('SUB2_EMAIL', '')
        sub2_cfg['password'] = os.environ.get('SUB2_PASSWORD', '')
        save_sub2_config(sub2_cfg['url'], sub2_cfg['email'], sub2_cfg['password'], sub2_cfg['group'])
        count_env = os.environ.get('BATCH_COUNT', '')
        if count_env:
            count = int(count_env)
            sms_country = os.environ.get('SMS_COUNTRY', '52')
            print(f'From env: count={count}, country={sms_country}, group={env_group}')
            import asyncio
            asyncio.run(batch_register_and_upload(count=count, sms_country=sms_country, sub2_url=sub2_cfg['url'], sub2_email=sub2_cfg['email'], sub2_password=sub2_cfg['password'], group_name=sub2_cfg['group'], warp_rotate_interval=int(os.environ.get('WARP_ROTATE', '0'))))
            return

    # 1. 输入注册数量
    while True:
        count_input = input("请输入要注册的数量 (1-100): ").strip()
        try:
            count = int(count_input)
            if 1 <= count <= 100:
                break
            else:
                print("⚠️ 请输入1-100之间的数字")
        except:
            print("⚠️ 请输入有效的数字")

    # 2. 选择国家
    # 从官方API获取的完整映射
    COUNTRY_CODES = {
        # === 推荐国家（已验证稳定）===
        "巴西": "73",     # ✅ Brazil - 库存足，价格低
        "泰国": "52",     # ✅ Thailand - 速度快
        "南非": "31",     # ✅ South Africa - 成功率高
        "波兰": "15",     # ✅ Poland - 性价比高

        # === 常用国家 ===
        "英国": "16",     # United Kingdom
        "美国": "0",      # (需要查询，价格贵)
        "加拿大": "36",   # Canada
        "德国": "43",     # Germany
        "法国": "0",      # (需要查询)
        "澳大利亚": "0",  # (需要查询)

        # === 亚洲国家 ===
        "中国": "3",           # China
        "印度": "22",          # India
        "印尼": "6",           # Indonesia
        "印度尼西亚": "6",
        "马来西亚": "7",       # Malaysia
        "越南": "10",          # Vietnam
        "泰国": "52",          # Thailand
        "菲律宾": "4",         # Philippines
        "新加坡": "0",         # (需要查询)
        "日本": "0",           # (需要查询)
        "韩国": "0",           # (需要查询)
        "香港": "14",          # Hong Kong
        "台湾": "55",          # Taiwan
        "澳门": "20",          # Macao

        # === 欧洲国家 ===
        "波兰": "15",          # Poland
        "英国": "16",          # United Kingdom
        "德国": "43",          # Germany
        "法国": "0",           # (需要查询)
        "荷兰": "48",          # Netherlands
        "奥地利": "50",        # Austria
        "瑞士": "0",           # (需要查询)
        "瑞典": "46",          # Sweden
        "爱尔兰": "23",        # Ireland
        "罗马尼亚": "32",      # Romania
        "乌克兰": "1",         # Ukraine
        "哈萨克斯坦": "2",     # Kazakhstan
        "白俄罗斯": "51",      # Belarus

        # === 美洲国家 ===
        "巴西": "73",          # Brazil
        "加拿大": "36",        # Canada
        "墨西哥": "54",        # Mexico
        "阿根廷": "39",        # Argentina
        "智利": "0",           # (需要查询)
        "哥伦比亚": "33",      # Colombia

        # === 其他国家 ===
        "南非": "31",          # South Africa
        "土耳其": "62",        # Turkey
        "以色列": "13",        # Israel
        "柬埔寨": "24",        # Cambodia

        # === 英文名 ===
        "brazil": "73",
        "thailand": "52",
        "south africa": "31",
        "poland": "15",
        "uk": "16",
        "united kingdom": "16",
        "britain": "16",
        "usa": "0",
        "america": "0",
        "canada": "36",
        "germany": "43",
        "deutschland": "43",
        "france": "0",
        "netherlands": "48",
        "holland": "48",
        "austria": "50",
        "china": "3",
        "india": "22",
        "indonesia": "6",
        "malaysia": "7",
        "vietnam": "10",
        "philippines": "4",
        "hong kong": "14",
        "taiwan": "55",
        "ukraine": "1",
        "kazakhstan": "2",
        "romania": "32",
        "turkey": "62",
        "mexico": "54",
        "argentina": "39",
        "colombia": "33",
        "ireland": "23",
        "cambodia": "24",
        "sweden": "46",
    }

    # 初始化智能国家解析器
    print("⏳ 正在从HeroSMS获取最新国家列表...")

    # 从config.json读取API密钥
    with open("config.json", 'r', encoding='utf-8') as f:
        config = json.load(f)
        api_key = config.get("heroSmsApiKey", "")

    resolver = CountryResolver(api_key=api_key)
    countries = resolver.get_countries()

    if countries:
        print(f"✅ 已加载 {len(countries)} 个国家\n")
    else:
        print("⚠️  无法获取国家列表，将使用本地映射\n")

    print(f"\n🌍 请输入国家名（中文或英文）\n")
    print(f"💡 推荐（已验证）: 巴西(73) 泰国(52) 南非(31) 波兰(15)")
    print(f"💡 其他可用: 英国 德国 奥地利 印尼 越南 马来西亚 等")
    print(f"💡 默认: 巴西 (直接回车)\n")

    user_input = input("请输入国家名: ").strip()

    if not user_input:
        sms_country = "73"  # 默认巴西
        country_name = "巴西"
        print(f"✅ 使用默认: {country_name} (代码: {sms_country})\n")
    elif user_input.isdigit():
        # 直接输入代码
        sms_country = user_input
        country_name = resolver.get_country_name(sms_country)
        print(f"✅ 使用代码: {sms_country} ({country_name})\n")
    else:
        # 使用智能解析器查找
        sms_country = resolver.find_country_code(user_input)

        if sms_country:
            country_name = resolver.get_country_name(sms_country)
            print(f"✅ 选择: {country_name} (代码: {sms_country})\n")
        else:
            # 降级到本地映射表
            sms_country = COUNTRY_CODES.get(user_input.lower())
            if sms_country:
                country_name = resolver.get_country_name(sms_country)
                print(f"✅ 选择: {country_name} (代码: {sms_country})\n")
            else:
                print(f"⚠️ 未识别的国家，使用默认: 巴西 (代码: 73)\n")
                sms_country = "73"
                country_name = "巴西"

    # 3. 是否上传到Sub2
    print("是否要自动上传到Sub2API？")
    print("  [1] 是，配置Sub2并自动上传")
    print("  [2] 否，仅注册不上传")

    upload_choice = input("\n请选择 [1/2]: ").strip()

    sub2_url = None
    sub2_email = None
    sub2_password = None
    group_name = "codex-auto"

    if upload_choice == "1":
        # 加载已保存的配置
        config = load_sub2_config()

        if config.get("url"):
            print(f"\n检测到已保存的配置:")
            print(f"  URL: {config.get('url')}")
            print(f"  邮箱: {config.get('email')}")
            print(f"  分组: {config.get('default_group', 'codex-auto')}")
            use_saved = input(f"\n使用已保存的配置？[Y/n]: ").strip().lower()

            if use_saved in ('', 'y', 'yes'):
                sub2_url = config.get("url")
                sub2_email = config.get("email")
                sub2_password = config.get("password")
                group_name = config.get("default_group", "codex-auto")

                config = {}

        if not config:
            print("\n请输入Sub2API配置:\n")

            env_url = os.environ.get("SUB2_URL", "")
            if env_url:
                sub2_url = env_url
                print(f"Sub2 URL: {sub2_url} (from env)")
            else:
                sub2_url = input("Sub2 URL (如 https://api.example.com): ").strip()
            if not sub2_url:
                print("❌ URL不能为空")
                return

            env_email = os.environ.get("SUB2_EMAIL", "")
            if env_email:
                sub2_email = env_email
                print(f"Sub2 email: {sub2_email} (from env)")
            else:
                sub2_email = input("Sub2 管理员邮箱: ").strip().strip()
            if not sub2_email:
                print("❌ 邮箱不能为空")
                return

            env_pwd = os.environ.get("SUB2_PASSWORD", "")
            if env_pwd:
                sub2_password = env_pwd
                print(f"Sub2 pwd: from env")
            else:
                sub2_password = input("Sub2 管理员密码: ").strip()
            if not sub2_password:
                print("❌ 密码不能为空")
                return

            # 保存配置
            save_choice = input("\n是否保存此配置？[Y/n]: ").strip().lower()
            if save_choice in ('', 'y', 'yes'):
                save_sub2_config(sub2_url, sub2_email, sub2_password, group_name)
                print("✅ 配置已保存\n")

    # 4. 确认并开始
    print(f"\n{'='*70}")
    print(f"📋 确认信息")
    print(f"{'='*70}")
    print(f"  注册数量: {count} 个")
    print(f"  接码国家: {sms_country}")
    if sub2_url:
        print(f"  Sub2上传: 是")
        print(f"  Sub2地址: {sub2_url}")
        print(f"  分组名称: {group_name}")
    else:
        print(f"  Sub2上传: 否")
    print(f"{'='*70}\n")

    confirm = input("确认开始？[Y/n]: ").strip().lower()
    if confirm not in ('', 'y', 'yes'):
        print("已取消")
        return

    # 5. 开始批量注册
    asyncio.run(batch_register_and_upload(
        count=count,
        sms_country=sms_country,
        sub2_url=sub2_url,
        sub2_email=sub2_email,
        sub2_password=sub2_password,
        group_name=group_name,
        warp_rotate_interval=int(os.environ.get("WARP_ROTATE", "0"))
    ))


if __name__ == "__main__":
    main()

