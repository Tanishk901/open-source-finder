# Changelog

## 0.2.0 (2026-10-24)

### New

- **Judge issues for free with a local model.** `--judge ollama` asks a model running in
  [Ollama](https://ollama.com) the same five questions as Jev. No API key needed, and it works
  offline once the issues are fetched. Not yet tested against a real model: please report how it
  does.
- **Scanning a repo again is mostly free.** Judgments are saved and reused for issues that haven't
  changed on GitHub. `--no-cache` judges everything again.
- **Newcomer-labeled issues are judged first** (`good first issue`, `first timers only`, `E-easy`,
  `help wanted`, …), then the newest issues. The table says which labels were used, and any
  newcomer label is flagged **beginner-label**.
- **Issues too big or complex for a first contribution are hidden.** Show them with `--all`.
- **Faster:** comments are fetched and issues judged 8 at a time (a 30-issue scan went from 32s to
  12s).
- The repo can be given as a GitHub link, including `/issues/...` links and `.git` clone URLs.
- The default model is now `jev-latest`.

### Fixed

- Hitting GitHub's rate limit while reading comments no longer ends the run. The scan finishes and
  lists the issues it couldn't check for claims.
- Ctrl+C or reaching the spending cap keeps the issues already judged (and already paid for).
- Archived repos and repos with GitHub issues turned off stop with a clear message.
- The spending record is written safely and recovers if it gets damaged.
- `.env` files saved with a BOM, quotes or comments are read correctly, `JEV_BUDGET_USD` set in
  `.env` is honored, and `.env` is found in the project folder when you run from elsewhere.
- GitHub 401/403 errors explain the real cause, and rate-limit errors say when the limit resets.
- TypeSafe API errors show a message instead of a traceback.
- Issues waiting on a maintainer decision are no longer recommended, and **unsure** is flagged
  only for low-confidence answers (below 0.3).
- Enough recent comments are read even when the last page holds only one.
- The table stays aligned for 6-digit issue numbers.
- The `--mock` judge no longer treats "Help wanted" titles as questions.

## 0.1.0 (2026-10-03)

First release: rank a GitHub repo's open issues for first-time contributors with Jev.
