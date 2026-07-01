#!/usr/bin/env bash
# Set up the backtesting environment: a dedicated venv with NautilusTrader.
#
# Idempotent: safe to re-run. Creates ./.venv-backtest next to the skill unless
# BACKTEST_VENV is set. Verifies the install with an import + tiny smoke run.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${BACKTEST_VENV:-$SKILL_DIR/.venv-backtest}"
PY="${PYTHON:-python3}"

echo "==> Python: $("$PY" --version 2>&1)  ($( "$PY" -c 'import platform;print(platform.machine())'))"
echo "==> Venv:   $VENV"

if [[ ! -d "$VENV" ]]; then
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install --quiet --upgrade pip

# NautilusTrader ships prebuilt manylinux wheels for cp311-cp313 (x86_64/arm64).
# No compiler needed. requests is used by the data fetcher (falls back to urllib).
if ! python -c "import nautilus_trader" 2>/dev/null; then
  echo "==> Installing nautilus_trader (prebuilt wheel, ~175 MB)…"
  python -m pip install --quiet "nautilus_trader" requests
else
  echo "==> nautilus_trader already present"
fi

echo "==> Verifying install…"
python - <<'PY'
import nautilus_trader, sys, pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import FillModel, FixedFeeModel
print(f"nautilus_trader {nautilus_trader.__version__}")
print(f"python {sys.version.split()[0]} | pandas {pd.__version__}")
print("OK: engine + fill/fee models import cleanly")
PY

echo
echo "Setup complete. Activate with:  source \"$VENV/bin/activate\""
echo "Next: configure a run (see SKILL.md), then:"
echo "  python scripts/fetch_data.py   --config your.config.json"
echo "  python scripts/run_backtest.py --config your.config.json"
