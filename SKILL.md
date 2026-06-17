---
name: anyfinancial
description: Financial data exploration skill for US market data. Use when an AI agent needs to discover available financial tables and columns, then query prices, news, fundamentals, dividends, settlement, or other US market datasets with SQL.
version: 1.0.0
authors:
  - AnyFinancial Team
---

## Overview

AnyFinancial is a specialized financial data skill. The agent workflow is deliberately simple:

1. Discover what tables and columns exist.
2. Write SQL to get the needed data.

Use the bundled CLI directly:

```bash
python3 scripts/anyfinancial_cli.py <command> [options]
```

The CLI is zero-configuration. It reads the data API key from `scripts/shared/constants.json`.

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

## Step 1 — Discover Tables And Columns

Always start here when the user asks for custom analysis, unfamiliar fields, joins, screening, or anything beyond a simple built-in lookup.

```bash
python3 scripts/anyfinancial_cli.py discover_schemas
```

For a narrow check:

```bash
python3 scripts/anyfinancial_cli.py discover_schemas --tables bars_1m
```

Use the discovered schema as the source of truth for table and column names before writing SQL.

## Step 2 — Write SQL To Get Data

Use `query` for custom data retrieval:

```bash
python3 scripts/anyfinancial_cli.py query "SELECT ticker, t, c FROM bars_1m WHERE ticker = 'AAPL' AND year = '2026' AND month = '6' ORDER BY t DESC LIMIT 5"
```

Use narrow column lists and `LIMIT` while exploring. Avoid selecting large embedding columns unless the user explicitly needs them.

### SQL Syntax Footnote

The SQL endpoint expects Data Fusion SQL syntax. Practical rules:

- For `bars_1m`, include `year` and `month` partition filters.
- For array ticker columns in `news` and `fundamentals`, use `ARRAY_CONTAINS(tickers, 'AAPL')`.
- Use ordinary SQL projection, filtering, ordering, grouping, and limits where supported.

## Convenience Commands

Use these only when they directly answer the request. For anything more complex, go back to Step 1 and Step 2.

```bash
python3 scripts/anyfinancial_cli.py price AAPL
python3 scripts/anyfinancial_cli.py news TSLA --limit 5
python3 scripts/anyfinancial_cli.py fundamentals MSFT --limit 3
```

## Decision Flow

```
User asks for financial data
  |
  +-- Simple latest price/news/fundamentals for one ticker?
  |     YES -> use price/news/fundamentals convenience command
  |
  +-- Anything custom, unfamiliar, broad, or multi-table?
        YES -> Step 1 discover_schemas -> Step 2 query
```

## Scenarios

### Discover Available Data

```bash
python3 scripts/anyfinancial_cli.py discover_schemas
```

### Latest Price

```bash
python3 scripts/anyfinancial_cli.py price AAPL
```

### Recent News

```bash
python3 scripts/anyfinancial_cli.py news AAPL --limit 5
```

### Latest Fundamentals

```bash
python3 scripts/anyfinancial_cli.py fundamentals AAPL --limit 5
```

### Custom Price Query

```bash
python3 scripts/anyfinancial_cli.py query "SELECT ticker, t, o, h, l, c, v FROM bars_1m WHERE ticker = 'AAPL' AND year = '2026' AND month = '6' ORDER BY t DESC LIMIT 20"
```

### Custom News Query

```bash
python3 scripts/anyfinancial_cli.py query "SELECT published_utc, title FROM news WHERE ARRAY_CONTAINS(tickers, 'AAPL') ORDER BY published_utc DESC LIMIT 5"
```
