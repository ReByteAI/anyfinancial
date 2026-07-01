#!/usr/bin/env python3
"""Local incremental builder for the us.news dataset.

Mirrors the served ``us.news`` table (Rebyte Financial Data Service) into a
local SQLite store so news can be refreshed to *today* and searched two ways:

  * **SQL**        — run read-only SQL against the local mirror.
  * **Semantic**   — cosine similarity over the 1536-dim ``content_embedding``
                     that the service already computes for every article.

Design notes
------------
* Source of truth is the served ``us.news`` table, reached through the same
  ``/api/data/financial/sql`` endpoint and the same auth resolution as
  ``scripts/anyfinancial_cli.py`` (imported here, single source of truth).
* ``refresh`` is incremental: it keyset-paginates by ``(published_utc, id)``
  from a stored watermark, so re-runs only pull genuinely new rows.
* Embeddings are fetched **only for ids not already embedded locally**
  ("embed only new ids"). The vectors are the service's own precomputed
  ``content_embedding`` — reused, not recomputed — so local semantic search
  lives in the exact same vector space the service uses.
* Stdlib only. ``numpy`` is used when present (faster cosine) but not required.

Commands
--------
    build.py refresh [--since YYYY-MM-DD | --days N] [--page N] [--max-rows N]
    build.py search  --like-id <id> [--ticker T] [--limit N]
    build.py search  --text "..."   [--ticker T] [--limit N]
    build.py sql     "SELECT ... FROM news ..."
    build.py status
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

# --- reuse the existing CLI's auth + HTTP + SQL primitives (one source of truth)
_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.normpath(os.path.join(_HERE, "..", "..", "scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import anyfinancial_cli as af  # noqa: E402

try:
    import numpy as np  # optional, only speeds up cosine
except ImportError:  # pragma: no cover - numpy is optional
    np = None

SOURCE_TABLE = "us.news"
EMBED_DIM = 1536
DB_NAME = "us_news.db"
DEFAULT_SINCE_DAYS = 7
DEFAULT_PAGE = 200
DEFAULT_EMBED_BATCH = 40


# --------------------------------------------------------------------------- #
# Remote access (served us.news via the financial SQL endpoint)
# --------------------------------------------------------------------------- #
def _api_url() -> str:
    env_url = os.environ.get("API_URL")
    if env_url:
        return env_url.rstrip("/")
    sandbox_url = af._read_auth_json().get("sandbox", {}).get("relay_url")
    if sandbox_url:
        return str(sandbox_url).rstrip("/")
    return af.DEFAULT_API_URL.rstrip("/")


def _token() -> str:
    env_token = os.environ.get("AUTH_TOKEN")
    if env_token:
        return env_token.strip()
    tok = af._run_rebyte_auth()
    if tok:
        return tok
    tok = af._read_auth_json().get("sandbox", {}).get("token")
    return str(tok).strip() if tok else ""


def remote_sql(sql: str, *, timeout: int = 120) -> list[dict[str, Any]]:
    """Run one read-only statement against the served financial service."""
    url = af._endpoint(_api_url(), "financial/sql")
    resp, body = af._request_json(
        "POST", url, token=_token(), payload={"sql": sql, "parameters": []}, timeout=timeout
    )
    if af._request_failed(resp, body):
        raise RuntimeError(f"remote SQL failed: {af._extract_error(body) or body}")
    return af._extract_rows(body)


def _sql_str(value: str) -> str:
    """Single-quote-escape a string for inline SQL literals."""
    return value.replace("'", "''")


# --------------------------------------------------------------------------- #
# Local store
# --------------------------------------------------------------------------- #
def db_path() -> str:
    return os.environ.get("US_NEWS_DB") or os.path.join(_HERE, DB_NAME)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS news (
            id            TEXT PRIMARY KEY,
            published_utc TEXT NOT NULL,
            title         TEXT,
            tickers       TEXT,   -- JSON array
            content       TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_news_published ON news(published_utc);
        CREATE TABLE IF NOT EXISTS embeddings (
            id  TEXT PRIMARY KEY,
            dim INTEGER NOT NULL,
            vec BLOB NOT NULL,      -- float32 little-endian
            FOREIGN KEY (id) REFERENCES news(id)
        );
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.commit()
    return conn


def meta_get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def pack_vec(values: Iterable[float]) -> bytes:
    return array.array("f", values).tobytes()


def unpack_vec(blob: bytes) -> array.array:
    a = array.array("f")
    a.frombytes(blob)
    return a


# --------------------------------------------------------------------------- #
# refresh
# --------------------------------------------------------------------------- #
def _default_since_cursor() -> tuple[str, str]:
    start = datetime.now(timezone.utc) - timedelta(days=DEFAULT_SINCE_DAYS)
    return start.strftime("%Y-%m-%dT%H:%M:%S"), ""


def cmd_refresh(args: argparse.Namespace) -> int:
    conn = connect()

    # Resolve the starting cursor: explicit flags override the stored watermark.
    if args.since:
        cursor_ts, cursor_id = f"{args.since}T00:00:00", ""
    elif args.days is not None:
        start = datetime.now(timezone.utc) - timedelta(days=args.days)
        cursor_ts, cursor_id = start.strftime("%Y-%m-%dT%H:%M:%S"), ""
    else:
        wm = meta_get(conn, "watermark_published_utc")
        wm_id = meta_get(conn, "watermark_id") or ""
        if wm:
            cursor_ts, cursor_id = wm, wm_id
        else:
            cursor_ts, cursor_id = _default_since_cursor()

    print(f"refresh: source={SOURCE_TABLE} cursor=({cursor_ts}, '{cursor_id[:12]}') "
          f"page={args.page} max_rows={args.max_rows or 'unbounded'}", file=sys.stderr)

    pulled = 0
    while True:
        remaining = None if not args.max_rows else max(0, args.max_rows - pulled)
        if remaining == 0:
            break
        page = args.page if remaining is None else min(args.page, remaining)
        sql = (
            "SELECT id, published_utc, title, tickers, content "
            f"FROM {SOURCE_TABLE} "
            f"WHERE published_utc > to_timestamp('{_sql_str(cursor_ts)}') "
            f"OR (published_utc = to_timestamp('{_sql_str(cursor_ts)}') "
            f"AND id > '{_sql_str(cursor_id)}') "
            "ORDER BY published_utc, id "
            f"LIMIT {page}"
        )
        rows = remote_sql(sql)
        if not rows:
            break

        with conn:
            for r in rows:
                tickers = r.get("tickers")
                conn.execute(
                    "INSERT INTO news(id, published_utc, title, tickers, content) "
                    "VALUES(?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (
                        r["id"],
                        r["published_utc"],
                        r.get("title"),
                        json.dumps(tickers, ensure_ascii=False) if tickers is not None else None,
                        r.get("content"),
                    ),
                )
        last = rows[-1]
        cursor_ts, cursor_id = last["published_utc"], last["id"]
        pulled += len(rows)
        with conn:
            meta_set(conn, "watermark_published_utc", cursor_ts)
            meta_set(conn, "watermark_id", cursor_id)
        print(f"  +{len(rows)} rows (total {pulled}), watermark={cursor_ts}", file=sys.stderr)
        if len(rows) < page:
            break

    embedded = 0 if args.no_embed else embed_new_ids(conn, batch=args.embed_batch)

    total = conn.execute("SELECT count(*) AS n FROM news").fetchone()["n"]
    total_emb = conn.execute("SELECT count(*) AS n FROM embeddings").fetchone()["n"]
    with conn:
        meta_set(conn, "last_refresh_utc", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    print(json.dumps({
        "pulled_rows": pulled,
        "newly_embedded": embedded,
        "total_news": total,
        "total_embeddings": total_emb,
        "watermark": cursor_ts,
    }, indent=2))
    conn.close()
    return 0


def embed_new_ids(conn: sqlite3.Connection, *, batch: int = DEFAULT_EMBED_BATCH) -> int:
    """Fetch embeddings ONLY for new, content-bearing ids.

    "New" = not already embedded locally. Rows whose upstream ``content`` is
    still empty (a known lag on the freshest articles) are skipped: the service
    embeds empty content to a single degenerate vector, so admitting them would
    make every recent article look identical. Skipped ids stay unembedded and
    are retried on a later refresh, once content has backfilled upstream.
    """
    missing = [
        row["id"]
        for row in conn.execute(
            "SELECT n.id FROM news n "
            "LEFT JOIN embeddings e ON e.id = n.id "
            "WHERE e.id IS NULL "
            "AND n.content IS NOT NULL AND length(trim(n.content)) > 0 "
            "ORDER BY n.published_utc"
        ).fetchall()
    ]
    if not missing:
        return 0
    print(f"embed: {len(missing)} new content-bearing id(s) to embed "
          f"(reusing served content_embedding)", file=sys.stderr)

    done = 0
    for i in range(0, len(missing), batch):
        chunk = missing[i:i + batch]
        in_list = ", ".join(f"'{_sql_str(cid)}'" for cid in chunk)
        rows = remote_sql(
            f"SELECT id, content_embedding FROM {SOURCE_TABLE} WHERE id IN ({in_list})"
        )
        with conn:
            for r in rows:
                vec = r.get("content_embedding")
                if not vec:
                    continue
                conn.execute(
                    "INSERT INTO embeddings(id, dim, vec) VALUES(?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET dim=excluded.dim, vec=excluded.vec",
                    (r["id"], len(vec), pack_vec(vec)),
                )
                done += 1
        print(f"  embedded {min(i + batch, len(missing))}/{len(missing)}", file=sys.stderr)
    return done


# --------------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------------- #
def _load_vectors(conn: sqlite3.Connection, ticker: Optional[str]):
    if ticker:
        pat = f'%"{ticker.upper()}"%'
        sql = ("SELECT e.id, e.vec, n.published_utc, n.title, n.tickers "
               "FROM embeddings e JOIN news n ON n.id = e.id "
               "WHERE n.tickers LIKE ?")
        rows = conn.execute(sql, (pat,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT e.id, e.vec, n.published_utc, n.title, n.tickers "
            "FROM embeddings e JOIN news n ON n.id = e.id"
        ).fetchall()
    return rows


def _cosine_rank(query_vec, rows, limit: int, exclude_id: Optional[str] = None):
    if np is not None:
        q = np.asarray(query_vec, dtype=np.float32)
        qn = q / (np.linalg.norm(q) or 1.0)
        scored = []
        for r in rows:
            if exclude_id and r["id"] == exclude_id:
                continue
            v = np.frombuffer(r["vec"], dtype=np.float32)
            denom = np.linalg.norm(v) or 1.0
            scored.append((float(np.dot(qn, v) / denom), r))
    else:
        qn_norm = math.sqrt(sum(x * x for x in query_vec)) or 1.0
        scored = []
        for r in rows:
            if exclude_id and r["id"] == exclude_id:
                continue
            v = unpack_vec(r["vec"])
            dot = sum(a * b for a, b in zip(query_vec, v))
            vn = math.sqrt(sum(b * b for b in v)) or 1.0
            scored.append((dot / (qn_norm * vn), r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:limit]


def _embed_query_text(text: str) -> Optional[list[float]]:
    """Embed query text via an OpenAI-compatible endpoint, if one is configured.

    Requires US_NEWS_EMBED_MODEL to name an embedding model reachable on the
    Rebyte model proxy (auth.json ``model_proxy``). Returns None when no such
    backend is configured/available — callers then fall back to keyword search.
    """
    model = os.environ.get("US_NEWS_EMBED_MODEL")
    if not model:
        return None
    mp = af._read_auth_json().get("model_proxy") or {}
    base = str(mp.get("relay_url", "")).rstrip("/")
    key = mp.get("api_key")
    if not base or not key:
        return None
    resp, body = af._request_json(
        "POST", base + "/v1/embeddings", token=key,
        payload={"input": text, "model": model}, timeout=30,
    )
    if af._request_failed(resp, body) or not isinstance(body, dict):
        print(f"warn: query embedding unavailable ({af._extract_error(body)})", file=sys.stderr)
        return None
    try:
        return body["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError):
        return None


def _print_hits(hits) -> None:
    out = []
    for score, r in hits:
        out.append({
            "score": round(float(score), 4),
            "id": r["id"],
            "published_utc": r["published_utc"],
            "title": r["title"],
            "tickers": json.loads(r["tickers"]) if r["tickers"] else [],
        })
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_search(args: argparse.Namespace) -> int:
    conn = connect()

    if args.like_id:
        seed = conn.execute("SELECT vec FROM embeddings WHERE id=?", (args.like_id,)).fetchone()
        if not seed:
            print(f"Error: id {args.like_id} has no local embedding. Run refresh first.", file=sys.stderr)
            return 1
        query_vec = list(unpack_vec(seed["vec"]))
        rows = _load_vectors(conn, args.ticker)
        hits = _cosine_rank(query_vec, rows, args.limit, exclude_id=args.like_id)
        _print_hits(hits)
        conn.close()
        return 0

    # text query
    query_vec = _embed_query_text(args.text)
    if query_vec is not None:
        rows = _load_vectors(conn, args.ticker)
        hits = _cosine_rank(query_vec, rows, args.limit)
        _print_hits(hits)
        conn.close()
        return 0

    # Fallback: no compatible embedding backend -> keyword search over titles.
    print("note: no embedding backend configured (US_NEWS_EMBED_MODEL); "
          "falling back to keyword title search.", file=sys.stderr)
    params: list[Any] = [f"%{args.text}%"]
    sql = "SELECT id, published_utc, title, tickers FROM news WHERE title LIKE ?"
    if args.ticker:
        sql += " AND tickers LIKE ?"
        params.append(f'%"{args.ticker.upper()}"%')
    sql += " ORDER BY published_utc DESC LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    print(json.dumps([
        {"id": r["id"], "published_utc": r["published_utc"], "title": r["title"],
         "tickers": json.loads(r["tickers"]) if r["tickers"] else []}
        for r in rows
    ], indent=2, ensure_ascii=False))
    conn.close()
    return 0


# --------------------------------------------------------------------------- #
# sql (read-only over the local mirror)
# --------------------------------------------------------------------------- #
def cmd_sql(args: argparse.Namespace) -> int:
    sql = args.sql or sys.stdin.read()
    af._validate_read_only_sql(sql)  # same read-only guard as the anyfinancial CLI
    conn = connect()
    try:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    except sqlite3.Error as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(json.dumps({"rows": rows, "rowCount": len(rows)}, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    conn = connect()
    row = conn.execute(
        "SELECT count(*) AS n, min(published_utc) AS oldest, max(published_utc) AS newest FROM news"
    ).fetchone()
    emb = conn.execute("SELECT count(*) AS n FROM embeddings").fetchone()["n"]
    empty_content = conn.execute(
        "SELECT count(*) AS n FROM news "
        "WHERE content IS NULL OR length(trim(content)) = 0"
    ).fetchone()["n"]
    print(json.dumps({
        "db_path": db_path(),
        "news_rows": row["n"],
        "embeddings": emb,
        "unembedded": row["n"] - emb,
        "unembedded_empty_content": empty_content,
        "oldest": row["oldest"],
        "newest": row["newest"],
        "watermark": meta_get(conn, "watermark_published_utc"),
        "last_refresh_utc": meta_get(conn, "last_refresh_utc"),
        "numpy": np is not None,
    }, indent=2))
    conn.close()
    return 0


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="us_news",
        description="Incremental builder + SQL/semantic search for the us.news dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  build.py refresh --days 3\n"
            "  build.py status\n"
            "  build.py sql \"SELECT published_utc, title FROM news ORDER BY published_utc DESC LIMIT 5\"\n"
            "  build.py search --like-id <news_id> --limit 5\n"
            "  build.py search --text \"data breach lawsuit\" --ticker MDT\n"
        ),
    )
    sub = p.add_subparsers(dest="command")

    r = sub.add_parser("refresh", help="Pull new rows to today and embed only new ids.")
    r.add_argument("--since", help="Start date YYYY-MM-DD (overrides stored watermark).")
    r.add_argument("--days", type=int, help="Start N days back (overrides stored watermark).")
    r.add_argument("--page", type=int, default=DEFAULT_PAGE, help="Rows per remote page.")
    r.add_argument("--max-rows", type=int, default=0, help="Cap rows pulled this run (0 = unbounded).")
    r.add_argument("--embed-batch", type=int, default=DEFAULT_EMBED_BATCH, help="Ids per embedding pull.")
    r.add_argument("--no-embed", action="store_true", help="Skip the embedding step.")
    r.set_defaults(func=cmd_refresh)

    s = sub.add_parser("search", help="Semantic (by id / text) or keyword search.")
    s.add_argument("--like-id", help="Seed news id: find semantically similar articles.")
    s.add_argument("--text", help="Free-text query (needs embedding backend; else keyword).")
    s.add_argument("--ticker", help="Restrict to a ticker, e.g. AAPL.")
    s.add_argument("--limit", type=int, default=10, help="Number of hits.")
    s.set_defaults(func=cmd_search)

    q = sub.add_parser("sql", help="Run one read-only SQL statement over the local mirror.")
    q.add_argument("sql", nargs="?", help="SQL string; read from stdin if omitted.")
    q.set_defaults(func=cmd_sql)

    st = sub.add_parser("status", help="Show local store counts, freshness and watermark.")
    st.set_defaults(func=cmd_status)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        sys.exit(0)
    if args.command == "search" and not args.like_id and not args.text:
        print("Error: search needs --like-id or --text.", file=sys.stderr)
        sys.exit(1)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
