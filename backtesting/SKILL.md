---
version: 1
name: backtesting
description: Run realistic event-driven backtests of trading strategies with NautilusTrader on real US market data retrieved via anyfinancial. Use this skill whenever the user wants to backtest, simulate, or evaluate a trading strategy, test a signal or indicator on historical prices, measure Sharpe/drawdown/returns, run in-sample vs out-of-sample, walk-forward, or compare strategy parameters — even if they don't say the word "backtest". Triggers include "backtest", "test this strategy", "simulate trading", "historical performance", "Sharpe ratio", "walk forward", "in-sample/out-of-sample", "does this strategy work". Do NOT use for live/real-money trading, single-quote lookups (use stock-analysis), or plain SQL data pulls (use anyfinancial).
---

# Backtesting

Realistic, event-driven strategy backtesting. **NautilusTrader** is the engine
(no look-ahead, real order/fill/commission accounting); **anyfinancial** is the
data layer (US OHLCV bars via read-only SQL). A small framework, run in phases —
not a one-off script.

This skill runs **local simulations on historical data only**. It never places
real orders and has no brokerage connectivity.

## How an agent uses this skill

Work through the five phases **in order**. Each phase has a **Goal**, the
**Actions** to take, and a **Gate** — a condition that must hold before you move
on. Do not skip a gate; skipping is how look-ahead bias and frictionless-fantasy
results sneak in.

```
Phase 1  SETUP        install + verify the engine
Phase 2  PARAMETERS   ask the user the forms below, write <run>.config.json
Phase 3  DATA         fetch bars via anyfinancial, validate coverage
Phase 4  EXECUTE      run in-sample, then out-of-sample, in NautilusTrader
Phase 5  REPORT       results in the fixed template, with caveats
```

**Read `references/domain_knowledge.md` before Phase 2.** Steering the user away
from look-ahead bias, overfitting, and zero-cost fills is the *point* of this
skill — raise those trade-offs while collecting parameters, not after a run.

---

## Phase 1 — Setup / install

**Goal:** a working engine venv.

**Actions:**
```bash
bash scripts/setup.sh                 # creates .venv-backtest, installs nautilus_trader + requests, self-verifies
source .venv-backtest/bin/activate
```
Prebuilt wheels (cp311–cp313, ~175 MB, no compiler). Data needs Rebyte API auth
(`AUTH_TOKEN` / `rebyte-auth` / `auth.json`) — resolved automatically. Engine
internals and version notes: `references/nautilus_patterns.md`.

**Gate:** `setup.sh` printed a `nautilus_trader <version>` line and `OK`.

---

## Phase 2 — Parameter collection (ask the user)

**Goal:** a complete `<run>.config.json`, with the user's informed choices.

**Actions:** Ask the two forms below with `AskUserQuestion` (skip any parameter
the user already gave; otherwise apply the **(Recommended)** option). Explain the
trade-off when it matters — especially costs and the OOS split. Then copy
`config.example.json` to `<run>.config.json` and fill it in from the answers
(mapping shown after the forms).

### Form A — Strategy & scope (one AskUserQuestion call, 4 questions)

- **Universe** — *header:* `Universe`
  - `Large-cap tech sample (Recommended)` — AAPL, MSFT, NVDA, AMZN, GOOGL
  - `Single ticker` — AAPL only (fastest to reason about)
  - `Diversified sample` — AAPL, JPM, XOM, JNJ, PG (cross-sector)
  - *(Other → user gives a custom ticker list)*
  - > Note in your ask: any hand-picked set is **not** survivorship-bias-free.
- **Date range** — *header:* `Date range`
  - `2022-01-01 → today (Recommended)` — spans a bear market + recovery
  - `Last 12 months` — recent regime only
  - `2021-06 → today` — maximum daily history available (`us.eod` starts 2021-06)
  - *(Other → custom start/end)*
- **Interval** — *header:* `Interval`
  - `Daily (Recommended)` — swing/position; cheap, long history (`us.eod`)
  - `1-minute intraday` — `us.bars_1m`; large and slow, bound the window
- **Strategy** — *header:* `Strategy`
  - `SMA crossover — built-in (Recommended)` — `strategies/sma_cross.py`
  - `EMA crossover — built-in` — bundled `nautilus_trader` example
  - *(Other → user wants a custom strategy; you'll write one, see Phase 4)*

### Form B — Capital & realism (one AskUserQuestion call, 3 questions)

- **Capital & account** — *header:* `Capital`
  - `$100k, MARGIN (Recommended)`
  - `$100k, CASH` — no shorting/leverage
  - `$1M, MARGIN`
  - *(Other → custom balance/account)*
- **Costs** — *header:* `Costs`
  - `$1/order + slippage 0.1 (Recommended)` — a reasonable retail baseline
  - `Higher: $5/order + slippage 0.3` — conservative / small-account
  - `Zero costs — frictionless` — ⚠️ not realistic; only for a sanity check
  - *(Other → custom commission/slippage)*
- **In-sample / out-of-sample split** — *header:* `OOS split`
  - `Hold out 30% (Recommended)` — tune on in-sample, judge on out-of-sample
  - `50 / 50` — stricter honesty, less tuning data
  - `No split — full series` — exploratory only; do not report as validated

### Answer → config mapping

| Answer | Config field |
|---|---|
| Universe | `data.tickers` |
| Date range | `data.start`, `data.end` (`"today"` allowed) |
| Interval | `data.interval` (`1day`→`us.eod`, `1min`→`us.bars_1m`) |
| Strategy | `strategy.path` + `strategy.config_path` + `strategy.params` |
| Capital & account | `venue.starting_balance`, `venue.account_type` |
| Costs | `venue.commission_per_order_usd`, `venue.slippage_prob` |
| OOS split | `evaluation.oos_split` |

Config schema (copy `config.example.json`):

```jsonc
{
  "run_name": "aapl_msft_sma_2024",
  "data":  { "source_table": "us.eod", "interval": "1day",
             "tickers": ["AAPL","MSFT"], "start": "2024-01-01",
             "end": "today", "cache_dir": "data_cache" },
  "venue": { "name": "XNAS", "account_type": "MARGIN", "base_currency": "USD",
             "starting_balance": 100000, "price_precision": 2,
             "commission_per_order_usd": 1.0, "slippage_prob": 0.1 },
  "strategy": { "path": "strategies.sma_cross:SMACross",
                "config_path": "strategies.sma_cross:SMACrossConfig",
                "params": { "fast_period": 10, "slow_period": 30, "trade_size": 100 } },
  "evaluation": { "oos_split": 0.3, "warmup_bars": 30, "random_seed": 42 }
}
```

**Gate:** `<run>.config.json` exists and every field is filled from a user
answer or a stated default. `strategy.params.slow_period` (or the slowest
indicator) ≤ `evaluation.warmup_bars`.

---

## Phase 3 — Data selection via anyfinancial

**Goal:** validated local bars for every ticker.

**Actions:**
```bash
python scripts/fetch_data.py --config <run>.config.json      # --force to re-pull
```
Pulls the config's tickers/range into `data_cache/` as CSV, from the
anyfinancial SQL service (`1day → us.eod`, `1min → us.bars_1m`). To explore
what's available first, use the anyfinancial workflow directly:
```bash
python3 /code/anyfinancial/data/scripts/anyfinancial_cli.py catalog
python3 /code/anyfinancial/data/scripts/anyfinancial_cli.py schema us.eod
```
Tables, DataFusion SQL, and data caveats: `references/data_sources.md`.

**Validate** the printed summary before running: each ticker returned enough
bars (≥ warmup + a meaningful test), the date range matches the request, and no
ticker came back near-empty (typo / delisted). If the window spans a known
split, confirm adjustment (see data_sources.md — `us.eod` is raw OHLCV).

**Gate:** every ticker has a non-trivial bar count and the coverage matches the
config.

---

## Phase 4 — Backtest execution (NautilusTrader)

**Goal:** in-sample and out-of-sample results.

**Actions:**
```bash
python scripts/run_backtest.py --config <run>.config.json --split in                 # tune here
python scripts/run_backtest.py --config <run>.config.json --split out --report out.json  # judge here
python scripts/run_backtest.py --config <run>.config.json --split full               # full-series view
```
One runner, any strategy, any universe. It builds the engine with commission +
slippage from the config, plugs in the configured strategy, runs event-driven,
and prints metrics (plus optional `--report` JSON).

**Swapping strategies is config-only** — point `strategy.path` /
`strategy.config_path` at any `Strategy`/`StrategyConfig` pair (a file in
`strategies/`, or a bundled one such as
`nautilus_trader.examples.strategies.ema_cross:EMACross`). To write a **custom
strategy**, copy `strategies/sma_cross.py` — it documents the plug-in contract
(first two config fields are `instrument_id` and `bar_type`, injected by the
runner). Engine assembly and the pandas-3.0 wrangler trap: `references/nautilus_patterns.md`.

**Gate:** in-sample and out-of-sample runs both completed and emitted metrics.

---

## Phase 5 — Results reporting

**Goal:** an honest report the user can act on.

**Actions:** Compare in-sample vs out-of-sample, and against buy-and-hold the
same universe. ALWAYS use this template:

```markdown
## Backtest: <run_name>
**Setup:** <universe> · <interval> · <start>→<end> · <strategy+params> · <capital/account> · costs <commission>/order, slippage <p>

| Metric | In-sample | Out-of-sample |
|---|---|---|
| Total return / PnL% | | |
| Sharpe (252d) | | |
| Max drawdown | | |
| Trades (orders/positions) | | |
| Final balance | | |

**Read:** <1–3 sentences: did OOS hold up vs in-sample? vs buy-and-hold?>
**Limitations:** bar-only fills (no order book); self-selected universe (survivorship);
costs modelled not exact; OOS is one pass, not a guarantee. <plus any data caveat hit>
```

A strong in-sample number that collapses out-of-sample is **overfitting** — say
so plainly. Never present a return without its drawdown and trade count.

**Gate:** report uses the template and states the limitations.

---

## Files

```
SKILL.md                      — this phase playbook
config.example.json           — copy per run → <run>.config.json
evals/evals.json              — sample tasks for skill testing (Skill Creator style)
scripts/setup.sh              — Phase 1: install + verify
scripts/fetch_data.py         — Phase 3: anyfinancial → local CSV cache
scripts/run_backtest.py       — Phase 4: config-driven runner (engine + report)
strategies/sma_cross.py       — example strategy + the plug-in contract
references/domain_knowledge.md — pitfalls, metrics, workflow (READ BEFORE Phase 2)
references/data_sources.md     — anyfinancial tables, SQL, data caveats
references/nautilus_patterns.md— engine assembly, wrangler trap, frictions
```
