# Backtesting domain knowledge

Read this *before* configuring a run. A backtest that ignores these produces
numbers that look great and mean nothing. The job of this skill is to stop that.

## The cardinal sins (each silently inflates results)

| Pitfall | What it is | Guard in this skill |
|---|---|---|
| **Look-ahead bias** | Using data the strategy could not have known at decision time (e.g. today's close to decide today's trade). | Event-driven engine: the strategy only sees each bar as it arrives. Never index "future" rows in a custom strategy. |
| **Survivorship bias** | Testing only tickers that exist today; delisted losers are missing. | Universe is user-chosen and *point-in-time-unaware*. State this limitation in every report. |
| **Overfitting / curve-fitting** | Tuning parameters until the past looks perfect. | In-sample/out-of-sample split (`evaluation.oos_split`). Tune on `--split in`, judge on `--split out`. |
| **Frictionless fills** | No commission, no slippage, fills at the exact price. | `commission_per_order_usd` + `slippage_prob` wired into the venue. Never report a zero-cost backtest as realistic. |
| **Warm-up leakage** | Trading before indicators have enough history. | Strategy waits for `indicators_initialized()`; set `evaluation.warmup_bars` ≥ slowest indicator period. |
| **Data-snooping** | Trying 100 strategies and reporting the best. | Report how many variants were tried; treat a single OOS pass as the real test. |

## Data granularity vs. strategy

- **Daily (`us.eod`)** — swing / position strategies, factor tests, multi-week
  holding. Cheap, long history (2021→today). Fills are bar-priced.
- **1-minute (`us.bars_1m`)** — intraday, scalping, execution studies. Large and
  slow to pull; bound the window tightly.
- A signal that needs the order book or the bid/ask spread **cannot** be
  realistically tested here — this data is OHLCV bars only, no quotes/ticks.

## Position sizing

- Fixed quantity (this skill's default `trade_size`) is simplest but ignores
  price level and volatility. A $100 trade in a $10 stock ≠ in a $1000 stock.
- Consider volatility-scaled or fixed-fractional sizing before drawing
  conclusions about risk-adjusted return.

## Metrics — what to actually look at

- **CAGR / total return** — headline, but meaningless without risk context.
- **Sharpe (252d)** — return per unit of total volatility. > 1 is decent for
  daily; be suspicious of > 3 on a short sample.
- **Sortino** — like Sharpe but only penalises downside volatility.
- **Max drawdown** — the worst peak-to-trough. The number that tells you whether
  you could actually have held the strategy.
- **Win rate + profit factor** — a low win rate can still be profitable if
  winners are large (profit factor = gross profit / gross loss).
- **Sample size** — 20 trades is a story, not evidence. Prefer 100+ and multiple
  market regimes.

## A healthy workflow

1. Form a hypothesis *before* looking at results.
2. Pick data range covering more than one regime (bull + drawdown).
3. Tune only on in-sample; leave out-of-sample untouched until the end.
4. Add realistic costs from the start, not as an afterthought.
5. Compare against a **baseline** (buy-and-hold the same universe).
6. Report drawdown and sample size next to any return figure.
7. Treat a good OOS result as a hypothesis to test live-paper, not a guarantee.
