import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional

from bidict import bidict

import hummingbot.connector.exchange.felix.felix_constants as CONSTANTS
from hummingbot.connector.exchange.felix import felix_utils
from hummingbot.connector.exchange.felix import felix_web_utils as web_utils
from hummingbot.connector.exchange.felix.felix_order_book import FelixOrderBook
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class FelixAPIOrderBookDataSource(OrderBookTrackerDataSource):
    HEARTBEAT_TIME_INTERVAL = 30.0
    TRADE_STREAM_ID = 1
    DIFF_STREAM_ID = 2
    ONE_HOUR = 60 * 60

    _logger: Optional[HummingbotLogger] = None
    _trading_pair_symbol_map: Mapping[str, str] = {}
    _trading_pair_symbol_type_map: Mapping[str, int] = {}
    _mapping_initialization_lock = asyncio.Lock()

    def __init__(self,
                 trading_pairs: List[str],
                 api_factory: Optional[WebAssistantsFactory] = None,
                 throttler: Optional[AsyncThrottler] = None,
                 time_synchronizer: Optional[TimeSynchronizer] = None):
        super().__init__(trading_pairs)
        self._time_synchronizer = time_synchronizer
        self._throttler = throttler
        self._api_factory = api_factory or web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
        )
        self._order_book_create_function = lambda: OrderBook()
        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    @classmethod
    async def get_last_traded_prices(cls,
                                     trading_pairs: List[str],
                                     api_factory: Optional[WebAssistantsFactory] = None,
                                     throttler: Optional[AsyncThrottler] = None,
                                     time_synchronizer: Optional[TimeSynchronizer] = None) -> Dict[str, float]:
        """
        Return a dictionary the trading_pair as key and the current price as value for each trading pair passed as
        parameter

        :param trading_pairs: list of trading pairs to get the prices for
        :param api_factory: the instance of the web assistant factory to be used when doing requests to the server.
            If no instance is provided then a new one will be created.
        :param throttler: the instance of the throttler to use to limit request to the server. If it is not specified
        the function will create a new one.
        :param time_synchronizer: the synchronizer instance being used to keep track of the time difference with the
            exchange

        :return: Dictionary of associations between token pair and its latest price
        """
        tasks = [cls._get_last_traded_price(
            trading_pair=t_pair,
            api_factory=api_factory,
            throttler=throttler,
            time_synchronizer=time_synchronizer) for t_pair in
            trading_pairs]
        results = await safe_gather(*tasks)
        return {t_pair: result for t_pair, result in zip(trading_pairs, results)}

    @classmethod
    def trading_pair_symbol_map_ready(cls):
        """
        Checks if the mapping from exchange symbols to client trading pairs has been initialized
        :return: True if the mapping has been initialized, False otherwise
        """
        return len(cls._trading_pair_symbol_map) > 0

    @classmethod
    async def trading_pair_symbol_map(
            cls,
            api_factory: Optional[WebAssistantsFactory] = None,
            throttler: Optional[AsyncThrottler] = None,
            time_synchronizer: Optional[TimeSynchronizer] = None,
    ) -> Dict[str, str]:
        """
        Returns the internal map used to translate trading pairs from and to the exchange notation.
        In general this should not be used. Instead call the methods `exchange_symbol_associated_to_pair` and
        `trading_pair_associated_to_exchange_symbol`

        :param api_factory: the web assistant factory to use in case the symbols information has to be requested
        :param throttler: the throttler instance to use in case the symbols information has to be requested
        :param time_synchronizer: the synchronizer instance being used to keep track of the time difference with the
            exchange

        :return: bidirectional mapping between trading pair exchange notation and client notation
        """
        if not cls.trading_pair_symbol_map_ready():
            async with cls._mapping_initialization_lock:
                # Check condition again (could have been initialized while waiting for the lock to be released)
                if not cls.trading_pair_symbol_map_ready():
                    await cls._init_trading_pair_symbols(
                        api_factory=api_factory,
                        throttler=throttler,
                        time_synchronizer=time_synchronizer)

        return cls._trading_pair_symbol_map

    @classmethod
    def trading_pair_symbol_type(cls, trading_pair: str):
        return cls._trading_pair_symbol_type_map[trading_pair]

    @staticmethod
    async def exchange_symbol_associated_to_pair(
            trading_pair: str,
            api_factory: Optional[WebAssistantsFactory] = None,
            throttler: Optional[AsyncThrottler] = None,
            time_synchronizer: Optional[TimeSynchronizer] = None,
    ) -> str:
        """
        Used to translate a trading pair from the client notation to the exchange notation

        :param trading_pair: trading pair in client notation
        :param api_factory: the web assistant factory to use in case the symbols information has to be requested
        :param throttler: the throttler instance to use in case the symbols information has to be requested
        :param time_synchronizer: the synchronizer instance being used to keep track of the time difference with the
            exchange

        :return: trading pair in exchange notation
        """
        symbol_map = await FelixAPIOrderBookDataSource.trading_pair_symbol_map(
            api_factory=api_factory,
            throttler=throttler,
            time_synchronizer=time_synchronizer)
        return symbol_map.inverse[trading_pair]

    @staticmethod
    async def trading_pair_associated_to_exchange_symbol(
            symbol: str,
            api_factory: Optional[WebAssistantsFactory] = None,
            throttler: Optional[AsyncThrottler] = None,
            time_synchronizer: Optional[TimeSynchronizer] = None) -> str:
        """
        Used to translate a trading pair from the exchange notation to the client notation

        :param symbol: trading pair in exchange notation
        :param api_factory: the web assistant factory to use in case the symbols information has to be requested
        :param throttler: the throttler instance to use in case the symbols information has to be requested
        :param time_synchronizer: the synchronizer instance being used to keep track of the time difference with the
            exchange

        :return: trading pair in client notation
        """
        symbol_map = await FelixAPIOrderBookDataSource.trading_pair_symbol_map(
            api_factory=api_factory,
            throttler=throttler,
            time_synchronizer=time_synchronizer)
        return symbol_map[symbol]

    @staticmethod
    async def fetch_trading_pairs(
            throttler: Optional[AsyncThrottler] = None,
            api_factory: Optional[WebAssistantsFactory] = None,
            time_synchronizer: Optional[TimeSynchronizer] = None) -> List[str]:
        """
        Returns a list of all known trading pairs enabled to operate with

        :param api_factory: the web assistant factory to use in case the symbols information has to be requested
        :param throttler: the throttler instance to use in case the symbols information has to be requested
        :param time_synchronizer: the synchronizer instance being used to keep track of the time difference with the
            exchange

        :return: list of trading pairs in client notation
        """
        mapping = await FelixAPIOrderBookDataSource.trading_pair_symbol_map(
            throttler=throttler,
            api_factory=api_factory,
            time_synchronizer=time_synchronizer,
        )
        return list(mapping.values())

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        """
        Creates a local instance of the exchange order book for a particular trading pair
        :param trading_pair: the trading pair for which the order book has to be retrieved
        :return: a local copy of the current order book in the exchange
        """
        snapshot: Dict[str, Any] = await self.get_snapshot(trading_pair, 1000)
        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = FelixOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        order_book = self.order_book_create_function()
        order_book.apply_snapshot(snapshot_msg.bids, snapshot_msg.asks, snapshot_msg.update_id)
        return order_book

    async def listen_for_trades(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Reads the trade events queue. For each event creates a trade message instance and adds it to the output queue
        :param ev_loop: the event loop the method will run in
        :param output: a queue to add the created trade messages
        """
        message_queue = self._message_queue[CONSTANTS.TRADE_EVENT_TYPE]
        while True:
            try:
                json_msg = await message_queue.get()

                if "result" in json_msg:
                    continue
                if "t" not in json_msg:
                    self.logger().debug(f"Trade event doesn't have 't'(trade ID): {json_msg}")
                    continue
                trading_pair = await FelixAPIOrderBookDataSource.trading_pair_associated_to_exchange_symbol(
                    symbol=json_msg["s"],
                    api_factory=self._api_factory,
                    throttler=self._throttler,
                    time_synchronizer=self._time_synchronizer)
                trade_msg: OrderBookMessage = FelixOrderBook.trade_message_from_exchange(
                    json_msg, {"trading_pair": trading_pair})
                output.put_nowait(trade_msg)

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error when processing public trade updates from exchange")

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Reads the order diffs events queue. For each event creates a diff message instance and adds it to the
        output queue
        :param ev_loop: the event loop the method will run in
        :param output: a queue to add the created diff messages
        """
        message_queue = self._message_queue[CONSTANTS.DIFF_EVENT_TYPE]
        while True:
            try:
                json_msg = await message_queue.get()
                if "result" in json_msg:
                    continue
                trading_pair = await FelixAPIOrderBookDataSource.trading_pair_associated_to_exchange_symbol(
                    symbol=json_msg["s"],
                    api_factory=self._api_factory,
                    throttler=self._throttler,
                    time_synchronizer=self._time_synchronizer)
                order_book_message: OrderBookMessage = FelixOrderBook.diff_message_from_exchange(
                    json_msg, time.time(), {"trading_pair": trading_pair})
                output.put_nowait(order_book_message)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error when processing public order book updates from exchange")

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        This method runs continuously and request the full order book content from the exchange every hour.
        The method uses the REST API from the exchange because it does not provide an endpoint to get the full order
        book through websocket. With the information creates a snapshot messages that is added to the output queue
        :param ev_loop: the event loop the method will run in
        :param output: a queue to add the created snapshot messages
        """
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    try:
                        snapshot: Dict[str, Any] = await self.get_snapshot(trading_pair=trading_pair)
                        snapshot_timestamp: float = time.time()
                        snapshot_msg: OrderBookMessage = FelixOrderBook.snapshot_message_from_exchange(
                            snapshot,
                            snapshot_timestamp,
                            metadata={"trading_pair": trading_pair}
                        )
                        output.put_nowait(snapshot_msg)
                        self.logger().debug(f"Saved order book snapshot for {trading_pair}")
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.logger().error(f"Unexpected error fetching order book snapshot for {trading_pair}.",
                                            exc_info=True)
                        await self._sleep(5.0)
                await self._sleep(self.ONE_HOUR)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error.", exc_info=True)
                await self._sleep(5.0)

    async def listen_for_subscriptions(self):
        """
        Connects to the trade events and order diffs websocket endpoints and listens to the messages sent by the
        exchange. Each message is stored in its own queue.
        """
        ws_url = CONSTANTS.WSS_URL_1
        if self._trading_pairs:
            token_type = FelixAPIOrderBookDataSource.trading_pair_symbol_type(trading_pair=self._trading_pairs[0])
            ws_url = CONSTANTS.WSS_URL_1 if token_type != CONSTANTS.DEFAULT_TYPE else CONSTANTS.WSS_URL_2

        ws = None
        while True:
            try:
                ws: WSAssistant = await self._api_factory.get_ws_assistant()
                await ws.connect(ws_url=ws_url,
                                 ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
                await self._subscribe_channels(ws)

                async for ws_response in ws.iter_messages():
                    data = ws_response.data
                    if "data" in data:
                        data = data["data"]
                    if "result" in data:
                        continue
                    event_type = data.get("e")
                    if event_type in [CONSTANTS.DIFF_EVENT_TYPE, CONSTANTS.TRADE_EVENT_TYPE]:
                        self._message_queue[event_type].put_nowait(data)

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error occurred when listening to order book streams. Retrying in 5 seconds...",
                    exc_info=True,
                )
                await self._sleep(5.0)
            finally:
                ws and await ws.disconnect()

    async def get_snapshot(
            self,
            trading_pair: str,
            limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        Retrieves a copy of the full order book from the exchange, for a particular trading pair.

        :param trading_pair: the trading pair for which the order book will be retrieved
        :param limit: the depth of the order book to retrieve

        :return: the response from the exchange (JSON dictionary)
        """
        token_type = FelixAPIOrderBookDataSource.trading_pair_symbol_type(trading_pair=trading_pair)
        path = CONSTANTS.SNAPSHOT_PATH_URL if token_type == CONSTANTS.DEFAULT_TYPE else CONSTANTS.SNAPSHOT_PATH_URL_1
        params = {
            "symbol": await self.exchange_symbol_associated_to_pair(
                trading_pair=trading_pair,
                api_factory=self._api_factory,
                throttler=self._throttler,
                time_synchronizer=self._time_synchronizer)
        }
        if limit != 0:
            params["limit"] = str(limit)

        data = await web_utils.api_request(
            path=path,
            api_factory=self._api_factory,
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            token_type=token_type,
            params=params,
            method=RESTMethod.GET,
        )

        return data["data"] if token_type == CONSTANTS.DEFAULT_TYPE else data

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.
        :param ws: the websocket assistant used to connect to the exchange
        """
        try:
            trade_params = []
            depth_params = []
            for trading_pair in self._trading_pairs:
                symbol = await self.exchange_symbol_associated_to_pair(
                    trading_pair=trading_pair,
                    api_factory=self._api_factory,
                    throttler=self._throttler,
                    time_synchronizer=self._time_synchronizer)
                token_type = FelixAPIOrderBookDataSource.trading_pair_symbol_type(trading_pair=trading_pair)
                if token_type == 1:
                    symbol = symbol.lower()
                trade_params.append(f"{symbol}@trade")
                depth_params.append(f"{symbol}@depth@100ms" if token_type == 1 else f"{symbol}@depth")
            payload = {
                "method": "SUBSCRIBE",
                "params": trade_params,
                "id": 1
            }
            subscribe_trade_request: WSRequest = WSRequest(payload=payload)

            payload = {
                "method": "SUBSCRIBE",
                "params": depth_params,
                "id": 2
            }
            subscribe_orderbook_request: WSRequest = WSRequest(payload=payload)

            await ws.send(subscribe_trade_request)
            await ws.send(subscribe_orderbook_request)

            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...",
                exc_info=True
            )
            raise

    @classmethod
    async def _get_last_traded_price(cls,
                                     trading_pair: str,
                                     api_factory: WebAssistantsFactory,
                                     throttler: AsyncThrottler,
                                     time_synchronizer: TimeSynchronizer) -> float:

        params = {
            "symbol": await cls.exchange_symbol_associated_to_pair(
                trading_pair=trading_pair,
                api_factory=api_factory,
                throttler=throttler,
                time_synchronizer=time_synchronizer)
        }

        resp_json = await web_utils.api_request(
            path=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,
            api_factory=api_factory,
            throttler=throttler,
            time_synchronizer=time_synchronizer,
            params=params,
            method=RESTMethod.GET,
        )
        if "code" not in resp_json or resp_json["code"] != 0:
            raise Exception(resp_json["msg"])

        return float(resp_json["data"]["price"])

    @classmethod
    async def _init_trading_pair_symbols(
            cls,
            api_factory: Optional[WebAssistantsFactory] = None,
            throttler: Optional[AsyncThrottler] = None,
            time_synchronizer: Optional[TimeSynchronizer] = None):
        """
        Initialize mapping of trade symbols in exchange notation to trade symbols in client notation
        """
        mapping = bidict()
        type_mapping = {}

        try:
            data = await web_utils.api_request(
                path=CONSTANTS.SYMBOLS_PATH_URL,
                api_factory=api_factory,
                throttler=throttler,
                time_synchronizer=time_synchronizer,
                method=RESTMethod.GET,
            )
            if "code" not in data or data["code"] != 0:
                raise Exception(data["msg"])

            for symbol_data in filter(felix_utils.is_exchange_information_valid, data["data"]["list"]):
                trading_pair = combine_to_hb_trading_pair(base=symbol_data["baseAsset"],
                                                          quote=symbol_data["quoteAsset"])
                mapping[symbol_data["symbol"].replace("_", "") if symbol_data["type"] == 1 else symbol_data["symbol"]] = trading_pair
                type_mapping[trading_pair] = symbol_data["type"]

        except Exception as ex:
            cls.logger().error(f"There was an error requesting symbols ({str(ex)})")

        cls._trading_pair_symbol_map = mapping
        cls._trading_pair_symbol_type_map = type_mapping
