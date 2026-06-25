[![Run on Rebyte](https://raw.githubusercontent.com/ReByteAI/run-any-skill-with-single-click/main/badge-v3.svg)](https://app.rebyte.ai/new?prompt=Use%20the%20anyfinancial%20skill.%20Connect%20to%20Rebyte%20Financial%20Data%20Service%2C%20inspect%20the%20catalog%2C%20and%20run%20a%20small%20LIMIT%20query.)

# AnyFinancial

Codex skill for Rebyte Financial Data Service.

The user-facing app is `https://app.rebyte.ai/financial`, but the Data Service API is accessed through the Relay API:

```text
https://api.rebyte.ai/api/data
```

Inside a Rebyte VM/workspace, the skill and CLI prefer the sandbox token and relay URL from `/home/user/.rebyte.ai/auth.json`.

## Usage

```bash
python3 scripts/anyfinancial_cli.py schema
python3 scripts/anyfinancial_cli.py catalog
python3 scripts/anyfinancial_cli.py query "SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
python3 scripts/anyfinancial_cli.py smoke --sql "SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10"
```

## Workflow

1. Call catalog first.
2. Inspect available tables.
3. Run a small read-only SQL query with `LIMIT`.
4. Report the exact command, HTTP result, `rowCount`, first 3 rows, and any error message.

## SQL Rules

- Allowed starts: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`.
- One SQL statement only.
- No mutating statements such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, or `TRUNCATE`.
