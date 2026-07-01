---
name: anyfinancial
description: Query Rebyte Financial Data Service through the Relay Data API — read-only SQL over financial tables, plus semantic (vector) search over news. Use when an agent needs to discover financial tables, read a table's exact schema, run read-only SQL, or find news by meaning (not keywords) from a Rebyte VM/workspace or compatible environment.
---

# AnyFinancial

Access to Rebyte Financial Data Service through the Relay Data API
(`/api/data/financial`). Two modes:

- **SQL** (`/sql`) — read-only **Apache DataFusion SQL** (Spice.ai) over every table.
  Work in three steps: **catalog → schema → query.**
- **Semantic search** (`/search`) — vector search over datasets that carry content
  embeddings (news). Query by *meaning*, not keywords. See the last section.

## Authentication

```bash
AUTH_TOKEN="$(rebyte-auth 2>/dev/null || jq -r '.sandbox.token' /home/user/.rebyte.ai/auth.json)"
API_URL="$(jq -r '.sandbox.relay_url // empty' /home/user/.rebyte.ai/auth.json 2>/dev/null || true)"
API_URL="${API_URL:-https://api.rebyte.ai}"
```

If `AUTH_TOKEN` is empty or `null`, report that authentication is unavailable and stop. Do not invent credentials.

## 1. Fetch the catalog — list every table

```bash
python3 scripts/anyfinancial_cli.py catalog
```

```bash
curl -fsS -X POST "$API_URL/api/data/financial/sql" \
  -H "Authorization: Bearer $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"sql":"SHOW TABLES","parameters":[]}' | jq '.'
```

The catalog is `SHOW TABLES`. It returns every registered table as `table_schema`,
`table_name`, `table_type`. Ignore rows where `table_schema = information_schema`
(system tables). Pick the fully-qualified table you need (e.g. `cn.bars_1m`).

> Use `SHOW TABLES`, not `information_schema.tables` — the latter omits tables
> that are not currently served and gives an incomplete catalog.

## 2. Get a table's exact schema — before querying it

Read the real columns and types of every table you intend to query. Do not guess column names.

```bash
python3 scripts/anyfinancial_cli.py schema cn.bars_1m
```

```bash
curl -fsS -X POST "$API_URL/api/data/financial/sql" \
  -H "Authorization: Bearer $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"sql":"DESCRIBE cn.bars_1m","parameters":[]}' | jq '.'
```

Returns one row per column with `column_name`, `data_type`, `is_nullable`.

## 3. Query

```bash
python3 scripts/anyfinancial_cli.py query "SELECT trade_time, o, h, l, c, v FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
```

```bash
curl -fsS -X POST "$API_URL/api/data/financial/sql" \
  -H "Authorization: Bearer $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"sql":"SELECT trade_time, c FROM cn.bars_1m WHERE ts_code = '\''000001.SZ'\'' ORDER BY trade_time DESC LIMIT 10","parameters":[]}' | jq '.'
```

## Semantic search — find news by meaning (not keywords)

For news, prefer semantic search over `... WHERE content ILIKE '%...%'`. You send a
natural-language `text`; the service embeds it server-side and returns the most
similar rows ranked by `_score` (higher = more relevant). No keys, no embedding on
your side.

```bash
python3 scripts/anyfinancial_cli.py search "Fed rate cut expectations" --columns title,published_utc,tickers
```

```bash
curl -fsS -X POST "$API_URL/api/data/financial/search" \
  -H "Authorization: Bearer $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"Fed rate cut expectations","datasets":["us.news"],"limit":5,"additional_columns":["title","published_utc","tickers"]}' | jq '.'
```

Body fields: `text` (required, natural language) · `datasets` (default `["us.news"]`
— the only dataset with embeddings today) · `limit` (default 5) · `additional_columns`
(optional extra columns returned in each result's `data`).

Each result: `_score` (similarity), `matches.content` (hit snippets), `data` (the
columns you named in `additional_columns`), `dataset`.

> Only `us.news` is searchable today. Other tables are SQL-only — use the three-step
> SQL flow above for them.

## SQL dialect — Apache DataFusion (NOT Postgres / MySQL / T-SQL)

Write DataFusion SQL. These are verified to work:

| Need | Use |
|---|---|
| Current time | `now()` |
| Truncate to period | `date_trunc('day', trade_time)` |
| Bucket into N-minute bars | `date_bin(INTERVAL '5 minutes', trade_time, TIMESTAMP '1970-01-01')` |
| Relative time filter | `trade_time > now() - INTERVAL '7 days'` |
| Parse a timestamp | `to_timestamp('2024-01-01T00:00:00')` |
| Part of a date | `extract(year FROM trade_time)` |
| Cast | `CAST(x AS BIGINT)` or `arrow_cast(x, 'Int64')` |
| String concat / match | `a || b`, `col ILIKE 'a%'` |
| Paging | `LIMIT 100 OFFSET 0` |

Do **not** use (they error — switch syntax, do not retry as-is):
`DATEADD` / `DATEDIFF` / `GETDATE()` (use `now()`, `date_trunc`, `INTERVAL` math),
`TOP n` (use `LIMIT n`), `SELECT INTO`, stored procedures, or vendor-specific functions.

## Rules

- Read-only, one statement per request. Allowed starts: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`.
- No mutating statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, …).
- Project only needed columns and add `LIMIT` while exploring.
- The catalog (step 1) and table schema (step 2) are the source of truth for table and column names.

## On error — do not loop

If a query fails, do not resubmit the same or a near-identical statement. Instead:

1. Read the error message. `Invalid function` / `No field named …` means wrong dialect or wrong column → fix it using the DataFusion table above and the table schema from step 2.
2. Change exactly one thing and retry.
3. After 2–3 failed attempts, **stop** and report the exact failing SQL and the exact error. Do not keep retrying.
