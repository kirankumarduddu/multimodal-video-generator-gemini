"""The review gate: build/review.html shows every card, cast still and keyframe with the exact prompt that will be
sent to the video model; `mvg approve` records what was approved, so a later change needs a new approval."""
from __future__ import annotations

import html
import os
import pathlib

from .clips import approval_key, approved, clip_path, video_settings
from .imagery import video_prompt
from .project import Project
from .spec import clock, starts, total_seconds


def _rel(project: Project, path: pathlib.Path) -> str:
    return pathlib.Path(os.path.relpath(path, project.path("build"))).as_posix()


def build_review(project: Project) -> pathlib.Path:
    story = project.story()
    begin = starts(story)
    rows = []
    for index, scene in enumerate(story["scenes"]):
        sid = html.escape(scene["id"])
        voice = "".join(f"<li>{html.escape(line['text'])}</li>" for line in scene.get("voice", []))
        if scene["kind"] == "card":
            poster = project.path("renders", "cards", f"{scene['id']}.png")
            video = project.path("renders", "cards", f"{scene['id']}.mp4")
            media = (f'<video src="{_rel(project, video)}" poster="{_rel(project, poster)}" controls muted></video>'
                     if video.exists() else '<div class="missing">not rendered: run <code>mvg cards</code></div>')
            detail = f"<p><b>{html.escape(scene['card']['template'])}</b> card</p>"
            status = '<span class="ok">card (no approval needed)</span>'
        else:
            frame = project.path("renders", "keyframes", f"{scene['id']}.png")
            clip = clip_path(project, scene["id"])
            if clip.exists():
                media = f'<video src="{_rel(project, clip)}" controls muted></video>'
            elif frame.exists():
                media = f'<img src="{_rel(project, frame)}" alt="keyframe">'
            else:
                media = '<div class="missing">no keyframe: run <code>mvg cast</code> then <code>mvg keyframes</code></div>'
            cast = "".join(
                f'<figure><img src="{_rel(project, project.path("renders", "cast", f"{ref}.png"))}" alt=""><figcaption>'
                f'{html.escape(ref)}</figcaption></figure>' for ref in scene["shot"].get("cast", []))
            settings = video_settings(project, scene)
            detail = (f"<p><b>{html.escape(settings['provider'])}</b> {html.escape(settings['model'])} · "
                      f"{settings['duration']}s · {settings['resolution']} · trim {scene.get('trim_start', 0)}s</p>"
                      f"<pre>{html.escape(video_prompt(project, scene))}</pre><div class='cast'>{cast}</div>")
            status = ('<span class="ok">approved</span>' if approved(project, scene) else
                      f'<span class="todo">needs approval: <code>mvg approve {sid}</code></span>')
        caption = f"<p>Caption: {html.escape(scene['caption'])}</p>" if scene.get("caption") else ""
        rows.append(f'<section><header><h2>{index + 1}. {sid}</h2><span>{clock(begin[index])} · {scene["seconds"]}s · '
                    f'{scene["kind"]}</span>{status}</header><div class="body"><div class="media">{media}</div>'
                    f'<div>{detail}{caption}<ul class="voice">{voice}</ul></div></div></section>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Review · {html.escape(story['title'])}</title>
<style>body{{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f4f4f2;color:#1d1d1f}}
main{{max-width:1200px;margin:auto;padding:24px}}section{{background:#fff;border-radius:12px;margin:16px 0;padding:16px 20px;box-shadow:0 1px 3px #0002}}
header{{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}}h2{{margin:0;font-size:18px}}
.body{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;margin-top:10px}}
.media img,.media video{{width:100%;border-radius:8px;background:#000}}pre{{white-space:pre-wrap;background:#f6f6f6;padding:10px;border-radius:8px;font-size:13px}}
.cast{{display:flex;gap:8px}}.cast figure{{margin:0;width:120px;font-size:12px}}.cast img{{width:100%;border-radius:6px}}
.ok{{color:#0a7d32;font-weight:600}}.todo{{color:#b45309;font-weight:600}}.missing{{padding:40px;background:#eee;border-radius:8px;text-align:center}}
.voice li{{font-style:italic}}</style></head><body><main>
<h1>{html.escape(story['title'])}</h1><p>{html.escape(story['logline'])}</p>
<p>Length {clock(total_seconds(story))} · {len(story['scenes'])} scenes. Approve shots with <code>mvg approve &lt;scene ids&gt;</code>
or <code>mvg approve --all</code>; then <code>mvg clips</code>. Any change to a shot, its keyframe or the video model needs a new approval.</p>
{''.join(rows)}</main></body></html>"""
    target = project.out("build", "review.html")
    target.write_text(page, encoding="utf-8")
    return target


def approve(project: Project, ids: list[str], all_shots: bool = False, revoke: bool = False) -> list[str]:
    story = project.story()
    shots = {scene["id"]: scene for scene in story["scenes"] if scene["kind"] == "live_action"}
    unknown = [i for i in ids if i not in shots]
    if unknown:
        raise SystemExit(f"not live-action scene ids: {', '.join(unknown)}")
    chosen = list(shots) if all_shots else ids
    approvals = project.approvals()
    lines = []
    for scene_id in chosen:
        scene = shots[scene_id]
        if revoke:
            approvals.pop(scene_id, None)
            lines.append(f"revoked {scene_id}")
            continue
        if not project.path("renders", "keyframes", f"{scene_id}.png").exists():
            lines.append(f"approved {scene_id} WITHOUT a keyframe (the video model will work from the cast stills)")
        else:
            lines.append(f"approved {scene_id}")
        approvals[scene_id] = approval_key(project, scene)
    project.save_approvals(approvals)
    return lines
