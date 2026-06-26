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
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    requests = None

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


class HttpResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def _decode_response_body(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def _request_json(method: str, url: str, *, token: Optional[str] = None, payload: Any = None, timeout: int = 60):
    if requests is not None:
        return _request_json_with_requests(method, url, token=token, payload=payload, timeout=timeout)
    return _request_json_with_urllib(method, url, token=token, payload=payload, timeout=timeout)


def _request_json_with_requests(
    method: str,
    url: str,
    *,
    token: Optional[str] = None,
    payload: Any = None,
    timeout: int = 60,
):
    try:
        resp = requests.request(method, url, headers=_headers(token), json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as e:
        return None, {"error": f"Connection Error: unable to reach the API endpoint: {e}"}
    except requests.exceptions.Timeout:
        return None, {"error": "Timeout: the API request timed out."}
    except requests.exceptions.RequestException as e:
        return None, {"error": str(e)}

    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    return HttpResponse(resp.status_code), body


def _request_json_with_urllib(
    method: str,
    url: str,
    *,
    token: Optional[str] = None,
    payload: Any = None,
    timeout: int = 60,
):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers=_headers(token), method=method)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = _decode_response_body(resp.read())
            return HttpResponse(resp.status), body
    except urlerror.HTTPError as e:
        body = _decode_response_body(e.read())
        return HttpResponse(e.code), body
    except urlerror.URLError as e:
        return None, {"error": f"Connection Error: unable to reach the API endpoint: {e.reason}"}
    except TimeoutError:
        return None, {"error": "Timeout: the API request timed out."}
    except OSError as e:
        return None, {"error": str(e)}


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


def _is_api_failure(body: Any) -> bool:
    return isinstance(body, dict) and body.get("success") is False


def _request_failed(resp: Optional[HttpResponse], body: Any) -> bool:
    return resp is None or resp.status_code >= 400 or _is_api_failure(body)


def _redacted_curl(method: str, url: str, payload: Optional[str] = None, auth: bool = False) -> str:
    parts = [f'curl -fsS -X {method} "{url}"']
    if auth:
        parts.append('  -H "Authorization: Bearer $AUTH_TOKEN"')
    parts.append('  -H "Content-Type: application/json"')
    if payload is not None:
        parts.append(f"  -d '{payload}'")
    return " \\\n".join(parts)


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def cmd_schema(args) -> None:
    """Return a single table's exact columns via DESCRIBE."""
    table = args.table.strip()
    if not _TABLE_NAME_RE.match(table):
        print(
            f"Error: invalid table name '{table}'. Use a schema-qualified identifier, e.g. cn.bars_1m.",
            file=sys.stderr,
        )
        sys.exit(1)

    api_url = _resolve_api_url(args)
    token = _resolve_token(args)
    if not token:
        print("Error: authentication token unavailable.", file=sys.stderr)
        sys.exit(1)

    url = _endpoint(api_url, "financial/sql")
    payload = {"sql": f"DESCRIBE {table}", "parameters": []}
    resp, body = _request_json("POST", url, token=token, payload=payload, timeout=args.timeout)
    if args.report:
        print("Command:")
        print(_redacted_curl("POST", url, json.dumps(payload, ensure_ascii=False), auth=True))
        print(f"HTTP result: {resp.status_code if resp is not None else 'request failed'}")
    _print_json(body)
    if _request_failed(resp, body):
        sys.exit(1)


def cmd_catalog(args) -> None:
    # SHOW TABLES is the complete registered catalog. (information_schema.tables
    # only lists currently-served tables and silently omits the rest.)
    api_url = _resolve_api_url(args)
    token = _resolve_token(args)
    if not token:
        print("Error: authentication token unavailable.", file=sys.stderr)
        sys.exit(1)
    url = _endpoint(api_url, "financial/sql")
    payload = {"sql": "SHOW TABLES", "parameters": []}
    resp, body = _request_json("POST", url, token=token, payload=payload, timeout=args.timeout)
    if args.report:
        print("Command:")
        print(_redacted_curl("POST", url, json.dumps(payload, ensure_ascii=False), auth=True))
        print(f"HTTP result: {resp.status_code if resp is not None else 'request failed'}")
    _print_json(body)
    if _request_failed(resp, body):
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

    if _request_failed(resp, body):
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anyfinancial",
        description="CLI for Rebyte Financial Data Service. Workflow: catalog -> schema -> query.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  anyfinancial catalog\n"
            "  anyfinancial schema cn.bars_1m\n"
            "  anyfinancial query \"SELECT * FROM cn.bars_1m LIMIT 10\" --report\n"
        ),
    )
    parser.add_argument("--api-url", help="Relay API base URL. Defaults to auth.json sandbox relay_url or https://api.rebyte.ai.")
    parser.add_argument("--auth-token", help="Bearer token. Defaults to AUTH_TOKEN, rebyte-auth, or auth.json sandbox token.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    catalog_p = subparsers.add_parser("catalog", help="List every table. POST /api/data/financial/catalog.")
    catalog_p.add_argument("--report", action="store_true", help="Include exact command and HTTP result.")
    catalog_p.set_defaults(func=cmd_catalog)

    schema_p = subparsers.add_parser("schema", help="Show one table's exact columns via DESCRIBE <table>.")
    schema_p.add_argument("table", help="Schema-qualified table name, e.g. cn.bars_1m.")
    schema_p.add_argument("--report", action="store_true", help="Include exact command and HTTP result.")
    schema_p.set_defaults(func=cmd_schema)

    query_p = subparsers.add_parser("query", help="Run one read-only SQL statement.")
    query_p.add_argument("sql", nargs="?", help="SQL string. If omitted, SQL is read from stdin.")
    query_p.add_argument("--report", action="store_true", help="Report command, HTTP result, rowCount, first 3 rows, and error.")
    query_p.set_defaults(func=cmd_query)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
