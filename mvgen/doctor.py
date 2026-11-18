"""`mvg doctor`: is this machine and this Google Cloud project ready? Every check says how to fix a failure."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Callable

import requests

from .project import Project, ProjectError

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
PREDICT = "aiplatform.endpoints.predict"


@dataclass
class Check:
    name: str
    status: str  # PASS, WARN, FAIL, SKIP
    detail: str
    fix: str = ""


def _google_error(response: requests.Response) -> str:
    try:
        error = response.json().get("error", {})
        message = error.get("message", "").splitlines()[0][:300]
        return f"HTTP {response.status_code} {error.get('status', '')}: {message}"
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:300]}"


def explain(error: Exception, project_id: str) -> tuple[str, str]:
    """A short detail and a concrete fix for an SDK error."""
    code = getattr(error, "code", None)
    status = getattr(error, "status", "") or ""
    message = (getattr(error, "message", None) or str(error)).splitlines()[0][:240]
    fixes = {
        403: f"Check that the project exists, Vertex AI is enabled (gcloud services enable aiplatform.googleapis.com "
             f"--project {project_id}) and you have roles/aiplatform.user",
        404: "Check the model id and location in studio.yaml (Gemini 3 models: global; Veo: a region such as us-central1)",
        429: "Quota or capacity: wait and retry, or lower limits.parallel in studio.yaml",
        400: "Check the model settings in studio.yaml",
    }
    return f"{code or type(error).__name__} {status}: {message}".strip(), fixes.get(code, "")


class Doctor:
    def __init__(self, project: Project, deep: bool = False):
        self.project, self.deep = project, deep
        self.checks: list[Check] = []
        self.session = None
        self.gcp = None
        self.who = None

    def add(self, *args, **kwargs) -> Check:
        check = Check(*args, **kwargs)
        self.checks.append(check)
        return check

    def guard(self, name: str, test: Callable[[], None]) -> None:
        try:
            test()
        except Exception as error:  # noqa: BLE001 - a check must never crash the report
            detail, fix = explain(error, self.gcp or "PROJECT")
            self.add(name, "FAIL", detail, fix)

    # --- local tools ----------------------------------------------------------------------------------------
    def tools(self) -> None:
        version = sys.version_info
        self.add("Python", "PASS" if version >= (3, 10) else "FAIL", sys.version.split()[0],
                 "" if version >= (3, 10) else "Install Python 3.10 or newer")

        def ffmpeg():
            from .media import FFMPEG
            self.add("ffmpeg", "PASS", FFMPEG)
        self.guard("ffmpeg", ffmpeg)

        def chromium():
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                browser.close()
            self.add("Playwright Chromium (cards)", "PASS", "launches")
        try:
            chromium()
        except Exception as error:  # noqa: BLE001
            self.add("Playwright Chromium (cards)", "FAIL", str(error).splitlines()[0][:200],
                     "playwright install chromium")
        self.add("gcloud CLI", "PASS" if shutil.which("gcloud") else "WARN",
                 shutil.which("gcloud") or "not on PATH (only needed to log in and set up the project)",
                 "" if shutil.which("gcloud") else "https://cloud.google.com/sdk/docs/install")

    # --- Google Cloud ---------------------------------------------------------------------------------------
    def credentials(self) -> bool:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession, Request

        try:
            self.gcp = self.project.gcp_project
        except ProjectError as error:
            self.add("Project ID", "FAIL", str(error), "Edit studio.yaml: gcp.project")
            return False
        self.add("Project ID", "PASS", self.gcp)
        try:
            credentials, adc_project = google.auth.default(scopes=[SCOPE])
            credentials.refresh(Request())
        except Exception as error:  # noqa: BLE001
            self.add("Application Default Credentials", "FAIL", str(error).splitlines()[0][:300],
                     "gcloud auth application-default login")
            return False
        who = getattr(credentials, "service_account_email", None)
        if not who:
            try:
                info = requests.get("https://oauth2.googleapis.com/tokeninfo",
                                    params={"access_token": credentials.token}, timeout=15).json()
                who = info.get("email")
            except requests.RequestException:
                who = None
        self.add("Application Default Credentials", "PASS", who or type(credentials).__name__)
        self.who = who
        quota = getattr(credentials, "quota_project_id", None)
        if hasattr(credentials, "quota_project_id") and not getattr(credentials, "service_account_email", None):
            if quota == self.gcp:
                self.add("ADC quota project", "PASS", quota)
            else:
                self.add("ADC quota project", "WARN", f"{quota or 'not set'} (requests bill quota to {self.gcp})",
                         f"gcloud auth application-default set-quota-project {self.gcp}")
        if adc_project and adc_project != self.gcp:
            self.add("Default project", "WARN", f"gcloud default is {adc_project}; studio.yaml uses {self.gcp}",
                     f"gcloud config set project {self.gcp}")
        self.session = AuthorizedSession(credentials)
        return True

    def api_enabled(self) -> None:
        for service, required in (("aiplatform.googleapis.com", True),
                                  ("storage.googleapis.com", bool(self.project.gcs_uri))):
            url = f"https://serviceusage.googleapis.com/v1/projects/{self.gcp}/services/{service}"
            response = self.session.get(url, timeout=30)
            if response.ok:
                state = response.json().get("state")
                ok = state == "ENABLED"
                self.add(f"API {service}", "PASS" if ok else ("FAIL" if required else "WARN"), state,
                         "" if ok else f"gcloud services enable {service} --project {self.gcp}")
            elif required:
                self.add(f"API {service}", "WARN", _google_error(response),
                         "Can't read the service state (needs serviceusage.services.get); the model checks below "
                         "will show whether the API works.")

    def iam(self) -> None:
        url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{self.gcp}:testIamPermissions"
        response = self.session.post(url, json={"permissions": [PREDICT]}, timeout=30)
        if not response.ok:
            self.add("IAM", "FAIL", _google_error(response), "Check the project ID and that you can see the project")
            return
        granted = response.json().get("permissions", [])
        member = (f"serviceAccount:{self.who}" if self.who and self.who.endswith(".gserviceaccount.com")
                  else f"user:{self.who or 'YOU@EXAMPLE.COM'}")
        self.add(f"IAM {PREDICT}", "PASS" if PREDICT in granted else "FAIL",
                 "granted" if PREDICT in granted else "missing",
                 "" if PREDICT in granted else
                 f"gcloud projects add-iam-policy-binding {self.gcp} --member={member} "
                 f"--role=roles/aiplatform.user   (an owner or IAM admin runs this)")

    def models(self) -> None:
        from .gcp import client

        def visible(kind: str) -> None:
            config = self.project.model(kind)
            if kind == "story" and config.get("provider", "gemini") != "gemini":
                return
            label = f"Model {kind}: {config['model']} @ {config.get('location', 'global')}"
            try:
                client(self.project, kind).models.get(model=config["model"])
                self.add(label, "PASS", "model id exists (access is proven by the calls below and the first run)")
            except Exception as error:  # noqa: BLE001
                detail, fix = explain(error, self.gcp)
                code = getattr(error, "code", None)
                self.add(label, "FAIL" if code == 404 else "WARN", detail, fix or
                         "Check the model id and location in studio.yaml")

        for kind in ("story", "image", "video", "tts", "music"):
            visible(kind)
        self.guard("Gemini call", self.ping)
        if self.deep:
            self.guard("TTS call", self.ping_tts)

    def ping(self) -> None:
        from .gcp import _client

        config = self.project.model("story")
        model = config["model"] if config.get("provider", "gemini") == "gemini" else "gemini-3.5-flash"
        response = _client(self.gcp, "global").models.generate_content(model=model, contents="Reply with OK.")
        self.add(f"Gemini call ({model})", "PASS", (response.text or "").strip()[:40] or "responded")

    def ping_tts(self) -> None:
        from google.genai import types

        from .gcp import client, first_inline

        config = self.project.model("tts")
        voice = (self.project.brand.get("voice") or {}).get("name", "Sulafat") if self.project.path("brand.yaml").exists() else "Sulafat"
        response = client(self.project, "tts").models.generate_content(
            model=config["model"], contents="Say: test.",
            config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
        data = first_inline(response)
        self.add(f"TTS call ({voice})", "PASS" if data else "FAIL", f"{len(data or b''):,} bytes of audio")

    # --- story LLM ------------------------------------------------------------------------------------------
    def story_llm(self) -> None:
        config = self.project.model("story")
        provider = config.get("provider", "gemini")
        if provider in ("gemini", "manual"):
            self.add("Story LLM", "PASS", "Gemini on Vertex (checked above)" if provider == "gemini" else
                     "manual: paste `mvg story prompt` into any LLM")
            return
        env = config.get("api_key_env", "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY")
        key = os.environ.get(env)
        if provider == "openai":
            base = str(config.get("base_url", "https://api.openai.com/v1")).rstrip("/")
            local = base.startswith(("http://localhost", "http://127.0.0.1"))
            if not key and not local:
                self.add("Story LLM key", "FAIL", f"{env} is not set", f"Set the {env} environment variable")
                return
            response = requests.get(f"{base}/models", timeout=20, headers={"Authorization": f"Bearer {key}"} if key else {})
        elif provider == "anthropic":
            if not key:
                self.add("Story LLM key", "FAIL", f"{env} is not set", f"Set the {env} environment variable")
                return
            response = requests.get(f"{str(config.get('base_url', 'https://api.anthropic.com')).rstrip('/')}/v1/models",
                                    timeout=20, headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
        else:
            self.add("Story LLM", "FAIL", f"unknown provider {provider}", "Use gemini, openai, anthropic or manual")
            return
        self.add(f"Story LLM ({provider} {config.get('model')})", "PASS" if response.ok else "FAIL",
                 "reachable, key accepted" if response.ok else f"HTTP {response.status_code}: {response.text[:200]}",
                 "" if response.ok else "Check the base_url, model and API key")

    def run(self) -> list[Check]:
        self.tools()
        if self.credentials():
            self.guard("API enabled", self.api_enabled)
            self.guard("IAM", self.iam)
            self.models()
        self.guard("Story LLM", self.story_llm)
        return self.checks


def report(checks: list[Check]) -> int:
    marks = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL", "SKIP": "SKIP"}
    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"[{marks[check.status]}] {check.name.ljust(width)}  {check.detail}")
        if check.fix and check.status != "PASS":
            print(f"       {' ' * width}  fix: {check.fix}")
    failed = sum(check.status == "FAIL" for check in checks)
    warned = sum(check.status == "WARN" for check in checks)
    print(f"\n{len(checks) - failed - warned} passed, {warned} warning(s), {failed} failure(s)")
    return 1 if failed else 0
