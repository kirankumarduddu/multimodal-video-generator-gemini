"""The CLI, the GitHub Pages guide and LLM agents share one schema and one prompt; keep the copies identical."""
import pathlib

from mvgen.cli import main
from mvgen.project import Project
from mvgen.story import build_prompt

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_docs_assets_match_the_package():
    for package_file, docs_file in (("mvgen/schema/story.schema.json", "docs/assets/story.schema.json"),
                                    ("mvgen/prompts/story_prompt.md", "docs/assets/story_prompt.md")):
        assert (ROOT / docs_file).read_bytes() == (ROOT / package_file).read_bytes(), \
            f"copy {package_file} to {docs_file}"


def test_prompt_fills_every_placeholder(tmp_path):
    assert main(["init", str(tmp_path / "film"), "--example", "kettle-and-kite"]) == 0
    prompt = build_prompt(Project(tmp_path / "film"))
    assert "{{" not in prompt
    assert "Kettle & Kite" in prompt and '"$defs"' in prompt and "length_seconds: 60" in prompt


def test_init_blank_project(tmp_path):
    assert main(["init", str(tmp_path / "blank")]) == 0
    for name in ("studio.yaml", "brand.yaml", "brief.yaml", ".gitignore"):
        assert (tmp_path / "blank" / name).exists()
    assert main(["init", str(tmp_path / "blank")]) == 2  # refuses a non-empty folder
