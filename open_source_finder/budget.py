"""Load the API key from .env and enforce a spending cap.

Adapted from budget.py in https://github.com/Tanishk901/jev-starter-examples (MIT).
Every Jev call is added up in ~/.open-source-finder/spend.json. A call is refused if it
could push the total past the limit, even in the worst case.
"""

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

DEFAULT_LIMIT_USD = 5.00
PRICE_PER_INPUT_TOKEN = 0.042 / 1_000_000  # Jev: $0.042 per million input tokens, output is free
MAX_TOKENS_PER_REQUEST = 64_000            # Jev's per-request limit, so the worst-case cost of one call

# ./.env first, then the project folder's .env (for a clone installed with `pip install -e .`).
# Both are read, so a .env in another folder that lacks the key doesn't hide the project's one.
ENV_FILES = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
SPEND_FILE = Path.home() / ".open-source-finder" / "spend.json"
PLACEHOLDER = "paste_your_key_here"


def parse_env(text):
    """Parse KEY=value lines. Handles a UTF-8 BOM, quotes, and `# comments` after a value."""
    values = {}
    for line in text.lstrip("﻿").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key or key.startswith("#"):
            continue
        value = value.strip()
        if value[:1] in ("'", '"') and value[0] in value[1:]:
            value = value[1:value.index(value[0], 1)]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key] = value
    return values


def load_env():
    """Read .env files into the environment. Variables already set win, then ./.env, then the
    project folder's .env. Returns True if a real TYPESAFE_API_KEY is set."""
    for env_file in ENV_FILES:
        if env_file.exists():
            for key, value in parse_env(env_file.read_text(encoding="utf-8-sig")).items():
                if value and value != PLACEHOLDER:
                    os.environ.setdefault(key, value)
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


WORST_CASE_USD = MAX_TOKENS_PER_REQUEST * PRICE_PER_INPUT_TOKEN
_lock = threading.Lock()
_in_flight = 0  # requests started but not yet recorded; each could cost up to WORST_CASE_USD


@contextmanager
def reserve():
    """Wrap each Jev request. Refuses to start it if it, plus every request already running,
    could push spending past the limit. Safe to use from several threads at once."""
    global _in_flight
    with _lock:
        spent = _load()["usd"]
        if spent + (_in_flight + 1) * WORST_CASE_USD > limit_usd():
            raise BudgetExceeded(f"${spent:.4f} spent of ${limit_usd():.2f} limit; stopping.")
        _in_flight += 1
    try:
        yield
    finally:
        with _lock:
            _in_flight -= 1


def record(usage):
    """Call after each request with response.usage."""
    with _lock:
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
