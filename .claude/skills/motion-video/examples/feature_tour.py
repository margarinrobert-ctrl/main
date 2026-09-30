"""Example: every primitive once, as a 4-second loop.

    python examples/feature_tour.py tour.webp
    python examples/feature_tour.py sticker.webp --transparent

Covers: keyframe tracks, typewriter text, rotated text, stars, a progress arc,
glow, particles from a seeded RNG, wiggle, and a seamless loop (every value
is a function of the loop phase, so frame 0 follows the last frame cleanly).
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from motion import (Frame, keys, mix, progress, render, spring,  # noqa: E402
                    tween, wiggle)

W, H, DUR = 960, 540, 4.0
TRANSPARENT = "--transparent" in sys.argv

# Particles: positions fixed once from a seeded RNG, animated by phase.
rng = random.Random(7)
PARTICLES = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(2, 5),
              rng.uniform(0, 1)) for _ in range(40)]


def scene(f: Frame, t: float):
    phase = t / DUR  # 0 -> 1 over the loop
    if not TRANSPARENT:
        f.gradient(mix("#1e1b4b", "#312e81", 0.5 + 0.5 * math.sin(phase * 2 * math.pi)),
                   "#0f172a", angle=100)
        for x, y, r, off in PARTICLES:  # drift upward, wrap around
            yy = (y - (phase + off) * H) % H
            f.circle(x + wiggle(t, 0.3, 6, seed=int(off * 100)), yy, r, "#a5b4fc",
                     opacity=0.25)

    # Keyframed badge: in, hold, pulse, out - and back to the start state.
    s = keys(t, [(0.0, 0.0), (0.5, 1.0, "out_back"), (2.6, 1.0),
                 (2.8, 1.12, "out_quad"), (3.0, 1.0, "in_out_sine"),
                 (3.6, 1.0), (3.95, 0.0, "in_back")])
    glow = f.layer()
    glow.star(W / 2, H / 2 - 40, 70 * s, 30 * s, points=5, fill="#fde047",
              rotation=-90 + 360 * progress(t, 0, DUR, "in_out_cubic"))
    f.glow(glow, color="#facc15", radius=22, strength=0.9)

    # Progress arc drawn around the star.
    p = progress(t, 0.3, 3.3, "in_out_cubic")
    f.arc(W / 2, H / 2 - 40, 120, -90, -90 + 360 * p, "#38bdf8", width=10,
          opacity=1 - progress(t, 3.4, 3.9))

    # Typewriter, then rotated tag that springs in.
    f.text("rendered with Pillow only", W / 2, H - 120, size=34, font="mono",
           color="#e0e7ff", reveal=progress(t, 0.6, 2.0),
           opacity=1 - progress(t, 3.4, 3.9))
    k = spring(t - 1.6, 200, 14) * (1 - progress(t, 3.4, 3.9))
    if k > 0.01:
        f.rect(W / 2 + 230, H / 2 - 140, 150, 48, fill="#f43f5e", radius=24,
               rotation=-12 * k, opacity=min(1, k))
        f.text("NEW", W / 2 + 230, H / 2 - 140, size=26, color="#ffffff",
               rotation=-12 * k, scale=max(0.05, k))
    f.line([(W / 2 - 160, H - 80), (W / 2 + 160, H - 80)], "#818cf8", width=4,
           progress=tween(t, 2.0, 2.8, 0, 1, "out_cubic"),
           opacity=1 - progress(t, 3.4, 3.9))


if __name__ == "__main__":
    out = next((a for a in sys.argv[1:] if not a.startswith("--")), "tour.webp")
    render(scene, out, duration=DUR, fps=25, size=(W, H),
           transparent=TRANSPARENT)
