# distutils: language=c++

from hummingbot.strategy.order_tracker import OrderTracker
from hummingbot.strategy.order_tracker cimport OrderTracker


cdef class WashTradingOrderTracker(OrderTracker):
    pass
