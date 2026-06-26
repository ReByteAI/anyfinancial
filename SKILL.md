---
name: anyfinancial
description: Query Rebyte Financial Data Service with read-only SQL through the Relay Data API. Use when an agent needs to discover financial tables, read a table's exact schema, and run read-only SQL from a Rebyte VM/workspace or compatible environment.
---

# AnyFinancial

Read-only SQL access to Rebyte Financial Data Service through the Relay Data API
(`/api/data/financial`). Always work in three steps: **catalog → schema → query.**

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
curl -fsS -X POST "$API_URL/api/data/financial/catalog" \
  -H "Authorization: Bearer $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{}' | jq '.'
```

Returns one row per table with `table_schema`, `table_name`, `table_type`. Pick the fully-qualified table you need (e.g. `cn.bars_1m`).

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

## SQL rules

- Read-only, one statement per request.
- Allowed starts: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`.
- No mutating statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, …).
- Keep exploratory queries narrow: project only needed columns and add `LIMIT`.
- The catalog (step 1) and table schema (step 2) are the source of truth for table and column names.
