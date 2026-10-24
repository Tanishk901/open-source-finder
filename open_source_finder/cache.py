"""Remember judgments, so scanning a repo again only pays for the issues that changed.

A saved judgment is reused while three things stay the same: the issue on GitHub (its `updated_at`,
which moves on every edit, label change and new comment), the model, and the questions in judge.py.
Entries older than MAX_AGE_DAYS are dropped, so the file stays small and answers don't go stale.
"""

import hashlib
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

from .rank import Judgment

CACHE_FILE = Path.home() / ".open-source-finder" / "judgments.json"
MAX_AGE_DAYS = 30


def _load():
    try:
        entries = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}  # missing or damaged: it's only a cache, so start empty
    oldest = time.time() - MAX_AGE_DAYS * 86400
    return {key: e for key, e in entries.items() if isinstance(e, dict) and e.get("saved_at", 0) >= oldest}


def _save(entries):
    # Same as budget._save: write a temporary file, then swap it in atomically.
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries), encoding="utf-8")
    tmp.replace(CACHE_FILE)


class CachedJudge:
    """Wraps another judge: answers from the cache when it can, and saves each new answer as it arrives."""

    def __init__(self, inner, model, questions):
        self.inner = inner
        # Changing the model or any question's wording invalidates every saved answer.
        self.version = hashlib.sha256(f"{model}\n{questions!r}".encode("utf-8")).hexdigest()[:16]
        self.hits = 0
        self._lock = threading.Lock()
        self._entries = _load()

    def judge(self, repo, issue):
        key = f"{repo.full_name}#{issue.number}"
        updated_at = getattr(issue, "updated_at", "")
        with self._lock:
            entry = self._entries.get(key)
            if updated_at and entry and entry.get("updated_at") == updated_at and entry.get("version") == self.version:
                try:
                    judgment = Judgment(**entry["judgment"])
                except (KeyError, TypeError):
                    pass  # saved by a version with different fields; judge it again
                else:
                    self.hits += 1
                    return judgment
        judgment = self.inner.judge(repo, issue)
        # Judged without its comments (rate limit): don't keep that answer, so the next scan reads them.
        if updated_at and not getattr(issue, "comments_skipped", False):
            with self._lock:
                self._entries[key] = {"updated_at": updated_at, "version": self.version,
                                      "saved_at": time.time(), "judgment": asdict(judgment)}
                _save(self._entries)
        return judgment
