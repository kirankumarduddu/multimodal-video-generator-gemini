"""The story file: parse, validate against the JSON Schema, check the timing, fill defaults."""
from __future__ import annotations

import json
import pathlib
import re
from importlib import resources
from typing import Any

import jsonschema

from .project import FADE, ProjectError

WORDS_PER_SECOND = 2.6


def schema() -> dict[str, Any]:
    return json.loads(resources.files("mvgen").joinpath("schema/story.schema.json").read_text(encoding="utf-8"))


def parse_json(text: str) -> dict[str, Any]:
    """Parse an LLM reply: tolerate ``` fences and text around the JSON object."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


def speech_seconds(text: str) -> float:
    return len(text.split()) / WORDS_PER_SECOND


def check_story(story: dict[str, Any], target_seconds: float | None = None) -> tuple[list[str], list[str]]:
    """Schema errors plus semantic errors, and warnings that do not stop generation."""
    validator = jsonschema.Draft202012Validator(schema())
    errors = [f"{'/'.join(str(p) for p in error.absolute_path) or '(root)'}: {error.message}"
              for error in sorted(validator.iter_errors(story), key=lambda e: list(e.absolute_path))]
    if errors:
        return errors, []
    warnings: list[str] = []
    scenes = story["scenes"]
    ids = [scene["id"] for scene in scenes]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        errors.append(f"duplicate scene ids: {', '.join(duplicates)}")
    cast_ids = {member["id"] for member in story["cast"]}
    for scene in scenes:
        for ref in (scene.get("shot") or {}).get("cast", []):
            if ref not in cast_ids:
                errors.append(f"{scene['id']}: shot.cast '{ref}' is not in cast")
        card = scene.get("card") or {}
        needs = {"statement": "lines", "list": "items", "flow": "items", "stat": "stats", "quote": "quote",
                 "screen": "image"}.get(card.get("template", ""))
        if needs and not card.get(needs):
            errors.append(f"{scene['id']}: a {card['template']} card needs '{needs}'")
        cursor = 0.0
        for line in scene.get("voice", []):
            at = max(line.get("at", 0.4), cursor)
            end = at + speech_seconds(line["text"])
            cursor = end + 0.3
            if end > scene["seconds"] + 0.5:
                warnings.append(f"{scene['id']}: voice runs about {end - scene['seconds']:.1f}s past the scene; "
                                f"lengthen seconds or shorten the line")
        if scene["kind"] == "live_action":
            shot = scene["shot"]
            if scene.get("trim_start", 0) + min(scene["seconds"], 30) > shot.get("duration", 8) + 0.01:
                warnings.append(f"{scene['id']}: trim_start + seconds is longer than the {shot.get('duration', 8)}s "
                                f"clip; the last frame is held")
    music = story["music"]
    if music and music[0]["starts_at"] != ids[0]:
        errors.append(f"music[0].starts_at must be the first scene ({ids[0]})")
    order = {scene_id: index for index, scene_id in enumerate(ids)}
    previous = -1
    for segment in music:
        if segment["starts_at"] not in order:
            errors.append(f"music '{segment['id']}': starts_at '{segment['starts_at']}' is not a scene id")
        elif order[segment["starts_at"]] <= previous:
            errors.append(f"music '{segment['id']}' must start after the previous segment")
        else:
            previous = order[segment["starts_at"]]
    last = scenes[-1]
    if (last.get("card") or {}).get("template") != "endcard":
        warnings.append("the last scene is usually an endcard")
    total = total_seconds(story)
    if target_seconds and abs(total - target_seconds) > 0.1 * target_seconds:
        warnings.append(f"length {total:.1f}s is more than 10% away from the brief's {target_seconds}s")
    return errors, warnings


def with_defaults(story: dict[str, Any]) -> dict[str, Any]:
    for scene in story["scenes"]:
        scene.setdefault("trim_start", 0)
        scene.setdefault("voice", [])
        for line in scene["voice"]:
            line.setdefault("at", 0.4)
        if scene["kind"] == "live_action":
            scene["shot"].setdefault("duration", 8)
            scene["shot"].setdefault("cast", [])
    for segment in story["music"]:
        segment.setdefault("align", "head")
    return story


def load_story(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        raise ProjectError(f"{path.name} is missing. Write it with `mvg story write`, or paste the reply to "
                           f"`mvg story prompt` from any LLM into {path.name}.")
    try:
        story = parse_json(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ProjectError(f"{path.name} is not valid JSON: {error}") from error
    errors, _warnings = check_story(story)
    if errors:
        raise ProjectError(f"{path.name} has {len(errors)} problem(s); run `mvg story check`:\n  " + "\n  ".join(errors))
    return with_defaults(story)


def starts(story: dict[str, Any]) -> list[float]:
    result, cursor = [], 0.0
    for scene in story["scenes"]:
        result.append(cursor)
        cursor += scene["seconds"] - FADE
    return result


def total_seconds(story: dict[str, Any]) -> float:
    return sum(scene["seconds"] for scene in story["scenes"]) - FADE * (len(story["scenes"]) - 1)


def music_spans(story: dict[str, Any]) -> list[tuple[dict[str, Any], float, float]]:
    """(segment, start, length) for each score segment; each runs to the next segment or the end."""
    begin = dict(zip((scene["id"] for scene in story["scenes"]), starts(story)))
    total = total_seconds(story)
    bounds = [begin[segment["starts_at"]] for segment in story["music"]] + [total]
    return [(segment, bounds[k], bounds[k + 1] - bounds[k]) for k, segment in enumerate(story["music"])]


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"
