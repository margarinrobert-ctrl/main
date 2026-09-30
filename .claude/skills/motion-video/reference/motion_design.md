# Motion design reference

Read this when the brief is more than a single title card, or when a preview
"looks off" and you can't say why. It is the reasoning behind the rules in
SKILL.md.

## Timing table

| What | Duration | Easing |
| --- | --- | --- |
| Small element appears (icon, dot, label) | 200-350 ms | `out_cubic`, or spring d=20 |
| Card / panel enters | 400-600 ms | `out_quint`, or spring s=150 d=22 |
| Headline enters | 500-800 ms | spring s=180 d=20, opacity leads position |
| Element moves on screen | 400-800 ms | `in_out_cubic` |
| Element leaves | 250-450 ms (~70 % of entrance) | `in_cubic` / `in_back` for flair |
| Whole-scene exit | 400-700 ms | `in_out_cubic`, one shared progress |
| Scene-to-scene transition | 500-900 ms | `in_out_quint` / `in_out_expo` |
| Stagger between siblings | 40-100 ms | - |
| Bar/number grows to value | 600-1200 ms | `out_expo` or spring d=14 (slight overshoot) |
| Line / path draws on | 700-1500 ms | `in_out_cubic` |
| Text on screen, readable | 0.3 s per word + 1 s | - |
| Final state held before the exit | >= 1 s | - |

At 30 fps, 100 ms is 3 frames. Anything shorter than ~5 frames reads as a cut.

## Why these easings

Objects in the world don't start or stop instantly. Something arriving
decelerates into place (ease *out*: fast start, slow end). Something leaving
accelerates away (ease *in*). Something travelling between two on-screen
positions does both (ease *in_out*). `linear` motion looks mechanical, which is
right only for things that *are* mechanical or continuous: a ticker, a spinner,
drifting particles, a scrolling background.

Exponential and quintic curves (`out_expo`, `out_quint`) feel more "designed"
than cubic because most of the travel happens in the first third; use them for
UI-style motion. Sine is the gentlest - good for ambient loops and breathing.

## Springs

`spring(t - start, stiffness, damping)` is a damped harmonic oscillator, so its
duration comes from the physics, not from a number you pick: with the defaults
(170, 26) it settles in ~0.6 s.

- damping 12-16: bouncy, overshoots visibly - playful brands, pops, stickers
- damping 18-22: one small overshoot - most titles and cards
- damping >= 26: no visible overshoot - calm, corporate
- stiffness up = faster. 120 lazy, 180 brisk, 300 snappy.

Opacity should not overshoot: use `min(1, s * 1.4)` so it reaches 1 early while
position is still settling. Scale overshoot above ~1.15 looks broken.

## The twelve principles, the parts that matter for graphics

- **Timing and spacing**: the easing *is* the spacing of positions between frames.
- **Slow in / slow out**: the easing rules above.
- **Anticipation**: a tiny move the opposite way before a big one (`in_back` on the
  way out, or a 3-5 % dip before a scale-up) tells the eye where to look.
- **Follow-through and overlapping action**: parts of a group arrive at slightly
  different times (stagger), and the last one settles a beat later (spring).
- **Staging**: one focal point at a time. Start the next element when the viewer
  has read the last one, not when the last one finished moving.
- **Arcs**: movement along a gentle curve reads as natural; along a straight line
  as mechanical. For a flying element, tween x and y with different easings.
- **Exaggeration**: small, and once. A single overshoot is polish; everything
  wobbling is noise.
- **Secondary action**: ambient motion (drift, shimmer, parallax background,
  `wiggle`) keeps a hold alive without stealing focus - keep its amplitude small.

## Composition

- Title-safe area: central 90 % of each dimension; keep all text inside it.
  Action-safe: 95 %.
- 16:9 1920x1080 for YouTube/presentations; 9:16 1080x1920 for Reels/TikTok/
  Shorts (keep text out of the bottom ~20 % and the top ~12 %, where the
  platforms draw UI); 1:1 1080x1080 for feeds.
- Minimum text size at 1080p: 36 px body, 64 px+ headings. For a 480 px GIF,
  scale proportionally: at least 16 px.
- Contrast >= 4.5:1 at every moment of the animation, not only at rest - check
  the mid-fade frames on the contact sheet.
- Limit to one typeface in two weights and a palette of background, ink, muted
  ink and one accent. The accent marks the focal point.

## Structures that work

- **Title card** (4-6 s): background in -> headline -> subhead -> hold -> exit.
- **Stat reveal** (5-8 s): label -> number counts up (`tween` the value, format
  it) -> context line -> hold.
- **Bar/line chart build** (6-10 s): axes/card -> bars grow with stagger ->
  line draws on -> highlight the one bar that matters -> hold.
- **List / steps** (2 s per item): items stagger in one at a time, the current
  one in the accent colour, previous ones dim to 50 %.
- **Logo sting** (2-3 s): shapes assemble with springs -> wordmark reveals
  (`reveal=` or a rect mask sliding off) -> brief hold. Loop-friendly.
- **Lower third** (5 s, transparent WebP/APNG for overlay): bar slides in
  `out_quint`, name then role stagger in, hold, reverse.
- **Kinetic type**: one to three words per beat, 0.5-0.9 s each, each beat with
  a different entrance direction; keep the reading rhythm steady.

## Counting numbers

```python
v = tween(t, 1.0, 2.2, 0, 1284, "out_expo")
f.text(f"{v:,.0f}", W/2, H/2, size=140, font="mono")  # mono: width won't jitter
```

Use a monospaced font (or fixed-width digits) for counters, otherwise the
number's width changes every frame and the text shimmies.
