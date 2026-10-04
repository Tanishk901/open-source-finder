"""Turn Jev's judgments into a ranked list. Pure code: no network, easy to test and tune.

Jev answers narrow questions; this file decides what to do with the answers.
Change WEIGHTS or the thresholds here without re-running any Jev requests.
"""

from dataclasses import dataclass, field

from .github import BEGINNER_LABEL_PATTERNS, NOT_BEGINNER_LABEL

# How much each dimension counts toward the beginner score (they add up to 1).
WEIGHTS = {"small_scope": 0.4, "clarity": 0.3, "low_context": 0.3}

# Thresholds were tuned on 120 real issues from pandas, rust, freeCodeCamp and ruff (Oct 2026).
ACTIONABLE_MIN = 0.5    # below this, the issue is a question/discussion, not a task -> skipped
CLAIMED_MIN = 0.6       # above this, someone is already on it (or it was declined) -> flagged, sorted last
UNSURE_CONFIDENCE = 0.3 # a Score answer below this confidence -> flagged "unsure" (~1 in 9 candidates)
MIN_BEGINNER = 0.45     # below this, too big or complex for a first contribution -> hidden unless --all

NOT_A_TASK = "not a concrete task (question or discussion)"
TOO_HARD = "too big or complex for a first contribution"


@dataclass
class Judgment:
    """Jev's answers for one issue. Scores are normalized to 0..1 (0 = lowest level)."""
    scope: float
    clarity: float
    context_needed: float
    actionable: float   # Noul: probability it is a concrete task
    claimed: float      # Noul: probability it is taken or declined
    confidences: dict[str, float] = field(default_factory=dict)  # Score name -> confidence


@dataclass
class Ranked:
    issue: object
    judgment: Judgment
    beginner: float
    flags: list[str]


def beginner_score(j, weights=WEIGHTS):
    return (weights["small_scope"] * (1 - j.scope)
            + weights["clarity"] * j.clarity
            + weights["low_context"] * (1 - j.context_needed))


def rank(judged, weights=WEIGHTS, min_beginner=MIN_BEGINNER):
    """judged: list of (issue, Judgment). Returns (ranked, skipped), best first.
    skipped holds (issue, reason, Judgment) for issues left out of the ranking."""
    ranked, skipped = [], []
    for issue, j in judged:
        if j.actionable < ACTIONABLE_MIN:
            skipped.append((issue, NOT_A_TASK, j))
            continue
        score = round(beginner_score(j, weights), 3)
        if score < min_beginner:
            skipped.append((issue, TOO_HARD, j))
            continue
        flags = []
        if j.claimed > CLAIMED_MIN:
            flags.append("claimed")
        if any(c < UNSURE_CONFIDENCE for c in j.confidences.values()):
            flags.append("unsure")
        if any(is_beginner_label(label) for label in getattr(issue, "labels", [])):
            flags.append("beginner-label")
        ranked.append(Ranked(issue, j, score, flags))

    ranked.sort(key=lambda r: ("claimed" in r.flags, -r.beginner))
    return ranked, skipped


def is_beginner_label(name):
    """True for labels like "good first issue", "first timers only" or "E-easy" ("help wanted" doesn't count)."""
    return not NOT_BEGINNER_LABEL.search(name) and any(p.search(name) for p in BEGINNER_LABEL_PATTERNS[:-1])


def size_label(scope):
    """Readable name for a normalized scope value."""
    names = ["tiny", "small", "medium", "large", "huge"]
    return names[min(len(names) - 1, round(scope * (len(names) - 1)))]
