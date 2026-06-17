#!/usr/bin/env python3
"""AnyFinancial CLI - Data Fusion SQL client for xyznot financial data."""

import argparse
import datetime as _dt
import io
import json
import os
import re
import sys
from typing import Any

import requests

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _load_constants() -> dict:
    path = os.path.join(_script_dir(), "shared", "constants.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


CONSTANTS = _load_constants()
ENDPOINT = CONSTANTS["endpoint"]
API_KEY = CONSTANTS["api_key"]
KNOWN_TABLES = CONSTANTS.get("known_tables", ["bars_1m", "news", "fundamentals"])


def _build_headers() -> dict:
    return {
        "Content-Type": "text/plain",
        "Accept": "application/json",
        "X-API-Key": API_KEY,
    }


def _call_sql(sql: str, timeout: int = 60) -> Any:
    try:
        resp = requests.post(ENDPOINT, data=sql.encode("utf-8"), headers=_build_headers(), timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}", file=sys.stderr)
        print(f"Response body: {resp.text[:1000]}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("Connection Error: Unable to reach the API endpoint.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Timeout: The API request timed out.", file=sys.stderr)
        sys.exit(1)

    try:
        return resp.json()
    except ValueError:
        return resp.text


def _print_result(result: Any, raw: bool = False) -> None:
    if raw:
        if isinstance(result, str):
            print(result)
        else:
            print(json.dumps(result, ensure_ascii=False))
        return
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,16}", ticker):
        print("Error: ticker must contain only letters, digits, dot, or hyphen.", file=sys.stderr)
        sys.exit(1)
    return ticker


def _positive_limit(value: int, max_limit: int = 100) -> int:
    if value < 1:
        print("Error: --limit must be at least 1.", file=sys.stderr)
        sys.exit(1)
    return min(value, max_limit)


def _table_name(value: str) -> str:
    table = value.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}", table):
        print(f"Error: invalid table name: {value}", file=sys.stderr)
        sys.exit(1)
    return table


def _read_sql(args) -> str:
    if args.sql:
        return args.sql
    sql = sys.stdin.read()
    if not sql.strip():
        print("Error: provide SQL as an argument or on stdin.", file=sys.stderr)
        sys.exit(1)
    return sql


def _schemas_as_markdown(schemas: dict) -> str:
    lines = ["# AnyFinancial Schema Discovery", ""]
    for table, rows in schemas.items():
        lines.append(f"## {table}")
        lines.append("")
        lines.append("| Column | Data type | Nullable |")
        lines.append("|--------|-----------|----------|")
        for row in rows:
            lines.append(
                f"| {row.get('column_name', '')} | {row.get('data_type', '')} | {row.get('is_nullable', '')} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def cmd_discover_schemas(args):
    tables = [_table_name(t) for t in (args.tables.split(",") if args.tables else KNOWN_TABLES) if t.strip()]
    schemas = {}
    for table in tables:
        schemas[table] = _call_sql(f"DESCRIBE {table}", timeout=args.timeout)
    if args.json:
        _print_result(schemas)
    else:
        print(_schemas_as_markdown(schemas))


def cmd_query(args):
    result = _call_sql(_read_sql(args), timeout=args.timeout)
    _print_result(result, raw=args.raw)


def cmd_price(args):
    ticker = _ticker(args.ticker)
    today = _dt.datetime.now(_dt.timezone.utc)
    year = str(args.year or today.year)
    month = str(args.month or today.month)
    limit = _positive_limit(args.limit)
    sql = (
        "SELECT ticker, t, o, h, l, c, v "
        "FROM bars_1m "
        f"WHERE ticker = {_sql_literal(ticker)} AND year = {_sql_literal(year)} AND month = {_sql_literal(month)} "
        "ORDER BY t DESC "
        f"LIMIT {limit}"
    )
    _print_result(_call_sql(sql, timeout=args.timeout))


def cmd_fundamentals(args):
    ticker = _ticker(args.ticker)
    limit = _positive_limit(args.limit)
    sql = (
        "SELECT company_name, tickers, fiscal_year, fiscal_period, start_date, end_date, "
        "is_net_income_loss, is_revenues, bs_assets "
        "FROM fundamentals "
        f"WHERE ARRAY_CONTAINS(tickers, {_sql_literal(ticker)}) "
        "ORDER BY end_date DESC "
        f"LIMIT {limit}"
    )
    _print_result(_call_sql(sql, timeout=args.timeout))


def cmd_news(args):
    ticker = _ticker(args.ticker)
    limit = _positive_limit(args.limit)
    sql = (
        "SELECT id, published_utc, title, tickers, content "
        "FROM news "
        f"WHERE ARRAY_CONTAINS(tickers, {_sql_literal(ticker)}) "
        "ORDER BY published_utc DESC "
        f"LIMIT {limit}"
    )
    _print_result(_call_sql(sql, timeout=args.timeout))


def _render_doc():
    doc_path = os.path.join(_script_dir(), "shared", "doc_spec.md")
    with open(doc_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    tpl = tpl.replace("{{LANG_NAME}}", "Python")
    tpl = tpl.replace("{{LANG_CODEBLOCK}}", "")
    tpl = tpl.replace("{{LANG_INVOKE}}", "python scripts/anyfinancial_cli.py")
    return tpl


def cmd_doc(args):
    print(_render_doc())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anyfinancial",
        description=(
            "AnyFinancial CLI - Data Fusion SQL client for xyznot financial data.\n\n"
            "Supports schema discovery, arbitrary SQL, latest price bars,\n"
            "company fundamentals, and ticker news."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  anyfinancial discover_schemas\n"
            "  anyfinancial price AAPL\n"
            "  anyfinancial fundamentals AAPL --limit 3\n"
            "  anyfinancial news TSLA --limit 5\n"
            "  anyfinancial query \"SELECT title FROM news LIMIT 1\"\n"
        ),
    )

    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    ds_p = subparsers.add_parser(
        "discover_schemas",
        help="Discover table schemas using Data Fusion SQL DESCRIBE",
        description="Run DESCRIBE against known or specified financial tables.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ds_p.add_argument("--tables", help="Comma-separated tables. Default: bars_1m,news,fundamentals.")
    ds_p.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    ds_p.set_defaults(func=cmd_discover_schemas)

    q_p = subparsers.add_parser(
        "query",
        help="Run arbitrary Data Fusion SQL",
        description="Run SQL against https://mcp.xyznot.com/v1/sql. If SQL is omitted, read from stdin.",
    )
    q_p.add_argument("sql", nargs="?", help="Data Fusion SQL query string.")
    q_p.add_argument("--raw", action="store_true", help="Print response without pretty JSON formatting.")
    q_p.set_defaults(func=cmd_query)

    price_p = subparsers.add_parser("price", help="Get latest price bars for a ticker")
    price_p.add_argument("ticker", help="Stock ticker, e.g. AAPL.")
    price_p.add_argument("--year", help="bars_1m partition year. Defaults to current UTC year.")
    price_p.add_argument("--month", help="bars_1m partition month. Defaults to current UTC month.")
    price_p.add_argument("--limit", type=int, default=1, help="Number of bars to return, default 1.")
    price_p.set_defaults(func=cmd_price)

    fundamentals_p = subparsers.add_parser("fundamentals", help="Get company fundamentals for a ticker")
    fundamentals_p.add_argument("ticker", help="Stock ticker, e.g. AAPL.")
    fundamentals_p.add_argument("--limit", type=int, default=5, help="Number of rows to return, default 5.")
    fundamentals_p.set_defaults(func=cmd_fundamentals)

    news_p = subparsers.add_parser("news", help="Get latest financial news for a ticker")
    news_p.add_argument("ticker", help="Stock ticker, e.g. AAPL.")
    news_p.add_argument("--limit", type=int, default=5, help="Number of articles to return, default 5.")
    news_p.set_defaults(func=cmd_news)

    doc_p = subparsers.add_parser("doc", help="Print AI-facing interface specification")
    doc_p.set_defaults(func=cmd_doc)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        print(_render_doc())
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
