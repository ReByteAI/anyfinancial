# Data sources (anyfinancial)

Price data comes from the Rebyte Financial Data Service — the read-only SQL
service the **anyfinancial** skill exposes (`/api/data/financial/sql`, Apache
DataFusion). `fetch_data.py` uses the anyfinancial CLI when present, else an
inline client with identical auth.

## Tables used

| Interval | Table | Columns |
|---|---|---|
| `1day` | `us.eod` | `ticker, t, o, h, l, c, v, n` |
| `1min` | `us.bars_1m` | `ticker, t, o, h, l, c, v, n` |

- `t` is a UTC `Timestamp(µs)`; `o/h/l/c` are Float64; `v` (volume) and `n`
  (trade count) are Int64.
- `us.eod` holds ~14M rows spanning **2021-06 → present** across US tickers.
- These are OHLCV bars only — **no bid/ask, no tick/quote data**.

## Discovering what's available

Always confirm with the anyfinancial workflow (catalog → schema → query):

```bash
python3 /code/anyfinancial/data/scripts/anyfinancial_cli.py catalog
python3 /code/anyfinancial/data/scripts/anyfinancial_cli.py schema us.eod
python3 /code/anyfinancial/data/scripts/anyfinancial_cli.py query \
  "SELECT count(*) n, min(t) oldest, max(t) newest FROM us.eod WHERE ticker='AAPL'"
```

## DataFusion SQL notes

- Time: `now()`, `to_timestamp('2024-01-01T00:00:00')`, `date_trunc`,
  `INTERVAL '7 days'`. **Not** `DATEADD`/`GETDATE()`/`TOP`.
- One read-only statement per request; page with `LIMIT` (the fetcher keyset-
  paginates on `t`).

## Coverage & quality caveats

- **Survivorship**: the table reflects tickers as identified today; it is not a
  point-in-time index membership set. Delisted names may be absent.
- **Corporate actions**: verify whether prices are split/dividend adjusted for
  your window before spanning a known split. `us.eod` is raw OHLCV — apply your
  own adjustment if needed.
- **Freshness**: `us.eod` typically lands the prior trading day; intraday
  `us.bars_1m` is delayed. Do not assume same-day bars exist.
- **Volume/precision**: equity prices use 2-decimal precision in the runner
  (`venue.price_precision`); adjust for sub-penny or high-priced instruments.

## Cache layout

`fetch_data.py` writes CSV (dependency-free, inspectable):

```
<cache_dir>/<table>/<TICKER>__<interval>.csv     # header: t,o,h,l,c,v
```

Re-running is incremental at the file level: existing files are skipped unless
`--force`. Delete a file (or use `--force`) to re-pull a ticker.
