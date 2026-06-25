#!/usr/bin/env python3
"""CLI for Rebyte Financial Data Service."""

import argparse
import io
import json
import os
import re
import subprocess
import sys
from typing import Any, Optional
from urllib.parse import urljoin

import requests

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


ALLOWED_SQL_STARTS = ("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")
BLOCKED_SQL_WORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "MERGE",
    "REPLACE",
    "GRANT",
    "REVOKE",
)


def _script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _load_constants() -> dict[str, Any]:
    path = os.path.join(_script_dir(), "shared", "constants.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


CONSTANTS = _load_constants()
DEFAULT_API_URL = CONSTANTS.get("default_api_url", "https://api.rebyte.ai")
AUTH_JSON = CONSTANTS.get("auth_json", "/home/user/.rebyte.ai/auth.json")
DATA_PATH = CONSTANTS.get("data_path", "/api/data")


def _read_auth_json(path: str = AUTH_JSON) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"Error: invalid auth JSON at {path}: {e}", file=sys.stderr)
        return {}


def _run_rebyte_auth() -> str:
    try:
        proc = subprocess.run(
            ["rebyte-auth"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _resolve_api_url(args) -> str:
    if args.api_url:
        return args.api_url.rstrip("/")
    env_url = os.environ.get("API_URL")
    if env_url:
        return env_url.rstrip("/")
    auth_data = _read_auth_json()
    sandbox_url = auth_data.get("sandbox", {}).get("relay_url")
    if sandbox_url:
        return str(sandbox_url).rstrip("/")
    return DEFAULT_API_URL.rstrip("/")


def _resolve_token(args) -> str:
    if getattr(args, "auth_token", None):
        return args.auth_token.strip()
    env_token = os.environ.get("AUTH_TOKEN")
    if env_token:
        return env_token.strip()
    auth_token = _run_rebyte_auth()
    if auth_token:
        return auth_token
    auth_data = _read_auth_json()
    token = auth_data.get("sandbox", {}).get("token")
    return str(token).strip() if token else ""


def _endpoint(api_url: str, suffix: str) -> str:
    base = api_url.rstrip("/") + DATA_PATH.rstrip("/") + "/"
    return urljoin(base, suffix.lstrip("/"))


def _headers(token: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(method: str, url: str, *, token: Optional[str] = None, payload: Any = None, timeout: int = 60):
    try:
        resp = requests.request(method, url, headers=_headers(token), json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        return None, {"error": "Connection Error: unable to reach the API endpoint."}
    except requests.exceptions.Timeout:
        return None, {"error": "Timeout: the API request timed out."}
    except requests.exceptions.RequestException as e:
        return None, {"error": str(e)}

    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    return resp, body


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _read_sql(args) -> str:
    if args.sql:
        return args.sql
    sql = sys.stdin.read()
    if not sql.strip():
        print("Error: provide SQL as an argument or on stdin.", file=sys.stderr)
        sys.exit(1)
    return sql


def _validate_read_only_sql(sql: str) -> None:
    stripped = sql.strip()
    if not stripped:
        print("Error: SQL is empty.", file=sys.stderr)
        sys.exit(1)
    sql_without_optional_trailing_semicolon = stripped[:-1] if stripped.endswith(";") else stripped
    if ";" in sql_without_optional_trailing_semicolon:
        print("Error: use one SQL statement only.", file=sys.stderr)
        sys.exit(1)
    first = re.match(r"^\s*([A-Za-z]+)", stripped)
    if not first or first.group(1).upper() not in ALLOWED_SQL_STARTS:
        allowed = ", ".join(ALLOWED_SQL_STARTS)
        print(f"Error: SQL must start with one of: {allowed}.", file=sys.stderr)
        sys.exit(1)
    blocked = re.search(r"\b(" + "|".join(BLOCKED_SQL_WORDS) + r")\b", stripped, flags=re.IGNORECASE)
    if blocked:
        print(f"Error: mutating SQL is not allowed: {blocked.group(1).upper()}.", file=sys.stderr)
        sys.exit(1)


def _extract_rows(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    for key in ("rows", "data", "result", "results"):
        value = body.get(key)
        if isinstance(value, list):
            return value
    nested = body.get("data")
    if isinstance(nested, dict):
        for key in ("rows", "result", "results"):
            value = nested.get(key)
            if isinstance(value, list):
                return value
    return []


def _extract_row_count(body: Any, rows: list[Any]) -> Optional[int]:
    if isinstance(body, dict):
        for key in ("rowCount", "row_count", "count", "total"):
            value = body.get(key)
            if isinstance(value, int):
                return value
        nested = body.get("data")
        if isinstance(nested, dict):
            for key in ("rowCount", "row_count", "count", "total"):
                value = nested.get(key)
                if isinstance(value, int):
                    return value
    return len(rows) if rows else None


def _extract_error(body: Any) -> Optional[str]:
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if value:
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return None


def _redacted_curl(method: str, url: str, payload: Optional[str] = None, auth: bool = False) -> str:
    parts = [f'curl -fsS -X {method} "{url}"']
    if auth:
        parts.append('  -H "Authorization: Bearer $AUTH_TOKEN"')
    parts.append('  -H "Content-Type: application/json"')
    if payload is not None:
        parts.append(f"  -d '{payload}'")
    return " \\\n".join(parts)


def cmd_schema(args) -> None:
    api_url = _resolve_api_url(args)
    url = _endpoint(api_url, "schema")
    resp, body = _request_json("GET", url, timeout=args.timeout)
    output = body
    if not args.all and isinstance(body, dict) and "financial" in body:
        output = body["financial"]
    if args.report:
        print(f"Command:\n{_redacted_curl('GET', url)}")
        print(f"HTTP result: {resp.status_code if resp is not None else 'request failed'}")
    _print_json(output)
    if resp is None or resp.status_code >= 400:
        sys.exit(1)


def cmd_catalog(args) -> None:
    api_url = _resolve_api_url(args)
    token = _resolve_token(args)
    if not token:
        print("Error: authentication token unavailable.", file=sys.stderr)
        sys.exit(1)
    url = _endpoint(api_url, "financial/catalog")
    resp, body = _request_json("POST", url, token=token, payload={}, timeout=args.timeout)
    if args.report:
        print(f"Command:\n{_redacted_curl('POST', url, '{}', auth=True)}")
        print(f"HTTP result: {resp.status_code if resp is not None else 'request failed'}")
    _print_json(body)
    if resp is None or resp.status_code >= 400:
        sys.exit(1)


def cmd_query(args) -> None:
    sql = _read_sql(args)
    _validate_read_only_sql(sql)
    api_url = _resolve_api_url(args)
    token = _resolve_token(args)
    if not token:
        print("Error: authentication token unavailable.", file=sys.stderr)
        sys.exit(1)

    url = _endpoint(api_url, "financial/sql")
    payload = {"sql": sql, "parameters": []}
    resp, body = _request_json("POST", url, token=token, payload=payload, timeout=args.timeout)
    rows = _extract_rows(body)
    row_count = _extract_row_count(body, rows)
    error = _extract_error(body)

    if args.report:
        print("Command:")
        print(_redacted_curl("POST", url, json.dumps(payload, ensure_ascii=False), auth=True))
        print(f"HTTP result: {resp.status_code if resp is not None else 'request failed'}")
        print(f"rowCount: {row_count if row_count is not None else 'unavailable'}")
        print("first 3 rows:")
        _print_json(rows[:3])
        print(f"error: {error or ''}")
    else:
        _print_json(body)

    if resp is None or resp.status_code >= 400:
        sys.exit(1)


def cmd_smoke(args) -> None:
    api_url = _resolve_api_url(args)
    token = _resolve_token(args)
    if not token:
        print("Error: authentication token unavailable.", file=sys.stderr)
        sys.exit(1)

    catalog_url = _endpoint(api_url, "financial/catalog")
    catalog_resp, catalog_body = _request_json("POST", catalog_url, token=token, payload={}, timeout=args.timeout)
    print("Catalog command:")
    print(_redacted_curl("POST", catalog_url, "{}", auth=True))
    print(f"Catalog HTTP result: {catalog_resp.status_code if catalog_resp is not None else 'request failed'}")
    if catalog_resp is None or catalog_resp.status_code >= 400:
        print("Catalog error:")
        _print_json(catalog_body)
        sys.exit(1)

    sql = args.sql
    _validate_read_only_sql(sql)
    sql_url = _endpoint(api_url, "financial/sql")
    payload = {"sql": sql, "parameters": []}
    query_resp, query_body = _request_json("POST", sql_url, token=token, payload=payload, timeout=args.timeout)
    rows = _extract_rows(query_body)
    row_count = _extract_row_count(query_body, rows)
    error = _extract_error(query_body)

    print("SQL command:")
    print(_redacted_curl("POST", sql_url, json.dumps(payload, ensure_ascii=False), auth=True))
    print(f"SQL HTTP result: {query_resp.status_code if query_resp is not None else 'request failed'}")
    print(f"rowCount: {row_count if row_count is not None else 'unavailable'}")
    print("first 3 rows:")
    _print_json(rows[:3])
    print(f"error: {error or ''}")

    if query_resp is None or query_resp.status_code >= 400:
        sys.exit(1)


def _render_doc() -> str:
    doc_path = os.path.join(_script_dir(), "shared", "doc_spec.md")
    with open(doc_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    tpl = tpl.replace("{{LANG_INVOKE}}", "python3 scripts/anyfinancial_cli.py")
    return tpl


def cmd_doc(args) -> None:
    print(_render_doc())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anyfinancial",
        description="CLI for Rebyte Financial Data Service.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  anyfinancial schema\n"
            "  anyfinancial catalog\n"
            "  anyfinancial query \"SELECT * FROM cn.bars_1m LIMIT 10\" --report\n"
            "  anyfinancial smoke --sql \"SELECT * FROM cn.bars_1m LIMIT 10\"\n"
        ),
    )
    parser.add_argument("--api-url", help="Relay API base URL. Defaults to auth.json sandbox relay_url or https://api.rebyte.ai.")
    parser.add_argument("--auth-token", help="Bearer token. Defaults to AUTH_TOKEN, rebyte-auth, or auth.json sandbox token.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    schema_p = subparsers.add_parser("schema", help="Call GET /api/data/schema; no auth required.")
    schema_p.add_argument("--all", action="store_true", help="Print the full schema response instead of only .financial.")
    schema_p.add_argument("--report", action="store_true", help="Include exact command and HTTP result.")
    schema_p.set_defaults(func=cmd_schema)

    catalog_p = subparsers.add_parser("catalog", help="Call POST /api/data/financial/catalog.")
    catalog_p.add_argument("--report", action="store_true", help="Include exact command and HTTP result.")
    catalog_p.set_defaults(func=cmd_catalog)

    query_p = subparsers.add_parser("query", help="Run one read-only SQL statement.")
    query_p.add_argument("sql", nargs="?", help="SQL string. If omitted, SQL is read from stdin.")
    query_p.add_argument("--report", action="store_true", help="Report command, HTTP result, rowCount, first 3 rows, and error.")
    query_p.set_defaults(func=cmd_query)

    smoke_p = subparsers.add_parser("smoke", help="Call catalog, then run a small SQL query and report the result.")
    smoke_p.add_argument(
        "--sql",
        default="SELECT * FROM cn.bars_1m WHERE ts_code = '000001.SZ' ORDER BY trade_time DESC LIMIT 10",
        help="Read-only SQL query to run after catalog.",
    )
    smoke_p.set_defaults(func=cmd_smoke)

    doc_p = subparsers.add_parser("doc", help="Print AI-facing interface specification.")
    doc_p.set_defaults(func=cmd_doc)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        print(_render_doc())
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
