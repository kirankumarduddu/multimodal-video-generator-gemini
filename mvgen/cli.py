"""The `mvg` command line."""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
from importlib import resources

from . import __version__
from .project import Project, ProjectError

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "examples"
PROJECT_GITIGNORE = "renders/\naudio/\nbuild/\n*.stamp\n"


def cmd_init(args) -> int:
    target = pathlib.Path(args.folder).resolve()
    if target.exists() and any(target.iterdir()):
        raise ProjectError(f"{target} exists and is not empty")
    target.mkdir(parents=True, exist_ok=True)
    if args.example:
        source = EXAMPLES / args.example
        if not source.is_dir():
            names = ", ".join(p.name for p in EXAMPLES.iterdir()) if EXAMPLES.exists() else "none (install from a clone)"
            raise ProjectError(f"no example '{args.example}'; available: {names}")
        for file in source.iterdir():
            if file.is_file():
                shutil.copy2(file, target / file.name)
    else:
        starter = resources.files("mvgen").joinpath("starter")
        for name in ("studio.yaml", "brand.yaml", "brief.yaml"):
            (target / name).write_text(starter.joinpath(name).read_text(encoding="utf-8"), encoding="utf-8")
    (target / "brand").mkdir(exist_ok=True)
    (target / ".gitignore").write_text(PROJECT_GITIGNORE, encoding="utf-8")
    print(f"Created {target}\nNext: edit studio.yaml (gcp.project), then `cd {args.folder}` and `mvg doctor`.\n"
          f"Answer the brief and brand questions in the guided setup: "
          f"https://kirankumarduddu.github.io/multimodal-video-generator-gemini/guide.html")
    return 0


def cmd_doctor(args, project: Project) -> int:
    from .doctor import Doctor, report

    return report(Doctor(project, deep=args.deep).run())


def cmd_story(args, project: Project) -> int:
    from . import story
    from .spec import check_story, clock, parse_json, total_seconds

    if args.action == "prompt":
        target = project.out("build", "story_prompt.md")
        target.write_text(story.build_prompt(project), encoding="utf-8")
        print(f"Wrote {target.relative_to(project.root)}. Paste it into any LLM and save the JSON reply as story.json, "
              f"then run `mvg story check`.")
        return 0
    if args.action == "write":
        warnings = story.write(project, force=args.force)
        print("Wrote story.json")
        for warning in warnings:
            print(f"  warning: {warning}")
        return 0
    data = parse_json(project.story_file.read_text(encoding="utf-8"))
    errors, warnings = check_story(data, (project.brief or {}).get("length_seconds"))
    for error in errors:
        print(f"  error: {error}")
    for warning in warnings:
        print(f"  warning: {warning}")
    if not errors:
        print(f"story.json is valid: {len(data['scenes'])} scenes, {clock(total_seconds(data))}")
    return 1 if errors else 0


def cmd_plan(args, project: Project) -> int:
    from .assemble import describe

    print("\n".join(describe(project)))
    return 0


def cmd_cards(args, project: Project) -> int:
    from .cards import render

    render(project, args.ids, args.force, posters=args.posters)
    return 0


def cmd_cast(args, project: Project) -> int:
    from .imagery import make_cast

    return 1 if any(line.startswith("FAILED") for line in make_cast(project, args.ids, args.force)) else 0


def cmd_keyframes(args, project: Project) -> int:
    from .imagery import make_keyframes

    return 1 if any(line.startswith("FAILED") for line in make_keyframes(project, args.ids, args.force)) else 0


def cmd_review(args, project: Project) -> int:
    from .review import build_review

    path = build_review(project)
    print(f"Open {path} in a browser. Approve with `mvg approve <ids>` or `mvg approve --all`.")
    return 0


def cmd_approve(args, project: Project) -> int:
    from .review import approve

    if not args.ids and not args.all:
        raise ProjectError("name the scene ids to approve, or pass --all")
    for line in approve(project, args.ids, args.all, args.revoke):
        print(line)
    return 0


def cmd_clips(args, project: Project) -> int:
    from .clips import animatics, generate

    if args.animatic:
        animatics(project, args.ids, args.force)
        return 0
    return 1 if any(line.startswith("FAILED") for line in generate(project, args.ids, args.force)) else 0


def cmd_voice(args, project: Project) -> int:
    from .audio import make_voice

    return 1 if any(line.startswith("FAILED") for line in make_voice(project, args.ids, args.force, args.placeholder)) else 0


def cmd_music(args, project: Project) -> int:
    from .audio import make_music

    return 1 if any(line.startswith("FAILED") for line in make_music(project, args.ids, args.force, args.placeholder)) else 0


def cmd_assemble(args, project: Project) -> int:
    from .assemble import assemble

    assemble(project, allow_gaps=args.allow_gaps, no_music=args.no_music)
    return 0


def cmd_run(args, project: Project) -> int:
    """Every step in order; stops at the approval gate before paid video generation."""
    from . import story
    from .assemble import assemble
    from .audio import make_music, make_voice
    from .cards import render
    from .clips import animatics, approved, generate
    from .imagery import make_cast, make_keyframes
    from .review import build_review

    if not project.story_file.exists():
        print("== story")
        story.write(project)
    data = project.story()
    print("== cards"); render(project)
    print("== cast"); make_cast(project)
    print("== keyframes"); make_keyframes(project)
    review = build_review(project)
    waiting = [s["id"] for s in data["scenes"] if s["kind"] == "live_action" and not approved(project, s)]
    if waiting:
        print("== animatic preview")
        animatics(project)
        print(f"\nApproval needed before video generation: {', '.join(waiting)}\n"
              f"  Review {review}\n  then `mvg approve --all` (or by id) and run `mvg run` again.")
        return 2
    print("== clips"); generate(project)
    print("== voice"); make_voice(project)
    print("== music"); make_music(project)
    print("== assemble"); assemble(project)
    return 0


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(prog="mvg", description="Brief and brand in, finished trailer out. Cards first, "
                                   "then Gemini video, voice and music on your own Google Cloud project.")
    main.add_argument("--version", action="version", version=f"mvg {__version__}")
    main.add_argument("-C", dest="project", default=".", help="project folder (default: current folder)")
    sub = main.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a project folder")
    init.add_argument("folder")
    init.add_argument("--example", help="start from an example, e.g. kettle-and-kite")

    doctor = sub.add_parser("doctor", help="check tools, credentials, project, APIs, IAM and models")
    doctor.add_argument("--deep", action="store_true", help="also make a tiny TTS call")

    story = sub.add_parser("story", help="write or check story.json")
    story.add_argument("action", choices=["prompt", "write", "check"])
    story.add_argument("--force", action="store_true", help="replace an existing story.json")

    sub.add_parser("plan", help="timeline, length and what is left to generate")

    def steps(name, text, placeholder=False):
        step = sub.add_parser(name, help=text)
        step.add_argument("ids", nargs="*", help="only these scene, cast or music ids")
        step.add_argument("--force", action="store_true", help="regenerate even if up to date")
        if placeholder:
            step.add_argument("--placeholder", action="store_true", help="silent stand-ins for a free timing draft")
        return step

    cards = steps("cards", "render brand cards and captions (HTML to MP4)")
    cards.add_argument("--posters", action="store_true", help="only a still of each card's last frame (fast)")
    steps("cast", "cast reference stills (Gemini image model)")
    steps("keyframes", "first frame of each live-action shot (Gemini image model)")
    sub.add_parser("review", help="build build/review.html")
    approve = sub.add_parser("approve", help="approve shots for video generation")
    approve.add_argument("ids", nargs="*")
    approve.add_argument("--all", action="store_true")
    approve.add_argument("--revoke", action="store_true")
    clips = steps("clips", "generate approved video clips (Veo or Omni)")
    clips.add_argument("--animatic", action="store_true", help="free preview clips from keyframes instead")
    steps("voice", "narration, one WAV per line (Gemini TTS)", placeholder=True)
    steps("music", "score segments (Lyria)", placeholder=True)
    assemble = sub.add_parser("assemble", help="cut the film (ffmpeg)")
    assemble.add_argument("--allow-gaps", action="store_true", help="accept music shorter than its chapter")
    assemble.add_argument("--no-music", action="store_true")
    sub.add_parser("run", help="every step in order, stopping at the approval gate")
    return main


COMMANDS = {"doctor": cmd_doctor, "story": cmd_story, "plan": cmd_plan, "cards": cmd_cards, "cast": cmd_cast,
            "keyframes": cmd_keyframes, "review": cmd_review, "approve": cmd_approve, "clips": cmd_clips,
            "voice": cmd_voice, "music": cmd_music, "assemble": cmd_assemble, "run": cmd_run}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        project = Project(pathlib.Path(args.project).resolve())
        if not project.path("studio.yaml").exists():
            raise ProjectError(f"no studio.yaml in {project.root}: run `mvg init <folder>` or pass -C <folder>")
        return COMMANDS[args.command](args, project)
    except ProjectError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
