from typing import Any, Dict

from hummingbot.client.config.config_methods import using_exchange
from hummingbot.client.config.config_var import ConfigVar

CENTRALIZED = True
EXAMPLE_PAIR = "ZRX-ETH"
DEFAULT_FEES = [0.1, 0.1]


def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return exchange_info.get("spotTradingEnable", None) == 1


KEYS = {
    "felix_api_key":
        ConfigVar(key="felix_api_key",
                  prompt="Enter your Felix API key >>> ",
                  required_if=using_exchange("felix"),
                  is_secure=True,
                  is_connect_key=True),
    "felix_api_secret":
        ConfigVar(key="felix_api_secret",
                  prompt="Enter your Felix API secret >>> ",
                  required_if=using_exchange("felix"),
                  is_secure=True,
                  is_connect_key=True),
}
