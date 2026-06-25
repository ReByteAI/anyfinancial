# AnyFinancial Interface Specification

Use Rebyte Financial Data Service through the Relay API.

## Endpoint

- App domain: `https://app.rebyte.ai/financial`
- Relay API default: `https://api.rebyte.ai`
- Data namespace: `/api/data`

Inside a Rebyte VM/workspace, prefer `/home/user/.rebyte.ai/auth.json`:

```bash
AUTH_TOKEN="$(rebyte-auth 2>/dev/null || jq -r '.sandbox.token' /home/user/.rebyte.ai/auth.json)"
API_URL="$(jq -r '.sandbox.relay_url // empty' /home/user/.rebyte.ai/auth.json 2>/dev/null || true)"
API_URL="${API_URL:-https://api.rebyte.ai}"
```

## CLI

```bash
{{LANG_INVOKE}} <command> [options]
```

Commands:

```bash
{{LANG_INVOKE}} schema
{{LANG_INVOKE}} schema --all
{{LANG_INVOKE}} catalog
{{LANG_INVOKE}} query "SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
{{LANG_INVOKE}} smoke --sql "SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
```

## API

### Schema, no auth required

```bash
curl -fsS "$API_URL/api/data/schema" | jq '.financial'
```

### Catalog, auth required

```bash
curl -fsS -X POST "$API_URL/api/data/financial/catalog" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | jq '.'
```

### SQL, auth required

```bash
SQL="SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
jq -n --arg sql "$SQL" '{sql: $sql, parameters: []}' > /tmp/financial-query.json

curl -fsS -X POST "$API_URL/api/data/financial/sql" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/financial-query.json | jq '.'
```

## SQL Rules

- SQL must be read-only.
- Allowed starts: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`.
- Use one SQL statement only.
- Do not use `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, or other mutating statements.
- Call catalog first, inspect available tables, then run a small `LIMIT` query.

## Reporting

Report the exact command, HTTP result, `rowCount`, first 3 rows, and any error message.
