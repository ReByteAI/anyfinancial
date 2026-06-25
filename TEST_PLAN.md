# Test Plan

Validate that the skill points only to Rebyte Financial Data Service through the Relay API.

## Static Checks

1. `SKILL.md` frontmatter contains only `name` and `description`.
2. No hardcoded API key is present.
3. Legacy endpoint and API-key auth paths are absent.
4. The CLI resolves auth from `AUTH_TOKEN`, `rebyte-auth`, or `/home/user/.rebyte.ai/auth.json`.
5. SQL validation rejects mutating statements and multiple statements.
6. The CLI has no required third-party Python dependency; `requests` is optional and stdlib fallback is available.
7. API responses with `success: false` fail the command even when the HTTP status is 200.

## Commands

| # | Command | Expected |
|---|---------|----------|
| 1 | `python3 scripts/anyfinancial_cli.py doc` | Prints the Rebyte Relay API spec |
| 2 | `python3 scripts/anyfinancial_cli.py schema --report` | Calls `GET /api/data/schema`; no auth required; prints `.financial` |
| 3 | `python3 scripts/anyfinancial_cli.py catalog --report` | Calls `POST /api/data/financial/catalog` with bearer auth |
| 4 | `python3 scripts/anyfinancial_cli.py query "SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10" --report` | Calls SQL endpoint and reports HTTP result, `rowCount`, first 3 rows, and error |
| 5 | `python3 scripts/anyfinancial_cli.py smoke` | Calls catalog first, then SQL query |
| 6 | `python3 scripts/anyfinancial_cli.py query "DELETE FROM cn.bars_1m WHERE 1=1"` | Fails before network request |
| 7 | `python3 scripts/anyfinancial_cli.py query "SELECT 1; SELECT 2"` | Fails before network request |
| 8 | `python3 -S scripts/anyfinancial_cli.py schema --report` | Uses the stdlib fallback path. In environments with a working Python CA bundle this should call schema; otherwise it must report the underlying TLS/connection reason clearly. |

## Manual Connectivity

In a Rebyte VM/workspace:

```bash
AUTH_TOKEN="$(rebyte-auth 2>/dev/null || jq -r '.sandbox.token' /home/user/.rebyte.ai/auth.json)"
API_URL="$(jq -r '.sandbox.relay_url // empty' /home/user/.rebyte.ai/auth.json 2>/dev/null || true)"
API_URL="${API_URL:-https://api.rebyte.ai}"

curl -fsS -X POST "$API_URL/api/data/financial/catalog" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | jq '.'
```
