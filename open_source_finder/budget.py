"""Load the API key from .env and enforce a spending cap.

Adapted from budget.py in https://github.com/Tanishk901/jev-starter-examples (MIT).
Every Jev call is added up in ~/.open-source-finder/spend.json. A call is refused if it
could push the total past the limit, even in the worst case.
"""

import json
import os
from pathlib import Path

DEFAULT_LIMIT_USD = 5.00
PRICE_PER_INPUT_TOKEN = 0.042 / 1_000_000  # Jev: $0.042 per million input tokens, output is free
MAX_TOKENS_PER_REQUEST = 64_000            # Jev's per-request limit, so the worst-case cost of one call

# ./.env first, then the project folder's .env (for a clone installed with `pip install -e .`).
ENV_FILES = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
SPEND_FILE = Path.home() / ".open-source-finder" / "spend.json"
PLACEHOLDER = "paste_your_key_here"


def load_env():
    """Read KEY=value lines from .env into the environment (existing variables win).
    Returns True if a real TYPESAFE_API_KEY is set."""
    env_file = next((f for f in ENV_FILES if f.exists()), None)
    if env_file:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"'))
    key = os.environ.get("TYPESAFE_API_KEY", "")
    return bool(key) and key != PLACEHOLDER


def limit_usd():
    """The spending cap. Read on every call so a JEV_BUDGET_USD set in .env is honored."""
    try:
        return float(os.environ.get("JEV_BUDGET_USD") or DEFAULT_LIMIT_USD)
    except ValueError:
        return DEFAULT_LIMIT_USD


class BudgetExceeded(Exception):
    pass


def _load():
    if SPEND_FILE.exists():
        return json.loads(SPEND_FILE.read_text(encoding="utf-8"))
    return {"input_tokens": 0, "requests": 0, "usd": 0.0}


def check():
    """Call before each request. Raises BudgetExceeded if the next call could cross the limit."""
    spent = _load()["usd"]
    worst_case = MAX_TOKENS_PER_REQUEST * PRICE_PER_INPUT_TOKEN
    if spent + worst_case > limit_usd():
        raise BudgetExceeded(f"${spent:.4f} spent of ${limit_usd():.2f} limit; stopping.")


def record(usage):
    """Call after each request with response.usage."""
    data = _load()
    data["input_tokens"] += usage.input_tokens or 0
    data["requests"] += 1
    data["usd"] = data["input_tokens"] * PRICE_PER_INPUT_TOKEN
    SPEND_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPEND_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def summary():
    data = _load()
    return (
        f"Total Jev spend so far: ${data['usd']:.6f} of ${limit_usd():.2f} "
        f"({data['requests']} requests, {data['input_tokens']:,} input tokens)"
    )
