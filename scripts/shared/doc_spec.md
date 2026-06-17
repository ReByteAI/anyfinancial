# AnyFinancial Interface Specification (for AI Agent)

## Protocol
- Endpoint: POST https://mcp.xyznot.com/v1/sql
- Format: raw **Data Fusion SQL** in the request body
- Headers:
  - `Content-Type: text/plain`
  - `Accept: application/json`
  - `X-API-Key: <API_KEY>`

## CLI Invocation ({{LANG_NAME}})

```{{LANG_CODEBLOCK}}
{{LANG_INVOKE}} <command> [options]
```

## Available Commands

### 1. discover_schemas - Discover known table schemas

Uses `DESCRIBE <table>` through the V1 SQL API for each known table.

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| --tables | string | no | Comma-separated table list. Default: bars_1m,news,fundamentals |
| --json | flag | no | Print raw JSON instead of Markdown |

### 2. query - Run arbitrary Data Fusion SQL

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| sql | string | YES | SQL query string. If omitted, SQL is read from stdin |
| --raw | flag | no | Print response body without JSON formatting |

### 3. price - Get latest price bars for a ticker

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| ticker | string | YES | Stock ticker |
| --year | string | no | bars_1m partition year. Defaults to current UTC year |
| --month | string | no | bars_1m partition month. Defaults to current UTC month without leading zero |
| --limit | int | no | Number of bars, default 1 |

### 4. fundamentals - Get company fundamentals

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| ticker | string | YES | Stock ticker |
| --limit | int | no | Number of filings/periods, default 5 |

### 5. news - Get latest news for a ticker

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| ticker | string | YES | Stock ticker |
| --limit | int | no | Number of articles, default 5 |

### 6. doc - Print this offline specification

No network request.

---

## Data Fusion SQL Tables

### bars_1m

Minute-level OHLCV price bars.

Important columns:

| Column | Meaning |
|--------|---------|
| ticker | Stock symbol |
| t | UTC timestamp |
| o | Open price |
| h | High price |
| l | Low price |
| c | Close price |
| v | Volume |
| year | String partition year |
| month | String partition month |

**Required performance rule:** `bars_1m` is partitioned by `year` and `month`. Include both in `WHERE` whenever querying this table:

```sql
WHERE ticker = 'AAPL' AND year = '2026' AND month = '6'
```

### news

Financial news articles.

Important columns:

| Column | Meaning |
|--------|---------|
| id | Article ID |
| published_utc | Publication timestamp |
| title | Headline |
| tickers | Array of mentioned tickers |
| content | Article text |
| content_embedding | Vector embedding; avoid selecting unless needed |

Ticker filtering:

```sql
WHERE ARRAY_CONTAINS(tickers, 'AAPL')
```

### fundamentals

SEC/XBRL-derived company fundamentals.

Important columns:

| Column | Meaning |
|--------|---------|
| company_name | Company name |
| tickers | Array of ticker symbols |
| fiscal_year | Fiscal year |
| fiscal_period | Fiscal period |
| start_date | Period start |
| end_date | Period end |
| is_net_income_loss | Net income/loss |
| is_revenues | Revenue |
| bs_assets | Balance-sheet assets |

The table has many more `is_*`, `bs_*`, `cf_*`, and `ci_*` columns. Run `discover_schemas` before using unfamiliar fields.

Ticker filtering:

```sql
WHERE ARRAY_CONTAINS(tickers, 'AAPL')
```

---

## Decision Flow

```
User query
  |
  +-- Latest ticker price?
  |     YES -> {{LANG_INVOKE}} price TICKER
  |
  +-- Recent ticker news?
  |     YES -> {{LANG_INVOKE}} news TICKER --limit N
  |
  +-- Fundamentals / revenue / net income / assets?
  |     YES -> {{LANG_INVOKE}} fundamentals TICKER --limit N
  |
  +-- Need custom SQL or multi-table analysis?
  |     YES -> discover_schemas if columns are uncertain, then query
```

---

## Scenario Examples (all runnable CLI commands)

### Scenario 1: Latest price

```bash
{{LANG_INVOKE}} price AAPL
```

### Scenario 2: Recent price bars

```bash
{{LANG_INVOKE}} price AAPL --year 2026 --month 6 --limit 5
```

### Scenario 3: Fundamentals

```bash
{{LANG_INVOKE}} fundamentals AAPL --limit 5
```

### Scenario 4: News

```bash
{{LANG_INVOKE}} news TSLA --limit 5
```

### Scenario 5: Schema discovery

```bash
{{LANG_INVOKE}} discover_schemas
```

### Scenario 6: Custom Data Fusion SQL

```bash
{{LANG_INVOKE}} query "SELECT ticker, t, o, h, l, c, v FROM bars_1m WHERE ticker = 'AAPL' AND year = '2026' AND month = '6' ORDER BY t DESC LIMIT 10"
```

### Scenario 7: Array ticker filtering

```bash
{{LANG_INVOKE}} query "SELECT published_utc, title FROM news WHERE ARRAY_CONTAINS(tickers, 'AAPL') ORDER BY published_utc DESC LIMIT 5"
```
