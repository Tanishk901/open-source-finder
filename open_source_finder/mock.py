"""Keyword-based stand-in for Jev, so you can try the tool without an API key.

It is deliberately simple and much less accurate than Jev. Use it to see the output
format and test the pipeline, not to pick issues.
"""

from .rank import Judgment

SMALL_HINTS = ("typo", "docs", "documentation", "readme", "spelling", "wording", "comment", "error message")
LARGE_HINTS = ("refactor", "redesign", "rewrite", "architecture", "migrate", "rfc", "breaking", "performance")
QUESTION_HINTS = ("how do i", "how to", "question", "is it possible", "help", "discussion", "tracking")
CLAIM_HINTS = ("i'm working on", "i am working on", "i'll take", "i will take", "can i work",
               "assign me", "opened a pr", "opened pr", "wontfix", "won't fix", "not planned")


class MockJudge:
    def judge(self, repo, issue):
        title = issue.title.lower()
        text = f"{title}\n{issue.body}".lower()
        comments = "\n".join(issue.recent_comments).lower()

        # Size and question hints only look at the title: issue templates repeat words like
        # "documentation" and "help" in every body.
        if any(h in title for h in LARGE_HINTS):
            scope = 0.75
        elif any(h in title for h in SMALL_HINTS):
            scope = 0.1
        else:
            scope = 0.4

        clarity = 0.3
        if len(issue.body) > 300:
            clarity += 0.3
        if "```" in issue.body or "steps to reproduce" in text or "expected" in text:
            clarity += 0.3

        context_needed = 0.2 if scope < 0.3 else 0.7 if scope > 0.6 else 0.45
        actionable = 0.2 if title.endswith("?") or any(h in title for h in QUESTION_HINTS) else 0.8
        claimed = 0.9 if any(h in comments for h in CLAIM_HINTS) else 0.1

        return Judgment(scope=scope, clarity=min(clarity, 1.0), context_needed=context_needed,
                        actionable=actionable, claimed=claimed,
                        confidences={"scope": 0.9, "clarity": 0.9, "context_needed": 0.9})
