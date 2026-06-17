# AnyFinancial Skill End-to-End Test Plan

## Test Goals

Verify the AnyFinancial skill can:

- Use the hardcoded API key from `scripts/shared/constants.json` with no configuration.
- Print offline docs with `doc`.
- Discover table schemas with `discover_schemas`.
- Run arbitrary SQL with `query`.
- Fetch latest price bars with `price`.
- Fetch company fundamentals with `fundamentals`.
- Fetch latest ticker news with `news`.
- Handle common SQL/auth/network failures with clear errors.

## Prerequisites

1. Python 3.6+ is available as `python` or `python3`.
2. `requests` is installed.
3. `scripts/shared/constants.json` contains a valid `api_key`.

## Test Cases

| # | Command | Expected result |
|---|---------|-----------------|
| 1 | `python3 scripts/anyfinancial_cli.py doc` | Prints `# AnyFinancial Interface Specification` |
| 2 | `python3 scripts/anyfinancial_cli.py discover_schemas` | Prints schemas for `bars_1m`, `news`, and `fundamentals` |
| 3 | `python3 scripts/anyfinancial_cli.py discover_schemas --json` | Prints a JSON object with table keys |
| 4 | `python3 scripts/anyfinancial_cli.py price AAPL` | Prints at least one row with `ticker`, `t`, and `c` |
| 5 | `python3 scripts/anyfinancial_cli.py price AAPL --year 2026 --month 6 --limit 3` | Prints up to 3 AAPL bars |
| 6 | `python3 scripts/anyfinancial_cli.py fundamentals AAPL --limit 2` | Prints up to 2 rows with `company_name` and fiscal fields |
| 7 | `python3 scripts/anyfinancial_cli.py news AAPL --limit 2` | Prints up to 2 rows with `published_utc` and `title` |
| 8 | `python3 scripts/anyfinancial_cli.py query "SELECT title, published_utc FROM news ORDER BY published_utc DESC LIMIT 1"` | Prints one latest news row |
| 9 | `echo "SELECT title FROM news LIMIT 1" \| python3 scripts/anyfinancial_cli.py query` | Reads SQL from stdin and prints one row |
| 10 | `python3 scripts/anyfinancial_cli.py query "SELECT ticker FROM bars_1m LIMIT 1"` | May fail or run slowly; agent should treat missing `year`/`month` as invalid usage |
| 11 | `python3 scripts/anyfinancial_cli.py price` | Argparse reports missing `ticker` |

## Passing Criteria

- Test cases 1-9 succeed.
- Test cases 10-11 fail safely with understandable error output.
- Convenience commands use `ARRAY_CONTAINS` for array ticker columns and include `year`/`month` for `bars_1m`.
