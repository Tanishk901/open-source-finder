"""Turn Jev's judgments into a ranked list. Pure code: no network, easy to test and tune.

Jev answers narrow questions; this file decides what to do with the answers.
Change WEIGHTS or the thresholds here without re-running any Jev requests.
"""

from dataclasses import dataclass, field

# How much each dimension counts toward the beginner score (they add up to 1).
WEIGHTS = {"small_scope": 0.4, "clarity": 0.3, "low_context": 0.3}

ACTIONABLE_MIN = 0.5    # below this, the issue is a question/discussion, not a task -> skipped
CLAIMED_MIN = 0.6       # above this, someone is already on it (or it was declined) -> flagged, sorted last
UNSURE_CONFIDENCE = 0.5 # a Score answer below this confidence -> flagged "unsure"; tune on real repos


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


def rank(judged, weights=WEIGHTS):
    """judged: list of (issue, Judgment). Returns (ranked, skipped), best first."""
    ranked, skipped = [], []
    for issue, j in judged:
        if j.actionable < ACTIONABLE_MIN:
            skipped.append((issue, "not a concrete task (question or discussion)"))
            continue
        flags = []
        if j.claimed > CLAIMED_MIN:
            flags.append("claimed")
        if any(c < UNSURE_CONFIDENCE for c in j.confidences.values()):
            flags.append("unsure")
        if any("good first issue" in label.lower() for label in getattr(issue, "labels", [])):
            flags.append("gfi-label")
        ranked.append(Ranked(issue, j, round(beginner_score(j, weights), 3), flags))

    ranked.sort(key=lambda r: ("claimed" in r.flags, -r.beginner))
    return ranked, skipped


def size_label(scope):
    """Readable name for a normalized scope value."""
    names = ["tiny", "small", "medium", "large", "huge"]
    return names[min(len(names) - 1, round(scope * (len(names) - 1)))]
