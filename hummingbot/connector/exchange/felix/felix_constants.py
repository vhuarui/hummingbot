from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.common import OrderType
from hummingbot.core.data_type.in_flight_order import OrderState

DEFAULT_TYPE = 2

HBOT_ORDER_ID_PREFIX = "FLX"
MAX_ORDER_ID_LEN = 32

# Base URL
REST_URL_1 = "https://api.binance.com/api"
REST_URL_2 = "https://trade.felix.com"
WSS_URL_1 = "wss://stream.binance.com/ws"
WSS_URL_2 = "wss://trade.felix.com/stream"

# Public API endpoints or FelixClient function
TICKER_PRICE_CHANGE_PATH_URL = "/v1/market/trading-pair"
SYMBOLS_PATH_URL = "/open/v1/common/symbols"
SNAPSHOT_PATH_URL_1 = "/v3/depth"
SNAPSHOT_PATH_URL = "/open/v1/market/depth"
SERVER_TIME_PATH_URL = "/open/v1/common/time"

# Private API endpoints or FelixClient function
ACCOUNTS_PATH_URL = "/open/v1/account/spot"
MY_TRADES_PATH_URL = "/open/v1/orders/trades"
CREATE_ORDER_PATH_URL = "/open/v1/orders"
CANCEL_ORDER_PATH_URL = "/open/v1/orders/cancel"
QUERY_ORDER_PATH_URL = "/open/v1/orders"
USER_STREAM_PATH_URL = "/open/v1/user-data-stream"

WS_HEARTBEAT_TIME_INTERVAL = 30

# Felix params

SIDE_BUY = '0'
SIDE_SELL = '1'

TIME_IN_FORCE_GTC = 'GTC'  # Good till cancelled
TIME_IN_FORCE_IOC = 'IOC'  # Immediate or cancel
TIME_IN_FORCE_FOK = 'FOK'  # Fill or kill

# Rate Limit Type
REQUEST_WEIGHT = "REQUEST_WEIGHT"

# Rate Limit time intervals
ONE_MINUTE = 60
ONE_SECOND = 1
ONE_DAY = 86400

MAX_REQUEST = 5000

# Order States
ORDER_STATE = {
    # "PENDING": OrderState.PENDING_CREATE,
    0: OrderState.OPEN,
    1: OrderState.PARTIALLY_FILLED,
    2: OrderState.FILLED,
    3: OrderState.CANCELED,
    4: OrderState.PENDING_CANCEL,
    5: OrderState.FAILED,
    6: OrderState.FAILED,
}

# Order States
ORDER_STATE_2 = {
    "PENDING": OrderState.PENDING_CREATE,
    "NEW": OrderState.OPEN,
    "FILLED": OrderState.FILLED,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "PENDING_CANCEL": OrderState.OPEN,
    "CANCELED": OrderState.CANCELED,
    "REJECTED": OrderState.FAILED,
    "EXPIRED": OrderState.FAILED,
}

ORDER_TYPE = {
    OrderType.LIMIT: "1",
    OrderType.MARKET: "2",
    OrderType.LIMIT_MAKER: "1"
}

# Websocket event types
DIFF_EVENT_TYPE = "depthUpdate"
TRADE_EVENT_TYPE = "trade"

RATE_LIMITS = [
    # Pools
    RateLimit(limit_id=REQUEST_WEIGHT, limit=1200, time_interval=ONE_MINUTE),
    # Weighted Limits
    RateLimit(limit_id=TICKER_PRICE_CHANGE_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 1)]),
    RateLimit(limit_id=SYMBOLS_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[(LinkedLimitWeightPair(REQUEST_WEIGHT, 1))]),
    RateLimit(limit_id=SNAPSHOT_PATH_URL_1, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 2)]),
    RateLimit(limit_id=SNAPSHOT_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=USER_STREAM_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 1)]),
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 1)]),
    RateLimit(limit_id=ACCOUNTS_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=CREATE_ORDER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 1)]),
    RateLimit(limit_id=QUERY_ORDER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
]
