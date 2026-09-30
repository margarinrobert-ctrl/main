---
name: motion-video
description: Make motion-graphics videos and animations with no video software installed - no After Effects, no ffmpeg, no Node, no Remotion. Renders title cards, animated charts, explainers, logo stings, kinetic type, social clips, looping GIFs and stickers from code, inside Claude's own sandbox (Python + Pillow only) or as a self-contained HTML page that exports a real H.264 MP4 in the viewer's browser. Use whenever the user asks for a video, animation, animated GIF, motion graphic, intro/outro, lower third, animated chart or infographic, or "make this move", even if they don't mention software or say "video" loosely.
---

# Motion video, zero install

Claude's code-execution sandbox has Python 3.11, Pillow and numpy - and **no ffmpeg,
no internet, 1 CPU, 5 GB RAM**. Every popular video skill (Remotion, HyperFrames,
Manim, MoviePy, the ffmpeg skills) needs software that is not there. This skill
ships its own renderer and its own container writers so the whole pipeline is code.

Two routes. Pick by where the video is going:

| The user wants | Route | Output |
| --- | --- | --- |
| A GIF for Slack/Discord/README/email | **A** Python | `.gif` (<= 640 px wide, <= 10 s) |
| Small, high-quality loop for web/chat | **A** Python | `.webp` (24-bit, 5-10x smaller than GIF) |
| Sticker / overlay with transparency | **A** Python | `.webp` or `.apng`, `transparent=True` |
| A file for an editor, YouTube, Keynote, QuickTime | **A** Python | `.mov` (Photo-JPEG) |
| A file for Windows' built-in player | **A** Python | `.avi` (Motion-JPEG) |
| **An .mp4** (social upload, PowerPoint, phones) | **B** browser | `.mp4` H.264, exported by the user's browser |
| Running locally with ffmpeg on PATH | **A** Python | `.mp4` H.264 directly |

Be straight with the user about the one real limit: **the sandbox cannot encode
H.264**, so an `.mp4` comes from route B (one click in Chrome, Edge or Safari) or from
a machine with ffmpeg. `render("x.mp4")` without ffmpeg writes `x.mov` and says so. Do
not claim you produced an MP4 when you produced a MOV.

No audio in either route. If they need sound, say so and suggest adding it in any
editor (the `.mov` imports everywhere).

## Workflow

1. **Brief** - pin down: message, duration, aspect (16:9 1920x1080, 9:16 1080x1920,
   1:1 1080x1080), destination (picks the format above), brand colours/fonts. Ask
   only what you can't sensibly default; default to 16:9, 6-10 s, 30 fps.
2. **Storyboard as a timeline** - write the beats as a dict of seconds *before*
   writing drawing code. Every animation reads its times from it.
   ```python
   T = dict(title_in=0.2, sub_in=0.55, chart_in=1.0, line_in=2.3,
            hold_until=4.9, out=5.0, out_end=5.6)
   ```
3. **Write `scene(f, t)`** - a pure function of time. Same `t` -> same frame. Use
   `random.Random(seed)` created once at module level, `wiggle()`, never
   `time.time()` or unseeded randomness. Purity is what lets frames be cached,
   renders resume, and the browser export run faster than real time.
4. **Preview cheap, then LOOK** - render small first and inspect the contact sheet:
   ```python
   render(scene, "preview.mov", duration=D, fps=12, size=(640, 360),
          design=(1920, 1080), ss=1)
   contact_sheet("preview.mov")   # PNG grid of 12 frames with indices
   motion_report("preview.mov")   # still spans + sudden jumps
   ```
   View the PNG (Read it in Claude Code; display it in claude.ai). Check: is
   anything visible before its entrance? Does everything leave on the exit? Is
   text inside the frame and readable at the final size? Then fix and re-preview.
5. **Final render** at full size. For anything over ~40 s of compute use the cache:
   ```python
   out = render(scene, "final.mov", duration=D, fps=30, size=(1920, 1080),
                cache="frames_final", time_budget=100)
   # returns None if it stopped on the budget -> run the SAME call again
   ```
6. **Deliver** - save to the outputs location the environment gives you
   (`/mnt/user-data/outputs/` in claude.ai), name the format, and say how to play
   it (`.mov` -> QuickTime/VLC/any editor; `.avi` -> Windows player/VLC).

## Route A - the Python engine

`scripts/motion.py` (copy it next to your script or `sys.path.insert` its folder).
Read `examples/title_card.py` first - it is the reference for structure. Read
`examples/feature_tour.py` for every primitive and a seamless loop.

```python
from motion import *

W, H = 1920, 1080
def scene(f, t):
    f.gradient("#0b1020", "#1b2346", angle=110)          # cached, cheap
    s = spring(t - 0.2, stiffness=180, damping=20)        # physical settle
    f.text("Launch day", W/2, 480 + (1 - s) * 60, size=120, opacity=min(1, s * 1.4))
    f.rect(W/2, 620, 600 * progress(t, 0.6, 1.2, "out_cubic"), 8,
           fill="#5eead4", radius=4)
render(scene, "launch.mov", duration=4, fps=30, size=(W, H))
```

**Timing helpers** (t in seconds): `progress(t, t0, t1, ease)` -> 0..1;
`tween(t, t0, t1, a, b, ease)` numbers/points/colours; `keys(t, [(t, v), (t, v, ease)])`
keyframes (ease shapes the segment *arriving* at a key); `spring(t - start, stiffness,
damping)`; `stagger(i, start, each)`; `wiggle(t, freq, amp, seed)`; `mix(c1, c2, p)`.
Easings: `linear`, `in/out/in_out_` + `sine quad cubic quart quint expo back`,
`out_elastic`, `out_bounce`.

**Drawing** (design pixels, origin top-left, `(x, y)` = centre unless noted):
`background`, `gradient(c1, c2, angle)`, `vignette(strength)`,
`rect(x, y, w, h, fill, radius, opacity, outline, width, rotation, anchor="center"|"topleft")`,
`circle`, `arc(cx, cy, r, start_deg, end_deg, color, width)` (progress ring:
`-90 -> -90 + 360*p`), `polygon`, `star`, `line(pts, color, width, progress=p)`
(draw-on), `text(s, x, y, size, color, font="bold"|"regular"|"mono"|"serif"|path,
anchor="mm", tracking, reveal=p, rotation, scale)`, `image(path_or_PIL, x, y, width,
rotation, scale, opacity)`, `grain(amount, seed=frame)`.
Groups: `L = f.layer()` draw into `L`, then `f.composite(L, opacity, blur)`,
`f.shadow(L, offset, blur, strength, opacity=group_fade)` or `f.glow(L, color, radius)`.

**render()** options: `size`, `design=(w, h)` (draw once at 1920x1080, export any
size), `fps`, `ss` (supersampling, 2 = smooth edges), `quality`, `transparent`,
`cache`, `time_budget`, `loop`, `gif_colors`, `lossless` (WebP).

**Budget** (measured, 1 CPU, typical scene with gradient + shadow layer):

| output | ss | ms/frame | 10 s @ 30 fps |
| --- | --- | --- | --- |
| 640x360 | 2 | ~60 | ~20 s |
| 1280x720 | 2 | ~230 | ~70 s |
| 1920x1080 | 1 | ~120 | ~40 s |
| 1920x1080 | 2 | ~500 | ~2.5 min -> use `cache` + `time_budget` |

The first frame is slower (fonts, cached gradients). `render` prints ms/frame after
5 frames - if the projection exceeds the tool-call limit, stop and switch to
`cache=` + `time_budget=`. Blur is the expensive primitive; one shadow layer per frame
is fine, a dozen is not. Pre-render static elements into a PIL image once and place
it with `f.image()`.

**Format rules**: video sizes must be even. GIF delays are centiseconds, so use 10,
20, 25 or 50 fps for exact timing; GIF has 256 colours, so gradients band - prefer
WebP unless the destination demands GIF. GIF/WebP hold all frames in RAM: keep them
<= 640 px and <= 15 s. MOV/AVI stream JPEGs and are fine at 1080p for minutes.

## Route B - the browser MP4 page

`templates/browser_video.html` is a complete player + exporter in one file, no
CDN. Copy it and replace only the block between `SCENE START` and `SCENE END`:
set `VIDEO = {width, height, fps, duration}` and write `draw(ctx, t)` with the
Canvas 2D API. The same helpers exist in JS (`progress`, `tween`, `keys`,
`spring`, `stagger`, `EASE`, `seeded(seed)` for deterministic randomness,
`rrect` for rounded rectangles). Keep `draw` pure - no `Date.now()`, no
`Math.random()`.

Then either publish it as an artifact / HTML file, or send the file. The user opens
it, previews with play/scrub, clicks **Export MP4**: WebCodecs encodes every frame
exactly (faster than real time) and the built-in muxer writes a standard MP4.
Fallbacks are automatic: H.264 (Chrome, Edge, Safari) -> VP9-in-MP4 (browsers
without H.264, e.g. some Linux Chromium builds; plays in Chrome/Firefox/VLC but not
QuickTime) -> real-time WebM via MediaRecorder. It tells the user which one happened.

Use route B also when the user wants to tweak the animation themselves, or when the
scene needs things Pillow does poorly: many soft shadows, blend modes, bezier
paths, gradients inside shapes, real web fonts, 60 fps at 1080p.

## Motion design rules

Short version; `reference/motion_design.md` has the reasoning and a timing table.

- **Ease out** things that arrive, **ease in** things that leave, **in_out** things
  that move on screen. `linear` only for constant motion (tickers, spinners,
  particles, scrolling).
- Entrances 300-600 ms, exits ~70 % of the entrance, element moves 400-800 ms.
  Anything under 150 ms reads as a pop, over 1 s as sluggish.
- **Stagger** groups by 40-100 ms. **One focal point** at a time: the next thing
  starts when the eye has landed on the last.
- **Hold** readable text for 0.3 s per word + 1 s. Hold the final state >= 1 s
  before the exit. Exit everything together with one shared `progress`.
- Springs for physical, playful motion (`damping` 12-16 bouncy, 20-26 crisp).
  `out_back` overshoot sparingly - once per scene reads as polish, everywhere as
  wobble.
- Move by distance you can see in 2-3 frames: a jump of more than ~1/8 of the frame
  width in one frame strobes (there is no motion blur). Slow it, or raise fps.
- Keep text inside the central 90 % (title-safe), >= 36 px at 1080p for body,
  >= 64 px for titles; contrast >= 4.5:1 against what is behind it at every moment.
- Seamless loop: make every value a function of `phase = t / duration` with period
  1, and end on the state you started in.
- Everything drawn needs an entrance *and* an exit - the classic bug is an element
  that is on screen at frame 0 because its opacity ignores its start time.

## Verification before you deliver

- `contact_sheet(out)` and look at it. `motion_report(out)` for dead air
  (`still_spans`) and pops (`jumps`); an entrance that should be smooth must not
  show up as a jump.
- Re-read the file's metadata line the renderer prints: frames, size, fps, MB.
- If you cannot view images in this environment, say you checked numerically only.

## Installing this skill

- **Claude Code**: put the folder in `~/.claude/skills/` (all projects) or
  `.claude/skills/` in a repo.
- **claude.ai / Desktop**: zip the `motion-video` folder, then Settings -> Capabilities
  -> Skills -> Upload skill. Needs code execution enabled.
- **API**: upload the folder with the Skills API and enable the code-execution tool.

`reference/research.md` records why it is built this way: what the existing video
skills require, what the sandbox actually provides, and what was tested.
