"""Prompts for generated imagery, cast reference stills and per-shot keyframes (Gemini image model)."""
from __future__ import annotations

import concurrent.futures
from typing import Any

from .gcp import client, first_inline, retry
from .project import Project, digest

SAFE = ("No readable text, captions, subtitles, logos, brand names, watermarks or user interfaces anywhere in frame; "
        "any phone or laptop screen shows only a soft glow. Invented, fictional people only, never a real or famous "
        "person. Realistic hands and faces.")
NEGATIVE = "text, captions, subtitles, letters, logos, watermark, user interface, distorted hands, extra fingers"
PORTRAIT = ("Photoreal documentary portrait photograph, natural soft window light, plain warm neutral background, "
            "waist-up, looking slightly off camera. An invented, fictional person, not a real person or celebrity. "
            "No text, no logos.")


def cast_by_id(story: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {member["id"]: member for member in story["cast"]}


def people_line(story: dict[str, Any], refs: list[str]) -> str:
    cast = cast_by_id(story)
    return " ".join(f"Reference image {i + 1} is exactly this person: {cast[ref]['description']} Keep their face, "
                    f"hair and clothing identical." for i, ref in enumerate(refs))


def shot_text(project: Project, scene: dict[str, Any]) -> str:
    shot = scene["shot"]
    parts = [project.brand.get("look", "Photoreal, cinematic, natural light, shallow depth of field."),
             f"Setting: {shot['setting']}." if shot.get("setting") else "", shot["action"],
             f"Camera: {shot['camera']}." if shot.get("camera") else ""]
    return " ".join(part.strip() for part in parts if part)


def keyframe_prompt(project: Project, scene: dict[str, Any]) -> str:
    story = project.story()
    ratio = story["aspect_ratio"]
    return (f"A single {ratio} film still: the first frame of this shot. {shot_text(project, scene)} "
            f"{people_line(story, scene['shot'].get('cast', []))} {SAFE}").strip()


def video_prompt(project: Project, scene: dict[str, Any]) -> str:
    story = project.story()
    return (f"{shot_text(project, scene)} {people_line(story, scene['shot'].get('cast', []))} "
            f"One continuous shot, no cuts, natural motion. {SAFE}").strip()


def cast_prompt(project: Project, member: dict[str, Any]) -> str:
    return f"{member['description']} {PORTRAIT} Color grade: {project.brand.get('look', 'natural')}."


def _image(project: Project, parts: list[Any], aspect_ratio: str, label: str) -> bytes:
    from google.genai import types

    model = project.model("image")["model"]
    api = client(project, "image")
    response = retry(lambda: api.models.generate_content(
        model=model, contents=parts,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"],
                                           image_config=types.ImageConfig(aspect_ratio=aspect_ratio))), label)
    data = first_inline(response)
    if not data:
        candidates = getattr(response, "candidates", None) or []
        reason = (getattr(candidates[0], "finish_reason", None) if candidates else
                  getattr(getattr(response, "prompt_feedback", None), "block_reason", None)) or "no candidates"
        raise RuntimeError(f"{label}: no image returned ({reason}); rephrase the description")
    return data


def make_cast(project: Project, only: list[str] | None = None, force: bool = False) -> list[str]:
    story = project.story()
    jobs = []
    for member in story["cast"]:
        if only and member["id"] not in only:
            continue
        target = project.out("renders", "cast", f"{member['id']}.png")
        key = digest("cast-v1", cast_prompt(project, member), project.model("image")["model"])
        if not force and project.fresh(target, key):
            print(f"cast {member['id']}: up to date", flush=True)
            continue
        jobs.append((member, target, key))

    def one(job):
        member, target, key = job
        ratio = "9:16" if story["aspect_ratio"] == "9:16" else "16:9"
        target.write_bytes(_image(project, [cast_prompt(project, member)], ratio, f"cast {member['id']}"))
        project.stamp(target, key)
        return f"cast {member['id']}: {target.stat().st_size:,} bytes"

    return _parallel(project, one, jobs)


def keyframe_key(project: Project, scene: dict[str, Any]) -> str:
    refs = [project.path("renders", "cast", f"{ref}.png") for ref in scene["shot"].get("cast", [])]
    return digest("keyframe-v1", keyframe_prompt(project, scene), project.model("image")["model"], *refs)


def make_keyframes(project: Project, only: list[str] | None = None, force: bool = False) -> list[str]:
    from google.genai import types

    story = project.story()
    jobs = []
    for scene in story["scenes"]:
        if scene["kind"] != "live_action" or (only and scene["id"] not in only):
            continue
        missing = [ref for ref in scene["shot"].get("cast", [])
                   if not project.path("renders", "cast", f"{ref}.png").exists()]
        if missing:
            raise FileNotFoundError(f"{scene['id']}: run `mvg cast` first (missing {', '.join(missing)})")
        target = project.out("renders", "keyframes", f"{scene['id']}.png")
        key = keyframe_key(project, scene)
        if not force and project.fresh(target, key):
            print(f"keyframe {scene['id']}: up to date", flush=True)
            continue
        jobs.append((scene, target, key))

    def one(job):
        scene, target, key = job
        parts: list[Any] = [types.Part.from_bytes(data=project.path("renders", "cast", f"{ref}.png").read_bytes(),
                                                  mime_type="image/png")
                            for ref in scene["shot"].get("cast", [])]
        parts.append(keyframe_prompt(project, scene))
        target.write_bytes(_image(project, parts, story["aspect_ratio"], f"keyframe {scene['id']}"))
        project.stamp(target, key)
        return f"keyframe {scene['id']}: {target.stat().st_size:,} bytes"

    return _parallel(project, one, jobs)


def _parallel(project: Project, work, jobs) -> list[str]:
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=project.parallel) as pool:
        for future in concurrent.futures.as_completed([pool.submit(work, job) for job in jobs]):
            try:
                line = future.result()
            except Exception as error:  # noqa: BLE001 - report and continue with the other jobs
                line = f"FAILED: {error}"
            print(line, flush=True)
            results.append(line)
    return results
