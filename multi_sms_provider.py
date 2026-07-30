"""
统一的SMS接码服务接口
支持多个平台：HeroSMS、SMSBower等
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from dataclasses import dataclass
import logging
from curl_cffi import requests

logger = logging.getLogger(__name__)


@dataclass
class PhoneNumber:
    """电话号码信息"""
    id: str                    # 激活ID
    number: str                # 完整号码（+86开头）
    country: str               # 国家代码
    service: str               # 服务代码
    cost: float                # 费用
    provider: str              # 平台名称
    raw_data: dict = None      # 原始响应数据


class SMSProviderBase(ABC):
    """SMS平台基类"""

    def __init__(self, api_key: str, service_code: str = "dr"):
        self.api_key = api_key
        self.service_code = service_code

    @abstractmethod
    def get_number(self, country: str) -> Optional[PhoneNumber]:
        """获取手机号"""
        pass

    @abstractmethod
    def get_code(self, activation_id: str, timeout: int = 180) -> Optional[str]:
        """获取验证码"""
        pass

    @abstractmethod
    def cancel(self, activation_id: str) -> bool:
        """取消并退款"""
        pass

    @abstractmethod
    def finish(self, activation_id: str) -> bool:
        """标记完成"""
        pass

    @abstractmethod
    def get_balance(self) -> Optional[float]:
        """获取余额"""
        pass

    @abstractmethod
    def get_countries(self) -> Dict[str, str]:
        """获取国家列表"""
        pass


class HeroSMSProvider(SMSProviderBase):
    """HeroSMS 平台实现"""

    def __init__(self, api_key: str, service_code: str = "dr"):
        super().__init__(api_key, service_code)
        self.base_url = "https://hero-sms.com/stubs/handler_api.php"
        self.provider_name = "HeroSMS"

    def _request(self, params: dict, timeout: int = 30) -> requests.Response:
        """发送API请求"""
        params["api_key"] = self.api_key
        return requests.get(
            self.base_url,
            params=params,
            timeout=timeout,
            impersonate="chrome110"
        )

    def get_number(self, country: str) -> Optional[PhoneNumber]:
        """获取手机号"""
        try:
            params = {
                "action": "getNumberV2",
                "service": self.service_code,
                "country": str(country)
            }

            resp = self._request(params)
            resp_text = resp.text.strip()

            logger.info(f"[{self.provider_name}] getNumberV2 响应: {resp_text[:200]}")

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
                        cost=float(data.get("activationCost", 0)),
                        provider=self.provider_name,
                        raw_data=data
                    )

                    logger.info(f"[{self.provider_name}] ✅ 获取号码成功: {phone} (ID: {activation_id})")
                    return result

            except Exception as json_err:
                logger.error(f"[{self.provider_name}] JSON解析失败: {json_err}")

            # 降级到 V1
            params["action"] = "getNumber"
            resp = self._request(params)
            resp_text = resp.text.strip()

            if resp_text.startswith("ACCESS_NUMBER:"):
                parts = resp_text.split(":")
                if len(parts) >= 3:
                    activation_id = parts[1]
                    phone = parts[2]
                    if not phone.startswith("+"):
                        phone = f"+{phone}"

                    result = PhoneNumber(
                        id=activation_id,
                        number=phone,
                        country=str(country),
                        service=self.service_code,
                        cost=0.0,
                        provider=self.provider_name
                    )

                    logger.info(f"[{self.provider_name}] ✅ 获取号码成功(V1): {phone} (ID: {activation_id})")
                    return result

            logger.warning(f"[{self.provider_name}] 无可用号码: {resp_text}")
            return None

        except Exception as e:
            logger.error(f"[{self.provider_name}] 获取号码失败: {e}")
            return None

    def get_code(self, activation_id: str, timeout: int = 180) -> Optional[str]:
        """获取验证码，超时后自动取消号码"""
        import time

        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1
            try:
                params = {
                    "action": "getStatus",
                    "id": activation_id
                }

                resp = self._request(params)
                status = resp.text.strip()

                if status.startswith("STATUS_OK:"):
                    code = status.split(":")[1]
                    logger.info(f"[{self.provider_name}] ✅ 收到验证码: {code}")
                    return code

                elif status == "STATUS_WAIT_CODE":
                    if attempt % 6 == 0:
                        logger.info(f"[{self.provider_name}] 等待验证码... ({int(time.time() - start_time)}s)")
                    time.sleep(5)

                elif status == "STATUS_CANCEL":
                    logger.warning(f"[{self.provider_name}] 号码已取消")
                    return None

                else:
                    logger.warning(f"[{self.provider_name}] 未知状态: {status}")
                    time.sleep(5)

            except Exception as e:
                logger.error(f"[{self.provider_name}] 获取验证码异常: {e}")
                time.sleep(5)

        logger.error(f"[{self.provider_name}] ❌ 超时未收到验证码 ({timeout}秒)")

        # 超时后自动取消号码
        logger.info(f"[{self.provider_name}] 尝试自动取消超时号码...")
        try:
            if self.cancel(activation_id):
                logger.info(f"[{self.provider_name}] ✅ 超时号码已自动取消并退款")
            else:
                logger.warning(f"[{self.provider_name}] ⚠️  超时号码取消失败（可能已过取消期限）")
        except Exception as e:
            logger.error(f"[{self.provider_name}] 自动取消异常: {e}")

        return None

    def cancel(self, activation_id: str) -> bool:
        """取消并退款"""
        try:
            params = {
                "action": "setStatus",
                "status": "8",  # 8 = 取消
                "id": activation_id
            }

            resp = self._request(params)
            result = resp.text.strip()

            if result == "ACCESS_CANCEL":
                logger.info(f"[{self.provider_name}] ✅ 取消成功: {activation_id}")
                return True
            else:
                logger.warning(f"[{self.provider_name}] 取消失败: {result}")
                return False

        except Exception as e:
            logger.error(f"[{self.provider_name}] 取消异常: {e}")
            return False

    def finish(self, activation_id: str) -> bool:
        """标记完成"""
        try:
            params = {
                "action": "setStatus",
                "status": "6",  # 6 = 完成
                "id": activation_id
            }

            resp = self._request(params)
            result = resp.text.strip()

            if result == "ACCESS_ACTIVATION":
                logger.info(f"[{self.provider_name}] ✅ 标记完成: {activation_id}")
                return True
            else:
                logger.warning(f"[{self.provider_name}] 标记完成失败: {result}")
                return False

        except Exception as e:
            logger.error(f"[{self.provider_name}] 标记完成异常: {e}")
            return False

    def get_countries_with_prices(self) -> list:
        try:
            params = {"api_key": self.api_key, "action": "getPrices", "service": self.service_code}
            resp = requests.get(self.base_url, params=params, timeout=15)
            data = resp.json()
            countries = []
            for code, price_info in data.items():
                try:
                    price = float(price_info["cost"]) if isinstance(price_info, dict) else float(price_info)
                    countries.append({"code": str(code), "price": price})
                except: pass
            countries.sort(key=lambda x: x["price"])
            return countries
        except:
            logger.warning(f"[{self.provider_name}] 无法获取国家价格")
            return []

    def get_balance(self) -> Optional[float]:
        """获取余额"""
        try:
            params = {"action": "getBalance"}
            resp = self._request(params)
            result = resp.text.strip()

            if result.startswith("ACCESS_BALANCE:"):
                balance = float(result.split(":")[1])
                logger.info(f"[{self.provider_name}] 余额: ${balance:.2f}")
                return balance

            logger.warning(f"[{self.provider_name}] 获取余额失败: {result}")
            return None

        except Exception as e:
            logger.error(f"[{self.provider_name}] 获取余额异常: {e}")
            return None

    def get_countries(self) -> Dict[str, str]:
        """获取国家列表"""
        try:
            params = {"action": "getCountries"}
            resp = self._request(params)
            data = resp.json()

            countries = {}
            for code, info in data.items():
                if isinstance(info, dict) and "eng" in info:
                    countries[code] = info["eng"]

            logger.info(f"[{self.provider_name}] 获取了 {len(countries)} 个国家")
            return countries

        except Exception as e:
            logger.error(f"[{self.provider_name}] 获取国家列表失败: {e}")
            return {}


class SMSBowerProvider(SMSProviderBase):
    """SMSBower 平台实现（API兼容HeroSMS）"""

    def __init__(self, api_key: str, service_code: str = "dr"):
        super().__init__(api_key, service_code)
        self.base_url = "https://smsbower.page/stubs/handler_api.php"
        self.provider_name = "SMSBower"

    def _request(self, params: dict, timeout: int = 30) -> requests.Response:
        """发送API请求"""
        params["api_key"] = self.api_key
        return requests.get(
            self.base_url,
            params=params,
            timeout=timeout,
            impersonate="chrome110"
        )

    def get_number(self, country: str) -> Optional[PhoneNumber]:
        """获取手机号（实现与HeroSMS相同）"""
        try:
            params = {
                "action": "getNumberV2",
                "service": self.service_code,
                "country": str(country)
            }

            resp = self._request(params)
            resp_text = resp.text.strip()

            logger.info(f"[{self.provider_name}] getNumberV2 响应: {resp_text[:200]}")

            try:
                data = resp.json()
                if isinstance(data, dict) and data.get("activationId"):
                    activation_id = str(data["activationId"])
                    phone_raw = str(data.get("phoneNumber", ""))
                    country_code = str(data.get("countryPhoneCode", ""))

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
                        cost=float(data.get("activationCost", 0)),
                        provider=self.provider_name,
                        raw_data=data
                    )

                    logger.info(f"[{self.provider_name}] ✅ 获取号码成功: {phone} (ID: {activation_id})")
                    return result

            except Exception:
                pass

            # 降级到 V1
            params["action"] = "getNumber"
            resp = self._request(params)
            resp_text = resp.text.strip()

            if resp_text.startswith("ACCESS_NUMBER:"):
                parts = resp_text.split(":")
                if len(parts) >= 3:
                    activation_id = parts[1]
                    phone = parts[2]
                    if not phone.startswith("+"):
                        phone = f"+{phone}"

                    result = PhoneNumber(
                        id=activation_id,
                        number=phone,
                        country=str(country),
                        service=self.service_code,
                        cost=0.0,
                        provider=self.provider_name
                    )

                    logger.info(f"[{self.provider_name}] ✅ 获取号码成功(V1): {phone} (ID: {activation_id})")
                    return result

            logger.warning(f"[{self.provider_name}] 无可用号码: {resp_text}")
            return None

        except Exception as e:
            logger.error(f"[{self.provider_name}] 获取号码失败: {e}")
            return None

    def get_code(self, activation_id: str, timeout: int = 180) -> Optional[str]:
        """获取验证码（实现与HeroSMS相同，超时自动取消）"""
        import time

        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1
            try:
                params = {
                    "action": "getStatus",
                    "id": activation_id
                }

                resp = self._request(params)
                status = resp.text.strip()

                if status.startswith("STATUS_OK:"):
                    code = status.split(":")[1]
                    logger.info(f"[{self.provider_name}] ✅ 收到验证码: {code}")
                    return code

                elif status == "STATUS_WAIT_CODE":
                    if attempt % 6 == 0:
                        logger.info(f"[{self.provider_name}] 等待验证码... ({int(time.time() - start_time)}s)")
                    time.sleep(5)

                elif status == "STATUS_CANCEL":
                    logger.warning(f"[{self.provider_name}] 号码已取消")
                    return None

                else:
                    logger.warning(f"[{self.provider_name}] 未知状态: {status}")
                    time.sleep(5)

            except Exception as e:
                logger.error(f"[{self.provider_name}] 获取验证码异常: {e}")
                time.sleep(5)

        logger.error(f"[{self.provider_name}] ❌ 超时未收到验证码 ({timeout}秒)")

        # 超时后自动取消号码
        logger.info(f"[{self.provider_name}] 尝试自动取消超时号码...")
        try:
            if self.cancel(activation_id):
                logger.info(f"[{self.provider_name}] ✅ 超时号码已自动取消并退款")
            else:
                logger.warning(f"[{self.provider_name}] ⚠️  超时号码取消失败（可能已过取消期限）")
        except Exception as e:
            logger.error(f"[{self.provider_name}] 自动取消异常: {e}")

        return None

    def cancel(self, activation_id: str) -> bool:
        """取消并退款"""
        try:
            params = {
                "action": "setStatus",
                "status": "8",
                "id": activation_id
            }

            resp = self._request(params)
            result = resp.text.strip()

            if result == "ACCESS_CANCEL":
                logger.info(f"[{self.provider_name}] ✅ 取消成功: {activation_id}")
                return True
            else:
                logger.warning(f"[{self.provider_name}] 取消失败: {result}")
                return False

        except Exception as e:
            logger.error(f"[{self.provider_name}] 取消异常: {e}")
            return False

    def finish(self, activation_id: str) -> bool:
        """标记完成"""
        try:
            params = {
                "action": "setStatus",
                "status": "6",
                "id": activation_id
            }

            resp = self._request(params)
            result = resp.text.strip()

            if result == "ACCESS_ACTIVATION":
                logger.info(f"[{self.provider_name}] ✅ 标记完成: {activation_id}")
                return True
            else:
                logger.warning(f"[{self.provider_name}] 标记完成失败: {result}")
                return False

        except Exception as e:
            logger.error(f"[{self.provider_name}] 标记完成异常: {e}")
            return False

    def get_countries_with_prices(self) -> list:
        try:
            params = {"api_key": self.api_key, "action": "getPrices", "service": self.service_code}
            resp = requests.get(self.base_url, params=params, timeout=15)
            data = resp.json()
            countries = []
            for code, price_info in data.items():
                try:
                    price = float(price_info["cost"]) if isinstance(price_info, dict) else float(price_info)
                    countries.append({"code": str(code), "price": price})
                except: pass
            countries.sort(key=lambda x: x["price"])
            return countries
        except:
            logger.warning(f"[{self.provider_name}] 无法获取国家价格")
            return []

    def get_balance(self) -> Optional[float]:
        """获取余额"""
        try:
            params = {"action": "getBalance"}
            resp = self._request(params)
            result = resp.text.strip()

            if result.startswith("ACCESS_BALANCE:"):
                balance = float(result.split(":")[1])
                logger.info(f"[{self.provider_name}] 余额: ${balance:.2f}")
                return balance

            logger.warning(f"[{self.provider_name}] 获取余额失败: {result}")
            return None

        except Exception as e:
            logger.error(f"[{self.provider_name}] 获取余额异常: {e}")
            return None

    def get_countries(self) -> Dict[str, str]:
        """获取国家列表"""
        try:
            params = {"action": "getCountries"}
            resp = self._request(params)
            data = resp.json()

            countries = {}
            for code, info in data.items():
                if isinstance(info, dict) and "eng" in info:
                    countries[code] = info["eng"]

            logger.info(f"[{self.provider_name}] 获取了 {len(countries)} 个国家")
            return countries

        except Exception as e:
            logger.error(f"[{self.provider_name}] 获取国家列表失败: {e}")
            return {}


class MultiProviderSMS:
    """
    多平台SMS服务管理器
    自动在多个平台间切换，选择最优平台
    """

    def __init__(self, providers: List[SMSProviderBase], max_price: float = None):
        self.providers = providers
        self.current_provider: Optional[SMSProviderBase] = None
        self.current_phone: Optional[PhoneNumber] = None
        self.max_price = max_price  # 价格上限

    def get_number(self, country: str, max_attempts: int = 3, max_price: float = None) -> Optional[PhoneNumber]:
        """
        获取号码 - 自动尝试所有平台

        Args:
            country: 国家代码（在所有平台上保持一致）
            max_attempts: 每个平台的最大尝试次数
            max_price: 价格上限（可选），超过此价格的号码会被拒绝并重试

        Returns:
            PhoneNumber 或 None
        """
        # 使用实例级别或调用级别的价格上限
        price_limit = max_price if max_price is not None else self.max_price

        logger.info(f"🌍 目标国家: {country} (所有平台将使用相同国家代码)")

        for provider in self.providers:
            logger.info(f"🔄 尝试平台: {provider.provider_name} - 国家: {country}")
            if price_limit is not None:
                logger.info(f"💰 价格上限: ${price_limit:.4f}")

            for attempt in range(1, max_attempts + 1):
                phone = provider.get_number(country)

                if phone:
                    # 验证国家代码一致性
                    if phone.country != str(country):
                        logger.error(
                            f"⚠️  国家代码不一致！请求: {country}, 返回: {phone.country}"
                        )

                    # 检查价格限制
                    if price_limit is not None and phone.cost > price_limit:
                        logger.warning(
                            f"⚠️  号码价格 ${phone.cost:.4f} 超过上限 ${price_limit:.4f}，"
                            f"尝试 {attempt}/{max_attempts}"
                        )
                        # 取消这个号码并退款
                        provider.cancel(phone.id)
                        continue

                    self.current_provider = provider
                    self.current_phone = phone
                    logger.info(
                        f"✅ 成功从 {provider.provider_name} 获取号码 "
                        f"(国家: {phone.country}, 价格: ${phone.cost:.4f})"
                    )
                    return phone

                logger.warning(f"⚠️  {provider.provider_name} 尝试 {attempt}/{max_attempts} 失败")

            logger.warning(f"❌ {provider.provider_name} 无可用号码，切换到下一个平台")

        logger.error("❌ 所有平台都无可用号码")
        return None

    def get_code(self, activation_id: str = None, timeout: int = 180) -> Optional[str]:
        """获取验证码"""
        if not self.current_provider:
            logger.error("没有活动的平台")
            return None

        if not activation_id and self.current_phone:
            activation_id = self.current_phone.id

        if not activation_id:
            logger.error("没有激活ID")
            return None

        return self.current_provider.get_code(activation_id, timeout)

    def cancel(self, activation_id: str = None) -> bool:
        """取消当前号码并退款"""
        if not self.current_provider:
            logger.warning("没有活动的平台，无法取消")
            return False

        if not activation_id and self.current_phone:
            activation_id = self.current_phone.id

        if not activation_id:
            logger.warning("没有激活ID，无法取消")
            return False

        result = self.current_provider.cancel(activation_id)
        if result:
            logger.info(f"✅ 号码 {activation_id} 已取消并退款")
        else:
            logger.error(f"❌ 号码 {activation_id} 取消失败")
        return result

    def cancel_number(self, activation_id: str = None) -> bool:
        """取消号码的别名方法（兼容性）"""
        return self.cancel(activation_id)

    def finish(self, activation_id: str = None) -> bool:
        """标记完成"""
        if not self.current_provider:
            return False

        if not activation_id and self.current_phone:
            activation_id = self.current_phone.id

        if not activation_id:
            return False

        return self.current_provider.finish(activation_id)

    def get_all_balances(self) -> Dict[str, float]:
        """获取所有平台的余额"""
        balances = {}
        for provider in self.providers:
            balance = provider.get_balance()
            if balance is not None:
                balances[provider.provider_name] = balance
        return balances


# 工厂函数
def create_sms_service(
    herosms_key: str = None,
    smsbower_key: str = None,
    service_code: str = "dr",
    max_price: float = None
) -> MultiProviderSMS:
    """
    创建SMS服务实例

    Args:
        herosms_key: HeroSMS API密钥
        smsbower_key: SMSBower API密钥
        service_code: 服务代码（默认"dr"=OpenAI）
        max_price: 价格上限（可选），例如 0.05 表示最多$0.05

    Returns:
        MultiProviderSMS实例
    """
    providers = []

    if herosms_key:
        providers.append(HeroSMSProvider(herosms_key, service_code))

    if smsbower_key:
        providers.append(SMSBowerProvider(smsbower_key, service_code))

    if not providers:
        raise ValueError("至少需要提供一个平台的API密钥")

    return MultiProviderSMS(providers, max_price=max_price)
