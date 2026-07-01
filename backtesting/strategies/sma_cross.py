"""Example pluggable strategy: Simple Moving Average (SMA) crossover.

This is the reference implementation of the strategy contract the runner expects:

    * a frozen ``StrategyConfig`` subclass whose first two fields are
      ``instrument_id`` and ``bar_type`` (the runner injects these at runtime);
      every other field is a user-tunable parameter supplied via config ``params``.
    * a ``Strategy`` subclass that consumes bars and submits market orders.

Copy this file to make your own strategy, then point the config's
``strategy.path`` / ``strategy.config_path`` at your new classes.

*** Educational example — no alpha edge. Do not trade live. ***
"""
from __future__ import annotations

from decimal import Decimal

from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.indicators import SimpleMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy


class SMACrossConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal = Decimal("100")
    fast_period: PositiveInt = 10
    slow_period: PositiveInt = 30


class SMACross(Strategy):
    """Enter long when fast SMA >= slow SMA, flip short when it crosses back."""

    def __init__(self, config: SMACrossConfig) -> None:
        PyCondition.is_true(
            config.fast_period < config.slow_period,
            "fast_period must be less than slow_period",
        )
        super().__init__(config)
        self.instrument: Instrument | None = None
        self.fast = SimpleMovingAverage(config.fast_period)
        self.slow = SimpleMovingAverage(config.slow_period)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"No instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.fast)
        self.register_indicator_for_bars(self.config.bar_type, self.slow)
        self.subscribe_bars(self.config.bar_type)  # bar-only backtest: no request needed

    def on_bar(self, bar: Bar) -> None:
        if not self.indicators_initialized():
            return
        if bar.is_single_price():  # OHLC collapsed to one price -> no information
            return

        iid = self.config.instrument_id
        if self.fast.value >= self.slow.value:
            if self.portfolio.is_flat(iid):
                self._enter(OrderSide.BUY)
            elif self.portfolio.is_net_short(iid):
                self.close_all_positions(iid)
                self._enter(OrderSide.BUY)
        else:
            if self.portfolio.is_flat(iid):
                self._enter(OrderSide.SELL)
            elif self.portfolio.is_net_long(iid):
                self.close_all_positions(iid)
                self._enter(OrderSide.SELL)

    def _enter(self, side: OrderSide) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=self.instrument.make_qty(self.config.trade_size),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.close_all_positions(self.config.instrument_id)
