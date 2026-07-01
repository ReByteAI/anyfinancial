#!/usr/bin/env python3
"""Config-driven NautilusTrader backtest runner.

Reads a JSON config, loads cached bars (see fetch_data.py), builds an engine
with realistic fills + commission, plugs in a strategy by import path, runs, and
writes a metrics report. One runner, any strategy, any universe — not a
single-strategy script.

    python run_backtest.py --config my.config.json [--split in|out|full]

Design choices baked in from hard-won lessons:
  * Bars are built as ``Bar`` objects DIRECTLY from CSV — we do NOT use
    ``BarDataWrangler``, which under pandas 3.0 (copy-on-write) can raise
    "buffer source array is read-only".
  * Commission (FixedFeeModel) and slippage (FillModel) are wired from config so
    results are not the frictionless fantasy of a naive close-to-close loop.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

# Make strategy modules importable whether run from the skill root or elsewhere:
# add the current dir and the skill root (parent of scripts/) to sys.path.
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent)
for _p in (str(Path.cwd()), _SKILL_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import FillModel, FixedFeeModel
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import AccountType, AggregationSource, BarAggregation, OmsType, PriceType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider

AGG = {"1day": BarAggregation.DAY, "1min": BarAggregation.MINUTE}


def _load_class(spec: str):
    """Import 'package.module:ClassName'."""
    mod_name, _, cls_name = spec.partition(":")
    if not cls_name:
        raise ValueError(f"strategy spec must be 'module:Class', got {spec!r}")
    return getattr(importlib.import_module(mod_name), cls_name)


def _read_bars_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _split_rows(rows: list[dict], split: str, oos_frac: float) -> list[dict]:
    if split == "full" or oos_frac <= 0:
        return rows
    cut = int(len(rows) * (1 - oos_frac))
    return rows[:cut] if split == "in" else rows[cut:]


def build_bars(rows: list[dict], bar_type: BarType, price_prec: int) -> list[Bar]:
    bars = []
    for r in rows:
        ts = pd.Timestamp(r["t"], tz="UTC").value
        bars.append(Bar(
            bar_type=bar_type,
            open=Price(float(r["o"]), price_prec),
            high=Price(float(r["h"]), price_prec),
            low=Price(float(r["l"]), price_prec),
            close=Price(float(r["c"]), price_prec),
            volume=Quantity(float(r["v"]), 0),
            ts_event=ts, ts_init=ts,
        ))
    return bars


def compute_report(engine: BacktestEngine, venue: Venue, currency) -> dict[str, Any]:
    result = engine.get_result()
    acct = engine.portfolio.account(venue)
    stats = {**result.stats_pnls.get(currency.code, {}), **result.stats_returns}
    return {
        "run_id": str(result.run_id),
        "iterations": result.iterations,
        "total_orders": result.total_orders,
        "total_positions": result.total_positions,
        "final_balance": str(acct.balance_total(currency)),
        "stats_pnls": result.stats_pnls,
        "stats_returns": result.stats_returns,
        "_headline": {
            "pnl_pct": stats.get("PnL% (total)"),
            "sharpe_252": stats.get("Sharpe Ratio (252 days)"),
            "sortino_252": stats.get("Sortino Ratio (252 days)"),
            "win_rate": stats.get("Win Rate"),
            "profit_factor": stats.get("Profit Factor"),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a config-driven NautilusTrader backtest.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--split", choices=["in", "out", "full"], default="full",
                    help="Use in-sample, out-of-sample, or the full series (default: full).")
    ap.add_argument("--report", help="Write the JSON report to this path.")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    data, ven, strat, ev = cfg["data"], cfg["venue"], cfg["strategy"], cfg.get("evaluation", {})

    interval = data.get("interval", "1day")
    if interval not in AGG:
        print(f"Error: unsupported interval {interval!r}", file=sys.stderr)
        return 1
    table = (data.get("source_table") or {"1day": "us.eod", "1min": "us.bars_1m"}[interval]).replace(".", "_")
    cache_dir = Path(data.get("cache_dir", "data_cache"))
    tickers = data["tickers"]
    oos_frac = float(ev.get("oos_split", 0.0))
    price_prec = int(ven.get("price_precision", 2))

    venue = Venue(ven.get("name", "XNAS"))
    account_type = getattr(AccountType, ven.get("account_type", "MARGIN"))
    currency = USD  # extend here for multi-currency

    # Realistic frictions from config.
    fill_model = FillModel(
        prob_fill_on_limit=1.0,
        prob_slippage=float(ven.get("slippage_prob", 0.0)),
        random_seed=int(ev.get("random_seed", 42)),
    )
    commission = float(ven.get("commission_per_order_usd", 0.0))
    fee_model = FixedFeeModel(commission=Money(commission, USD)) if commission > 0 else None

    engine = BacktestEngine(config=BacktestEngineConfig(
        trader_id="BACKTESTER-001",
        logging=LoggingConfig(log_level=cfg.get("log_level", "ERROR"), log_colors=False),
    ))
    engine.add_venue(
        venue=venue, oms_type=OmsType.NETTING, account_type=account_type,
        base_currency=currency, starting_balances=[Money(ven["starting_balance"], currency)],
        fill_model=fill_model, fee_model=fee_model, bar_execution=True,
    )

    strat_cls = _load_class(strat["path"])
    cfg_cls = _load_class(strat["config_path"])
    params = dict(strat.get("params", {}))
    if "trade_size" in params:
        params["trade_size"] = Decimal(str(params["trade_size"]))

    loaded = {}
    for tk in tickers:
        instrument = TestInstrumentProvider.equity(tk, venue=venue.value)
        engine.add_instrument(instrument)
        bar_type = BarType(instrument.id, BarSpecification(1, AGG[interval], PriceType.LAST),
                            AggregationSource.EXTERNAL)
        csv_path = cache_dir / table / f"{tk}__{interval}.csv"
        if not csv_path.exists():
            print(f"Error: no cache for {tk} at {csv_path}. Run fetch_data.py first.", file=sys.stderr)
            return 1
        rows = _split_rows(_read_bars_csv(csv_path), args.split, oos_frac)
        bars = build_bars(rows, bar_type, price_prec)
        engine.add_data(bars)
        engine.add_strategy(strat_cls(cfg_cls(instrument_id=instrument.id, bar_type=bar_type, **params)))
        loaded[tk] = len(bars)

    print(f"run: split={args.split} tickers={loaded} "
          f"commission=${commission} slippage_prob={ven.get('slippage_prob', 0.0)}", file=sys.stderr)
    engine.run()
    report = compute_report(engine, venue, currency)
    report["config"] = {"run_name": cfg.get("run_name"), "split": args.split,
                        "interval": interval, "bars_per_ticker": loaded}
    engine.dispose()

    print(json.dumps(report, indent=2, default=str))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, default=str))
        print(f"\nreport -> {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
