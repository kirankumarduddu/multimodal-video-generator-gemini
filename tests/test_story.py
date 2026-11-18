"""Story writers: request shapes for each provider and the repair round, without network calls."""
import json
import pathlib

import pytest

from mvgen import story as story_module
from mvgen.cli import main
from mvgen.project import Project, ProjectError

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOOD = (ROOT / "examples" / "kettle-and-kite" / "story.json").read_text(encoding="utf-8")


class Reply:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.text = payload, status, json.dumps(payload)

    def json(self):
        return self.payload


@pytest.fixture
def film(tmp_path):
    main(["init", str(tmp_path / "film"), "--example", "kettle-and-kite"])
    (tmp_path / "film" / "story.json").unlink()
    return tmp_path / "film"


def configure(film, line):
    studio = (film / "studio.yaml").read_text(encoding="utf-8")
    studio = studio.replace("story: {provider: gemini, model: gemini-3.5-flash, location: global}", line)
    (film / "studio.yaml").write_text(studio, encoding="utf-8")


def test_openai_compatible(film, monkeypatch):
    configure(film, "story: {provider: openai, model: m1, base_url: http://localhost:11434/v1}")
    calls = []

    def post(url, headers, json, timeout):
        calls.append((url, headers, json))
        return Reply({"choices": [{"message": {"content": "```json\n" + GOOD + "\n```"}}]})

    monkeypatch.setattr(story_module.requests, "post", post)
    story_module.write(Project(film))
    url, headers, body = calls[0]
    assert url == "http://localhost:11434/v1/chat/completions" and "Authorization" not in headers
    assert body["model"] == "m1" and body["response_format"] == {"type": "json_object"}
    assert json.loads((film / "story.json").read_text(encoding="utf-8"))["title"].startswith("Kettle")


def test_anthropic_needs_a_key(film, monkeypatch):
    configure(film, "story: {provider: anthropic, model: claude-x}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProjectError, match="ANTHROPIC_API_KEY"):
        story_module.write(Project(film))


def test_repair_round(film, monkeypatch):
    configure(film, "story: {provider: anthropic, model: claude-x}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    broken = json.loads(GOOD)
    broken["scenes"][0]["kind"] = "hologram"
    replies = [json.dumps(broken), GOOD]
    prompts = []

    def post(url, timeout, json, headers):
        prompts.append(json["messages"][0]["content"])
        assert headers["x-api-key"] == "test"
        return Reply({"content": [{"type": "text", "text": replies.pop(0)}]})

    monkeypatch.setattr(story_module.requests, "post", post)
    story_module.write(Project(film))
    assert len(prompts) == 2 and "Fix these problems" in prompts[1]


def test_manual_provider_explains_what_to_do(film):
    configure(film, "story: {provider: manual}")
    with pytest.raises(ProjectError, match="mvg story prompt"):
        story_module.write(Project(film))
