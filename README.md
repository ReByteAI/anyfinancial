[![Run on Rebyte](https://raw.githubusercontent.com/ReByteAI/run-any-skill-with-single-click/main/badge-v3.svg)](https://app.rebyte.ai/new?prompt=Use%20the%20anyfinancial%20data%20skill.%20List%20the%20catalog%2C%20read%20a%20table%20schema%2C%20and%20run%20a%20small%20LIMIT%20query.)

# AnyFinancial

A multi-skill **ripple** for financial data and strategy research on Rebyte.
Each skill lives in its own top-level directory with its own `SKILL.md` and
bundled resources; agents load whichever skill a task needs.

## Skills

| Skill | Directory | What it does |
|---|---|---|
| **data** | [`data/`](data/) | Read-only **SQL** over the Rebyte Financial Data Service (Apache DataFusion), plus **semantic (vector) search** over news. Workflow: catalog → schema → query. Includes the `us_news` local builder (incremental mirror + embeddings). |
| **backtesting** | [`backtesting/`](backtesting/) | Realistic, event-driven **backtests** with **NautilusTrader**, using the **data** skill for price retrieval. Phase-based: setup → parameters → data → execute → report. |

## Layout

```
anyfinancial/                     ← the ripple (this repo)
├── data/                         ← skill: data
│   ├── SKILL.md
│   ├── scripts/                  (anyfinancial_cli.py, shared/constants.json)
│   ├── data_builder/us_news/     (local mirror + semantic search)
│   ├── README.md · TEST_PLAN.md · .env.example
├── backtesting/                  ← skill: backtesting
│   ├── SKILL.md
│   ├── scripts/                  (setup.sh, fetch_data.py, run_backtest.py)
│   ├── strategies/ · references/ · evals/
│   └── config.example.json
└── README.md · .gitignore        ← ripple-level
```

## How the skills compose

`backtesting` retrieves prices through `data`: its `fetch_data.py` calls the
`data` skill's CLI (`data/scripts/anyfinancial_cli.py`) to pull OHLCV bars from
`us.eod` / `us.bars_1m`, then runs them through NautilusTrader. You can use
`data` on its own for any read-only financial SQL or news search.

## Quickstart

```bash
# data skill — discover and query
python3 data/scripts/anyfinancial_cli.py catalog
python3 data/scripts/anyfinancial_cli.py schema us.eod
python3 data/scripts/anyfinancial_cli.py query "SELECT t, c FROM us.eod WHERE ticker='AAPL' ORDER BY t DESC LIMIT 5"

# backtesting skill — install, then follow backtesting/SKILL.md
bash backtesting/scripts/setup.sh
```

Inside a Rebyte VM/workspace both skills read the sandbox token and relay URL
from `/home/user/.rebyte.ai/auth.json` automatically. See each skill's `SKILL.md`
for the full workflow.
