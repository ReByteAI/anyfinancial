# NautilusTrader patterns & gotchas (v1.230)

Verified against `nautilus_trader 1.230.0`, Python 3.13, pandas 3.0.

## Engine assembly order

```
BacktestEngine(config=BacktestEngineConfig(logging=...))
  → add_venue(venue, oms_type, account_type, base_currency,
              starting_balances=[Money(...)], fill_model=, fee_model=,
              bar_execution=True)
  → add_instrument(instrument)          # once per ticker
  → add_data(bars)                      # list[Bar], per instrument
  → add_strategy(Strategy(StrategyConfig(...)))
  → run()
  → get_result() / portfolio.account(venue)
  → dispose()
```

## Building bars — do NOT use BarDataWrangler

Under **pandas 3.0 copy-on-write**, `BarDataWrangler.process(df)` can raise
`ValueError: buffer source array is read-only` — the Cython layer receives a
read-only numpy buffer from certain DataFrame operations (e.g. `.astype()`).
It is operation-dependent and therefore an unreliable trap for real data.

**This skill builds `Bar` objects directly** (see `run_backtest.py:build_bars`):

```python
ts = pd.Timestamp(row["t"], tz="UTC").value        # ns since epoch, UTC
Bar(bar_type=bt,
    open=Price(float(row["o"]), 2), high=Price(float(row["h"]), 2),
    low=Price(float(row["l"]), 2),  close=Price(float(row["c"]), 2),
    volume=Quantity(float(row["v"]), 0),
    ts_event=ts, ts_init=ts)
```

If you must use the wrangler, first force a writable buffer:
`np.ascontiguousarray(col.to_numpy(), dtype="float64")` per column.

## BarType

```python
BarType(instrument.id,
        BarSpecification(1, BarAggregation.DAY, PriceType.LAST),
        AggregationSource.EXTERNAL)     # EXTERNAL = pre-aggregated bars we supply
```

Use `BarAggregation.MINUTE` for 1-minute data. The strategy's `bar_type` must
match the one attached to the data.

## Realistic frictions

- **Slippage**: `FillModel(prob_fill_on_limit=1.0, prob_slippage=p, random_seed=s)`
  passed as `add_venue(fill_model=...)`.
- **Commission**: `FixedFeeModel(commission=Money(x, USD))` as
  `add_venue(fee_model=...)`. `MakerTakerFeeModel()` uses per-instrument
  maker/taker fees instead.
- `bar_execution=True` lets orders fill against bar prices (required for a
  bar-only backtest with no quotes).

## Strategy contract (what the runner plugs in)

- A `StrategyConfig(frozen=True)` subclass. First two fields **must** be
  `instrument_id: InstrumentId` and `bar_type: BarType` (runner injects them);
  the rest are user params from config `params`.
- A `Strategy` subclass: `on_start` (resolve instrument, register indicators,
  `subscribe_bars`), `on_bar` (guard on `indicators_initialized()`, submit via
  `order_factory.market(...)`), optional `on_stop` (`close_all_positions`).
- In a bar-only backtest set `request_bars=False` / don't subscribe to ticks —
  there is no data client to serve historical requests or trade ticks.
- `Decimal` for `trade_size`; the runner converts config numbers to `Decimal`.

## Results

`engine.get_result()` exposes `total_orders`, `total_positions`, `iterations`,
`stats_pnls[currency]` (PnL total/%, win rate, expectancy) and `stats_returns`
(Sharpe/Sortino 252d, volatility, profit factor). `portfolio.account(venue)
.balance_total(USD)` is the ending balance. A single `run_id` is generated per
run (varies between runs — not a determinism bug).

## Install

Prebuilt `cp311`–`cp313` manylinux/macOS wheels (~175 MB, no compiler). Pin a
version for reproducibility. A fresh venv per project avoids dependency drift
(pandas/numpy majors move fast and Nautilus tracks them).
