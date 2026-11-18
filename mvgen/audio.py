"""Narration (Gemini TTS, one WAV per line) and score (Lyria, one take per music segment)."""
from __future__ import annotations

import base64
import concurrent.futures
import pathlib
from typing import Any

from . import media
from .gcp import client, first_inline, retry, wait_interaction
from .project import Project, digest
from .spec import music_spans, speech_seconds

DEFAULT_DIRECTION = "Read this as the warm, confident narrator of a premium brand film. Natural pauses, no hype"


def voice_lines(story: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """(key, scene, line) for every narration line; key is <scene id>-<n>."""
    return [(f"{scene['id']}-{n}", scene, line) for scene in story["scenes"]
            for n, line in enumerate(scene.get("voice", []), start=1)]


def voice_path(project: Project, key: str) -> pathlib.Path:
    return project.path("audio", "voice", f"{key}.wav")


def is_placeholder(project: Project, output: pathlib.Path) -> bool:
    stamp = output.with_name(output.name + ".stamp")
    return stamp.exists() and stamp.read_text().startswith("placeholder")


def make_voice(project: Project, only: list[str] | None = None, force: bool = False, placeholder: bool = False) -> list[str]:
    from google.genai import types

    story = project.story()
    voice = project.brand.get("voice") or {}
    name = voice.get("name", "Sulafat")
    direction = (voice.get("direction") or DEFAULT_DIRECTION).rstrip(" :.")
    model = project.model("tts")["model"]
    done = []
    jobs = []
    for key, scene, line in voice_lines(story):
        if only and scene["id"] not in only and key not in only:
            continue
        target = project.out("audio", "voice", f"{key}.wav")
        stamp = ("placeholder-" if placeholder else "") + digest("voice-v1", line["text"], name, direction, model)
        if not force and project.fresh(target, stamp):
            continue
        if placeholder:
            media.silence(target, speech_seconds(line["text"]) + 0.3)
            project.stamp(target, stamp)
            done.append(f"voice {key}: placeholder {speech_seconds(line['text']) + 0.3:.1f}s")
            continue
        jobs.append((key, line, target, stamp))

    def one(job):
        key, line, target, stamp = job
        api = client(project, "tts")
        response = retry(lambda: api.models.generate_content(
            model=model, contents=f"{direction}: {line['text']}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=name))))), f"voice {key}", base=5)
        pcm = first_inline(response)
        if not pcm:
            raise RuntimeError(f"voice {key}: no audio returned")
        seconds = media.write_wav(target, pcm)
        project.stamp(target, stamp)
        return f"voice {key}: {seconds:.1f}s  {line['text']}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=project.parallel) as pool:
        for future in [pool.submit(one, job) for job in jobs]:
            try:
                done.append(future.result())
            except Exception as error:  # noqa: BLE001
                done.append(f"FAILED: {error}")
    for line in done:
        print(line, flush=True)
    return done


def music_path(project: Project, segment_id: str) -> pathlib.Path | None:
    for suffix in (".mp3", ".wav"):
        path = project.path("audio", "music", f"{segment_id}{suffix}")
        if path.exists():
            return path
    return None


def music_prompt(segment: dict[str, Any], seconds: float) -> str:
    return f"{segment['prompt'].rstrip('. ')}. The piece runs about {round(seconds + 4)} seconds."


def make_music(project: Project, only: list[str] | None = None, force: bool = False, placeholder: bool = False) -> list[str]:
    story = project.story()
    model = project.model("music")["model"]
    done = []
    for segment, _start, span in music_spans(story):
        if only and segment["id"] not in only:
            continue
        prompt = music_prompt(segment, span)
        if placeholder:
            target = project.out("audio", "music", f"{segment['id']}.wav")
            if force or not music_path(project, segment["id"]) or is_placeholder(project, target):
                media.silence(target, span + 4)
                project.stamp(target, "placeholder-" + digest(span))
                done.append(f"music {segment['id']}: placeholder {span + 4:.0f}s")
            continue
        target = project.out("audio", "music", f"{segment['id']}.mp3")
        key = digest("music-v1", prompt, model)
        if not force and project.fresh(target, key):
            done.append(f"music {segment['id']}: up to date")
            continue
        api = client(project, "music")
        interaction = retry(lambda: api.interactions.create(model=model, input=prompt), f"music {segment['id']}", base=30)
        interaction = wait_interaction(api, interaction, f"music {segment['id']}")
        audio = getattr(interaction, "output_audio", None)
        if interaction.status != "completed" or audio is None:
            done.append(f"FAILED: music {segment['id']}: {interaction.status}")
            continue
        target.write_bytes(base64.b64decode(audio.data))
        project.stamp(target, key)
        placeholder_file = project.path("audio", "music", f"{segment['id']}.wav")
        if placeholder_file.exists():
            placeholder_file.unlink()
        done.append(f"music {segment['id']}: {media.duration(target):.0f}s ({model})")
    for line in done:
        print(line, flush=True)
    return done
