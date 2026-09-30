"""Example: a 6-second product title card with a bar chart build.

    python examples/title_card.py out.mov        # or .gif / .webp / .avi / .mp4

Shows the patterns the skill asks for: a timeline written as data, staggered
entrances, overshoot on arrival, a hold, a coordinated exit, a layer with a
shadow, and a draw-on line.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from motion import (Frame, contact_sheet, keys, motion_report, progress,  # noqa: E402
                    render, spring, stagger)

W, H = 1280, 720
BG1, BG2 = "#0b1020", "#1b2346"
INK, MUTED, ACCENT = "#f5f7ff", "#8b93b8", "#5eead4"
BARS = [0.35, 0.52, 0.47, 0.70, 0.88]
DUR = 6.0

# Timeline, in seconds. Edit here, not inside the drawing code.
T = dict(title_in=0.2, sub_in=0.55, card_in=1.0, bars_in=1.35, line_in=2.3,
         hold_until=4.9, out=5.0, out_end=5.6)


def scene(f: Frame, t: float):
    f.gradient(BG1, BG2, angle=110)

    # Everything leaves together: one exit progress drives fade + drift.
    ex = progress(t, T["out"], T["out_end"], "in_out_cubic")
    fade = 1 - ex
    lift = -40 * ex

    # Title: rises and settles on a spring; subtitle follows 0.35s later.
    s = spring(t - T["title_in"], stiffness=180, damping=20)
    f.text("Q3 in motion", W / 2, 150 + (1 - s) * 60 + lift, size=76,
           color=INK, opacity=min(1, s * 1.4) * fade, tracking=1)
    f.text("Revenue by month, zero-install render", W / 2, 222 + lift,
           size=28, font="regular", color=MUTED,
           opacity=progress(t, T["sub_in"], T["sub_in"] + 0.5) * fade)

    # Card: on its own layer so it can cast a soft shadow.
    c = spring(t - T["card_in"], stiffness=150, damping=22)
    card = f.layer()
    cw, ch = 760, 330
    cy = 470 + (1 - c) * 80 + lift
    card.rect(W / 2, cy, cw * (0.92 + 0.08 * c), ch, fill="#ffffff",
              radius=22, opacity=0.07)
    card.rect(W / 2, cy, cw * (0.92 + 0.08 * c), ch, outline="#ffffff",
              width=1.5, radius=22, opacity=0.14)
    f.shadow(card, offset=(0, 18), blur=24, strength=0.35,
             opacity=min(1.0, c * 1.5) * fade)

    # Bars: staggered, each overshoots slightly and settles.
    base_y = cy + ch / 2 - 40
    bw, gap = 90, 38
    x0 = W / 2 - (len(BARS) * bw + (len(BARS) - 1) * gap) / 2 + bw / 2
    tops = []
    for i, v in enumerate(BARS):
        g = spring(t - stagger(i, T["bars_in"], 0.09), stiffness=140, damping=14)
        h = v * 230 * g
        x = x0 + i * (bw + gap)
        f.rect(x, base_y - h / 2, bw, h, fill=ACCENT if i == 4 else "#7c8cff",
               radius=10, opacity=fade)
        tops.append((x, base_y - v * 230 - 22))
        f.text(["Jan", "Feb", "Mar", "Apr", "May"][i], x, base_y + 20, size=18,
               font="regular", color=MUTED, opacity=min(1, g) * fade)

    # Trend line draws on across the bar tops, then a value pops in.
    p = progress(t, T["line_in"], T["line_in"] + 1.1, "in_out_cubic")
    f.line(tops, "#ffffff", width=3, progress=p, opacity=0.9 * fade)
    pop = keys(t, [(T["line_in"] + 1.0, 0.0), (T["line_in"] + 1.25, 1.15, "out_cubic"),
                   (T["line_in"] + 1.4, 1.0, "in_out_sine")])
    if pop > 0:
        f.circle(*tops[-1], 9 * pop, ACCENT, opacity=fade)
        f.text("+88%", tops[-1][0] + 58, tops[-1][1] - 4, size=26, color=ACCENT,
               opacity=min(1, pop) * fade, scale=max(0.01, pop))

    f.vignette(0.35)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "title_card.mov"
    small = out.endswith((".gif", ".webp", ".png"))
    written = render(scene, out, duration=DUR, fps=25 if small else 30,
                     size=(640, 360) if small else (W, H), design=(W, H))
    out = written or out
    print(contact_sheet(out))
    motion_report(out)
