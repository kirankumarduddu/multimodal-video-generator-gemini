"""A film project folder: its config files, its output folders and freshness stamps."""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    "story": {"provider": "gemini", "model": "gemini-3.5-flash", "location": "global"},
    "image": {"model": "gemini-3-pro-image", "location": "global"},
    "video": {"provider": "veo", "model": "veo-3.1-generate-001", "location": "us-central1", "resolution": "1080p",
              "generate_audio": False},
    "tts": {"model": "gemini-3.1-flash-tts-preview", "location": "global"},
    "music": {"model": "lyria-3-pro-preview", "location": "global"},
}
FPS = 24
FADE = 0.4  # crossfade between scenes, seconds


class ProjectError(Exception):
    """A problem the user can fix in their project files."""


def digest(*parts: Any) -> str:
    sha = hashlib.sha256()
    for part in parts:
        if isinstance(part, (bytes, bytearray)):
            sha.update(part)
        elif isinstance(part, pathlib.Path):
            sha.update(part.read_bytes() if part.exists() else b"<missing>")
        else:
            sha.update(json.dumps(part, sort_keys=True, default=str).encode())
        sha.update(b"\x00")
    return sha.hexdigest()[:16]


@dataclass
class Project:
    root: pathlib.Path
    _cache: dict[str, Any] = field(default_factory=dict)

    # --- files ----------------------------------------------------------------------------------------------
    def path(self, *parts: str) -> pathlib.Path:
        return self.root.joinpath(*parts)

    def out(self, *parts: str) -> pathlib.Path:
        """An output path; its folder is created."""
        target = self.root.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _yaml(self, name: str, required: bool = True) -> dict[str, Any]:
        if name not in self._cache:
            file = self.path(name)
            if not file.exists():
                if required:
                    raise ProjectError(f"{file} is missing. Run `mvg init` or copy it from examples/.")
                self._cache[name] = {}
            else:
                try:
                    self._cache[name] = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError as error:
                    raise ProjectError(f"{name} is not valid YAML: {error}") from error
        return self._cache[name]

    @property
    def studio(self) -> dict[str, Any]:
        return self._yaml("studio.yaml")

    @property
    def brand(self) -> dict[str, Any]:
        return self._yaml("brand.yaml")

    @property
    def brief(self) -> dict[str, Any]:
        return self._yaml("brief.yaml", required=False)

    @property
    def gcp_project(self) -> str:
        project = (self.studio.get("gcp") or {}).get("project")
        if not project or project == "your-gcp-project-id":
            raise ProjectError("Set gcp.project in studio.yaml to your Google Cloud project ID.")
        return project

    def model(self, kind: str) -> dict[str, Any]:
        configured = (self.studio.get("models") or {}).get(kind) or {}
        merged = dict(DEFAULT_MODELS[kind])
        if configured.get("provider") and configured.get("provider") != merged.get("provider"):
            merged = {"location": "global"}  # a different provider: drop the defaults of the other one
        merged.update(configured)
        return merged

    @property
    def parallel(self) -> int:
        return max(1, int((self.studio.get("limits") or {}).get("parallel", 3)))

    @property
    def gcs_uri(self) -> str | None:
        return (self.studio.get("output") or {}).get("gcs_uri") or None

    # --- story ----------------------------------------------------------------------------------------------
    @property
    def story_file(self) -> pathlib.Path:
        return self.path("story.json")

    def story(self) -> dict[str, Any]:
        from .spec import load_story

        if "story" not in self._cache:
            self._cache["story"] = load_story(self.story_file)
        return self._cache["story"]

    @property
    def size(self) -> tuple[int, int]:
        return (1080, 1920) if self.story().get("aspect_ratio") == "9:16" else (1920, 1080)

    # --- freshness ------------------------------------------------------------------------------------------
    def fresh(self, output: pathlib.Path, key: str) -> bool:
        stamp = output.with_name(output.name + ".stamp")
        return output.exists() and stamp.exists() and stamp.read_text().strip() == key

    def stamp(self, output: pathlib.Path, key: str) -> None:
        output.with_name(output.name + ".stamp").write_text(key)

    # --- approvals ------------------------------------------------------------------------------------------
    @property
    def approvals_file(self) -> pathlib.Path:
        return self.path("approvals.json")

    def approvals(self) -> dict[str, str]:
        if self.approvals_file.exists():
            return json.loads(self.approvals_file.read_text(encoding="utf-8"))
        return {}

    def save_approvals(self, approvals: dict[str, str]) -> None:
        self.approvals_file.write_text(json.dumps(approvals, indent=1, sort_keys=True), encoding="utf-8")
