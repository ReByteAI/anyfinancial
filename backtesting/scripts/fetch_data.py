#!/usr/bin/env python3
"""Fetch OHLCV bars from the anyfinancial data service into a local CSV cache.

Data layer
----------
This is the *data-retrieval* half of the backtesting skill. It reads price bars
from the Rebyte Financial Data Service — the same read-only SQL service the
``anyfinancial`` skill exposes (``/api/data/financial/sql``, Apache DataFusion).

Interval → source table:
    1day  -> us.eod       (columns: ticker, t, o, h, l, c, v, n)
    1min  -> us.bars_1m   (columns: ticker, t, o, h, l, c, v, n)

If the ``anyfinancial`` CLI is found (env ``ANYFINANCIAL_CLI`` or a common path)
it is used verbatim (honouring its read-only guard); otherwise an inline client
with identical auth resolution (env → ``rebyte-auth`` → ``auth.json``) is used.

Cache layout (CSV, dependency-free, human-inspectable):
    <cache_dir>/<table>/<TICKER>__<interval>.csv   with header t,o,h,l,c,v
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import request as urlrequest, error as urlerror

INTERVAL_TABLE = {"1day": "us.eod", "1min": "us.bars_1m"}
AUTH_JSON = "/home/user/.rebyte.ai/auth.json"
DEFAULT_API = "https://api.rebyte.ai"


# --------------------------------------------------------------------------- #
# auth (mirrors the anyfinancial resolution order)
# --------------------------------------------------------------------------- #
def _read_auth() -> dict[str, Any]:
    try:
        return json.loads(Path(AUTH_JSON).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _api_url() -> str:
    if os.environ.get("API_URL"):
        return os.environ["API_URL"].rstrip("/")
    url = _read_auth().get("sandbox", {}).get("relay_url")
    return (url or DEFAULT_API).rstrip("/")


def _token() -> str:
    if os.environ.get("AUTH_TOKEN"):
        return os.environ["AUTH_TOKEN"].strip()
    try:
        p = subprocess.run(["rebyte-auth"], capture_output=True, text=True, timeout=10)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return str(_read_auth().get("sandbox", {}).get("token") or "").strip()


# --------------------------------------------------------------------------- #
# SQL execution — prefer the anyfinancial CLI, fall back to an inline client
# --------------------------------------------------------------------------- #
def _find_cli() -> Optional[str]:
    cand = os.environ.get("ANYFINANCIAL_CLI")
    paths = [cand] if cand else []
    paths += [
        "/code/anyfinancial/data/scripts/anyfinancial_cli.py",
        str(Path.home() / "anyfinancial/data/scripts/anyfinancial_cli.py"),
    ]
    for p in paths:
        if p and Path(p).is_file():
            return p
    return None


def run_sql(sql: str, *, timeout: int = 120) -> list[dict[str, Any]]:
    cli = _find_cli()
    if cli:
        proc = subprocess.run(
            [sys.executable, cli, "query", sql],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"anyfinancial CLI failed: {proc.stderr.strip() or proc.stdout.strip()}")
        body = json.loads(proc.stdout)
        return _rows(body)
    # inline client
    token = _token()
    if not token:
        raise RuntimeError("no auth token (set AUTH_TOKEN, or provide rebyte-auth / auth.json)")
    url = _api_url() + "/api/data/financial/sql"
    data = json.dumps({"sql": sql, "parameters": []}).encode()
    req = urlrequest.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except urlerror.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode('utf-8','replace')}") from None
    if isinstance(body, dict) and body.get("success") is False:
        raise RuntimeError(f"SQL error: {body.get('error') or body}")
    return _rows(body)


def _rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ("rows", "data", "result", "results"):
            if isinstance(body.get(k), list):
                return body[k]
    return []


# --------------------------------------------------------------------------- #
def _resolve_end(end: str) -> str:
    if end in ("today", "now", ""):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return end


def fetch_ticker(table: str, ticker: str, start: str, end: str, *, page: int = 5000) -> list[dict]:
    """Keyset-paginate bars for one ticker over [start, end] (ascending by t)."""
    out: list[dict] = []
    cursor = f"{start}T00:00:00"
    while True:
        sql = (
            f"SELECT t, o, h, l, c, v FROM {table} "
            f"WHERE ticker = '{ticker}' "
            f"AND t > to_timestamp('{cursor}') "
            f"AND t <= to_timestamp('{end}T23:59:59') "
            f"ORDER BY t LIMIT {page}"
        )
        rows = run_sql(sql)
        if not rows:
            break
        out.extend(rows)
        cursor = rows[-1]["t"]
        if len(rows) < page:
            break
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        for r in rows:
            w.writerow([r["t"], r["o"], r["h"], r["l"], r["c"], r["v"]])


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch bars from anyfinancial into a local CSV cache.")
    ap.add_argument("--config", required=True, help="Backtest config JSON (uses its data section).")
    ap.add_argument("--force", action="store_true", help="Re-fetch even if a cache file exists.")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    data = cfg["data"]
    interval = data.get("interval", "1day")
    table = data.get("source_table") or INTERVAL_TABLE.get(interval)
    if not table:
        print(f"Error: unknown interval '{interval}'. Known: {list(INTERVAL_TABLE)}", file=sys.stderr)
        return 1
    tickers = data["tickers"]
    start = data["start"]
    end = _resolve_end(data.get("end", "today"))
    cache_dir = Path(cfg["data"].get("cache_dir", "data_cache"))

    print(f"fetch: table={table} interval={interval} tickers={tickers} range={start}..{end}", file=sys.stderr)
    summary = {}
    for tk in tickers:
        out = cache_dir / table.replace(".", "_") / f"{tk}__{interval}.csv"
        if out.exists() and not args.force:
            n = sum(1 for _ in out.open()) - 1
            print(f"  {tk}: cached ({n} bars) -> {out}", file=sys.stderr)
            summary[tk] = {"bars": n, "cached": True, "path": str(out)}
            continue
        rows = fetch_ticker(table, tk, start, end)
        write_csv(out, rows)
        print(f"  {tk}: fetched {len(rows)} bars -> {out}", file=sys.stderr)
        summary[tk] = {"bars": len(rows), "cached": False, "path": str(out)}

    print(json.dumps({"table": table, "interval": interval, "range": [start, end], "tickers": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
