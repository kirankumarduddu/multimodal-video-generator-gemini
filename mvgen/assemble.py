"""Assemble the film with ffmpeg: scenes crossfaded, captions, narration placed per scene, the score fitted to its
chapters and ducked under the voice, loudness-normalised; a master plus web and phone copies."""
from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
from typing import Any

from . import media
from .audio import is_placeholder, music_path, voice_lines, voice_path
from .clips import animatic_path, clip_path
from .project import FADE, FPS, Project, ProjectError
from .spec import clock, music_spans, starts, total_seconds

SCORE_XFADE = 2.5
MAX_GAP = 1.0  # seconds a score segment may leave unscored at the end of its chapter
TEMPO_RANGE = (0.92, 1.08)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "film"


def scene_source(project: Project, scene: dict[str, Any]) -> tuple[pathlib.Path, bool]:
    """(video file, is_draft) for a scene."""
    if scene["kind"] == "card":
        path = project.path("renders", "cards", f"{scene['id']}.mp4")
        if not path.exists():
            raise ProjectError(f"{scene['id']}: card not rendered; run `mvg cards`")
        return path, False
    clip = clip_path(project, scene["id"])
    if clip.exists():
        return clip, False
    preview = animatic_path(project, scene["id"])
    if preview.exists():
        return preview, True
    raise ProjectError(f"{scene['id']}: no clip; run `mvg clips` (after approval) or `mvg clips --animatic` for a preview")


def voice_cues(project: Project, story: dict[str, Any]) -> list[tuple[float, pathlib.Path, float]]:
    """(absolute start, wav, seconds) for each narration line, pushed later so lines never overlap."""
    begin = dict(zip((scene["id"] for scene in story["scenes"]), starts(story)))
    cues, previous_end = [], 0.0
    raw = sorted(((begin[scene["id"]] + line.get("at", 0.4), key) for key, scene, line in voice_lines(story)))
    for at, key in raw:
        path = voice_path(project, key)
        if not path.exists():
            raise ProjectError(f"voice {key} missing; run `mvg voice` (or `mvg voice --placeholder` for a timing draft)")
        seconds = media.duration(path)
        at = max(at, previous_end + 0.3)
        previous_end = at + seconds
        cues.append((at, path, seconds))
    return cues


def score_plan(project: Project, story: dict[str, Any], allow_gaps: bool = False) -> list[dict[str, Any]]:
    plan = []
    spans = music_spans(story)
    for k, (segment, start, length) in enumerate(spans):
        last = k == len(spans) - 1
        span = length + (0 if last else SCORE_XFADE)
        path = music_path(project, segment["id"])
        if not path:
            raise ProjectError(f"music '{segment['id']}' missing; run `mvg music` (or `mvg music --placeholder`)")
        source = media.duration(path)
        tempo = max(TEMPO_RANGE[0], min(TEMPO_RANGE[1], source / span)) if source < span else 1.0
        skip = max(0.0, source - span * tempo) if segment.get("align") == "tail" else 0.0
        ends = start + (source - skip) / tempo
        gap = start + span - (0 if last else SCORE_XFADE) - ends
        if gap > MAX_GAP and not allow_gaps:
            raise ProjectError(f"music '{segment['id']}' is {source:.0f}s but its chapter needs {span:.0f}s: it would "
                               f"leave {gap:.1f}s of silence. Regenerate it (`mvg music {segment['id']} --force`), start "
                               f"another segment earlier, or pass --allow-gaps.")
        plan.append({"segment": segment, "path": path, "start": start, "span": span, "tempo": tempo, "skip": skip})
    return plan


def describe(project: Project) -> list[str]:
    """The `mvg plan` report: scenes, timing, sources and what is left to generate."""
    story = project.story()
    from .clips import video_settings

    lines, begin = [], starts(story)
    for index, scene in enumerate(story["scenes"]):
        what = (scene["card"]["template"] if scene["kind"] == "card"
                else f"shot {video_settings(project, scene)['duration']}s")
        try:
            source, draft = scene_source(project, scene)
            state = "animatic" if draft else "ready"
        except ProjectError:
            state = "todo"
        voices = len(scene.get("voice", []))
        lines.append(f"{index + 1:2d} {clock(begin[index])} {scene['seconds']:5.1f}s  {scene['id']:22s} "
                     f"{scene['kind']:11s} {what:10s} voice {voices}  {state}")
    total = total_seconds(story)
    shots = [s for s in story["scenes"] if s["kind"] == "live_action"]
    lines.append(f"length {clock(total)}  ·  {len(story['scenes'])} scenes  ·  {len(shots)} shots "
                 f"({sum(video_settings(project, s)['duration'] for s in shots)}s of video to generate)  ·  "
                 f"{len(voice_lines(story))} voice lines  ·  {len(story['music'])} music segments")
    return lines


def assemble(project: Project, allow_gaps: bool = False, no_music: bool = False) -> pathlib.Path:
    story = project.story()
    width, height = project.size
    total = total_seconds(story)
    begin = starts(story)
    sources = [scene_source(project, scene) for scene in story["scenes"]]
    cues = voice_cues(project, story)
    score = [] if no_music else score_plan(project, story, allow_gaps)
    draft = any(d for _p, d in sources) or any(is_placeholder(project, path) for _a, path, _s in cues) or \
        any(item["path"].suffix == ".wav" for item in score)

    args: list[str] = []
    for scene, (path, _draft) in zip(story["scenes"], sources):
        trim = scene.get("trim_start", 0) if scene["kind"] == "live_action" else 0
        args += ["-ss", f"{trim:.2f}", "-i", str(path)]
    caption_input = {}
    for index, scene in enumerate(story["scenes"]):
        png = project.path("renders", "captions", f"{scene['id']}.png")
        if scene.get("caption"):
            if not png.exists():
                raise ProjectError(f"{scene['id']}: caption not rendered; run `mvg cards`")
            caption_input[index] = len(story["scenes"]) + len(caption_input)
            args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{scene['seconds'] + 1:.2f}", "-i", str(png)]
    voice_base = len(story["scenes"]) + len(caption_input)
    for _at, path, _seconds in cues:
        args += ["-i", str(path)]
    score_base = voice_base + len(cues)
    for item in score:
        args += ["-i", str(item["path"])]

    graph: list[str] = []
    for index, scene in enumerate(story["scenes"]):
        seconds = scene["seconds"]
        chain = (f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,"
                 f"format=yuv420p,setpts=PTS-STARTPTS,fps={FPS},tpad=stop_mode=clone:stop_duration=30,"
                 f"trim=0:{seconds:.3f},setpts=PTS-STARTPTS,settb=AVTB,fps={FPS}")
        if index in caption_input:
            graph.append(f"{chain}[b{index}]")
            graph.append(f"[{caption_input[index]}:v]scale={width}:{height},format=rgba,setpts=PTS-STARTPTS,"
                         f"fade=t=in:st=0.5:d=0.6:alpha=1,fade=t=out:st={max(seconds - 1.0, 1.2):.2f}:d=0.5:alpha=1[c{index}]")
            graph.append(f"[b{index}][c{index}]overlay=0:0:shortest=1,format=yuv420p,setpts=PTS-STARTPTS,settb=AVTB,"
                         f"fps={FPS}[v{index}]")
        else:
            graph.append(f"{chain}[v{index}]")
    previous, elapsed = "v0", story["scenes"][0]["seconds"]
    for index in range(1, len(story["scenes"])):
        graph.append(f"[{previous}][v{index}]xfade=transition=fade:duration={FADE}:offset={elapsed - FADE:.3f}[x{index}]")
        previous, elapsed = f"x{index}", elapsed + story["scenes"][index]["seconds"] - FADE
    graph.append(f"[{previous}]fade=t=in:st=0:d=0.8,fade=t=out:st={max(total - 1.4, 0):.2f}:d=1.4,"
                 f"scale=out_range=tv,format=yuv420p[vout]")

    stereo = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    if cues:
        labels = []
        for k, (at, _path, _seconds) in enumerate(cues):
            delay = int(at * 1000)
            graph.append(f"[{voice_base + k}:a]{stereo},adelay={delay}|{delay},volume=1.6[vo{k}]")
            labels.append(f"[vo{k}]")
        graph.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad=whole_dur={total:.2f},"
                     f"atrim=0:{total:.2f}[voice]")
    else:
        graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.2f},aformat=sample_fmts=fltp[voice]")
    if score:
        graph.append("[voice]asplit=2[voicemix][voicekey]")
        parts = []
        for k, item in enumerate(score):
            span, start = item["span"], item["start"]
            head = f"atrim=start={item['skip']:.2f},asetpts=PTS-STARTPTS," if item["skip"] else ""
            fade_in = f"afade=t=in:st=0:d={SCORE_XFADE}," if k else ""
            graph.append(f"[{score_base + k}:a]{stereo},{fade_in}{head}atempo={item['tempo']:.4f},"
                         f"apad=whole_dur={span:.2f},atrim=0:{span:.2f},afade=t=out:st={max(span - SCORE_XFADE, 0):.2f}:"
                         f"d={SCORE_XFADE},adelay={int(start * 1000)}|{int(start * 1000)}[m{k}]")
            parts.append(f"[m{k}]")
        graph.append(f"{''.join(parts)}amix=inputs={len(parts)}:normalize=0,volume=0.8,apad=whole_dur={total:.2f},"
                     f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(total - 4.0, 0):.2f}:d=4.0,atrim=0:{total:.2f}[music]")
        graph.append("[music][voicekey]sidechaincompress=threshold=0.03:ratio=8:attack=40:release=500:makeup=1[ducked]")
        graph.append("[ducked][voicemix]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
    else:
        graph.append("[voice]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")

    name = slug(story["title"]) + ("-draft" if draft else "")
    output = project.out("build", f"{name}.mp4")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        handle.write(";\n".join(graph))
        script = handle.name
    try:
        media.run([*args, "-/filter_complex", script, "-map", "[vout]", "-map", "[aout]",
                   "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-profile:v", "high",
                   "-color_range", "tv",
                   "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.2f}", str(output)])
    finally:
        pathlib.Path(script).unlink(missing_ok=True)
    scale = "scale=1280:-2" if width >= height else "scale=720:-2"
    for suffix, crf, bitrate in (("web", "24", "128k"), ("phone", "28", "96k")):
        copy = output.with_name(f"{name}-{suffix}.mp4")
        media.run(["-i", str(output), "-vf", scale, "-c:v", "libx264", "-crf", crf, "-preset", "medium",
                   "-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart", str(copy)])
    print(f"{output.relative_to(project.root)}  {clock(total)}" + ("  (draft: animatic or placeholder audio)" if draft else ""))
    return output


def loudness(path: pathlib.Path) -> float | None:
    """Integrated loudness (LUFS) of a file, for checks."""
    probe = subprocess.run([media.FFMPEG, "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True)
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", probe.stderr)
    return float(found[-1]) if found else None
