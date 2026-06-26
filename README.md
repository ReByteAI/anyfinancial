[![Run on Rebyte](https://raw.githubusercontent.com/ReByteAI/run-any-skill-with-single-click/main/badge-v3.svg)](https://app.rebyte.ai/new?prompt=Use%20the%20anyfinancial%20skill.%20List%20the%20catalog%2C%20read%20a%20table%20schema%2C%20and%20run%20a%20small%20LIMIT%20query.)

# AnyFinancial

Read-only SQL access to Rebyte Financial Data Service through the Relay Data API
(`https://api.rebyte.ai/api/data/financial`).

The API is market-agnostic: it exposes a single catalog of tables and a read-only
SQL endpoint. Whatever tables the service holds appear in the catalog — the skill
does not special-case any market.

Inside a Rebyte VM/workspace the skill and CLI read the sandbox token and relay URL
from `/home/user/.rebyte.ai/auth.json`.

## Workflow: catalog → schema → query

```bash
# 1. List every table the service holds
python3 scripts/anyfinancial_cli.py catalog

# 2. Read a table's exact columns before querying it
python3 scripts/anyfinancial_cli.py schema cn.bars_1m

# 3. Run one read-only SQL statement
python3 scripts/anyfinancial_cli.py query "SELECT trade_time, c FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
```

The CLI has no required third-party packages — it uses `requests` when available and
falls back to Python's standard-library HTTP client.

## SQL rules

- Read-only, one statement per request.
- Allowed starts: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`.
- No mutating statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, …).
