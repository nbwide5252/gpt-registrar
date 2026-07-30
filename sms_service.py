"""
HeroSMS / SmsBower 接码服务

基于原始实验项目的sms_provider.py简化版本
HeroSMS使用与sms-activate.org兼容的API协议
"""
import requests
import time
import logging
from typing import Optional
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PhoneNumber:
    """手机号信息"""
    id: str              # 激活ID
    number: str          # 手机号（带+前缀）
    country: str         # 国家代码
    service: str = "dr"  # 服务代码
    cost: float = 0.0    # 费用
    provider: str = "herosms"


class HeroSMSService:
    """
    HeroSMS接码服务（使用SmsBower协议）

    API协议兼容: sms-activate.org / SmsBower
    """

    def __init__(self, api_key: str, base_url: str = "https://hero-sms.com/stubs/handler_api.php"):
        """
        初始化HeroSMS服务

        Args:
            api_key: HeroSMS API Key
            base_url: API基础URL（默认hero-sms.com）
        """
        self.api_key = api_key
        self.base_url = base_url
        self.service_code = "dr"  # OpenAI/ChatGPT服务代码

    def _request(self, params: dict, timeout: int = 30) -> requests.Response:
        """发送请求"""
        params["api_key"] = self.api_key

        try:
            resp = requests.get(
                self.base_url,
                params=params,
                timeout=timeout
            )
            # 403通常是并发限制
            if resp.status_code == 403:
                try:
                    # 尝试解析JSON错误信息
                    error_data = resp.json()
                    if error_data.get("title") == "CHANNELS_LIMIT":
                        current = error_data.get("info", {}).get("current_threads", "?")
                        max_allowed = error_data.get("info", {}).get("max_allowed", "?")
                        logger.warning(f"⚠️  HeroSMS并发限制: {current}/{max_allowed} 线程")
                        raise Exception("CHANNELS_LIMIT")
                except:
                    # JSON解析失败，检查文本
                    if "CHANNELS_LIMIT" in resp.text or "Forbidden" in resp.text:
                        logger.warning(f"收到403响应，可能是并发限制")
                        raise Exception("CHANNELS_LIMIT")

            resp.raise_for_status()
            return resp
        except Exception as e:
            error_msg = str(e)
            if "CHANNELS_LIMIT" not in error_msg:
                logger.error(f"请求失败: {e}")
            raise

    def get_balance(self) -> float:
        """获取余额"""
        try:
            resp = self._request({"action": "getBalance"})
            text = resp.text.strip()

            if text.startswith("ACCESS_BALANCE:"):
                balance = float(text.split(":", 1)[1])
                logger.info(f"HeroSMS余额: ${balance:.2f}")
                return balance
            else:
                logger.error(f"获取余额失败: {text}")
                return 0.0
        except Exception as e:
            logger.error(f"获取余额异常: {e}")
            return 0.0

    def get_number(self, country: str = "52") -> Optional[PhoneNumber]:
        """
        获取手机号

        Args:
            country: 国家代码（字符串）- 基于country_names.py的HeroSMS官方映射
                52 = 泰国（OpenAI SMS最稳定）
                6 = 印尼
                7 = 俄罗斯
                15 = 菲律宾
                1 = 英国
                4 = 法国

        Returns:
            PhoneNumber对象或None
        """
        # 尝试V2 API
        for action in ["getNumberV2", "getNumber"]:
            try:
                logger.info(f"尝试 {action}: service={self.service_code}, country={country}")

                params = {
                    "action": action,
                    "service": self.service_code,
                    "country": str(country)
                }

                resp = self._request(params)
                resp_text = resp.text.strip()

                logger.info(f"{action} 响应: {resp_text[:200]}")

                # 解析响应
                if action == "getNumberV2":
                    # V2返回JSON
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and data.get("activationId"):
                            activation_id = str(data["activationId"])
                            phone_raw = str(data.get("phoneNumber", ""))
                            country_code = str(data.get("countryPhoneCode", ""))

                            # 格式化手机号
                            if phone_raw.startswith("+"):
                                phone = phone_raw
                            elif country_code and phone_raw.startswith(country_code):
                                phone = f"+{phone_raw}"
                            elif country_code:
                                phone = f"+{country_code}{phone_raw}"
                            else:
                                phone = f"+{phone_raw}"

                            result = PhoneNumber(
                                id=activation_id,
                                number=phone,
                                country=str(country),
                                service=self.service_code,
                                cost=float(data.get("price", 0)),
                                provider="herosms"
                            )

                            logger.info(f"✅ 获取号码成功: {phone} (ID: {activation_id})")
                            return result
                    except Exception as e:
                        logger.debug(f"V2解析失败: {e}")
                        continue

                else:  # getNumber (V1)
                    # 检查特殊错误
                    if "CHANNELS_LIMIT" in resp_text:
                        logger.warning(f"⚠️  HeroSMS并发限制，需要等待: {resp_text}")
                        # 对于并发限制，抛出特殊异常而不是返回None
                        raise Exception("CHANNELS_LIMIT")

                    if "NO_NUMBERS" in resp_text:
                        logger.warning(f"⚠️  暂无库存: {resp_text}")
                        # 无库存继续尝试下一个API
                        continue

                    # V1返回: ACCESS_NUMBER:id:phone
                    if resp_text.startswith("ACCESS_NUMBER:"):
                        parts = resp_text.split(":", 2)
                        if len(parts) == 3:
                            activation_id = parts[1]
                            phone_raw = parts[2]

                            # 格式化手机号
                            if not phone_raw.startswith("+"):
                                phone = f"+{phone_raw}"
                            else:
                                phone = phone_raw

                            result = PhoneNumber(
                                id=activation_id,
                                number=phone,
                                country=str(country),
                                service=self.service_code,
                                provider="herosms"
                            )

                            logger.info(f"✅ 获取号码成功: {phone} (ID: {activation_id})")
                            return result
                    else:
                        logger.warning(f"V1响应格式错误: {resp_text}")

            except Exception as e:
                error_msg = str(e)
                # CHANNELS_LIMIT需要向上传播，不要继续尝试
                if "CHANNELS_LIMIT" in error_msg:
                    raise
                logger.debug(f"{action} 失败: {e}")
                continue

        logger.error(f"所有方法都失败了，无法获取号码 (country={country})")
        return None

    def get_status(self, activation_id: str) -> dict:
        """
        获取状态（V1）

        Returns:
            {"status": "wait_code" | "ok", "code": "123456"}
        """
        try:
            resp = self._request({
                "action": "getStatus",
                "id": activation_id
            })

            text = resp.text.strip()

            # 解析状态
            if text == "STATUS_WAIT_CODE":
                return {"status": "wait_code"}
            elif text.startswith("STATUS_OK:"):
                code = text.split(":", 1)[1]
                return {"status": "ok", "code": code}
            elif text == "STATUS_CANCEL":
                return {"status": "cancel"}
            elif text.startswith("STATUS_WAIT_RETRY"):
                return {"status": "wait_retry"}
            else:
                return {"status": "unknown", "raw": text}

        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {"status": "error"}

    def get_status_v2(self, activation_id: str) -> dict:
        """获取状态（V2，JSON格式）"""
        try:
            resp = self._request({
                "action": "getStatusV2",
                "id": activation_id
            })

            try:
                data = resp.json()

                # 检查SMS或call渠道的code
                for channel in ("sms", "call"):
                    item = data.get(channel)
                    if isinstance(item, dict):
                        code = item.get("code")
                        if code:
                            return {"status": "ok", "code": str(code)}

                # 检查status字段
                status = data.get("status", "")
                if status == "STATUS_WAIT_CODE":
                    return {"status": "wait_code"}
                elif status.startswith("STATUS_OK:"):
                    code = status.split(":", 1)[1]
                    return {"status": "ok", "code": code}

                return {"status": "wait_code"}

            except Exception:
                # 如果不是JSON，fallback到V1解析
                return self._parse_status_text(resp.text)

        except Exception as e:
            logger.error(f"获取状态V2失败: {e}")
            return {"status": "error"}

    def _parse_status_text(self, text: str) -> dict:
        """解析状态文本"""
        text = text.strip()
        if text == "STATUS_WAIT_CODE":
            return {"status": "wait_code"}
        elif text.startswith("STATUS_OK:"):
            return {"status": "ok", "code": text.split(":", 1)[1]}
        elif text == "STATUS_CANCEL":
            return {"status": "cancel"}
        else:
            return {"status": "unknown", "raw": text}

    def get_code(self, activation_id: str, max_wait: int = 180, poll_interval: int = 3) -> Optional[str]:
        """
        等待并获取验证码

        Args:
            activation_id: 激活ID
            max_wait: 最大等待时间（秒）
            poll_interval: 轮询间隔（秒）

        Returns:
            验证码字符串或None
        """
        start_time = time.time()
        attempt = 0

        logger.info(f"等待验证码 (ID: {activation_id}, 最长{max_wait}秒)...")

        while time.time() - start_time < max_wait:
            attempt += 1

            # 尝试V2和V1
            for src in ("v2", "v1"):
                try:
                    if src == "v2":
                        result = self.get_status_v2(activation_id)
                    else:
                        result = self.get_status(activation_id)

                    status = result.get("status")

                    if status == "ok":
                        code = result.get("code", "").strip()
                        if code:
                            elapsed = int(time.time() - start_time)
                            logger.info(f"✅ 收到验证码: {code} (等待{elapsed}秒)")
                            return code
                    elif status == "cancel":
                        logger.warning("号码已被取消")
                        return None

                except Exception as e:
                    logger.debug(f"状态查询{src}失败: {e}")

            # 每30秒打印一次进度
            if attempt % 10 == 0:
                elapsed = int(time.time() - start_time)
                logger.info(f"  等待中... ({elapsed}/{max_wait}秒)")

            time.sleep(poll_interval)

        logger.error(f"获取验证码超时 (ID: {activation_id})")
        return None

    def finish(self, activation_id: str) -> bool:
        """
        标记为完成

        Args:
            activation_id: 激活ID

        Returns:
            是否成功
        """
        try:
            resp = self._request({
                "action": "setStatus",
                "id": activation_id,
                "status": "6"  # 6 = 完成
            })

            success = "ACCESS_FINISH" in resp.text or "ACCESS_OK" in resp.text

            if success:
                logger.info(f"✅ 已标记完成 (ID: {activation_id})")
            else:
                logger.warning(f"标记完成可能失败: {resp.text}")

            return success
        except Exception as e:
            logger.error(f"标记完成失败: {e}")
            return False

    def cancel(self, activation_id: str) -> bool:
        """
        取消并退款

        Args:
            activation_id: 激活ID

        Returns:
            是否成功
        """
        # 尝试方法1: cancelActivation
        try:
            resp = self._request({
                "action": "cancelActivation",
                "id": activation_id
            })

            if resp.status_code == 204 or "ACCESS_CANCEL" in resp.text:
                logger.info(f"✅ 已取消并退款 (ID: {activation_id})")
                return True
        except Exception:
            pass

        # 尝试方法2: setStatus 8
        try:
            resp = self._request({
                "action": "setStatus",
                "id": activation_id,
                "status": "8"  # 8 = 取消
            })

            success = "ACCESS_CANCEL" in resp.text

            if success:
                logger.info(f"✅ 已取消并退款 (ID: {activation_id})")
            else:
                logger.warning(f"取消可能失败: {resp.text}")

            return success
        except Exception as e:
            logger.error(f"取消失败: {e}")
            return False

    def get_top_countries(self, service: str = "dr", limit: int = 10) -> list:
        """
        获取指定服务最便宜的国家列表

        Args:
            service: 服务代码（默认"dr"表示OpenAI）
            limit: 返回数量

        Returns:
            国家列表，按价格排序
        """
        try:
            # 尝试多个API接口
            actions = ['getTopCountriesByService', 'getTopCountriesByServiceRank']

            for action in actions:
                try:
                    logger.info(f"尝试 {action}: service={service}")
                    resp = self._request({"action": action, "service": service}, timeout=30)

                    if resp.status_code == 200:
                        data = resp.json() if isinstance(resp.text, str) else resp.text

                        # 调试：打印原始数据
                        logger.info(f"原始响应数据: {str(data)[:500]}")

                        # 解析响应
                        countries = self._parse_top_countries(data, service)

                        if countries:
                            # 按价格排序
                            sorted_countries = sorted(countries, key=lambda x: (x.get('price', 999), -x.get('count', 0)))
                            logger.info(f"✅ 获取到 {len(sorted_countries)} 个国家")
                            return sorted_countries[:limit]

                except Exception as e:
                    logger.warning(f"{action} 失败: {e}")
                    continue

            logger.warning("所有API都失败，返回空列表")
            return []

        except Exception as e:
            logger.error(f"获取价格列表失败: {e}")
            return []

    def _parse_top_countries(self, data: any, service: str) -> list:
        """解析价格列表响应"""
        countries = []

        try:
            # 处理字符串响应
            if isinstance(data, str):
                import json
                data = json.loads(data)

            # 处理嵌套结构
            if isinstance(data, dict):
                # 尝试展开常见的包装字段
                for key in ['data', 'result', 'response', 'countries']:
                    if key in data:
                        data = data[key]
                        break

            # 解析数组
            if isinstance(data, list):
                for item in data:
                    country = self._parse_country_item(item)
                    if country:
                        countries.append(country)

            # 解析对象（key是国家代码）
            elif isinstance(data, dict):
                for key, value in data.items():
                    if key.isdigit() and isinstance(value, dict):
                        country = self._parse_country_item(value, country_code=key)
                        if country:
                            countries.append(country)

        except Exception as e:
            logger.error(f"解析价格数据失败: {e}")

        return countries

    def _parse_country_item(self, item: dict, country_code: str = None) -> dict:
        """解析单个国家项"""
        if not isinstance(item, dict):
            return None

        try:
            # 提取国家代码
            code = country_code or item.get('country') or item.get('countryId') or item.get('country_id') or item.get('id')

            # 提取价格
            price = item.get('price') or item.get('cost') or item.get('retail_price') or item.get('retailPrice')
            if price:
                price = float(str(price).replace('$', '').replace(',', ''))
            else:
                return None

            # 提取库存
            count = item.get('count') or item.get('qty') or item.get('available') or item.get('stock') or item.get('total') or 0
            if count:
                count = int(count)

            # 提取名称 - 扩展更多字段
            name = (
                item.get('name') or
                item.get('countryName') or
                item.get('country_name') or
                item.get('title') or
                item.get('text') or
                item.get('label') or
                item.get('countryText') or
                item.get('eng') or
                item.get('en') or
                None
            )

            # 如果API没返回名称，使用映射表
            if not name or name == '':
                try:
                    from country_names import get_country_name
                    name = get_country_name(str(code))
                except:
                    name = f"国家{code}"

            # 提取ISO代码
            iso_code = item.get('isoCode') or item.get('iso') or item.get('code') or item.get('iso2') or ''

            return {
                'heroSmsCountry': str(code),
                'apiName': str(name),
                'price': price,
                'count': count,
                'isoCode': str(iso_code).upper(),
            }

        except Exception as e:
            logger.error(f"解析国家项失败: {e}")
            return None


# 别名，方便导入
SMSService = HeroSMSService


# 测试代码
if __name__ == "__main__":
    import os

    # 使用你的API Key
    api_key = "f5ebbcdA48f70A3d3950631A44ce9b5e"

    # 创建服务
    sms = HeroSMSService(api_key)

    # 测试余额
    print("\n=== 测试余额 ===")
    balance = sms.get_balance()

    if balance < 0.5:
        print(f"❌ 余额不足: ${balance:.2f}")
        exit(1)

    print(f"✅ 余额充足: ${balance:.2f}")

    # 测试获取号码
    print("\n=== 测试获取号码 ===")
    print("国家: 52 (泰国 - OpenAI SMS最稳定)")

    choice = input("是否继续获取号码测试? (y/n): ").strip().lower()

    if choice == 'y':
        phone = sms.get_number(country="52")  # 泰国

        if phone:
            print(f"\n✅ 成功获取号码!")
            print(f"   手机号: {phone.number}")
            print(f"   激活ID: {phone.id}")
            print(f"   费用: ${phone.cost:.2f}")

            # 询问是否取消
            choice2 = input("\n立即取消退款? (y/n): ").strip().lower()

            if choice2 == 'y':
                sms.cancel(phone.id)
            else:
                print(f"号码已保留: {phone.number}")
                print(f"请在几分钟内使用")
        else:
            print("❌ 获取号码失败")
    else:
        print("\n跳过获取号码测试")

    print("\n✅ 测试完成!")
