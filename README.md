# AnyFinancial

Specialized financial data skill for AI agents. Use this repo when an agent needs US market data through the bundled CLI.

## Status

Beta. No access setup is needed right now; this may change later.

## Data Available

- Daily financial news with ticker-linked articles
- Tick data / OHLCV bars
- End-of-day data
- 1-minute bar data, updated daily, not real-time
- Fundamental data: income statement, balance sheet, cash flow
- Dividend yield data
- Settlement data
- US market coverage only

All data is daily-refreshed. This is not streaming or real-time market data.

## CLI

Zero configuration. The CLI reads the hardcoded xyznot API key from `scripts/shared/constants.json`.

One-line usage:

```bash
python3 scripts/anyfinancial_cli.py discover_schemas
python3 scripts/anyfinancial_cli.py price AAPL
python3 scripts/anyfinancial_cli.py news TSLA --limit 5
python3 scripts/anyfinancial_cli.py fundamentals MSFT --limit 3
python3 scripts/anyfinancial_cli.py query "SELECT ticker, t, c FROM bars_1m WHERE ticker = 'AAPL' AND year = '2026' AND month = '6' ORDER BY t DESC LIMIT 5"
python3 scripts/anyfinancial_cli.py doc
```

## SQL Rules

- For `bars_1m`, always include `year` and `month` filters.
- For ticker arrays in `news` and `fundamentals`, use `ARRAY_CONTAINS(tickers, 'AAPL')`.
- Run `discover_schemas` before using unfamiliar columns.
