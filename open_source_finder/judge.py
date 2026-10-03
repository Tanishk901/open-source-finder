"""Ask Jev five narrow questions about each issue, in a single request per issue.

The questions run in parallel on the same state and cannot see each other's answers.
Combining the answers into a ranking is rank.py's job, not Jev's.
"""

from typesafe_sdk import Noul, NoulCriteria, Score, TypeSafeClient

from . import budget
from .rank import Judgment

SCOPE = [
    "A one-line or typo-level change in a single file, such as fixing a typo, a wording, or a constant.",
    "A small, self-contained change in one or two files, such as adding a parameter, a test, or an error message.",
    "A moderate change to one feature across a few files, usually with new tests.",
    "A large change spanning several modules, or a new feature that needs its own design.",
    "A cross-cutting redesign, migration, or architectural change across the project.",
]

CLARITY = [
    "It is unclear what is being asked: the issue is vague or missing key details.",
    "The problem is described, but the desired outcome or how to check it is left open.",
    "The desired outcome is clear, but nothing points to where in the code or docs to change it.",
    "The desired outcome and how to reproduce or verify it are stated, and the relevant file, "
    "function, or doc page is pointed out.",
]

CONTEXT_NEEDED = [
    "A newcomer could do it after reading the issue and the file it points to.",
    "It needs some reading of surrounding code or docs to follow conventions, but no project history.",
    "It needs good familiarity with the project's internals or a specific subsystem.",
    "It needs a design decision from maintainers, deep domain expertise, or knowledge of project history.",
]

QUESTIONS = {
    "scope": Score(
        instructions="How large is the change needed to resolve `issue` in `repo`?",
        criteria=SCOPE,
    ),
    "clarity": Score(
        instructions="How clearly does `issue` describe what a contributor should do and how to verify it?",
        criteria=CLARITY,
    ),
    "context_needed": Score(
        instructions="How much prior knowledge of `repo` would a first-time contributor need to resolve `issue`?",
        criteria=CONTEXT_NEEDED,
    ),
    "actionable": Noul(
        instructions="Does `issue` ask for a concrete change to code, docs, or tests that could be "
                     "submitted as a pull request?",
        criteria=NoulCriteria(
            true="A specific bug fix, feature, documentation, or test change is requested.",
            false="It is a usage question, support request, open-ended discussion, proposal still "
                  "under debate, or a tracking/meta issue.",
        ),
    ),
    "claimed": Noul(
        instructions="Based on `issue.recent_comments`, is `issue` already taken or not wanted?",
        criteria=NoulCriteria(
            true="A commenter says they are working on it or has opened a pull request, or a "
                 "maintainer says it will not be done or is blocked.",
            false="Nobody has claimed it and maintainers have not declined it, or there are no comments.",
        ),
    ),
}

LEVELS = {"scope": len(SCOPE), "clarity": len(CLARITY), "context_needed": len(CONTEXT_NEEDED)}


def build_state(repo, issue):
    return {
        "repo": {"name": repo.full_name, "description": repo.description, "language": repo.language},
        "issue": {
            "title": issue.title,
            "body": issue.body,
            "labels": issue.labels,
            "age_days": issue.age_days,
            "recent_comments": issue.recent_comments,
        },
    }


class JevJudge:
    def __init__(self, model="jev"):
        self.client = TypeSafeClient(model=model)

    def judge(self, repo, issue):
        budget.check()
        response = self.client.system_one(build_state(repo, issue), QUESTIONS)
        budget.record(response.usage)
        return to_judgment(response)


def to_judgment(response):
    scores, nouls = response.scores, response.nouls
    # Normalize each Score to 0..1 by its highest level so dimensions are comparable.
    norm = {name: scores[name].score / (levels - 1) for name, levels in LEVELS.items()}
    return Judgment(
        scope=norm["scope"],
        clarity=norm["clarity"],
        context_needed=norm["context_needed"],
        actionable=nouls["actionable"].noul,
        claimed=nouls["claimed"].noul,
        confidences={name: scores[name].confidence for name in LEVELS},
    )
