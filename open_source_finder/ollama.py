"""Ask a local model, through Ollama, the same five questions Jev answers. Free and offline.

The prompt is built from QUESTIONS in judge.py, so both judges always ask the same thing.
Local models are less reliable than Jev at giving calibrated answers: they pick a level for each
Score and a 0..1 likelihood for each Noul, and give no confidence, so issues are never flagged "unsure".
"""

import json
import math
import os
import urllib.error
import urllib.request

from .judge import LEVELS, QUESTIONS, build_state
from .rank import Judgment

DEFAULT_URL = "http://localhost:11434"
TIMEOUT = 300  # seconds; a local model on a laptop CPU can take a minute or more per issue
ATTEMPTS = 2   # ask again once if the reply can't be read

NOULS = [name for name in QUESTIONS if name not in LEVELS]

# Ollama constrains the reply to this JSON schema, which makes unreadable replies rare but not impossible.
SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "integer", "minimum": 0, "maximum": levels - 1} for name, levels in LEVELS.items()},
        **{name: {"type": "number", "minimum": 0, "maximum": 1} for name in NOULS},
    },
    "required": list(QUESTIONS),
}


class OllamaError(Exception):
    """Ollama can't be used at all (not running, model not pulled): stop the run."""


class UnreadableReply(Exception):
    """The model's reply for one issue couldn't be read, even after asking again: skip that issue."""


def build_prompt():
    lines = ["You judge GitHub issues for first-time contributors. You get JSON with `repo` and `issue`.",
             "Answer each question independently. Reply with JSON only, using these keys:", ""]
    for name, question in QUESTIONS.items():
        lines.append(f"{name}: {question.instructions}")
        if name in LEVELS:
            lines.append("  Reply with the number of the option that fits best:")
            lines += [f"  {i}. {option}" for i, option in enumerate(question.criteria)]
        else:
            lines.append("  Reply with how likely this is true, from 0 (certainly false) to 1 (certainly true).")
            lines.append(f"  True means: {question.criteria['true']}")
            lines.append(f"  False means: {question.criteria['false']}")
        lines.append("")
    return "\n".join(lines)


PROMPT = build_prompt()


class OllamaJudge:
    def __init__(self, model, url=None):
        self.model = model
        self.url = (url or os.environ.get("OLLAMA_HOST") or DEFAULT_URL).rstrip("/")
        if "://" not in self.url:
            self.url = "http://" + self.url  # OLLAMA_HOST is often set as just host:port

    def judge(self, repo, issue):
        state = json.dumps(build_state(repo, issue), ensure_ascii=False)
        for attempt in range(ATTEMPTS):
            try:
                return parse_reply(self._chat(state))
            except UnreadableReply:
                if attempt == ATTEMPTS - 1:
                    raise UnreadableReply(f"#{issue.number}") from None

    def _chat(self, state):
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": state}],
            "format": SCHEMA,
            "stream": False,
            "options": {"temperature": 0},
        }).encode("utf-8")
        request = urllib.request.Request(f"{self.url}/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read())["message"]["content"]
        except urllib.error.HTTPError as error:
            detail = _error_text(error)
            if error.code == 404:
                raise OllamaError(f"Ollama doesn't have the model '{self.model}'. "
                                  f"Run `ollama pull {self.model}` first, or pick another with --model.") from None
            raise OllamaError(f"Ollama error {error.code}: {detail}") from None
        except (urllib.error.URLError, ConnectionError) as error:
            raise OllamaError(f"Can't reach Ollama at {self.url} ({getattr(error, 'reason', error)}). "
                              "Is it installed and running?") from None
        except TimeoutError:
            raise OllamaError(f"Ollama took over {TIMEOUT}s to answer one issue. "
                              "Try a smaller model, or fewer issues with --max-issues.") from None
        except (ValueError, KeyError, TypeError):
            raise UnreadableReply() from None


def _error_text(error):
    try:
        return json.loads(error.read()).get("error", "")
    except (ValueError, AttributeError):
        return ""


def parse_reply(content):
    """Read the model's JSON reply into a Judgment, clamping numbers into range."""
    try:
        reply = json.loads(content)
        levels = {name: min(max(round(float(reply[name])), 0), n - 1) for name, n in LEVELS.items()}
        nouls = {name: float(reply[name]) for name in NOULS}
        if not all(math.isfinite(value) for value in nouls.values()):
            raise ValueError("NaN or infinity")
        nouls = {name: min(max(value, 0.0), 1.0) for name, value in nouls.items()}
    except (ValueError, KeyError, TypeError, OverflowError):
        raise UnreadableReply() from None
    # Normalize each Score to 0..1 by its highest level, the same way judge.to_judgment does.
    norm = {name: levels[name] / (n - 1) for name, n in LEVELS.items()}
    return Judgment(scope=norm["scope"], clarity=norm["clarity"], context_needed=norm["context_needed"],
                    actionable=nouls["actionable"], claimed=nouls["claimed"])
