---
name: anyfinancial
description: Connect to Rebyte Financial Data Service to discover financial datasets and run read-only SQL through the Rebyte Relay API. Use when an AI agent needs financial data catalog inspection, schema discovery, or read-only financial SQL queries from a Rebyte VM/workspace or compatible environment.
---

# AnyFinancial

Use Rebyte Financial Data Service through the Relay API.

Important endpoints:

- User-facing app: `https://app.rebyte.ai/financial`
- Data Service API: `https://api.rebyte.ai/api/data`
- Inside a Rebyte VM/workspace, prefer the sandbox relay URL and token from `/home/user/.rebyte.ai/auth.json`.

The service is not hosted on `app.rebyte.ai`; use the Relay API.

## Authentication

Resolve auth before calling protected endpoints:

```bash
AUTH_TOKEN="$(rebyte-auth 2>/dev/null || jq -r '.sandbox.token' /home/user/.rebyte.ai/auth.json)"
API_URL="$(jq -r '.sandbox.relay_url // empty' /home/user/.rebyte.ai/auth.json 2>/dev/null || true)"
API_URL="${API_URL:-https://api.rebyte.ai}"
```

If `AUTH_TOKEN` is empty or `null`, report that authentication is unavailable and do not invent credentials.

## Required Workflow

1. Call catalog first.
2. Inspect available databases, schemas, tables, and columns.
3. Run a small `LIMIT` SQL query against a relevant table.
4. Report the exact command, HTTP result, `rowCount`, first 3 rows, and any error message.

Use the bundled CLI when available:

```bash
python3 scripts/anyfinancial_cli.py catalog
python3 scripts/anyfinancial_cli.py query "SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
```

For a full connectivity check:

```bash
python3 scripts/anyfinancial_cli.py smoke --sql "SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
```

## API Calls

### Schema

No auth required:

```bash
curl -fsS "$API_URL/api/data/schema" | jq '.financial'
```

### Catalog

Auth required:

```bash
curl -fsS -X POST "$API_URL/api/data/financial/catalog" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | jq '.'
```

### SQL Query

Auth required:

```bash
SQL="SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
jq -n --arg sql "$SQL" '{sql: $sql, parameters: []}' > /tmp/financial-query.json

curl -fsS -X POST "$API_URL/api/data/financial/sql" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/financial-query.json | jq '.'
```

## SQL Rules

- Use read-only SQL only.
- Allowed starts: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`.
- Use exactly one SQL statement.
- Do not use `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, or other mutating statements.
- Use narrow projections and `LIMIT` while exploring.
- Treat the catalog and schema response as the source of truth for table and column names.

## Reporting Format

When asked to connect or test the service, include:

- Exact command run, with tokens redacted as `$AUTH_TOKEN`.
- HTTP status or curl/CLI failure.
- `rowCount`, if present or inferable from returned rows.
- First 3 rows only.
- Any error message from the API.
