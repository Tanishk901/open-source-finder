"""Tests for the code-side policy. No network and no API key needed."""

import json
from types import SimpleNamespace

import pytest
from typesafe_sdk import SystemOneResponse

from open_source_finder import budget, cli, github
from open_source_finder.judge import to_judgment
from open_source_finder.rank import Judgment, beginner_score, rank, size_label


def issue(number, labels=()):
    return SimpleNamespace(number=number, title=f"Issue {number}", labels=list(labels))


def judgment(scope=0.2, clarity=0.8, context=0.2, actionable=0.9, claimed=0.1, confidence=0.9):
    return Judgment(scope=scope, clarity=clarity, context_needed=context, actionable=actionable,
                    claimed=claimed, confidences={"scope": confidence, "clarity": confidence})


def test_beginner_score_extremes():
    assert beginner_score(judgment(scope=0, clarity=1, context=0)) == pytest.approx(1.0)
    assert beginner_score(judgment(scope=1, clarity=0, context=1)) == pytest.approx(0.0)


def test_small_clear_issue_ranks_above_big_vague_one():
    ranked, _ = rank([
        (issue(1), judgment(scope=0.9, clarity=0.2, context=0.9)),
        (issue(2), judgment(scope=0.1, clarity=0.9, context=0.1)),
    ])
    assert [r.issue.number for r in ranked] == [2, 1]


def test_questions_and_discussions_are_skipped():
    ranked, skipped = rank([(issue(1), judgment(actionable=0.2)), (issue(2), judgment())])
    assert [r.issue.number for r in ranked] == [2]
    assert skipped[0][0].number == 1


def test_claimed_issue_is_flagged_and_sorted_last_even_if_easier():
    ranked, _ = rank([
        (issue(1), judgment(scope=0.0, clarity=1.0, context=0.0, claimed=0.95)),
        (issue(2), judgment(scope=0.5, clarity=0.5, context=0.5)),
    ])
    assert [r.issue.number for r in ranked] == [2, 1]
    assert "claimed" in ranked[1].flags


def test_low_confidence_is_flagged_unsure():
    ranked, _ = rank([(issue(1), judgment(confidence=0.3))])
    assert "unsure" in ranked[0].flags


def test_existing_label_is_shown_but_does_not_change_score():
    plain, _ = rank([(issue(1), judgment())])
    labeled, _ = rank([(issue(1, labels=["Good First Issue"]), judgment())])
    assert "gfi-label" in labeled[0].flags
    assert labeled[0].beginner == plain[0].beginner


def test_size_label():
    assert size_label(0.0) == "tiny"
    assert size_label(1.0) == "huge"


def score_answer(score, levels, confidence=0.8):
    keys = [str(i) for i in range(levels)]
    return {"type": "score", "score": score, "confidence": confidence,
            "legend": {k: f"level {k}" for k in keys}, "probabilities": {k: 1 / levels for k in keys}}


def test_to_judgment_normalizes_real_sdk_response():
    response = SystemOneResponse.model_validate_json(json.dumps({  # parsed from JSON, like a real API reply
        "model": "jev",
        "usage": {"input_tokens": 500, "output_tokens": 5},
        "answers": {
            "scope": score_answer(2.0, 5),           # 2 of 0..4 -> 0.5
            "clarity": score_answer(3.0, 4, 0.95),   # 3 of 0..3 -> 1.0
            "context_needed": score_answer(0.0, 4),  # -> 0.0
            "actionable": {"type": "noul", "noul": 0.97},
            "claimed": {"type": "noul", "noul": 0.04},
        },
    }))
    j = to_judgment(response)
    assert (j.scope, j.clarity, j.context_needed) == (0.5, 1.0, 0.0)
    assert (j.actionable, j.claimed) == (0.97, 0.04)
    assert j.confidences["clarity"] == 0.95


def test_budget_refuses_call_that_could_cross_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, "SPEND_FILE", tmp_path / "spend.json")
    monkeypatch.setenv("JEV_BUDGET_USD", "0.01")
    budget.check()  # nothing spent yet: allowed
    budget.record(SimpleNamespace(input_tokens=200_000))  # ~$0.0084 spent
    with pytest.raises(budget.BudgetExceeded):
        budget.check()


def test_budget_limit_set_in_env_file_is_honored(tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_BUDGET_USD", raising=False)
    (tmp_path / ".env").write_text("JEV_BUDGET_USD=0.50\n", encoding="utf-8")
    monkeypatch.setattr(budget, "ENV_FILES", [tmp_path / ".env"])
    budget.load_env()
    assert budget.limit_usd() == 0.50


@pytest.mark.parametrize("line, expected", [
    ("TYPESAFE_API_KEY=abc", "abc"),
    ("TYPESAFE_API_KEY = abc", "abc"),
    ('TYPESAFE_API_KEY="abc"', "abc"),
    ("TYPESAFE_API_KEY='abc'   # my key", "abc"),
    ("TYPESAFE_API_KEY=abc  # my key", "abc"),
    ("\ufeffTYPESAFE_API_KEY=abc", "abc"),  # saved as "UTF-8 with BOM" by some Windows editors
])
def test_parse_env_handles_common_formats(line, expected):
    assert budget.parse_env(line)["TYPESAFE_API_KEY"] == expected


def test_parse_env_ignores_comments_and_blank_lines():
    assert budget.parse_env("# comment\n\nNO_EQUALS\nA=1") == {"A": "1"}


def test_load_env_reads_project_env_when_local_one_lacks_the_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    local, project = tmp_path / "local.env", tmp_path / "project.env"
    local.write_text("TYPESAFE_API_KEY=paste_your_key_here\nOTHER=1\n", encoding="utf-8")
    project.write_text("TYPESAFE_API_KEY=real-key\n", encoding="utf-8-sig")
    monkeypatch.setattr(budget, "ENV_FILES", [local, project])
    assert budget.load_env() is True
    assert budget.os.environ["TYPESAFE_API_KEY"] == "real-key"


@pytest.mark.parametrize("text", [
    "rust-lang/rustlings",
    "rust-lang/rustlings/",
    " rust-lang/rustlings ",
    "https://github.com/rust-lang/rustlings",
    "https://github.com/rust-lang/rustlings/issues/2453",
    "github.com/rust-lang/rustlings.git",
    "git@github.com:rust-lang/rustlings.git",
])
def test_parse_repo_accepts_names_and_urls(text):
    assert github.parse_repo(text) == "rust-lang/rustlings"


@pytest.mark.parametrize("text", ["owner", "", "https://gitlab.com/a/b", "a b/c"])
def test_parse_repo_rejects_non_repos(text):
    with pytest.raises(github.GitHubError):
        github.parse_repo(text)


@pytest.mark.parametrize("value", ["0", "-1"])
def test_top_must_be_positive(value):
    with pytest.raises(SystemExit):
        cli.main(["scan", "a/b", "--top", value, "--mock"])


def http_error(code, headers=None):
    import email.message
    import urllib.error
    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", msg, None)


@pytest.mark.parametrize("code, headers, expected", [
    (401, {}, "rejected GITHUB_TOKEN"),
    (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}, "rate limit"),
    (429, {}, "rate limit"),
    (403, {"X-RateLimit-Remaining": "4000"}, "refused access"),
    (404, {}, "Not found"),
])
def test_github_errors_explain_the_cause(monkeypatch, code, headers, expected):
    def fail(*args, **kwargs):
        raise http_error(code, headers)
    monkeypatch.setattr(github.urllib.request, "urlopen", fail)
    with pytest.raises(github.GitHubError, match=expected):
        github.fetch_repo("a/b")
