"""Live-action clips: Veo (generate_videos) or Gemini Omni (Interactions API), animated from the approved keyframe.

Nothing here runs without an approval in approvals.json that matches the current prompt, keyframe and model, so a
changed shot must be reviewed again before it is paid for. `--animatic` makes free preview clips instead.
"""
from __future__ import annotations

import base64
import concurrent.futures
import time
import urllib.parse
from typing import Any

from . import media
from .gcp import client, retry, wait_interaction
from .imagery import NEGATIVE, video_prompt
from .project import Project, digest

VEO_DURATIONS = (4, 6, 8)


def video_settings(project: Project, scene: dict[str, Any]) -> dict[str, Any]:
    config = project.model("video")
    duration = int(scene["shot"].get("duration", 8))
    resolution = config.get("resolution", "1080p")
    if config.get("provider", "veo") == "veo" and resolution in ("1080p", "4k") and duration != 8:
        duration = 8  # Veo 3.1 makes 1080p and 4k only as 8-second clips
    return {"provider": config.get("provider", "veo"), "model": config["model"], "resolution": resolution,
            "duration": duration, "generate_audio": bool(config.get("generate_audio", False)),
            "person_generation": config.get("person_generation", "allow_adult")}


def keyframe(project: Project, scene: dict[str, Any]):
    return project.path("renders", "keyframes", f"{scene['id']}.png")


def approval_key(project: Project, scene: dict[str, Any]) -> str:
    return digest("clip-v1", video_prompt(project, scene), video_settings(project, scene), keyframe(project, scene),
                  project.story()["aspect_ratio"])


def approved(project: Project, scene: dict[str, Any]) -> bool:
    return project.approvals().get(scene["id"]) == approval_key(project, scene)


def clip_path(project: Project, scene_id: str):
    return project.path("renders", "clips", f"{scene_id}.mp4")


def animatic_path(project: Project, scene_id: str):
    return project.path("renders", "animatic", f"{scene_id}.mp4")


def _download_gcs(uri: str) -> bytes:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    bucket, _, name = uri.removeprefix("gs://").partition("/")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    response = AuthorizedSession(credentials).get(
        f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{urllib.parse.quote(name, safe='')}?alt=media",
        timeout=300)
    response.raise_for_status()
    return response.content


def _veo(project: Project, scene: dict[str, Any], prompt: str, settings: dict[str, Any]) -> bytes:
    from google.genai import types

    api = client(project, "video")
    frame = keyframe(project, scene)
    references = None
    if not frame.exists():
        references = [
            types.VideoGenerationReferenceImage(
                image=types.Image(image_bytes=project.path("renders", "cast", f"{ref}.png").read_bytes(),
                                  mime_type="image/png"), reference_type="asset")
            for ref in scene["shot"].get("cast", [])[:3]] or None
    config = types.GenerateVideosConfig(
        aspect_ratio=project.story()["aspect_ratio"], resolution=settings["resolution"],
        duration_seconds=settings["duration"], generate_audio=settings["generate_audio"], number_of_videos=1,
        negative_prompt=NEGATIVE, person_generation=settings["person_generation"],
        output_gcs_uri=project.gcs_uri, reference_images=references)
    kwargs: dict[str, Any] = {"model": settings["model"], "prompt": prompt, "config": config}
    if frame.exists():
        kwargs["image"] = types.Image(image_bytes=frame.read_bytes(), mime_type="image/png")
    operation = retry(lambda: api.models.generate_videos(**kwargs), f"clip {scene['id']}", base=30)
    started = time.monotonic()
    while not operation.done:
        if time.monotonic() - started > 1200:
            raise TimeoutError(f"clip {scene['id']}: Veo still running after 20 minutes")
        time.sleep(15)
        operation = api.operations.get(operation)
    if operation.error:
        raise RuntimeError(f"clip {scene['id']}: {operation.error}")
    response = operation.response or operation.result
    videos = getattr(response, "generated_videos", None) or []
    if not videos:
        reasons = getattr(response, "rai_media_filtered_reasons", None)
        raise RuntimeError(f"clip {scene['id']}: no video returned ({reasons or 'filtered'}); rephrase the shot")
    video = videos[0].video
    if getattr(video, "video_bytes", None):
        return video.video_bytes
    return _download_gcs(video.uri)


def _omni(project: Project, scene: dict[str, Any], prompt: str, settings: dict[str, Any]) -> bytes:
    api = client(project, "video")
    frame = keyframe(project, scene)
    images = [frame] if frame.exists() else [project.path("renders", "cast", f"{ref}.png")
                                              for ref in scene["shot"].get("cast", [])]
    content: list[dict[str, Any]] = [{"type": "image", "mime_type": "image/png",
                                      "data": base64.b64encode(path.read_bytes()).decode()} for path in images]
    if frame.exists():
        prompt = f"The reference image is the first frame of this shot. {prompt}"
    content.append({"type": "text", "text": prompt})
    interaction = retry(lambda: api.interactions.create(
        model=settings["model"], input=content, background=True,
        response_format={"type": "video", "aspect_ratio": project.story()["aspect_ratio"],
                         "resolution": settings["resolution"], "duration": f"{settings['duration']}s",
                         "delivery": "inline"}), f"clip {scene['id']}", base=30)
    interaction = wait_interaction(api, interaction, f"clip {scene['id']}", poll=15)
    output = getattr(interaction, "output_video", None)
    if interaction.status != "completed" or not output:
        raise RuntimeError(f"clip {scene['id']}: {interaction.status}")
    return base64.b64decode(output.data)


def generate(project: Project, only: list[str] | None = None, force: bool = False) -> list[str]:
    story = project.story()
    jobs, waiting = [], []
    for scene in story["scenes"]:
        if scene["kind"] != "live_action" or (only and scene["id"] not in only):
            continue
        target = clip_path(project, scene["id"])
        key = approval_key(project, scene)
        if not force and project.fresh(target, key):
            print(f"clip {scene['id']}: up to date", flush=True)
            continue
        if not approved(project, scene):
            waiting.append(scene["id"])
            continue
        jobs.append(scene)
    if waiting:
        print(f"Not approved (or changed since approval): {', '.join(waiting)}.\n"
              f"  Run `mvg review`, look at build/review.html, then `mvg approve {' '.join(waiting)}`.", flush=True)

    def one(scene):
        settings = video_settings(project, scene)
        prompt = video_prompt(project, scene)
        started = time.monotonic()
        data = (_omni if settings["provider"] == "omni" else _veo)(project, scene, prompt, settings)
        target = project.out("renders", "clips", f"{scene['id']}.mp4")
        target.write_bytes(data)
        project.stamp(target, approval_key(project, scene))
        return f"clip {scene['id']}: {len(data):,} bytes in {time.monotonic() - started:.0f}s ({settings['model']})"

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=project.parallel) as pool:
        for future in concurrent.futures.as_completed([pool.submit(one, scene) for scene in jobs]):
            try:
                line = future.result()
            except Exception as error:  # noqa: BLE001 - one failed shot should not stop the others
                line = f"FAILED: {error}"
            print(line, flush=True)
            results.append(line)
    return results


def animatics(project: Project, only: list[str] | None = None, force: bool = False) -> list[str]:
    """Free preview clips: a slow push-in on each keyframe (or a brand-colored hold when there is none)."""
    story = project.story()
    color = (project.brand.get("colors") or {}).get("surface", "#222222")
    done = []
    for scene in story["scenes"]:
        if scene["kind"] != "live_action" or (only and scene["id"] not in only):
            continue
        target = project.out("renders", "animatic", f"{scene['id']}.mp4")
        frame = keyframe(project, scene)
        seconds = scene.get("trim_start", 0) + scene["seconds"]
        key = digest("animatic-v1", frame, seconds, project.size, color)
        if not force and project.fresh(target, key):
            continue
        media.animatic(frame if frame.exists() else None, target, seconds, project.size, color)
        project.stamp(target, key)
        done.append(scene["id"])
        print(f"animatic {scene['id']}{'' if frame.exists() else ' (no keyframe yet: plain hold)'}", flush=True)
    return done
