import copy
import json
import pathlib

import pytest

from mvgen.spec import check_story, music_spans, parse_json, starts, total_seconds, with_defaults

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "examples" / "kettle-and-kite" / "story.json").read_text(encoding="utf-8"))


def story():
    return copy.deepcopy(EXAMPLE)


def test_example_story_is_valid_and_close_to_the_brief():
    errors, warnings = check_story(story(), 60)
    assert errors == []
    assert not any("length" in warning for warning in warnings)


def test_parse_json_tolerates_fences_and_chatter():
    text = "Here you go:\n```json\n{\"a\": 1}\n```"
    assert parse_json(text) == {"a": 1}
    assert parse_json("Sure! {\"a\": {\"b\": 2}} hope this helps") == {"a": {"b": 2}}


@pytest.mark.parametrize("mutate, expected", [
    (lambda s: s["scenes"].append(copy.deepcopy(s["scenes"][0])), "duplicate scene ids"),
    (lambda s: s["scenes"][0]["shot"]["cast"].append("ghost"), "'ghost' is not in cast"),
    (lambda s: s["music"][0].update(starts_at="s03-title"), "music[0].starts_at must be the first scene"),
    (lambda s: s["scenes"][2]["card"].update(template="list"), "needs 'items'"),
    (lambda s: s["scenes"][2]["card"].update(template="hologram"), "is not one of"),
    (lambda s: s["scenes"][0].update(card={"template": "title"}), "should not be valid"),
    (lambda s: s.pop("scenes"), "'scenes' is a required property"),
])
def test_errors(mutate, expected):
    data = story()
    mutate(data)
    errors, _ = check_story(data)
    assert any(expected in error for error in errors), errors


def test_voice_overrun_and_missing_endcard_are_warnings():
    data = story()
    data["scenes"][2]["voice"] = [{"text": " ".join(["word"] * 40), "at": 1}]
    data["scenes"][-1]["card"]["template"] = "title"
    errors, warnings = check_story(data)
    assert errors == []
    assert any("voice runs" in w for w in warnings) and any("endcard" in w for w in warnings)


def test_timeline_math():
    data = with_defaults(story())
    begin = starts(data)
    assert begin[0] == 0 and begin[1] == pytest.approx(data["scenes"][0]["seconds"] - 0.4)
    assert total_seconds(data) == pytest.approx(sum(s["seconds"] for s in data["scenes"]) - 0.4 * (len(data["scenes"]) - 1))
    (segment, start, length), = music_spans(data)
    assert start == 0 and length == pytest.approx(total_seconds(data))
