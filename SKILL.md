---
name: anyfinancial
description: Financial data exploration and querying skill for Data Fusion SQL over xyznot market data, including price bars, company fundamentals, and financial news.
version: 1.0.0
authors:
  - AnyFinancial Team
---

## Overview

AnyFinancial is a Data Fusion SQL skill for financial market data exploration. It queries the xyznot V1 SQL endpoint directly and provides convenience commands for latest prices, fundamentals, news, arbitrary SQL, and schema discovery. Use the bundled CLI for routine financial questions and run `doc` only when the interface is unknown or a command fails due to argument uncertainty.

## Trigger

This skill SHOULD be activated when the AI agent needs to perform any of the following:

1. **Financial data exploration** — discovering available tables and columns before analysis.
2. **Market price queries** — latest or historical OHLCV bars for listed tickers.
3. **Company fundamentals** — revenue, net income, assets, fiscal periods, and SEC/XBRL-derived metrics.
4. **Financial news lookup** — recent articles for a ticker, including title, time, and content.
5. **Custom financial SQL** — joins, filters, aggregations, event studies, and backtest inputs using Data Fusion SQL.

**Rule:** This skill is for xyznot financial data, not general web search. For web results, use a search skill. For this skill, prefer the convenience commands (`price`, `fundamentals`, `news`) when they answer the request; use `discover_schemas` before custom SQL when column names are uncertain.

## Recommended Entry Point

Prefer direct CLI invocation. If `<skill_dir>/runtime.conf` exists and the requested command shape is already obvious (`price`, `fundamentals`, `news`, `query`, or `discover_schemas`), the agent SHOULD use the configured command directly and SHOULD NOT run `doc` on every activation. Run `doc` only when the CLI interface is unknown, the skill was just installed/updated, or a command fails due to argument/schema uncertainty.

### Command Cheat Sheet

Use these exact command shapes for routine calls. Replace `<cmd>` with the command from `runtime.conf` or `python3 <skill_dir>/scripts/anyfinancial_cli.py`.

```bash
# Offline CLI docs
<cmd> doc

# Discover schemas for known financial tables
<cmd> discover_schemas

# Arbitrary Data Fusion SQL
<cmd> query "SELECT ticker, t, c FROM bars_1m WHERE ticker = 'AAPL' AND year = '2026' AND month = '6' ORDER BY t DESC LIMIT 5"

# Convenience commands
<cmd> price AAPL
<cmd> price AAPL --year 2026 --month 6 --limit 5
<cmd> fundamentals AAPL --limit 5
<cmd> news TSLA --limit 10
```

Invalid examples: do not query `bars_1m` without `year` and `month` filters. Those partition predicates are required for practical performance.

**Security & Privacy notes:**
- The `doc` command is local-only and makes no network requests.
- SQL queries and API keys are sent to `https://mcp.xyznot.com/v1/sql`.
- Avoid sending private portfolios, unpublished trade plans, or secrets in SQL comments or query literals unless the user explicitly approves.

## API Key Management

The CLI is zero-configuration. It reads the xyznot API key directly from `scripts/shared/constants.json` and sends it as the `X-API-Key` header on every SQL request.

`.env.example` remains only as a reference for users who want to know what historical external configuration looked like.

## Platform Detection & CLI Routing

### Pre-detected Runtime

If `<skill_dir>/runtime.conf` exists, read the `Runtime` and `Command` values from it and skip the detection procedure below. Treat this as the normal fast path for routine financial queries.

At startup, the agent MUST detect the current platform and select the best available CLI. The priority order is:

```
Python  >  Shell
```

### Detection Procedure

**Step 1 — Check Python**
```
python --version 2>&1
python3 --version 2>&1
```
- If either `python` or `python3` exists with version >= 3.6, use `anyfinancial_cli.py`.
- Dependency: `requests` library, matching the AnySearch Python CLI pattern.

**Step 2 — Check Shell** (if Python failed)

Use shell only to report that Python is required for this skill. This repo intentionally ships the Python CLI as the authoritative runtime.

### CLI Invocation

| Runtime | Invocation |
|---------|-----------|
| Python | `python <skill_dir>/scripts/anyfinancial_cli.py <command> [options]` or `python3 <skill_dir>/scripts/anyfinancial_cli.py <command> [options]` |

### Fallback & Error Handling

- If a command fails due to missing columns, run `discover_schemas`.
- If a command fails due to malformed SQL, simplify the query and validate with `LIMIT`.
- If the API returns auth errors, inspect `scripts/shared/constants.json` and verify the hardcoded `api_key` value.

## Data Fusion SQL Decision Flow

Financial requests have three paths. Path 1 is the default for common ticker questions. Path 2 is for custom analysis. Path 3 is for schema uncertainty.

### Path 1 — Convenience command

Use for straightforward ticker lookups:

```bash
<cmd> price AAPL
<cmd> fundamentals AAPL --limit 3
<cmd> news AAPL --limit 5
```

### Path 2 — Custom SQL

Use for joins, aggregations, screening, backtests, and event studies:

```bash
<cmd> query "SELECT ... FROM ... WHERE ... LIMIT 100"
```

Always include `year` and `month` in `bars_1m` queries.

### Path 3 — Schema discovery

Use before writing unfamiliar SQL or when a query references a missing column:

```bash
<cmd> discover_schemas
```

```
User query
  |
  +-- Single ticker latest price/news/fundamentals?
  |     YES -> Path 1: convenience command
  |
  +-- Need custom joins, filters, aggregates, or backtest inputs?
  |     YES -> Path 2: query with Data Fusion SQL
  |
  +-- Unsure about tables/columns?
        YES -> Path 3: discover_schemas, then query
```

## Data Fusion SQL Constraints

Before issuing SQL, obey these constraints:

1. `bars_1m` is partitioned by string columns `year` and `month`. Include both in `WHERE`.
2. `news.tickers` and `fundamentals.tickers` are arrays. Filter them with `ARRAY_CONTAINS(tickers, 'AAPL')`.
3. Avoid `SELECT *` for wide tables and avoid `content_embedding` unless explicitly needed.
4. Use `LIMIT` while exploring.

## Scenario Examples (all runnable CLI commands)

### Scenario 1: Latest price

```bash
<cmd> price AAPL
```

### Scenario 2: Recent minute bars

```bash
<cmd> price MSFT --year 2026 --month 6 --limit 10
```

### Scenario 3: Latest company fundamentals

```bash
<cmd> fundamentals NVDA --limit 5
```

### Scenario 4: Latest ticker news

```bash
<cmd> news TSLA --limit 10
```

### Scenario 5: Discover table schemas

```bash
<cmd> discover_schemas
```

### Scenario 6: Custom SQL over price bars

```bash
<cmd> query "SELECT ticker, t, o, h, l, c, v FROM bars_1m WHERE ticker = 'AAPL' AND year = '2026' AND month = '6' ORDER BY t DESC LIMIT 20"
```

### Scenario 7: Custom SQL over array ticker columns

```bash
<cmd> query "SELECT published_utc, title FROM news WHERE ARRAY_CONTAINS(tickers, 'AAPL') ORDER BY published_utc DESC LIMIT 5"
```
