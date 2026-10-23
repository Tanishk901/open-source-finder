"""Tests for the Ollama judge. Ollama's HTTP API is faked: no Ollama or model needed."""

import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from open_source_finder import cli, ollama
from open_source_finder.judge import QUESTIONS

REPO = SimpleNamespace(full_name="a/b", description="", language="Python")
ISSUE = SimpleNamespace(number=7, title="Fix typo", body="", labels=[], age_days=1, recent_comments=[])
GOOD = {"scope": 0, "clarity": 3, "context_needed": 0, "actionable": 0.9, "claimed": 0.1}


class FakeOllama:
    """Stands in for urlopen: answers with each reply in turn (a dict, a raw string, or an exception)."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, request, timeout):
        self.requests.append(json.loads(request.data))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return io.BytesIO(json.dumps({"message": {"content": content}}).encode())


@pytest.fixture
def fake(monkeypatch):
    def install(*replies):
        server = FakeOllama(*replies)
        monkeypatch.setattr(ollama.urllib.request, "urlopen", server)
        return server
    return install


def test_good_reply_becomes_a_normalized_judgment(fake):
    server = fake(GOOD)
    j = ollama.OllamaJudge("qwen2.5:7b").judge(REPO, ISSUE)
    assert (j.scope, j.clarity, j.context_needed, j.actionable, j.claimed) == (0, 1, 0, 0.9, 0.1)
    sent = server.requests[0]
    assert sent["model"] == "qwen2.5:7b" and sent["format"] == ollama.SCHEMA and "Fix typo" in sent["messages"][1]["content"]


def test_prompt_asks_every_question_judge_py_asks():
    for name, question in QUESTIONS.items():
        assert f"{name}: {question.instructions}" in ollama.PROMPT


@pytest.mark.parametrize("reply, expected", [
    ({"scope": 9, "actionable": 1.7}, (1.0, 1.0)),         # above range -> top
    ({"scope": -2, "actionable": -0.5}, (0.0, 0.0)),       # below range -> bottom
    ({"scope": "2", "actionable": True}, (0.5, 1.0)),      # numbers as text, a yes/no instead of a number
])
def test_out_of_range_or_oddly_typed_answers_are_clamped(reply, expected):
    j = ollama.parse_reply(json.dumps({**GOOD, **reply}))
    assert (j.scope, j.actionable) == expected


@pytest.mark.parametrize("content", ["not json", "[]", json.dumps({**GOOD, "clarity": "very"}),
                                     json.dumps({k: v for k, v in GOOD.items() if k != "claimed"}),
                                     '{"scope": 0, "clarity": 3, "context_needed": 0, "actionable": NaN, "claimed": 0}'])
def test_unreadable_replies_are_rejected(content):
    with pytest.raises(ollama.UnreadableReply):
        ollama.parse_reply(content)


def test_garbled_reply_is_asked_again_once(fake):
    server = fake("garbled", GOOD)
    assert ollama.OllamaJudge("m").judge(REPO, ISSUE).clarity == 1
    assert len(server.requests) == 2


def test_issue_garbled_twice_is_skipped_and_the_run_goes_on(fake, capsys):
    fake("garbled", "garbled again", GOOD)
    issues = [ISSUE, SimpleNamespace(**{**vars(ISSUE), "number": 8})]
    judged = cli.judge_all(ollama.OllamaJudge("m"), REPO, issues, workers=1)
    assert [i.number for i, _ in judged] == [8]
    assert "Skipped 1 issue(s) whose answers the model garbled: #7" in capsys.readouterr().err


@pytest.mark.parametrize("error, expected", [
    (urllib.error.URLError(ConnectionRefusedError()), "Can't reach Ollama at http://localhost:11434"),
    (urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error": "model not found"}')),
     "ollama pull qwen2.5:7b"),
    (TimeoutError(), "took over"),
])
def test_ollama_problems_stop_the_run_with_a_clear_message(fake, monkeypatch, error, expected):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    fake(error)
    with pytest.raises(SystemExit) as stop:
        cli.judge_all(ollama.OllamaJudge("qwen2.5:7b"), REPO, [ISSUE], workers=1)
    assert expected in str(stop.value)


@pytest.mark.parametrize("host, url", [("127.0.0.1:9999", "http://127.0.0.1:9999"),
                                       ("http://box:11434/", "http://box:11434")])
def test_ollama_host_env_var_is_honored(monkeypatch, host, url):
    monkeypatch.setenv("OLLAMA_HOST", host)
    assert ollama.OllamaJudge("m").url == url


def test_cached_ollama_answers_are_kept_apart_from_jev_ones(tmp_path, monkeypatch):
    from open_source_finder import cache
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "judgments.json")
    local = cli.make_judge("ollama", "qwen2.5:7b")
    jev = cache.CachedJudge(None, "jev-latest", QUESTIONS)  # what make_judge("jev", ...) builds
    assert isinstance(local.inner, ollama.OllamaJudge) and local.version != jev.version


def test_model_default_depends_on_the_judge(monkeypatch):
    seen = {}

    def stop_after_choosing(name, model, use_cache):
        seen["model"] = model
        raise SystemExit

    monkeypatch.setattr(cli, "make_judge", stop_after_choosing)
    monkeypatch.setattr(cli.budget, "load_env", lambda: False)  # no API key: must still be allowed
    with pytest.raises(SystemExit):
        cli.main(["scan", "a/b", "--judge", "ollama"])
    assert seen["model"] == "qwen2.5:7b"
