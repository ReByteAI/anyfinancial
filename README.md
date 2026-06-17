# AnyFinancial Skill

Financial data exploration skill for AI agents. AnyFinancial queries xyznot market data with **Data Fusion SQL** through the V1 SQL endpoint and includes convenience commands for prices, fundamentals, news, schema discovery, and arbitrary SQL.

## Download & Install

### For AI Agents

Install this folder into your agent's skill directory:

```bash
cp -R anyfinancial <your_agent_skill_dir>/anyfinancial
```

Example paths:

```bash
# Claude Code
cp -R anyfinancial ~/.claude/skills/anyfinancial

# Cursor/Windsurf project-local skills
cp -R anyfinancial <project>/.skills/anyfinancial

# Shared agents
cp -R anyfinancial ~/.agents/skills/anyfinancial
```

### For Humans

1. Place the repo in your agent skill directory.
2. Configure the API key if needed.
3. Run the entry test to verify installation.

## API Key Configuration

No runtime configuration is required. The CLI reads the xyznot API key from:

```
scripts/shared/constants.json
```

The `.env.example` file is kept only as a reference. `anyfinancial_cli.py` does not load `.env` and does not read external API-key environment variables.

## Post-Install Verification

### Step 1: Check Python

```bash
python --version
python3 --version
```

Use Python 3.6+ with the `requests` library.

### Step 2: Run offline docs

```bash
python3 scripts/anyfinancial_cli.py doc
```

### Step 3: Run live API checks

```bash
python3 scripts/anyfinancial_cli.py discover_schemas
python3 scripts/anyfinancial_cli.py price AAPL
python3 scripts/anyfinancial_cli.py fundamentals AAPL --limit 2
python3 scripts/anyfinancial_cli.py news AAPL --limit 2
python3 scripts/anyfinancial_cli.py query "SELECT title, published_utc FROM news ORDER BY published_utc DESC LIMIT 1"
```

## Routine Agent Usage

```bash
python3 scripts/anyfinancial_cli.py price AAPL
python3 scripts/anyfinancial_cli.py news TSLA --limit 5
python3 scripts/anyfinancial_cli.py fundamentals MSFT --limit 3
python3 scripts/anyfinancial_cli.py query "SELECT ticker, t, c FROM bars_1m WHERE ticker = 'AAPL' AND year = '2026' AND month = '6' ORDER BY t DESC LIMIT 5"
```

## File Structure

```text
anyfinancial/
├── .env.example
├── SKILL.md
├── README.md
├── TEST_PLAN.md
└── scripts/
    ├── anyfinancial_cli.py
    └── shared/
        ├── constants.json
        └── doc_spec.md
```
