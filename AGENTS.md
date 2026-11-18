# AGENTS.md: how an LLM agent makes a film with this repo

You are helping a person turn a brief and a brand into a finished trailer with the `mvg` CLI. They run it on **their
own Google Cloud project**; every generation is billed to them. Your job: ask the right questions, write a good story,
make the cheap assets first, get a human approval, and only then spend on video.

Human guide with the same flow: https://kirankumarduddu.github.io/multimodal-video-generator-gemini/guide.html

## The one rule: cards first, then video

```
brief.yaml + brand.yaml ──► story.json (any LLM)
        │
        ▼  Stage 1: cheap, exact, reviewable
   mvg cards --posters   brand check in seconds (stills of every card)
   mvg cards             every word, number and logo, rendered from HTML in the brand's styling
   mvg cast              one reference still per fictional person (Gemini image model)
   mvg keyframes         the first frame of every live-action shot, from the cast stills
   mvg clips --animatic  free preview clips (slow push-in on each keyframe)
   mvg voice --placeholder / mvg music --placeholder, then mvg assemble  → a timed draft film, no video spend
        │
        ▼  Gate: a human looks at build/review.html and runs `mvg approve <ids>` (or --all)
        │
        ▼  Stage 2: billed
   mvg clips             Veo or Gemini Omni animates each APPROVED keyframe
   mvg voice             Gemini TTS, one WAV per line
   mvg music             Lyria, one take per score segment
   mvg assemble          ffmpeg: crossfades, captions, voice, ducked score, -16 LUFS; master + web + phone
```

Why: cards are deterministic and brand-exact, keyframes are cheap and show the shot before it is animated, and video
is the expensive step. An approval in `approvals.json` is tied to a hash of the shot's prompt, keyframe and video
model, so **any change to a shot needs a new approval**. Never approve on the person's behalf unless they explicitly
tell you to (`mvg approve --all` is their decision, not yours).

## Before writing a story: ask these questions

Ask only what `brief.yaml` and `brand.yaml` don't already answer. Write the answers into those files.

**Brief** (`brief.yaml`)
1. Purpose: launch trailer, teaser, explainer, recruiting film, customer story, event recap?
2. Audience and where it plays (social feed, website hero, event screen, sales deck)?
3. Length (15/30/60/90/120 s) and shape: 16:9 or 9:16?
4. The one sentence they should remember (key message)?
5. The opening situation and the turn (story angle)?
6. The beats, in order (3 to 6)?
7. Proof points: facts and numbers they can stand behind. **The story may use only these.**
8. Quotes: only real, approved quotes, with who said them.
9. Call to action?
10. Characters (fictional roles), settings, mood, music mood?
11. Screenshots or product images for screen/feature cards (they must own the rights)?
12. Must include / must avoid?

**Brand** (`brand.yaml`)
1. Name and tagline?
2. Six colors: background, surface, primary, accent, text, muted (hex)?
3. Heading and body fonts (Google Fonts names, or font files in `brand/`)?
4. Logo file (transparent PNG/SVG in `brand/`), if any?
5. Look: the color grade and camera feel applied to every generated shot?
6. Narrator voice (a Gemini TTS prebuilt voice, e.g. Sulafat warm, Charon informative, Puck upbeat) and direction?
7. Brand rules (things never to show or say)?

**Setup** (`studio.yaml`)
1. Google Cloud project ID? Run `mvg doctor` and fix every FAIL before spending anything.
2. Which LLM writes the story: Gemini on Vertex, an OpenAI-compatible endpoint, Anthropic, or you (manual)?
3. Video model: Veo (`veo-3.1-generate-001`, regional, default) or Gemini Omni (Interactions API, global)?

## Writing the story

- Get the exact prompt with `mvg story prompt` (writes `build/story_prompt.md`); it contains the brief, the brand
  and the JSON Schema (`mvgen/schema/story.schema.json`). If you are the writer, follow it and return only JSON.
- Or let the configured LLM write it: `mvg story write` (validates, asks for one repair round).
- Always finish with `mvg story check` and fix every error. Warnings (voice overruns, length off by >10%, no
  endcard) should be fixed unless the person accepts them.
- Words, numbers, names and logos go on **cards** only. Live-action shots describe people, places and action, with
  no readable text, logos, UIs or real people. Screens in shot show only a soft glow.
- Invented, fictional people only. Never describe a real or famous person, even if asked; say why.
- Voice reads at about 2.6 words per second. `at + words / 2.6 + 0.4 <= seconds` for each line.
- Scenes crossfade 0.4 s; total = sum(seconds) − 0.4 × (scenes − 1).
- Veo makes 1080p only as 8 s clips; use `seconds` and `trim_start` to pick the part you want on the timeline.
- Music: 1 to 4 segments, each a full instrumental brief (length, BPM, instruments, arc with timestamps, no vocals);
  the first starts at the first scene; a take is at most about 3 minutes.

## Card templates (`card.template`)

| template | fields | use |
| --- | --- | --- |
| `title` | eyebrow, headline, sub | opening or chapter title (shows the logo) |
| `statement` | lines[] | kinetic type, one line at a time; the last line is highlighted |
| `feature` | eyebrow, headline, sub, image? | one capability; with an image it shows it on a tilted panel |
| `list` | headline, items[] (≤6) | benefits |
| `stat` | headline, stats[{value,label}] (≤4) | numbers from the brief's proof points only |
| `quote` | quote, by | approved quotes only |
| `flow` | headline, items[] | how it works, as connected steps |
| `screen` | headline, image | a product screenshot in a frame |
| `endcard` | headline (tagline), sub, cta | always last; shows the logo |

`caption` on any scene adds a lower caption.

## Working on the code

- Layout: `mvgen/cli.py` (commands) → `spec.py` (schema, checks, timing) · `cards.py` (HTML templates, Playwright
  capture) · `imagery.py` (prompts, cast, keyframes) · `review.py` (review page, approvals) · `clips.py` (Veo, Omni,
  animatic) · `audio.py` (TTS, Lyria) · `assemble.py` (ffmpeg) · `story.py` (LLM providers) · `doctor.py` (checks).
- Every step is idempotent: outputs carry a `.stamp` with a hash of their inputs and are skipped when fresh;
  `--force` regenerates; ids limit a step to some scenes.
- The schema and the story prompt exist twice, in `mvgen/` and `docs/assets/` (the Pages guide loads them). Edit the
  `mvgen/` copy and copy it over; `tests/test_contracts.py` fails if they differ.
- Adding a card template: a `t_<name>` builder in `cards.py`, register it in `BUILDERS`, add it to the schema enum
  (both copies), the table above, the story prompt and a test.
- Adding a story provider: a function in `story.py` and a branch in `ask()` and in `doctor.py`'s `story_llm()`.
- Tests: `python -m pytest -q` (offline; the pipeline test needs `playwright install chromium`). Never call paid
  APIs in tests.
- Never commit API keys, `.env` files, access tokens, generated media or anyone's project ID.
