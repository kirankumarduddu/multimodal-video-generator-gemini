"""Brand cards: HTML templates in the brand's colors, fonts and logo, captured frame by frame (Playwright) to MP4.

Cards carry every word, number and logo in the film; generated footage never does. They are cheap, exact and
deterministic, so they are made first and reviewed before any video is generated.
"""
from __future__ import annotations

import base64
import functools
import html
import pathlib
import subprocess
import urllib.parse
from typing import Any, Callable

import requests

from .media import FFMPEG
from .project import FPS, Project, digest

TEMPLATES = ("title", "statement", "feature", "list", "stat", "quote", "flow", "screen", "endcard")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".svg": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf", ".woff2": "font/woff2"}
FALLBACK_COLORS = {"background": "#101418", "surface": "#1C2630", "primary": "#E8B04B", "accent": "#F6EBD3",
                   "text": "#FFFFFF", "muted": "#B8C4CC"}


def esc(text: Any) -> str:
    return html.escape(str(text or ""))


def data_uri(path: pathlib.Path) -> str:
    return f"data:{MIME.get(path.suffix.lower(), 'application/octet-stream')};base64," + base64.b64encode(path.read_bytes()).decode()


def anim(name: str, start: float, length: float = 1.0, ease: str = "") -> str:
    style = f"animation-name:{name};animation-delay:{start:.2f}s;animation-duration:{length:.2f}s;"
    return style + (f"animation-timing-function:{ease};" if ease else "")


@functools.lru_cache(maxsize=32)
def google_font_css(family: str) -> str | None:
    """The Google Fonts stylesheet URL for a family, trying richer weight sets first; None when offline/unknown."""
    name = urllib.parse.quote_plus(family)
    for axis in (":wght@300;400;600;700", ":wght@400;700", ""):
        url = f"https://fonts.googleapis.com/css2?family={name}{axis}&display=block"
        try:
            if requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}).status_code == 200:
                return url
        except requests.RequestException:
            return None
    return None


def font_head(project: Project) -> tuple[str, str, str]:
    """(<head> font markup, heading family, body family)."""
    fonts = project.brand.get("fonts") or {}
    markup, families = [], []
    for role, fallback in (("heading", "Georgia, serif"), ("body", "system-ui, 'Segoe UI', Arial, sans-serif")):
        spec = fonts.get(role) or ("Playfair Display" if role == "heading" else "Inter")
        if isinstance(spec, dict) and spec.get("file"):
            family = spec.get("family") or f"brand-{role}"
            markup.append(f"<style>@font-face{{font-family:'{family}';src:url('{data_uri(project.path(spec['file']))}');"
                          f"font-weight:100 900;}}</style>")
        elif isinstance(spec, dict) and spec.get("system"):
            family = spec["family"]  # installed on this machine: nothing to load
        else:
            family = spec["family"] if isinstance(spec, dict) else str(spec)
            url = google_font_css(family)
            if url:
                markup.append(f'<link rel="stylesheet" href="{esc(url)}">')
            else:
                print(f"  font '{family}' could not be loaded (offline or not on Google Fonts); using a system font")
        families.append(f"'{family}', {fallback}")
    return "".join(markup), families[0], families[1]


def base_css(project: Project, size: tuple[int, int]) -> str:
    colors = {**FALLBACK_COLORS, **(project.brand.get("colors") or {})}
    width, height = size
    rem = min(width, height) / 1080 * 20
    return f"""
:root{{--bg:{colors['background']};--surface:{colors['surface']};--primary:{colors['primary']};--accent:{colors['accent']};
--text:{colors['text']};--muted:{colors['muted']}}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:{rem:.3f}px}}
html,body{{width:{width}px;height:{height}px;overflow:hidden}}
body{{background:radial-gradient(ellipse 80% 70% at 50% 42%,color-mix(in srgb,var(--surface) 92%,white 8%) 0%,var(--bg) 72%);
color:var(--text);font-family:var(--body);-webkit-font-smoothing:antialiased}}
body.clear{{background:transparent}}
.stage{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:6rem 8rem;text-align:center}}
.portrait .stage{{padding:10rem 5rem}}
.col{{display:flex;flex-direction:column;align-items:center;gap:1.6rem;max-width:100rem}}
.a{{animation-fill-mode:both;animation-timing-function:cubic-bezier(.22,.8,.26,1)}}
@keyframes up{{from{{opacity:0;transform:translateY(2.2rem)}}to{{opacity:1;transform:none}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes blurin{{from{{opacity:0;filter:blur(.9rem);transform:translateY(.8rem)}}to{{opacity:1;filter:none;transform:none}}}}
@keyframes pop{{0%{{opacity:0;transform:scale(.7)}}70%{{opacity:1;transform:scale(1.04)}}100%{{opacity:1;transform:scale(1)}}}}
@keyframes rule{{from{{width:0}}to{{width:var(--w,14rem)}}}}
@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes growy{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
@keyframes drift{{from{{transform:translate(-8%,-4%)}}to{{transform:translate(8%,4%)}}}}
@keyframes zoom{{from{{transform:scale(1)}}to{{transform:scale(1.045)}}}}
@keyframes tilt{{from{{transform:perspective(160rem) rotateY(-9deg) rotateX(2deg)}}to{{transform:perspective(160rem) rotateY(-3deg) rotateX(0)}}}}
.eyebrow{{font:600 1.35rem/1.2 var(--body);letter-spacing:.24em;text-transform:uppercase;color:var(--primary)}}
.h1{{font:600 4.6rem/1.08 var(--head);color:var(--accent)}}
.h2{{font:600 3.3rem/1.12 var(--head);color:var(--accent)}}
.sub{{font:300 1.85rem/1.45 var(--body);color:var(--muted);max-width:70rem}}
.rule{{height:.22rem;background:var(--primary);width:var(--w,14rem);border-radius:1rem}}
.logo{{max-height:7rem;max-width:30rem;object-fit:contain}}
.glow{{position:absolute;width:90rem;height:90rem;left:calc(50% - 45rem);top:calc(50% - 50rem);pointer-events:none;
background:radial-gradient(circle,color-mix(in srgb,var(--primary) 22%,transparent) 0%,transparent 60%);opacity:.55}}
.vig{{position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at center,transparent 55%,rgba(0,0,0,.45) 100%)}}
.panel{{background:color-mix(in srgb,var(--surface) 88%,transparent);border:1px solid color-mix(in srgb,var(--primary) 30%,transparent);
border-radius:1.6rem;box-shadow:0 2rem 5rem rgba(0,0,0,.35)}}
"""


def ambient(seconds: float) -> str:
    return (f'<div class="glow a" style="{anim("drift", 0, max(seconds, 1), "linear")}"></div>'
            '<div class="vig"></div>')


def logo_tag(project: Project, delay: float = 0.1) -> str:
    logo = project.brand.get("logo")
    if not logo or not project.path(logo).exists():
        return ""
    return f'<img class="logo a" style="{anim("pop", delay, 0.9)}" src="{data_uri(project.path(logo))}" alt="">'


def image_tag(project: Project, card: dict[str, Any], css: str = "", cls: str = "") -> str:
    path = project.path(card["image"]) if card.get("image") else None
    if not path or not path.exists():
        raise FileNotFoundError(f"card image not found: {card.get('image')}")
    return f'<img class="{cls}" src="{data_uri(path)}" style="display:block;{css}" alt="">'


# --- templates: (project, card, seconds) -> body HTML -------------------------------------------------------

def t_title(project: Project, card: dict, seconds: float) -> str:
    parts = [logo_tag(project)]
    if card.get("eyebrow"):
        parts.append(f'<div class="eyebrow a" style="{anim("up", .3, .9)}">{esc(card["eyebrow"])}</div>')
    parts.append(f'<div class="h1 a" style="{anim("blurin", .6, 1.2)}">{esc(card.get("headline"))}</div>')
    parts.append(f'<div class="rule a" style="margin:.6rem 0;{anim("rule", 1.2, 1.0)}"></div>')
    if card.get("sub"):
        parts.append(f'<div class="sub a" style="{anim("up", 1.5, 1.0)}">{esc(card["sub"])}</div>')
    return f'<div class="stage"><div class="col">{"".join(parts)}</div></div>'


def t_statement(project: Project, card: dict, seconds: float) -> str:
    lines = card.get("lines") or [card.get("headline", "")]
    step = min(1.0, max(0.35, (seconds - 1.6) / max(len(lines), 1)))
    rows = []
    for index, line in enumerate(lines):
        color = "var(--primary)" if index == len(lines) - 1 and len(lines) > 1 else "var(--accent)"
        rows.append(f'<div class="h1 a" style="color:{color};{anim("blurin", .3 + index * step, .9)}">{esc(line)}</div>')
    return f'<div class="stage"><div class="col" style="gap:.8rem">{"".join(rows)}</div></div>'


def _text_block(card: dict, align: str = "center", start: float = .3) -> str:
    parts = []
    if card.get("eyebrow"):
        parts.append(f'<div class="eyebrow a" style="{anim("up", start, .8)}">{esc(card["eyebrow"])}</div>')
    if card.get("headline"):
        parts.append(f'<div class="h2 a" style="{anim("blurin", start + .3, 1.0)}">{esc(card["headline"])}</div>')
    parts.append(f'<div class="rule a" style="--w:9rem;{anim("rule", start + .8, .8)}"></div>')
    if card.get("sub"):
        parts.append(f'<div class="sub a" style="{anim("up", start + 1.0, .9)}">{esc(card["sub"])}</div>')
    items = "flex-start" if align == "left" else "center"
    return f'<div class="col" style="align-items:{items};text-align:{align};gap:1.4rem">{"".join(parts)}</div>'


def t_feature(project: Project, card: dict, seconds: float) -> str:
    if not card.get("image"):
        return f'<div class="stage">{_text_block(card)}</div>'
    portrait = project.size[1] > project.size[0]
    picture = image_tag(project, card, f"max-width:100%;max-height:{int(project.size[1] * 0.55)}px;width:auto;"
                        "height:auto;border-radius:1.2rem")
    shot = (f'<div class="panel a" style="padding:1rem;max-width:{"100%" if portrait else "56%"};'
            f'{anim("tilt", 0, seconds, "ease-out")}"><div class="a" style="{anim("fade", .4, .9)}">{picture}</div></div>')
    layout = "flex-direction:column;gap:4rem" if portrait else "gap:5rem;text-align:left"
    text = _text_block(card, "center" if portrait else "left")
    return f'<div class="stage" style="{layout}"><div style="{"" if portrait else "flex:1"}">{text}</div>{shot}</div>'


def t_list(project: Project, card: dict, seconds: float) -> str:
    items = card.get("items") or []
    step = min(.55, max(.3, (seconds - 2.2) / max(len(items), 1)))
    rows = "".join(
        f'<li class="a" style="{anim("up", 1.0 + i * step, .7)}"><span class="tick">✓</span>{esc(item)}</li>'
        for i, item in enumerate(items))
    css = ("<style>.list{list-style:none;display:flex;flex-direction:column;gap:1.3rem;text-align:left;margin-top:1.6rem}"
           ".list li{font:400 2.2rem/1.3 var(--body);color:var(--text);display:flex;align-items:center;gap:1.4rem}"
           ".tick{flex:none;width:3rem;height:3rem;border-radius:50%;background:var(--primary);color:var(--bg);"
           "display:grid;place-items:center;font:700 1.6rem var(--body)}</style>")
    head = f'<div class="h2 a" style="{anim("blurin", .3, 1.0)}">{esc(card.get("headline"))}</div>' if card.get("headline") else ""
    return f'{css}<div class="stage"><div class="col">{head}<ul class="list">{rows}</ul></div></div>'


def t_stat(project: Project, card: dict, seconds: float) -> str:
    stats = card.get("stats") or []
    blocks = "".join(
        f'<div class="stat panel a" style="{anim("pop", 1.0 + i * .45, .9)}"><div class="value">{esc(s["value"])}</div>'
        f'<div class="label">{esc(s["label"])}</div></div>' for i, s in enumerate(stats))
    css = ("<style>.stats{display:flex;gap:2.4rem;flex-wrap:wrap;justify-content:center;margin-top:2rem}"
           ".stat{padding:2.4rem 3rem;min-width:22rem}.value{font:700 5.6rem/1 var(--head);color:var(--primary)}"
           ".label{font:400 1.6rem/1.3 var(--body);color:var(--muted);margin-top:.9rem}"
           ".portrait .stats{flex-direction:column}</style>")
    head = f'<div class="h2 a" style="{anim("blurin", .3, 1.0)}">{esc(card.get("headline"))}</div>' if card.get("headline") else ""
    return f'{css}<div class="stage"><div class="col">{head}<div class="stats">{blocks}</div></div></div>'


def t_quote(project: Project, card: dict, seconds: float) -> str:
    return ('<div class="stage"><div class="col" style="max-width:90rem">'
            f'<div class="a" style="font:700 12rem/0.6 var(--head);color:var(--primary);{anim("pop", .2, .8)}">&ldquo;</div>'
            f'<div class="h2 a" style="font-style:italic;font-weight:500;{anim("blurin", .6, 1.4)}">{esc(card.get("quote"))}</div>'
            f'<div class="rule a" style="--w:6rem;{anim("rule", 1.6, .7)}"></div>'
            f'<div class="eyebrow a" style="{anim("up", 1.9, .8)}">{esc(card.get("by"))}</div></div></div>')


def t_flow(project: Project, card: dict, seconds: float) -> str:
    items = card.get("items") or []
    portrait = project.size[1] > project.size[0]
    step = min(.9, max(.45, (seconds - 2.4) / max(len(items), 1)))
    draw = max(step * (len(items) - 1), .4)
    nodes = "".join(
        f'<div class="node a" style="{anim("pop", 1.0 + i * step, .7)}"><div class="num">{i + 1}</div>'
        f'<div class="nlabel">{esc(item)}</div></div>' for i, item in enumerate(items))
    if portrait:
        layout = (".flow{position:relative;display:flex;flex-direction:column;gap:3.4rem;margin-top:3rem;text-align:left}"
                  ".node{display:flex;align-items:center;gap:2rem;position:relative}"
                  ".track{position:absolute;left:3.2rem;top:3.2rem;bottom:3.2rem;width:.3rem;transform-origin:top}")
        track = f'<div class="track a" style="{anim("growy", 1.0, draw, "linear")}"></div>'
    else:
        layout = (".flow{position:relative;display:flex;gap:2rem;margin-top:3rem}"
                  ".node{display:flex;flex-direction:column;align-items:center;gap:1.2rem;width:24rem;position:relative}"
                  ".track{position:absolute;left:12rem;right:12rem;top:3.05rem;height:.3rem;transform-origin:left}")
        track = f'<div class="track a" style="{anim("grow", 1.0, draw, "linear")}"></div>'
    css = (f"<style>{layout}.track{{background:var(--primary);opacity:.75}}"
           ".num{flex:none;width:6.4rem;height:6.4rem;border-radius:50%;border:.25rem solid var(--primary);display:grid;"
           "place-items:center;font:600 2.6rem var(--head);color:var(--primary);background:var(--surface)}"
           ".nlabel{font:500 1.9rem/1.3 var(--body);color:var(--text)}</style>")
    head = f'<div class="h2 a" style="{anim("blurin", .3, 1.0)}">{esc(card.get("headline"))}</div>' if card.get("headline") else ""
    return f'{css}<div class="stage"><div class="col">{head}<div class="flow">{track}{nodes}</div></div></div>'


def t_screen(project: Project, card: dict, seconds: float) -> str:
    width, height = project.size
    picture = image_tag(project, card, f"max-width:100%;max-height:{int(height * 0.6)}px;width:auto;height:auto;"
                        f"border-radius:1rem;{anim('zoom', 0, seconds, 'ease-out')}", "a")
    frame = (f'<div class="panel a" style="max-width:100%;padding:1.1rem;overflow:hidden;{anim("up", .5, 1.0)}">'
             f'<div style="overflow:hidden;border-radius:1rem">{picture}</div></div>')
    head = f'<div class="h2 a" style="font-size:2.8rem;{anim("blurin", .2, .9)}">{esc(card.get("headline"))}</div>' if card.get("headline") else ""
    return f'<div class="stage"><div class="col" style="gap:2.4rem">{head}{frame}</div></div>'


def t_endcard(project: Project, card: dict, seconds: float) -> str:
    parts = [logo_tag(project, .2)]
    parts.append(f'<div class="h1 a" style="{anim("blurin", .5, 1.3)}">{esc(card.get("headline") or project.brand.get("tagline"))}</div>')
    parts.append(f'<div class="rule a" style="{anim("rule", 1.3, .9)}"></div>')
    sub = card.get("sub") or project.brand.get("name")
    if sub:
        parts.append(f'<div class="eyebrow a" style="{anim("up", 1.6, .9)}">{esc(sub)}</div>')
    if card.get("cta"):
        parts.append(f'<div class="a" style="margin-top:1.6rem;padding:1.2rem 2.8rem;border-radius:5rem;background:var(--primary);'
                     f'color:var(--bg);font:600 1.8rem var(--body);{anim("pop", 2.1, .8)}">{esc(card["cta"])}</div>')
    return f'<div class="stage"><div class="col">{"".join(parts)}</div></div>'


BUILDERS: dict[str, Callable[[Project, dict, float], str]] = {
    "title": t_title, "statement": t_statement, "feature": t_feature, "list": t_list, "stat": t_stat,
    "quote": t_quote, "flow": t_flow, "screen": t_screen, "endcard": t_endcard,
}


def document(project: Project, body: str, seconds: float, clear: bool = False) -> str:
    size = project.size
    fonts, heading, body_font = font_head(project)
    classes = " ".join(c for c in ("clear" if clear else "", "portrait" if size[1] > size[0] else "") if c)
    return (f'<!doctype html><html><head><meta charset="utf-8">{fonts}<style>{base_css(project, size)}'
            f':root{{--head:{heading};--body:{body_font}}}</style></head>'
            f'<body class="{classes}">{"" if clear else ambient(seconds)}{body}</body></html>')


def card_html(project: Project, scene: dict) -> str:
    card = scene["card"]
    return document(project, BUILDERS[card["template"]](project, card, scene["seconds"]), scene["seconds"])


def caption_html(project: Project, text: str) -> str:
    body = ('<div style="position:absolute;left:0;right:0;bottom:7%;display:flex;justify-content:center">'
            '<div style="max-width:80%;padding:1rem 2.2rem;border-radius:1rem;background:rgba(0,0,0,.5);'
            f'color:var(--text);font:500 1.9rem/1.35 var(--body);text-align:center">{esc(text)}</div></div>')
    return document(project, body, 1, clear=True)


TEMPLATE_VERSION = digest(pathlib.Path(__file__).read_bytes())


def card_key(project: Project, scene: dict) -> str:
    card = scene["card"]
    image = project.path(card["image"]) if card.get("image") else None
    logo = project.path(project.brand["logo"]) if project.brand.get("logo") else None
    return digest("card", TEMPLATE_VERSION, card, scene["seconds"], project.brand, project.size, image, logo)


def render(project: Project, only: list[str] | None = None, force: bool = False, posters: bool = False) -> list[str]:
    """Render card scenes to renders/cards/<id>.mp4 (+ .png poster) and captions to renders/captions/<id>.png.
    With posters=True only the final-frame PNGs are made: a quick look at the branding."""
    from playwright.sync_api import sync_playwright

    story = project.story()
    width, height = project.size
    done = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        for scene in story["scenes"]:
            if only and scene["id"] not in only:
                continue
            if scene.get("caption"):
                target = project.out("renders", "captions", f"{scene['id']}.png")
                key = digest("caption", TEMPLATE_VERSION, scene["caption"], project.brand, project.size)
                if force or not project.fresh(target, key):
                    page.set_content(caption_html(project, scene["caption"]), wait_until="networkidle")
                    page.evaluate("document.fonts.ready.then(() => true)")
                    page.screenshot(path=str(target), omit_background=True)
                    project.stamp(target, key)
                    print(f"caption {scene['id']}", flush=True)
            if scene["kind"] != "card":
                continue
            target = project.out("renders", "cards", f"{scene['id']}.mp4")
            key = card_key(project, scene)
            if posters:
                page.set_content(card_html(project, scene), wait_until="networkidle")
                page.evaluate("document.fonts.ready.then(() => true)")
                page.evaluate(f"document.getAnimations().forEach(a => {{ a.pause(); a.currentTime = {scene['seconds'] * 1000 - 1} }})")
                page.screenshot(path=str(target.with_suffix(".png")))
                done.append(scene["id"])
                print(f"poster {scene['id']} ({scene['card']['template']})", flush=True)
                continue
            if not force and project.fresh(target, key):
                print(f"card {scene['id']}: up to date", flush=True)
                continue
            page.set_content(card_html(project, scene), wait_until="networkidle")
            page.evaluate("document.fonts.ready.then(() => true)")
            page.evaluate("document.getAnimations().forEach(a => a.pause())")
            encoder = subprocess.Popen(
                [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS),
                 "-c:v", "mjpeg", "-i", "-", "-vf", "scale=out_range=tv,format=yuv420p", "-c:v", "libx264",
                 "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-color_range", "tv", str(target)],
                stdin=subprocess.PIPE)
            frames = round(scene["seconds"] * FPS)
            for frame in range(frames):
                page.evaluate(f"document.getAnimations().forEach(a => a.currentTime = {frame * 1000 / FPS})")
                encoder.stdin.write(page.screenshot(type="jpeg", quality=92))
            encoder.stdin.close()
            if encoder.wait():
                raise RuntimeError(f"ffmpeg could not encode card {scene['id']}")
            page.screenshot(path=str(target.with_suffix(".png")))
            project.stamp(target, key)
            done.append(scene["id"])
            print(f"card {scene['id']} ({scene['card']['template']}, {scene['seconds']}s)", flush=True)
        browser.close()
    return done
