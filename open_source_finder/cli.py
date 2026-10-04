"""open-source-finder: find the open issues in a GitHub repo that suit a first-time contributor."""

import argparse
import json
import sys
from dataclasses import asdict

from . import budget, github
from .rank import MIN_BEGINNER, NOT_A_TASK, TOO_HARD, rank, size_label

TITLE_WIDTH = 46

# A judge is any object with judge(repo, issue) -> rank.Judgment.
# To add a new one (e.g. a local LLM), write the class and register it here.
JUDGES = ["jev", "mock"]


def make_judge(name, model):
    if name == "mock":
        from .mock import MockJudge
        return MockJudge()
    from .judge import JevJudge
    return JevJudge(model=model)


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(prog="open-source-finder", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="rank a repo's open issues for beginners")
    scan.add_argument("repo", help="GitHub repo as owner/name or URL, e.g. rust-lang/rustlings")
    scan.add_argument("--top", type=positive_int, default=10, help="how many issues to show (default 10)")
    scan.add_argument("--max-issues", type=positive_int, default=30,
                      help="how many open issues to fetch and judge (default 30; each costs one Jev request)")
    scan.add_argument("--json", action="store_true", help="print full results as JSON")
    scan.add_argument("--all", action="store_true",
                      help="also show issues judged too big or complex for a first contribution")
    scan.add_argument("--judge", choices=JUDGES, default="jev", help="who judges the issues (default jev)")
    scan.add_argument("--mock", action="store_true", help="shorthand for --judge mock (no API key needed)")
    scan.add_argument("--model", default="jev-latest", help="TypeSafe model: jev-latest (default) or jev-preview")
    args = parser.parse_args(argv)
    if args.mock:
        args.judge = "mock"

    # Issue titles often contain emoji; don't crash on consoles that can't show them (e.g. Windows cp1252).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    has_key = budget.load_env()
    if args.judge == "jev" and not has_key:
        sys.exit("No TYPESAFE_API_KEY found. Put it in .env (see .env.example), or try --mock.")
    judge = make_judge(args.judge, args.model)

    try:
        repo = github.fetch_repo(github.parse_repo(args.repo))
        issues = github.fetch_issues(repo.full_name, args.max_issues)
    except github.GitHubError as error:
        sys.exit(str(error))

    judged = []
    for i, issue in enumerate(issues, 1):
        print(f"\rJudging issue {i}/{len(issues)}...", end="", file=sys.stderr, flush=True)
        try:
            judged.append((issue, judge.judge(repo, issue)))
        except budget.BudgetExceeded as error:
            print(f"\n{error} Showing the {len(judged)} issues judged so far.", file=sys.stderr)
            break
        except Exception as error:
            # SDK errors (bad key, unknown model, rate limit) carry a clear message; show it, not a traceback.
            if type(error).__module__.startswith("typesafe_sdk"):
                sys.exit(f"\nTypeSafe API error: {error}")
            raise
    print(file=sys.stderr)

    ranked, skipped = rank(judged, min_beginner=0 if args.all else MIN_BEGINNER)
    if args.json:
        print_json(repo, ranked, skipped, args)
    else:
        print_table(repo, ranked[:args.top], skipped, args)


def print_table(repo, ranked, skipped, args):
    mode = "mock rules (not Jev)" if args.judge == "mock" else f"Jev ({args.model})"
    print(f"\n{repo.full_name} - best issues for a first contribution - judged by {mode}\n")
    if not ranked:
        print("No suitable open issues found.")
    else:
        # Big repos have 6-digit issue numbers; size the column to fit so the table stays aligned.
        num_width = max(5, *(len(str(r.issue.number)) for r in ranked))
        print(f" #  {'Issue':<{TITLE_WIDTH + num_width + 2}} Beginner  Clear  Size    Flags")
        for i, r in enumerate(ranked, 1):
            title = r.issue.title if len(r.issue.title) <= TITLE_WIDTH else r.issue.title[:TITLE_WIDTH - 3] + "..."
            print(f"{i:>2}  #{r.issue.number:<{num_width}} {title:<{TITLE_WIDTH}} {r.beginner:>8.2f}  "
                  f"{r.judgment.clarity:>5.2f}  {size_label(r.judgment.scope):<6}  {','.join(r.flags)}")
            print(f"    {r.issue.url}")
    not_tasks = sum(reason == NOT_A_TASK for _, reason, _ in skipped)
    too_hard = sum(reason == TOO_HARD for _, reason, _ in skipped)
    print(f"\nSkipped {not_tasks} issue(s) that look like questions or discussions.")
    if too_hard:
        print(f"Hid {too_hard} issue(s) that look too big or complex for a first contribution "
              "(show them with --all).")
    print("Flags: claimed = someone is already on it or it was declined; unsure = Jev was not confident; "
          "gfi-label = maintainers labeled it 'good first issue'.")
    if args.judge == "jev":
        print(budget.summary())


def print_json(repo, ranked, skipped, args):
    out = {
        "repo": repo.full_name,
        "judge": args.judge if args.judge != "jev" else args.model,
        "ranked": [{
            "number": r.issue.number, "title": r.issue.title, "url": r.issue.url,
            "labels": r.issue.labels, "beginner": r.beginner, "flags": r.flags,
            "judgment": asdict(r.judgment),
        } for r in ranked],
        "skipped": [{"number": issue.number, "title": issue.title, "url": issue.url, "reason": reason,
                     "judgment": asdict(j)} for issue, reason, j in skipped],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
