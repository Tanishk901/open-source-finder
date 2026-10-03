# open-source-finder

[![tests](https://github.com/Tanishk901/open-source-finder/actions/workflows/test.yml/badge.svg)](https://github.com/Tanishk901/open-source-finder/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
[![Built with Jev](https://img.shields.io/badge/built%20with-Jev-8250df.svg)](https://docs.typesafe.ai)

**Find the open issues in any GitHub repo that suit a first-time contributor.**

Most repos have dozens of open issues, and only a few are a good first contribution. The
`good first issue` label helps, but it's often missing, out of date, or on issues someone
already took. `open-source-finder` reads each open issue and ranks them by how small, clear, and
self-contained they are. It also flags issues that someone is already working on.

![Real output for rust-lang/rustlings: a ranked table of beginner-friendly issues with scores, sizes, flags and links](docs/demo.svg)

Real output from a scan of [rust-lang/rustlings](https://github.com/rust-lang/rustlings) on
4 October 2026 (rows 5–9 left out). Your results will change as issues are opened and closed.

Built with [Jev](https://docs.typesafe.ai), TypeSafe AI's System One model, which answers
narrow questions with typed, calibrated answers instead of generated text.

> **Note:** This project's code is open source (MIT). Jev itself is a hosted model, so judging
> real issues needs a TypeSafe API key and costs a small amount per issue (see [Cost](#cost)).
> You can try everything else for free with `--mock`.
> This is a community project, not affiliated with TypeSafe AI.

## Contents

- [Install](#install)
- [Add your API key](#add-your-api-key)
- [Use](#use)
- [How it works](#how-it-works)
- [What Jev catches](#what-jev-catches)
- [Cost](#cost)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

## Install

You need Python 3.10 or newer and git.

**Windows (PowerShell):**

```powershell
git clone https://github.com/Tanishk901/open-source-finder
cd open-source-finder
python -m venv .venv
.venv\Scripts\python -m pip install -e .
```

**macOS / Linux:**

```bash
git clone https://github.com/Tanishk901/open-source-finder
cd open-source-finder
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

This installs the `open-source-finder` command inside the project's own `.venv` folder, so
it doesn't affect the rest of your system.

## Add your API key

![Copy .env.example to .env in the project folder, then paste your key after TYPESAFE_API_KEY=](docs/api-key.svg)

1. Get a key from the [TypeSafe console](https://console.typesafe.ai/keys).
2. In the `open-source-finder` folder, copy `.env.example` to a new file named `.env`:

   ```bash
   cp .env.example .env      # macOS / Linux / Git Bash
   copy .env.example .env    # Windows Command Prompt
   ```

3. Open `.env` and replace `paste_your_key_here` with your key:

   ```ini
   TYPESAFE_API_KEY=your-key-here
   ```

`.env` is listed in `.gitignore`, so your key is never committed. The tool reads `.env` from
the folder you run it in, or else from the project folder. You can also set
`TYPESAFE_API_KEY` as an environment variable instead.

**Optional: GitHub token.** Without one, GitHub allows only 60 requests an hour, which is
about two scans. A free token raises this to 5,000:

1. Open [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new).
2. Name it `open-source-finder` and set **Repository access** to **Public repositories (read-only)**.
   No other permissions are needed.
3. Click **Generate token**, then paste the token after `GITHUB_TOKEN=` in `.env`.

## Use

From the `open-source-finder` folder, run `scan` with any public repo written as `owner/name`.

**Windows (PowerShell):**

```powershell
.venv\Scripts\open-source-finder scan rust-lang/rustlings
```

**macOS / Linux:**

```bash
.venv/bin/open-source-finder scan rust-lang/rustlings
```

If you activate the virtual environment first (`.venv\Scripts\activate` on Windows,
`source .venv/bin/activate` on macOS/Linux), you can type just `open-source-finder`.
The examples below use that short form:

```bash
# Try it without any key (keyword rules instead of Jev, much less accurate):
open-source-finder scan pandas-dev/pandas --mock

# Show only the best 5 issues:
open-source-finder scan pandas-dev/pandas --top 5

# Machine-readable output, including every raw judgment:
open-source-finder scan pandas-dev/pandas --json > issues.json
```

**Reading the results:**

| Column | Meaning |
| --- | --- |
| **Beginner** | Overall fit for a first contribution, from 0 to 1. Higher is better. |
| **Clear** | How clearly the issue says what to do and how to check it, from 0 to 1. |
| **Size** | How big the change is: tiny, small, medium, large, or huge. |
| **Flags** | `claimed`: someone is on it, or maintainers declined it. `unsure`: Jev wasn't confident, so read it yourself. `gfi-label`: maintainers labeled it "good first issue". |

| Option | Default | Meaning |
| --- | --- | --- |
| `--top N` | 10 | How many issues to show |
| `--max-issues N` | 30 | How many open issues to fetch and judge (one Jev request each) |
| `--json` | off | Print full results as JSON |
| `--judge` | `jev` | Who judges the issues: `jev` or `mock` |
| `--mock` | off | Shorthand for `--judge mock`: keyword rules, no API key needed |
| `--model` | `jev-latest` | TypeSafe model: `jev-latest` or `jev-preview` |


## How it works

![How it works: fetch issues, ask Jev five questions per issue, rank in code, show your list](docs/how-it-works.svg)

1. **Fetch** open issues from the GitHub API. Pull requests and assigned issues are dropped,
   and the latest 5 comments are read for each remaining issue.
2. **Judge.** Each issue goes to Jev in one request with five questions that run in parallel:

   | Question | Type | What it asks |
   | --- | --- | --- |
   | `scope` | Score, 5 levels | One-line fix → cross-cutting redesign |
   | `clarity` | Score, 4 levels | Unclear request → outcome, verification, and location all stated |
   | `context_needed` | Score, 4 levels | Newcomer can do it → needs maintainer decisions |
   | `actionable` | Noul (yes/no) | A concrete code/docs/test change, not a question or discussion? |
   | `claimed` | Noul (yes/no) | Do the comments show someone is on it, or that it was declined? |

3. **Rank** in plain code ([`rank.py`](open_source_finder/rank.py)):
   - Issues with `actionable < 0.5` are skipped.
   - The beginner score is `0.4 × small scope + 0.3 × clarity + 0.3 × low context needed`,
     each normalized to 0–1.
   - `claimed > 0.6` → flagged **claimed** and sorted to the bottom.
   - Any Score answered with confidence below 0.5 → flagged **unsure**.
   - The existing `good first issue` label is shown as **gfi-label**, but it doesn't change the
     score, so you can compare Jev's view with the maintainers'.

   Jev answers the questions; the code decides what to do with the answers. To change the
   weights or thresholds, edit the constants at the top of `rank.py`.

## What Jev catches

Real examples from the first scans (October 2026):

- **Already claimed.** In `rust-lang/rustlings`, issue
  [#1937](https://github.com/rust-lang/rustlings/issues/1937) looks perfect for a beginner:
  small, and with a clarity of 0.94. But in its comments the maintainer says, *"I will take care
  of it before releasing v7, no help needed."* Jev flagged it **claimed**, so it was sorted to
  the bottom instead of being recommended.
- **Not a task.** In `fastapi/fastapi`, Jev skipped the pinned "Roadmap" issue and a
  promotional post. Both are open issues, but neither is something a contributor can fix.
- **Better than keywords.** The `--mock` keyword rules gave almost every rustlings issue the
  same score. Jev spread them from 0.30 to 0.93, with a tiny, clearly described docs fix at the
  top.

## Cost

Each judged issue is one Jev request of roughly 1,000–3,000 input tokens (issue bodies are cut
to 3,000 characters, and comments to 500 each). At Jev's listed price of $0.042 per million
input tokens, a 30-issue scan costs well under a cent. Check
[TypeSafe's docs](https://docs.typesafe.ai) for current pricing.

A spending cap is built in. Total spend is tracked in `~/.open-source-finder/spend.json`, and the
run stops before any request that could cross `$5.00` (set `JEV_BUDGET_USD` to change this).

## Troubleshooting

| You see | What it means | Fix |
| --- | --- | --- |
| `The module '.venv' could not be loaded` (PowerShell) | You're not in the project folder. | `cd` into `open-source-finder` first, then run the command again. |
| `No TYPESAFE_API_KEY found` | There's no `.env`, or the key line still says `paste_your_key_here`. | Follow [Add your API key](#add-your-api-key), or try `--mock`. |
| `GitHub rate limit hit. It resets in about N minute(s).` | You've used GitHub's 60 requests an hour for unauthenticated users. | Add a free `GITHUB_TOKEN` (see [Add your API key](#add-your-api-key)), or wait. |
| `TypeSafe API error: ... Unknown model` | The `--model` name isn't one your account offers. | Use `jev-latest` (the default) or `jev-preview`. |
| `TypeSafe API error: ... 401` | The API key is wrong or was revoked. | Create a new key in the [TypeSafe console](https://console.typesafe.ai/keys) and update `.env`. |
| `Not found: /repos/...` | There's a typo in the repo name, or the repo is private. | Use the `owner/name` from the repo's GitHub URL. |
| `... spent of $5.00 limit; stopping.` | The spending cap was reached. | Raise `JEV_BUDGET_USD` in `.env` if you want to spend more. |
| `owner/repo` gives "Not found" | `owner/repo` is a placeholder. | Use a real repo, e.g. `rust-lang/rustlings`. |

## Roadmap

- [x] Judge issues with Jev
- [ ] Judge issues with local models (e.g. through Ollama), so the tool can run free and offline
- [ ] Compare judges on the same issues, to see which picks the best first contributions

Judges are pluggable. A judge is any class with `judge(repo, issue)` that returns a
[`Judgment`](open_source_finder/rank.py) (the same five answers, normalized to 0–1). To add one,
register it in `JUDGES` and `make_judge()` in [`cli.py`](open_source_finder/cli.py). The ranking
code doesn't change.

## Development

```bash
pip install -e ".[test]"
pytest
```

The tests cover the ranking policy, conversion of SDK responses, and the budget cap. They use no
network and need no API key.

## Credits

- [TypeSafe Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python) (MIT)
- The budget helper is adapted from [jev-starter-examples](https://github.com/Tanishk901/jev-starter-examples)
- More Jev projects: [awesome-jev](https://github.com/heyjunpenn/awesome-jev) / [jevbest.com](https://jevbest.com)

## License

[MIT](LICENSE)
