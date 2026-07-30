"""
智能国家代码解析器
自动从 HeroSMS API 获取最新的国家映射
"""
import logging
from typing import Optional, Dict
from curl_cffi import requests

logger = logging.getLogger(__name__)


class CountryResolver:
    """国家代码解析器"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://hero-sms.com/stubs/handler_api.php"
        self._cache: Optional[Dict[str, str]] = None

        # 中文到英文的映射
        self.zh_to_en = {
            "巴西": "brazil",
            "泰国": "thailand",
            "南非": "south africa",
            "波兰": "poland",
            "英国": "united kingdom",
            "美国": "united states",
            "加拿大": "canada",
            "德国": "germany",
            "法国": "france",
            "荷兰": "netherlands",
            "奥地利": "austria",
            "瑞士": "switzerland",
            "瑞典": "sweden",
            "中国": "china",
            "印度": "india",
            "印尼": "indonesia",
            "印度尼西亚": "indonesia",
            "马来西亚": "malaysia",
            "越南": "vietnam",
            "菲律宾": "philippines",
            "日本": "japan",
            "韩国": "korea",
            "香港": "hong kong",
            "台湾": "taiwan",
            "澳门": "macao",
            "俄罗斯": "russia",
            "乌克兰": "ukraine",
            "哈萨克斯坦": "kazakhstan",
            "白俄罗斯": "belarus",
            "罗马尼亚": "romania",
            "土耳其": "turkey",
            "以色列": "israel",
            "墨西哥": "mexico",
            "阿根廷": "argentina",
            "智利": "chile",
            "哥伦比亚": "colombia",
            "柬埔寨": "cambodia",
            "爱尔兰": "ireland",
        }

    def fetch_countries(self) -> Dict[str, str]:
        """
        从 HeroSMS API 获取国家列表

        Returns:
            {id: name} 映射
        """
        try:
            params = {
                "api_key": self.api_key,
                "action": "getCountries"
            }

            resp = requests.get(self.base_url, params=params, timeout=10, impersonate="chrome110")
            resp.raise_for_status()

            data = resp.json()

            # 提取 {id: name}
            countries = {}
            for code, info in data.items():
                if isinstance(info, dict) and "eng" in info:
                    countries[code] = info["eng"]

            logger.info(f"✅ 从API获取了 {len(countries)} 个国家")
            return countries

        except Exception as e:
            logger.error(f"❌ 获取国家列表失败: {e}")
            return {}

    def get_countries(self) -> Dict[str, str]:
        """获取国家列表（带缓存）"""
        if self._cache is None:
            self._cache = self.fetch_countries()
        return self._cache

    def find_country_code(self, query: str) -> Optional[str]:
        """
        查找国家代码

        Args:
            query: 国家名（中文或英文）

        Returns:
            HeroSMS 国家代码，未找到返回 None
        """
        query = query.strip().lower()

        # 先查本地映射
        if query in self.zh_to_en:
            query = self.zh_to_en[query]

        # 从API获取
        countries = self.get_countries()

        # 精确匹配
        for code, name in countries.items():
            if name.lower() == query:
                return code

        # 部分匹配
        for code, name in countries.items():
            if query in name.lower() or name.lower() in query:
                return code

        return None

    def get_country_name(self, code: str) -> str:
        """根据代码获取国家名"""
        countries = self.get_countries()
        return countries.get(code, f"国家{code}")


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    resolver = CountryResolver(api_key="f5ebbcdA48f70A3d3950631A44ce9b5e")

    test_cases = ["巴西", "泰国", "奥地利", "德国", "brazil", "austria"]

    print("="*70)
    print("国家代码查询测试")
    print("="*70)

    for query in test_cases:
        code = resolver.find_country_code(query)
        if code:
            name = resolver.get_country_name(code)
            print(f"{query:<15} → 代码: {code:<4} ({name})")
        else:
            print(f"{query:<15} → 未找到")
