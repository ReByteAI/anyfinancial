# us_news data builder

Incremental **local mirror + search layer** over the served `us.news` table
(Rebyte Financial Data Service). It lets you refresh US news to *today*, run
read-only SQL over the mirror, and do **semantic "more-like-this"** search over
the embeddings the service already computes — reusing the same
`catalog → schema → query` API and auth as the top-level AnyFinancial CLI.

## Why a builder at all

`us.news` is already served and queryable with SQL. This builder adds two things
the raw SQL endpoint does not give you directly:

1. A **local, incrementally-refreshed** copy so repeated work does not re-scan
   806k+ remote rows, and so you have an offline SQLite you can join/analyze.
2. **Vector search** over `content_embedding` (1536-dim). DataFusion has no
   vector-similarity operator exposed here, so similarity is computed locally.

## Data source (verified)

`us.news` columns: `id`, `published_utc` (µs), `title`, `tickers` (list),
`content`, `content_embedding` (`FixedSizeList(1536 × Float32)`).
~806k rows, 2016 → present. The `content_embedding` is the service's own
precomputed vector; this builder **reuses** it rather than recomputing.

## Commands

```bash
cd data_builder/us_news

# Refresh new rows up to now and embed only new ids.
#   - first run with no watermark defaults to the last 7 days
#   - --since / --days override the stored watermark
#   - --max-rows caps a single run
python3 build.py refresh                     # continue from stored watermark
python3 build.py refresh --days 3            # last 3 days
python3 build.py refresh --since 2023-03-15  # backfill from a date

# Local counts, freshness, watermark
python3 build.py status

# Read-only SQL over the local mirror (same guard as the anyfinancial CLI)
python3 build.py sql "SELECT published_utc, title FROM news ORDER BY published_utc DESC LIMIT 5"

# Semantic search: find articles similar to a seed article (works today)
python3 build.py search --like-id <news_id> --limit 5
python3 build.py search --like-id <news_id> --ticker JPM

# Free-text semantic search (needs an embedding backend, see below);
# otherwise it falls back to keyword title search.
python3 build.py search --text "regional bank stress" --limit 5
```

## How refresh works

* **Incremental**: keyset pagination on `(published_utc, id)` from a stored
  watermark (`meta` table). Re-runs pull only genuinely new rows; inserts are
  `ON CONFLICT DO NOTHING`.
* **Embed only new ids**: after inserting, only ids that are *not yet embedded
  locally* have their vector fetched, in batches, via
  `SELECT content_embedding FROM us.news WHERE id IN (...)`. Vectors are stored
  as little-endian float32 BLOBs.

## Local store

SQLite at `us_news.db` (override with `US_NEWS_DB`), gitignored:

* `news(id PK, published_utc, title, tickers /*json*/, content)`
* `embeddings(id PK, dim, vec /*float32 blob*/)`
* `meta(key, value)` — watermark + timestamps.

`numpy` is used for cosine when installed; a pure-Python path runs otherwise.

## Semantic-search modes

| Mode | Status | Notes |
|---|---|---|
| `--like-id` (seed article → similar) | **Works now** | Uses stored vectors only; fully offline after refresh. |
| `--text` (free text → similar) | **Needs embedding backend** | The query must be embedded into the *same* 1536-dim space as `content_embedding`. Set `US_NEWS_EMBED_MODEL` to an embedding model reachable on the Rebyte model proxy. If unset/unavailable, `--text` falls back to keyword title search. |

## Known limitations

* **The current month lags on `content` backfill.** Upstream, `content` fills
  in with a lag of up to ~1 month: measured on this dataset, ~49% of the current
  partial month (June 2026) had empty `content` while every prior month was
  100% populated. The service embeds empty text to a single degenerate vector,
  so admitting those rows would make recent articles rank as identical
  (cosine ≈ 1.0). The builder therefore **withholds embedding for empty-content
  ids** and retries them on a later refresh once content backfills. They are
  still stored and SQL-searchable; `status.unembedded_empty_content` counts them.
  Net effect: semantic search is fully effective on anything older than the
  current month, and newest articles become searchable as their content lands.
* **No embedding model is currently exposed** on the Rebyte model proxy
  (chat/completions only), so `--text` semantic search is inactive by default.
  It activates automatically once `US_NEWS_EMBED_MODEL` names a working
  embedding model in the same space as the served vectors.
* **Once a row passes the watermark it is not re-pulled**, so if its `content`
  backfills upstream later, the local `content` stays empty. Re-run with an
  explicit `--since` to re-pull a window when you need backfilled content.
* **Transport is JSON-over-SQL**, so full-history backfill (806k rows ×
  1536 floats) is large and slow; refresh in bounded windows via `--since` /
  `--max-rows`. This builder is designed for rolling refresh, not bulk export.
* Similarity is brute-force cosine over the loaded vectors (fine for tens of
  thousands of rows). For much larger mirrors, add an ANN index.
