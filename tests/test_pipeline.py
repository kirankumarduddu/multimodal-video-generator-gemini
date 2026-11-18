"""Offline end to end: cards, approvals, animatic, placeholder audio and assembly, in both aspect ratios."""
import json
import pathlib

import pytest

from mvgen import media
from mvgen.assemble import assemble, loudness
from mvgen.cli import main
from mvgen.clips import approved, generate
from mvgen.project import Project
from mvgen.review import approve, build_review

ROOT = pathlib.Path(__file__).resolve().parents[1]


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
        return True
    except Exception:  # noqa: BLE001
        return False


needs_chromium = pytest.mark.skipif(not chromium_available(), reason="run `playwright install chromium`")

SHORT = {
    "title": "Pipeline test", "logline": "A short offline test film.", "aspect_ratio": "16:9",
    "cast": [{"id": "host", "description": "A fictional host in her 30s with short dark hair and a green coat."}],
    "music": [{"id": "main", "starts_at": "a-open", "prompt": "Gentle instrumental test score, 70 BPM, piano only, no vocals."}],
    "scenes": [
        {"id": "a-open", "kind": "live_action", "seconds": 3.0, "trim_start": 0.5,
         "shot": {"cast": ["host"], "action": "She looks up from a cup of tea and smiles warmly at the window."},
         "voice": [{"text": "A short test.", "at": 0.3}]},
        {"id": "b-title", "kind": "card", "seconds": 3.0, "caption": "A caption",
         "card": {"template": "title", "eyebrow": "Test", "headline": "Cards first", "sub": "Then video."}},
        {"id": "c-end", "kind": "card", "seconds": 2.6, "card": {"template": "endcard", "headline": "The end", "cta": "Go"},
         "voice": [{"text": "The end.", "at": 0.3}]},
    ],
}


def make_film(tmp_path, ratio="16:9"):
    film = tmp_path / f"film-{ratio.replace(':', 'x')}"
    main(["init", str(film), "--example", "kettle-and-kite"])
    data = json.loads(json.dumps(SHORT))
    data["aspect_ratio"] = ratio
    (film / "story.json").write_text(json.dumps(data), encoding="utf-8")
    brand = (film / "brand.yaml").read_text(encoding="utf-8")  # offline: system fonts, no network needed
    brand = brand.replace("heading: Fraunces", "heading: {family: Georgia, system: true}")
    brand = brand.replace("body: Inter", "body: {family: Arial, system: true}")
    (film / "brand.yaml").write_text(brand, encoding="utf-8")
    return Project(film)


def test_approval_gate_blocks_video_and_tracks_changes(tmp_path, capsys):
    project = make_film(tmp_path)
    scene = project.story()["scenes"][0]
    assert not approved(project, scene)
    assert generate(project) == []  # nothing generated without an approval
    assert "mvg approve a-open" in capsys.readouterr().out
    approve(project, ["a-open"])
    assert approved(Project(project.root), scene)
    data = json.loads(project.story_file.read_text(encoding="utf-8"))
    data["scenes"][0]["shot"]["action"] = "She waves at the camera, then turns to the window and smiles."
    project.story_file.write_text(json.dumps(data), encoding="utf-8")
    changed = Project(project.root)
    assert not approved(changed, changed.story()["scenes"][0])  # a changed shot needs a new approval


@needs_chromium
@pytest.mark.parametrize("ratio, size", [("16:9", (1920, 1080)), ("9:16", (1080, 1920))])
def test_offline_film(tmp_path, ratio, size):
    project = make_film(tmp_path, ratio)
    root = str(project.root)
    assert main(["-C", root, "cards"]) == 0
    assert (project.root / "renders" / "captions" / "b-title.png").exists()
    assert main(["-C", root, "clips", "--animatic"]) == 0
    assert main(["-C", root, "voice", "--placeholder"]) == 0
    assert main(["-C", root, "music", "--placeholder"]) == 0
    review = build_review(Project(project.root))
    assert "needs approval" in review.read_text(encoding="utf-8")
    output = assemble(Project(project.root))
    assert output.name == "pipeline-test-draft.mp4"
    assert media.duration(output) == pytest.approx(3.0 + 3.0 + 2.6 - 0.8, abs=0.15)
    for suffix in ("web", "phone"):
        assert output.with_name(f"pipeline-test-draft-{suffix}.mp4").exists()
    probe = __import__("subprocess").run([media.FFMPEG, "-hide_banner", "-i", str(output)], capture_output=True, text=True)
    assert f"{size[0]}x{size[1]}" in probe.stderr and "yuv420p" in probe.stderr and "yuvj" not in probe.stderr
    assert loudness(output) is not None
