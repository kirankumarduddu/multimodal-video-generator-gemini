"""Write the story with any LLM: Gemini on Vertex, any OpenAI-compatible endpoint, Anthropic, or copy-paste."""
from __future__ import annotations

import json
import os
from importlib import resources
from typing import Any

import requests
import yaml

from .gcp import client, retry
from .project import Project, ProjectError
from .spec import check_story, parse_json


def build_prompt(project: Project) -> str:
    template = resources.files("mvgen").joinpath("prompts/story_prompt.md").read_text(encoding="utf-8")
    schema_text = resources.files("mvgen").joinpath("schema/story.schema.json").read_text(encoding="utf-8")
    brief = project.brief or {}
    if not brief:
        raise ProjectError("brief.yaml is missing or empty: answer the brief questions first (see the guide).")
    dump = lambda data: yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110).strip()  # noqa: E731
    return (template.replace("{{BRIEF}}", dump(brief)).replace("{{BRAND}}", dump(project.brand))
            .replace("{{SCHEMA}}", schema_text.strip()))


def _gemini(project: Project, config: dict[str, Any], prompt: str) -> str:
    from google.genai import types

    api = client(project, "story")
    response = retry(lambda: api.models.generate_content(
        model=config["model"], contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json",
                                           temperature=float(config.get("temperature", 0.8)))), "story")
    return response.text or ""


def _key(config: dict[str, Any], default_env: str) -> str:
    env = config.get("api_key_env", default_env)
    key = os.environ.get(env, "")
    if not key and not str(config.get("base_url", "")).startswith(("http://localhost", "http://127.0.0.1")):
        raise ProjectError(f"Set the {env} environment variable (never put API keys in studio.yaml).")
    return key


def _openai(config: dict[str, Any], prompt: str) -> str:
    base = str(config.get("base_url", "https://api.openai.com/v1")).rstrip("/")
    key = _key(config, "OPENAI_API_KEY")
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
    body: dict[str, Any] = {"model": config["model"], "messages": [{"role": "user", "content": prompt}]}
    if config.get("json_mode", True):
        body["response_format"] = {"type": "json_object"}
    response = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=600)
    if response.status_code == 400 and "response_format" in body:  # some compatible servers lack JSON mode
        body.pop("response_format")
        response = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=600)
    if response.status_code >= 400:
        raise RuntimeError(f"story LLM HTTP {response.status_code}: {response.text[:500]}")
    return response.json()["choices"][0]["message"]["content"]


def _anthropic(config: dict[str, Any], prompt: str) -> str:
    key = _key(config, "ANTHROPIC_API_KEY")
    base = str(config.get("base_url", "https://api.anthropic.com")).rstrip("/")
    response = requests.post(f"{base}/v1/messages", timeout=600, json={
        "model": config["model"], "max_tokens": int(config.get("max_tokens", 16000)),
        "messages": [{"role": "user", "content": prompt}]},
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    if response.status_code >= 400:
        raise RuntimeError(f"story LLM HTTP {response.status_code}: {response.text[:500]}")
    return "".join(block.get("text", "") for block in response.json().get("content", []))


def ask(project: Project, prompt: str) -> str:
    config = project.model("story")
    provider = config.get("provider", "gemini")
    if provider == "gemini":
        return _gemini(project, config, prompt)
    if provider == "openai":
        return _openai(config, prompt)
    if provider == "anthropic":
        return _anthropic(config, prompt)
    if provider == "manual":
        raise ProjectError("models.story.provider is manual: run `mvg story prompt`, paste the prompt into any LLM "
                           "and save its reply as story.json.")
    raise ProjectError(f"unknown story provider '{provider}' (use gemini, openai, anthropic or manual)")


def write(project: Project, force: bool = False) -> list[str]:
    """Ask the configured LLM for story.json; one repair round if the reply fails validation."""
    if project.story_file.exists() and not force:
        raise ProjectError("story.json exists; pass --force to replace it.")
    prompt = build_prompt(project)
    target = (project.brief or {}).get("length_seconds")
    reply = ask(project, prompt)
    for attempt in range(2):
        try:
            story = parse_json(reply)
            errors, warnings = check_story(story, target)
        except json.JSONDecodeError as error:
            story, errors, warnings = None, [f"not valid JSON: {error}"], []
        if not errors:
            project.story_file.write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
            return warnings
        if attempt == 1:
            raw = project.out("build", "story_reply.txt")
            raw.write_text(reply, encoding="utf-8")
            raise ProjectError(f"the LLM's story still has {len(errors)} problem(s) (reply saved to {raw.name}):\n  "
                               + "\n  ".join(errors[:12]))
        print(f"story: {len(errors)} problem(s), asking the LLM to fix them", flush=True)
        reply = ask(project, f"{prompt}\n\n## Your previous reply\n{reply}\n\n## Fix these problems and return the whole "
                             f"corrected JSON object only\n- " + "\n- ".join(errors[:30]))
    return []
