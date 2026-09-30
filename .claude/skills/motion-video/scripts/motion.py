"""motion.py - a zero-install motion-graphics engine for Claude's sandbox.

Needs only Pillow and numpy, both pre-installed in Claude's code-execution
container (which has no ffmpeg and no internet). Writes:

    .gif  .webp  .apng   animated images, via Pillow
    .mov                 Photo-JPEG QuickTime, container written in pure Python
    .avi                 Motion-JPEG AVI, container written in pure Python
    .mp4                 H.264 - ONLY when an ffmpeg binary exists (local Claude
                         Code); otherwise it falls back to .mov and says so

Usage:

    from motion import *

    def scene(f, t):                      # f: Frame, t: seconds
        f.background("#0f172a")
        x = tween(t, 0.2, 1.0, 200, 1080, "out_back")
        f.circle(x, 360, 60, "#38bdf8")
        f.text("Hello", 640, 560, size=72, color="#f8fafc",
               opacity=tween(t, 0.6, 1.2, 0, 1))

    render(scene, "hello.mov", duration=3, fps=30, size=(1280, 720))

Coordinates are output pixels, origin top-left. Every drawing call is
supersampled (ss=2 by default) and downsampled with a Lanczos filter, which is
what makes edges smooth without a vector renderer.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import struct
import subprocess
import sys
import time
from contextlib import contextmanager

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

__all__ = [
    "EASE", "ease", "clamp01", "lerp", "mix", "tween", "keys", "progress",
    "stagger", "spring", "wiggle", "rgb", "Frame", "render", "contact_sheet",
    "motion_report", "find_font",
]

# --------------------------------------------------------------------------
# Easing. t in [0, 1] -> [0, 1] (back/elastic overshoot on purpose).
# --------------------------------------------------------------------------


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def _bounce_out(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def _in_out(f):
    return lambda t: f(2 * t) / 2 if t < 0.5 else 1 - f(2 - 2 * t) / 2


_C1 = 1.70158
_C3 = _C1 + 1

EASE = {
    "linear": lambda t: t,
    "in_sine": lambda t: 1 - math.cos(t * math.pi / 2),
    "out_sine": lambda t: math.sin(t * math.pi / 2),
    "in_out_sine": lambda t: -(math.cos(math.pi * t) - 1) / 2,
    "in_quad": lambda t: t * t,
    "out_quad": lambda t: 1 - (1 - t) ** 2,
    "in_cubic": lambda t: t ** 3,
    "out_cubic": lambda t: 1 - (1 - t) ** 3,
    "in_quart": lambda t: t ** 4,
    "out_quart": lambda t: 1 - (1 - t) ** 4,
    "in_quint": lambda t: t ** 5,
    "out_quint": lambda t: 1 - (1 - t) ** 5,
    "in_expo": lambda t: 0.0 if t == 0 else 2 ** (10 * t - 10),
    "out_expo": lambda t: 1.0 if t == 1 else 1 - 2 ** (-10 * t),
    "in_back": lambda t: _C3 * t ** 3 - _C1 * t * t,
    "out_back": lambda t: 1 + _C3 * (t - 1) ** 3 + _C1 * (t - 1) ** 2,
    "out_elastic": lambda t: t if t in (0, 1) else
    2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1,
    "out_bounce": _bounce_out,
}
EASE["in_out_quad"] = _in_out(EASE["in_quad"])
EASE["in_out_cubic"] = _in_out(EASE["in_cubic"])
EASE["in_out_quart"] = _in_out(EASE["in_quart"])
EASE["in_out_quint"] = _in_out(EASE["in_quint"])
EASE["in_out_expo"] = _in_out(EASE["in_expo"])
EASE["in_out_back"] = _in_out(EASE["in_back"])
# Aliases people reach for.
EASE["ease"] = EASE["in_out_cubic"]
EASE["ease_in"] = EASE["in_cubic"]
EASE["ease_out"] = EASE["out_cubic"]
EASE["ease_in_out"] = EASE["in_out_cubic"]


def ease(name_or_fn, t):
    fn = EASE[name_or_fn] if isinstance(name_or_fn, str) else name_or_fn
    return fn(clamp01(t))


def spring(t, stiffness=170.0, damping=26.0, mass=1.0):
    """Damped spring from 0 to 1, t in SECONDS since the spring started.

    Physical, not normalised: it settles when it settles (about 0.6s with
    the defaults). Lower damping -> more overshoot and wobble.
    """
    if t <= 0:
        return 0.0
    w0 = math.sqrt(stiffness / mass)
    zeta = damping / (2 * math.sqrt(stiffness * mass))
    if zeta < 1:
        wd = w0 * math.sqrt(1 - zeta * zeta)
        return 1 - math.exp(-zeta * w0 * t) * (
            math.cos(wd * t) + zeta * w0 / wd * math.sin(wd * t))
    return 1 - math.exp(-w0 * t) * (1 + w0 * t)  # critically damped


def lerp(a, b, t):
    """Interpolate numbers, or tuples/lists of numbers (points, colours)."""
    if isinstance(a, (tuple, list)):
        return type(a)(lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t


def rgb(c):
    """'#rgb' / '#rrggbb' / '#rrggbbaa' / (r,g,b[,a]) -> (r,g,b,a) ints."""
    if isinstance(c, str):
        h = c.lstrip("#")
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        v = tuple(int(h[i:i + 2], 16) for i in range(0, len(h), 2))
        return v if len(v) == 4 else v + (255,)
    c = tuple(int(round(x)) for x in c)
    return c if len(c) == 4 else c + (255,)


def mix(c1, c2, t):
    """Blend two colours."""
    return tuple(int(round(v)) for v in lerp(rgb(c1), rgb(c2), clamp01(t)))


def progress(t, t0, t1, easing="linear"):
    """Eased 0..1 progress of the window [t0, t1] at time t."""
    if t1 <= t0:
        return 1.0 if t >= t1 else 0.0
    return ease(easing, (t - t0) / (t1 - t0))


def tween(t, t0, t1, a, b, easing="out_cubic"):
    """Value moving from a (at t0) to b (at t1), held outside the window."""
    return lerp(a, b, progress(t, t0, t1, easing))


def keys(t, frames):
    """Keyframe track: [(time, value), (time, value, easing), ...].

    The easing on a key shapes the segment ARRIVING at that key.
    """
    if t <= frames[0][0]:
        return frames[0][1]
    for k0, k1 in zip(frames, frames[1:]):
        if t <= k1[0]:
            e = k1[2] if len(k1) > 2 else "in_out_cubic"
            return tween(t, k0[0], k1[0], k0[1], k1[1], e)
    return frames[-1][1]


def stagger(i, start, each=0.06):
    """Start time of item i in a staggered group."""
    return start + i * each


def wiggle(t, freq=2.0, amp=1.0, seed=0):
    """Smooth deterministic noise in [-amp, amp] - handheld drift, shimmer."""
    s = seed * 12.9898
    return amp * (0.5 * math.sin(t * freq * 2 * math.pi + s)
                  + 0.3 * math.sin(t * freq * 3.7 * math.pi + s * 1.7)
                  + 0.2 * math.sin(t * freq * 7.3 * math.pi + s * 2.3))


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

_FONT_DIRS = [
    "/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
    "/Library/Fonts", "/System/Library/Fonts", "C:/Windows/Fonts",
]
_FONT_PREFS = {
    "regular": ["Inter-Regular", "DejaVuSans", "LiberationSans-Regular",
                "NotoSans-Regular", "FreeSans", "Arial", "Helvetica"],
    "bold": ["Inter-Bold", "DejaVuSans-Bold", "LiberationSans-Bold",
             "NotoSans-Bold", "FreeSansBold", "Arial Bold", "arialbd"],
    "mono": ["DejaVuSansMono", "LiberationMono-Regular", "NotoSansMono-Regular",
             "FreeMono", "Menlo", "consola"],
    "serif": ["DejaVuSerif", "LiberationSerif-Regular", "NotoSerif-Regular",
              "FreeSerif", "Georgia", "Times New Roman"],
}
_font_index = None
_font_cache = {}


def _font_dirs():
    dirs = list(_FONT_DIRS)
    try:  # matplotlib ships DejaVu Sans/Serif/Mono and is in Claude's sandbox
        import importlib.util
        spec = importlib.util.find_spec("matplotlib")
        if spec and spec.submodule_search_locations:
            dirs.append(os.path.join(list(spec.submodule_search_locations)[0],
                                     "mpl-data", "fonts", "ttf"))
    except Exception:
        pass
    return dirs


def _scan_fonts():
    global _font_index
    if _font_index is None:
        _font_index = {}
        for d in _font_dirs():
            for root, _, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith((".ttf", ".otf", ".ttc")):
                        _font_index.setdefault(os.path.splitext(fn)[0].lower(),
                                               os.path.join(root, fn))
    return _font_index


def find_font(style="bold"):
    """Path of a font for 'regular' | 'bold' | 'mono' | 'serif', or a path."""
    if style and os.path.isfile(style):
        return style
    idx = _scan_fonts()
    for name in _FONT_PREFS.get(style, [style]):
        p = idx.get(name.lower())
        if p:
            return p
    return None  # Pillow's built-in scalable font is used instead


def _font(style, px):
    key = (style, int(px))
    if key not in _font_cache:
        path = find_font(style)
        if path:
            _font_cache[key] = ImageFont.truetype(path, max(1, int(px)))
        else:
            try:
                _font_cache[key] = ImageFont.load_default(size=max(1, int(px)))
            except TypeError:  # Pillow < 10.1: fixed-size bitmap font only
                _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


# --------------------------------------------------------------------------
# Frame: the drawing surface handed to a scene function
# --------------------------------------------------------------------------


_CACHE = {}


def _with_opacity(color, opacity):
    r, g, b, a = rgb(color)
    return (r, g, b, int(round(a * clamp01(opacity))))


def _amin(*cols):
    return min([c[3] for c in cols if c] or [255])


class Frame:
    """One frame. Draw in output pixels; it is supersampled internally."""

    def __init__(self, width, height, ss=2, background=None, transparent=False,
                 unit=1.0):
        # w, h: the DESIGN size you draw in. unit: output px per design px.
        self.w, self.h, self.ss, self.unit = width, height, int(ss), unit
        self.k = self.ss * unit
        self.out_size = (int(round(width * unit)), int(round(height * unit)))
        fill = (0, 0, 0, 0) if transparent else rgb(background or "#000000")
        self.img = Image.new("RGBA", (self.out_size[0] * self.ss,
                                      self.out_size[1] * self.ss), fill)
        self._draw = ImageDraw.Draw(self.img)
        self._scratch = None
        self.transparent = transparent

    # -- helpers ----------------------------------------------------------
    def _s(self, v):
        return v * self.k

    def _pts(self, pts):
        return [(x * self.k, y * self.k) for x, y in pts]

    @contextmanager
    def _paint(self, bbox, alpha=255, soft=False):
        """Yield an ImageDraw for one shape and blend it in correctly.

        Pillow REPLACES pixels when it draws a translucent colour onto an
        RGBA image rather than blending, so opaque hard-edged shapes go
        straight to the canvas and anything translucent or anti-aliased
        (text) is drawn alone on a scratch layer, then alpha-composited.
        Drawing a shape and its round caps in one call also stops the caps
        from doubling up the alpha where they overlap the stroke.
        """
        if alpha >= 255 and not soft:
            yield self._draw
            return
        if self._scratch is None:
            self._scratch = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
            self._sdraw = ImageDraw.Draw(self._scratch)
        yield self._sdraw
        W, H = self.img.size
        x0, y0 = max(int(math.floor(bbox[0])) - 2, 0), max(int(math.floor(bbox[1])) - 2, 0)
        x1, y1 = min(int(math.ceil(bbox[2])) + 2, W), min(int(math.ceil(bbox[3])) + 2, H)
        if x1 > x0 and y1 > y0:
            box = (x0, y0, x1, y1)
            self.img.alpha_composite(self._scratch.crop(box), dest=(x0, y0))
            self._scratch.paste((0, 0, 0, 0), box)

    @staticmethod
    def _bbox(pts, pad=0):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    @staticmethod
    def _rotate(pts, cx, cy, deg):
        if not deg:
            return pts
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        return [(cx + (x - cx) * c - (y - cy) * s,
                 cy + (x - cx) * s + (y - cy) * c) for x, y in pts]

    # -- fills ------------------------------------------------------------
    def background(self, color):
        self.img.paste(rgb(color), (0, 0, self.img.width, self.img.height))
        return self

    def gradient(self, c1, c2, angle=90, opacity=1.0):
        """Linear gradient over the whole frame. angle 90 = top->bottom.

        Cached: a gradient that does not change costs one composite a frame.
        Animate it by animating c1/c2/angle (then each new value is computed).
        """
        key = ("grad", self.img.size, rgb(c1), rgb(c2), round(angle, 2),
               round(clamp01(opacity), 3))
        self._blit(key, lambda: self._gradient_img(c1, c2, angle, opacity))
        return self

    def _gradient_img(self, c1, c2, angle, opacity):
        W, H = self.out_size  # smooth fields need no supersampling
        a = math.radians(angle)
        yy, xx = np.ogrid[0:H, 0:W]
        d = (xx - W / 2) * math.cos(a) + (yy - H / 2) * math.sin(a)
        span = abs(W * math.cos(a)) + abs(H * math.sin(a))
        t = np.clip(d / span + 0.5, 0, 1)[..., None]
        arr = (np.array(rgb(c1), np.float32) * (1 - t)
               + np.array(rgb(c2), np.float32) * t)
        arr[..., 3] *= clamp01(opacity)
        return Image.fromarray(arr.astype(np.uint8), "RGBA")

    def vignette(self, strength=0.45, color="#000000"):
        key = ("vig", self.img.size, round(strength, 3), rgb(color))

        def build():
            W, H = self.out_size
            yy, xx = np.ogrid[0:H, 0:W]
            r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2
                        + ((yy - H / 2) / (H / 2)) ** 2)
            a = np.clip((r - 0.55) / 0.9, 0, 1) ** 1.6 * 255 * strength
            layer = np.zeros((H, W, 4), np.uint8)
            layer[..., :3] = rgb(color)[:3]
            layer[..., 3] = a.astype(np.uint8)
            return Image.fromarray(layer, "RGBA")
        self._blit(key, build)
        return self

    def _blit(self, key, build):
        im = _CACHE.get(key)
        if im is None:
            im = build()
            if im.size != self.img.size:
                im = im.resize(self.img.size, Image.BILINEAR)
            if len(_CACHE) > 64:
                _CACHE.clear()
            im.info["opaque"] = im.getchannel("A").getextrema()[0] == 255
            _CACHE[key] = im
        if im.info.get("opaque"):
            self.img.paste(im)  # covers everything: no blend needed
        else:
            self.img.alpha_composite(im)

    # -- shapes -----------------------------------------------------------
    def rect(self, x, y, w, h, fill=None, radius=0, opacity=1.0, outline=None,
             width=0, anchor="center", rotation=0):
        """Rectangle. anchor='center' means (x, y) is the centre."""
        if anchor == "center":
            x, y = x - w / 2, y - h / 2
        if w <= 0 or h <= 0 or opacity <= 0:
            return self
        if rotation:
            cx, cy = x + w / 2, y + h / 2
            r = min(radius, w / 2, h / 2)
            if r > 0:  # rounded corners as short arcs, then rotate the outline
                pts = []
                for (ox, oy), a0 in (((x + w - r, y + r), -90), ((x + w - r, y + h - r), 0),
                                     ((x + r, y + h - r), 90), ((x + r, y + r), 180)):
                    for k in range(9):
                        a = math.radians(a0 + k * 90 / 8)
                        pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
            else:
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            return self.polygon(self._rotate(pts, cx, cy, rotation), fill,
                                opacity, outline, width)
        box = [self._s(x), self._s(y), self._s(x + w), self._s(y + h)]
        fc = _with_opacity(fill, opacity) if fill else None
        oc = _with_opacity(outline, opacity) if outline else None
        kw = dict(fill=fc, outline=oc, width=int(self._s(width)))
        r = min(radius, w / 2, h / 2)
        with self._paint(box, _amin(fc, oc)) as d:
            if r > 0:
                d.rounded_rectangle(box, radius=self._s(r), **kw)
            else:
                d.rectangle(box, **kw)
        return self

    def circle(self, cx, cy, r, fill=None, opacity=1.0, outline=None, width=0):
        if r <= 0 or opacity <= 0:
            return self
        box = [self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)]
        fc = _with_opacity(fill, opacity) if fill else None
        oc = _with_opacity(outline, opacity) if outline else None
        with self._paint(box, _amin(fc, oc)) as d:
            d.ellipse(box, fill=fc, outline=oc, width=int(self._s(width)))
        return self

    def arc(self, cx, cy, r, start, end, color, width=8, opacity=1.0, cap=True):
        """Stroke from angle start to end (degrees, 0 = 3 o'clock, clockwise).

        A progress ring is arc(cx, cy, r, -90, -90 + 360 * p, ...).
        """
        if r <= 0 or end <= start or opacity <= 0:
            return self
        box = [self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)]
        col = _with_opacity(color, opacity)
        with self._paint(box, col[3]) as d:
            d.arc(box, start, end, fill=col, width=int(self._s(width)))
            if cap:
                hw = self._s(width / 2)
                for ang in (start, end):
                    a = math.radians(ang)
                    rr = self._s(r - width / 2)
                    px, py = self._s(cx) + rr * math.cos(a), self._s(cy) + rr * math.sin(a)
                    d.ellipse([px - hw, py - hw, px + hw, py + hw], fill=col)
        return self

    def polygon(self, pts, fill=None, opacity=1.0, outline=None, width=0):
        if opacity <= 0:
            return self
        sp = self._pts(pts)
        fc = _with_opacity(fill, opacity) if fill else None
        oc = _with_opacity(outline, opacity) if outline else None
        with self._paint(self._bbox(sp, self._s(width)),
                         _amin(fc, oc)) as d:
            d.polygon(sp, fill=fc, outline=oc,
                      width=max(1, int(self._s(width))) if outline else 1)
        return self

    def line(self, pts, color, width=4, opacity=1.0, progress=1.0, cap=True):
        """Polyline. progress < 1 draws only the first part (draw-on effect)."""
        pts = list(pts)
        if progress < 1:
            seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
            left = sum(seg) * clamp01(progress)
            out = [pts[0]]
            for (a, b), L in zip(zip(pts, pts[1:]), seg):
                if left >= L:
                    out.append(b)
                    left -= L
                else:
                    if L > 0 and left > 0:
                        out.append(lerp(a, b, left / L))
                    break
            pts = out
        if len(pts) < 2 or opacity <= 0:
            return self
        col = _with_opacity(color, opacity)
        sp = self._pts(pts)
        hw = self._s(width / 2)
        with self._paint(self._bbox(sp, hw + 2), col[3]) as d:
            d.line(sp, fill=col, width=int(self._s(width)), joint="curve")
            if cap:
                for px, py in (sp[0], sp[-1]):
                    d.ellipse([px - hw, py - hw, px + hw, py + hw], fill=col)
        return self

    def star(self, cx, cy, r_out, r_in=None, points=5, fill="#ffffff",
             opacity=1.0, rotation=-90):
        r_in = r_in or r_out * 0.45
        pts = []
        for i in range(points * 2):
            r = r_out if i % 2 == 0 else r_in
            a = math.radians(rotation + i * 180 / points)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return self.polygon(pts, fill, opacity)

    # -- text -------------------------------------------------------------
    def text_size(self, s, size=48, font="bold", tracking=0):
        f = _font(font, size * self.k)
        l, t, r, b = self._draw.multiline_textbbox((0, 0), s, font=f)
        extra = tracking * max(0, len(s) - 1) * self.k
        return (r - l + extra) / self.k, (b - t) / self.k

    def text(self, s, x, y, size=48, color="#ffffff", font="bold", anchor="mm",
             opacity=1.0, tracking=0, align="center", rotation=0, scale=1.0,
             reveal=None):
        """Draw text. anchor is Pillow's: 'mm' centre, 'la' left-top, 'ls' ...

        font: 'regular' | 'bold' | 'mono' | 'serif' | a .ttf path.
        tracking: extra px between letters. reveal: 0..1 typewriter.
        rotation/scale != default renders through a sprite (slower).
        """
        if reveal is not None:
            s = s[: int(round(len(s) * clamp01(reveal)))]
        if not s or opacity <= 0 or scale <= 0:
            return self
        if rotation or scale != 1.0:
            spr = self._text_sprite(s, size * scale, color, font, tracking, align)
            spr = spr.rotate(-rotation, resample=Image.BICUBIC, expand=True)
            return self._paste_sprite(spr, x, y, opacity)
        f = _font(font, size * self.k)
        col = _with_opacity(color, opacity)
        X, Y = self._s(x), self._s(y)
        if tracking and "\n" not in s:
            w, _ = self.text_size(s, size, font, tracking)
            cx = X - {"l": 0, "m": w / 2, "r": w}.get(anchor[0], 0) * self.k
            v = anchor[1]
            l, t, r, b = self._draw.textbbox((cx, Y), s, font=f, anchor="l" + v)
            with self._paint((l, t, cx + w * self.k, b), col[3], soft=True) as d:
                for ch in s:
                    d.text((cx, Y), ch, font=f, fill=col, anchor="l" + v)
                    cx += d.textlength(ch, font=f) + tracking * self.k
            return self
        if "\n" in s:
            kw = dict(font=f, anchor=anchor, align=align,
                      spacing=int(size * self.k * 0.25))
            bbox = self._draw.multiline_textbbox((X, Y), s, **kw)
            with self._paint(bbox, col[3], soft=True) as d:
                d.multiline_text((X, Y), s, fill=col, **kw)
        else:
            bbox = self._draw.textbbox((X, Y), s, font=f, anchor=anchor)
            with self._paint(bbox, col[3], soft=True) as d:
                d.text((X, Y), s, font=f, fill=col, anchor=anchor)
        return self

    def _text_sprite(self, s, size, color, font, tracking, align):
        f = _font(font, size * self.k)
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        l, t, r, b = d.multiline_textbbox((0, 0), s, font=f, align=align)
        pad = int(size * self.k * 0.2)
        spr = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(spr).multiline_text((pad - l, pad - t), s, font=f,
                                           fill=rgb(color), align=align)
        return spr

    # -- images, layers ---------------------------------------------------
    def _paste_sprite(self, spr, x, y, opacity=1.0):
        """spr is already at supersampled scale; (x, y) is its centre."""
        if opacity < 1:
            a = spr.getchannel("A").point(lambda v: int(v * clamp01(opacity)))
            spr = spr.copy()
            spr.putalpha(a)
        px = int(round(self._s(x) - spr.width / 2))
        py = int(round(self._s(y) - spr.height / 2))
        self.img.alpha_composite(spr, dest=(max(px, 0), max(py, 0)),
                                 source=(max(-px, 0), max(-py, 0)))
        return self

    def image(self, src, x, y, width=None, height=None, opacity=1.0,
              rotation=0, scale=1.0):
        """Place an image (path or PIL.Image), centred at (x, y)."""
        im = Image.open(src) if isinstance(src, (str, os.PathLike)) else src
        im = im.convert("RGBA")
        if width and not height:
            height = im.height * width / im.width
        elif height and not width:
            width = im.width * height / im.height
        width, height = (width or im.width) * scale, (height or im.height) * scale
        spr = im.resize((max(1, int(self._s(width))), max(1, int(self._s(height)))),
                        Image.LANCZOS)
        if rotation:
            spr = spr.rotate(-rotation, resample=Image.BICUBIC, expand=True)
        return self._paste_sprite(spr, x, y, opacity)

    def layer(self):
        """A transparent Frame of the same size, to composite() back later.

        Use for group fades, blur, glows and drop shadows.
        """
        return Frame(self.w, self.h, self.ss, transparent=True, unit=self.unit)

    def composite(self, layer, opacity=1.0, blur=0, offset=(0, 0), tint=None):
        """Composite a layer. tint recolours it (shadows, glows)."""
        im = layer.img
        box = im.getchannel("A").getbbox()
        if box is None or opacity <= 0:
            return self
        r = self._s(blur)
        pad = int(3 * r) + 2
        x0, y0 = max(box[0] - pad, 0), max(box[1] - pad, 0)
        x1, y1 = min(box[2] + pad, im.width), min(box[3] + pad, im.height)
        im = im.crop((x0, y0, x1, y1))
        if tint is not None:
            c = rgb(tint)
            solid = Image.new("RGBA", im.size, c[:3] + (255,))
            solid.putalpha(im.getchannel("A"))
            im = solid
        if blur:
            # A wide blur is invisible at low resolution: blur small, scale up.
            k = max(1, int(r / 6))
            if k > 1:
                small = im.resize((max(1, im.width // k), max(1, im.height // k)),
                                  Image.BILINEAR)
                small = small.filter(ImageFilter.GaussianBlur(r / k))
                im = small.resize(im.size, Image.BILINEAR)
            else:
                im = im.filter(ImageFilter.GaussianBlur(r))
        if opacity < 1:
            im.putalpha(im.getchannel("A").point(lambda v: int(v * clamp01(opacity))))
        dx, dy = x0 + int(self._s(offset[0])), y0 + int(self._s(offset[1]))
        src = (max(-dx, 0), max(-dy, 0))
        if src[0] < im.width and src[1] < im.height:
            self.img.alpha_composite(im, dest=(max(dx, 0), max(dy, 0)), source=src)
        return self

    def glow(self, layer, color=None, radius=18, strength=1.0, opacity=1.0):
        """Composite a layer over a soft glow of `color` (default: its own)."""
        self.composite(layer, opacity=strength * opacity, blur=radius, tint=color)
        return self.composite(layer, opacity=opacity)

    def shadow(self, layer, offset=(0, 12), blur=16, strength=0.45,
               color="#000000", opacity=1.0):
        """Composite a layer over its own drop shadow.

        strength: shadow darkness. opacity: the whole group (fade it out).
        """
        self.composite(layer, opacity=strength * opacity, blur=blur,
                       offset=offset, tint=color)
        return self.composite(layer, opacity=opacity)

    def grain(self, amount=0.04, seed=0):
        """Film grain. Deterministic for a given seed (pass the frame index)."""
        rng = np.random.default_rng(seed)
        arr = np.asarray(self.img).astype(np.int16)
        noise = rng.normal(0, 255 * amount, arr.shape[:2])[..., None]
        arr[..., :3] = np.clip(arr[..., :3] + noise, 0, 255)
        self.img = Image.fromarray(arr.astype(np.uint8), "RGBA")
        self._draw = ImageDraw.Draw(self.img)
        return self

    def finish(self):
        """Downsample to output size. Returns RGBA if transparent else RGB."""
        im = self.img
        if im.size != self.out_size:
            if im.size == (self.out_size[0] * self.ss, self.out_size[1] * self.ss):
                im = im.reduce(self.ss)  # box filter = exact supersample average
            else:
                im = im.resize(self.out_size, Image.LANCZOS)
        return im if self.transparent else im.convert("RGB")


# --------------------------------------------------------------------------
# Containers written in pure Python (no ffmpeg anywhere)
# --------------------------------------------------------------------------


def _box(kind, *payload):
    body = b"".join(payload)
    return struct.pack(">I4s", 8 + len(body), kind) + body


def _full(kind, version, flags, *payload):
    return _box(kind, struct.pack(">I", (version << 24) | flags), *payload)


_MATRIX = struct.pack(">9I", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)


def _pascal(s, size=None):
    b = s.encode()
    out = bytes([len(b)]) + b
    return out.ljust(size, b"\0") if size else out


def write_mov(jpegs, path, width, height, fps):
    """QuickTime .mov with Photo-JPEG samples. jpegs: list of bytes.

    Plays in QuickTime Player, VLC, IINA, mpv; imports into Premiere,
    Final Cut, DaVinci Resolve; accepted by YouTube/Vimeo upload.
    """
    fps = int(round(fps))
    n = len(jpegs)
    ftyp = _box(b"ftyp", b"qt  ", struct.pack(">I", 0x200), b"qt  ")
    mdat_body = b"".join(jpegs)
    if 8 + len(ftyp) + len(mdat_body) >= 2 ** 32:
        raise ValueError("over 4 GB - lower the quality or split the clip")
    data_start = len(ftyp) + 8
    movie_ts, dur_movie = 1000, int(round(n * 1000 / fps))
    mvhd = _full(b"mvhd", 0, 0, struct.pack(">IIII", 0, 0, movie_ts, dur_movie),
                 struct.pack(">IH", 0x10000, 0x100), b"\0" * 10, _MATRIX,
                 b"\0" * 24, struct.pack(">I", 2))
    tkhd = _full(b"tkhd", 0, 0xF, struct.pack(">IIII", 0, 0, 1, 0),
                 struct.pack(">I", dur_movie), b"\0" * 8,
                 struct.pack(">hhhh", 0, 0, 0, 0), _MATRIX,
                 struct.pack(">II", width << 16, height << 16))
    mdhd = _full(b"mdhd", 0, 0, struct.pack(">IIII", 0, 0, fps, n),
                 struct.pack(">HH", 0x55C4, 0))
    hdlr = _full(b"hdlr", 0, 0, b"mhlr", b"vide", b"\0" * 12,
                 _pascal("VideoHandler"))
    vmhd = _full(b"vmhd", 0, 1, struct.pack(">HHHH", 0, 0, 0, 0))
    dhlr = _full(b"hdlr", 0, 0, b"dhlr", b"alis", b"\0" * 12,
                 _pascal("DataHandler"))
    dinf = _box(b"dinf", _full(b"dref", 0, 0, struct.pack(">I", 1),
                               _full(b"alis", 0, 1)))
    entry = _box(b"jpeg", b"\0" * 6, struct.pack(">H", 1),
                 struct.pack(">HH", 0, 0), b"\0" * 4,
                 struct.pack(">II", 0, 0x200),
                 struct.pack(">HH", width, height),
                 struct.pack(">II", 0x480000, 0x480000), struct.pack(">I", 0),
                 struct.pack(">H", 1), _pascal("Photo - JPEG", 32),
                 struct.pack(">Hh", 24, -1))
    stbl = _box(b"stbl",
                _full(b"stsd", 0, 0, struct.pack(">I", 1), entry),
                _full(b"stts", 0, 0, struct.pack(">III", 1, n, 1)),
                _full(b"stsc", 0, 0, struct.pack(">IIII", 1, 1, n, 1)),
                _full(b"stsz", 0, 0, struct.pack(">II", 0, n),
                      struct.pack(">%dI" % n, *map(len, jpegs))),
                _full(b"stco", 0, 0, struct.pack(">II", 1, data_start)))
    minf = _box(b"minf", vmhd, dhlr, dinf, stbl)
    trak = _box(b"trak", tkhd, _box(b"mdia", mdhd, hdlr, minf))
    moov = _box(b"moov", mvhd, trak)
    with open(path, "wb") as fh:
        fh.write(ftyp)
        fh.write(struct.pack(">I4s", 8 + len(mdat_body), b"mdat"))
        fh.write(mdat_body)
        fh.write(moov)


def write_avi(jpegs, path, width, height, fps):
    """Motion-JPEG .avi. Plays in Windows' built-in players, VLC, mpv."""
    fps = int(round(fps))
    n = len(jpegs)
    maxsz = max(map(len, jpegs))
    chunks, index, off = [], [], 4  # offsets are from the 'movi' fourcc
    for j in jpegs:
        pad = b"\0" if len(j) % 2 else b""
        chunks.append(struct.pack("<4sI", b"00dc", len(j)) + j + pad)
        index.append(struct.pack("<4sIII", b"00dc", 0x10, off, len(j)))
        off += 8 + len(j) + len(pad)
    avih = struct.pack("<IIIIIIIIII4I", int(1e6 / fps), maxsz * fps, 0, 0x10,
                       n, 0, 1, maxsz, width, height, 0, 0, 0, 0)
    strh = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"MJPG", 0, 0, 0, 0,
                       1, fps, 0, n, maxsz, 0xFFFFFFFF, 0, 0, 0, width, height)
    strf = struct.pack("<IiiHH4sIiiII", 40, width, height, 1, 24, b"MJPG",
                       width * height * 3, 0, 0, 0, 0)

    def chunk(fcc, data):
        return struct.pack("<4sI", fcc, len(data)) + data

    def lst(kind, data):
        return struct.pack("<4sI4s", b"LIST", 4 + len(data), kind) + data

    hdrl = lst(b"hdrl", chunk(b"avih", avih) +
               lst(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf)))
    movi = lst(b"movi", b"".join(chunks))
    body = b"AVI " + hdrl + movi + chunk(b"idx1", b"".join(index))
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sI", b"RIFF", len(body)) + body)


def _ffmpeg():
    if os.environ.get("MOTION_NO_FFMPEG"):  # simulate Claude's sandbox
        return None
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:  # pip's imageio-ffmpeg bundles a static binary
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


# --------------------------------------------------------------------------
# Render loop
# --------------------------------------------------------------------------


def _frame_path(cache, i, ext):
    return os.path.join(cache, "f%05d.%s" % (i, ext))


def render(scene, out, duration, fps=30, size=(1280, 720), ss=2,
           background="#000000", transparent=False, quality=90,
           cache=None, time_budget=None, loop=0, gif_colors=256,
           lossless=False, design=None, verbose=True):
    """Render scene(frame, t) to `out`. The extension picks the format.

    cache       directory for rendered frames. Re-running skips frames that
                exist, so a long render can be split across tool calls.
    time_budget seconds; stop cleanly once exceeded and return None.
                Re-run the same call (same cache) to continue.
    quality     JPEG quality for .mov/.avi, WebP quality, x264 CRF mapping.
    transparent keep alpha (.webp, .apng, .gif only).
    design      (w, h) you draw in, if different from the output `size`.
                Write the scene once at 1920x1080 and export a 480x270 GIF
                of it with design=(1920, 1080), size=(480, 270).

    Returns `out` when the file was written.
    """
    W, H = size
    ext = os.path.splitext(out)[1].lower().lstrip(".")
    if ext == "png":
        ext = "apng"
    if ext not in ("gif", "webp", "apng", "mov", "avi", "mp4"):
        raise ValueError("unsupported output ." + ext)
    if ext == "mp4" and not _ffmpeg():
        alt = os.path.splitext(out)[0] + ".mov"
        print("[motion] no ffmpeg here, so no H.264 encoder: writing %s "
              "(Photo-JPEG QuickTime) instead of %s." % (alt, out))
        out, ext = alt, "mov"
    if transparent and ext not in ("webp", "apng", "gif"):
        raise ValueError("transparency needs .webp, .apng or .gif")
    if ext in ("mp4", "mov", "avi") and (W % 2 or H % 2):
        raise ValueError("video sizes must be even, got %dx%d" % (W, H))

    n = max(1, int(round(duration * fps)))
    video = ext in ("mov", "avi", "mp4")
    cext = "jpg" if video and ext != "mp4" else "png"
    if cache:
        os.makedirs(cache, exist_ok=True)

    pipe = None
    if ext == "mp4":
        crf = int(round(np.interp(quality, [50, 100], [30, 14])))
        cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H), "-r", str(fps),
               "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf",
               str(crf), "-preset", "medium", "-movflags", "+faststart", out]

    frames = []
    t_start = time.time()
    done_now = 0
    for i in range(n):
        path = _frame_path(cache, i, cext) if cache else None
        if path and os.path.exists(path):
            frames.append(path)
            continue
        if time_budget and done_now and time.time() - t_start > time_budget:
            left = n - i
            per = (time.time() - t_start) / done_now
            print("[motion] time budget hit at frame %d/%d; about %.0fs left. "
                  "Re-run the same render() call to continue." % (i, n, left * per))
            return None
        dw, dh = design or size
        f = Frame(dw, dh, ss, background, transparent, unit=W / dw)
        scene(f, i / fps)
        im = f.finish()
        if cext == "jpg":
            buf = io.BytesIO()
            # 4:2:0 is the one JPEG layout every MJPEG decoder accepts
            # (QuickTime, Windows Media Foundation, hardware decoders).
            im.save(buf, "JPEG", quality=quality, subsampling=2)
            data = buf.getvalue()
            if path:
                with open(path, "wb") as fh:
                    fh.write(data)
            frames.append(path or data)
        elif path:
            im.save(path, "PNG", compress_level=1)
            frames.append(path)
        elif ext == "mp4":  # stream straight into the encoder
            if pipe is None:
                pipe = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            pipe.stdin.write(im.convert("RGB").tobytes())
        else:
            frames.append(im)
        done_now += 1
        if verbose and done_now == 5:
            per = (time.time() - t_start) / done_now
            print("[motion] %.0f ms/frame -> about %.0fs to go (%d frames)"
                  % (per * 1000, per * (n - i - 1), n))

    def load(x):
        return Image.open(x) if isinstance(x, str) else x

    if ext in ("mov", "avi"):
        jp = [open(x, "rb").read() if isinstance(x, str) else x for x in frames]
        (write_mov if ext == "mov" else write_avi)(jp, out, W, H, fps)
    elif ext == "mp4":
        if pipe is None:
            pipe = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for x in frames:  # cached frames on disk, if any
            pipe.stdin.write(load(x).convert("RGB").tobytes())
        pipe.stdin.close()
        if pipe.wait():
            raise RuntimeError("ffmpeg failed")
    else:
        ims = [load(x) for x in frames]
        ms = 1000 / fps
        if ext == "gif":
            ims = _gif_frames(ims, gif_colors, transparent)
            # GIF stores centiseconds: fps of 10/20/25/50 are exact.
            durs = _cs_durations(n, fps)
            ims[0].save(out, save_all=True, append_images=ims[1:], loop=loop,
                        duration=durs, disposal=2 if transparent else 1,
                        optimize=False)
        elif ext == "webp":
            ims[0].save(out, "WEBP", save_all=True, append_images=ims[1:],
                        duration=int(round(ms)), loop=loop, quality=quality,
                        lossless=lossless, method=4)
        else:
            ims[0].save(out, "PNG", save_all=True, append_images=ims[1:],
                        duration=ms, loop=loop, default_image=False)
    if verbose:
        print("[motion] wrote %s  (%d frames, %dx%d @ %dfps, %.1f MB, %.1fs)"
              % (out, n, W, H, fps, os.path.getsize(out) / 1e6,
                 time.time() - t_start))
    return out


def _cs_durations(n, fps):
    """Per-frame GIF delays in ms that stay on the centisecond grid and
    accumulate to the right total (so 30 fps averages 33.3 ms)."""
    out, acc = [], 0
    for i in range(1, n + 1):
        target = int(round(i * 100 / fps)) * 10
        out.append(max(20, target - acc))
        acc += out[-1]
    return out


def _gif_frames(ims, colors, transparent):
    """One shared palette built from sampled frames: no palette flicker."""
    step = max(1, len(ims) // 16)
    sample = ims[::step]
    w, h = sample[0].size
    thumb_w = max(1, w // 2)
    thumb_h = max(1, h // 2)
    sheet = Image.new("RGB", (thumb_w, thumb_h * len(sample)))
    for k, im in enumerate(sample):
        sheet.paste(im.convert("RGB").resize((thumb_w, thumb_h)), (0, k * thumb_h))
    ncol = min(colors, 255 if transparent else 256)
    pal = sheet.quantize(ncol, method=Image.Quantize.MEDIANCUT)
    out = []
    for im in ims:
        q = im.convert("RGB").quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
        if transparent:
            alpha = im.getchannel("A")
            q.paste(255, mask=alpha.point(lambda a: 255 if a < 128 else 0))
            q.info["transparency"] = 255
        out.append(q)
    return out


# --------------------------------------------------------------------------
# Self-checks: look at your own motion before you ship it
# --------------------------------------------------------------------------


def _read_frames(path, max_frames=None):
    ext = os.path.splitext(path)[1].lower()
    frames = []
    if ext in (".mov", ".avi"):
        data = open(path, "rb").read()
        k = 0
        while True:  # JPEG SOI ... EOI scan; fine for our own files
            a = data.find(b"\xff\xd8\xff", k)
            if a < 0:
                break
            b = data.find(b"\xff\xd9", a)
            frames.append(Image.open(io.BytesIO(data[a:b + 2])).convert("RGB"))
            k = b + 2
    elif ext == ".mp4":
        exe = _ffmpeg()
        if not exe:
            raise RuntimeError("reading .mp4 needs ffmpeg; check the .mov")
        probe = subprocess.run([exe, "-i", path, "-f", "image2pipe", "-vcodec",
                                "png", "-"], capture_output=True).stdout
        k = 0
        while True:
            a = probe.find(b"\x89PNG", k)
            if a < 0:
                break
            b = probe.find(b"IEND", a) + 8
            frames.append(Image.open(io.BytesIO(probe[a:b])).convert("RGB"))
            k = b
    else:
        im = Image.open(path)
        for i in range(getattr(im, "n_frames", 1)):
            im.seek(i)
            frames.append(im.convert("RGB"))
    return frames[:max_frames] if max_frames else frames


def contact_sheet(path, out=None, cols=4, rows=3, width=1600):
    """Grid of evenly spaced frames with timestamps - LOOK at this."""
    frames = _read_frames(path)
    k = cols * rows
    idx = [round(i * (len(frames) - 1) / max(1, k - 1)) for i in range(k)]
    tw = width // cols
    th = int(tw * frames[0].height / frames[0].width)
    sheet = Image.new("RGB", (tw * cols, (th + 22) * rows), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    f = _font("mono", 14)
    for j, i in enumerate(idx):
        x, y = (j % cols) * tw, (j // cols) * (th + 22)
        sheet.paste(frames[i].resize((tw, th), Image.LANCZOS), (x, y + 22))
        d.text((x + 6, y + 4), "#%d" % i, font=f, fill=(220, 220, 220))
    out = out or os.path.splitext(path)[0] + "_sheet.png"
    sheet.save(out)
    return out


def motion_report(path, fps=None):
    """Numbers that catch dead or jittery motion without watching it.

    - still spans: (first, last, count) runs where nothing moved - holds
      you meant, or dead air you did not. GIF/WebP merge identical frames,
      so read those counts on a .mov/.avi render.
    - jumps: frames that change far more than their neighbours (pops, cuts)
    """
    frames = _read_frames(path)
    w = min(320, frames[0].width)
    h = max(1, round(frames[0].height * w / frames[0].width))
    small = [np.asarray(f.resize((w, h), Image.BOX), np.float32) for f in frames]
    delta = [np.abs(a - b) for a, b in zip(small, small[1:])]
    diffs = np.array([d.mean() for d in delta])
    # "still" = nothing moved anywhere (max, so a thin line drawing on counts)
    still = np.array([d.max() < 6 for d in delta])
    spans, run = [], 0
    for i, st in enumerate(still):
        if st:
            run += 1
        elif run:
            spans.append((i - run, i, run))
            run = 0
    if run:
        spans.append((len(still) - run, len(still), run))
    med = float(np.median(diffs[~still])) if (~still).any() else 0.0
    jumps = [int(i) + 1 for i in np.where(diffs > max(8.0, 6 * med))[0]]
    rep = {
        "frames": len(frames),
        "size": frames[0].size,
        "mean_change": round(float(diffs.mean()), 2) if len(diffs) else 0.0,
        "still_spans": [(a, b, r) for a, b, r in spans if r >= 3],
        "jumps": jumps,
    }
    if fps:
        rep["seconds"] = round(len(frames) / fps, 2)
    print("[motion] %s" % rep)
    return rep


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "check":
        for p in sys.argv[2:]:
            print(contact_sheet(p))
            motion_report(p)
    else:
        print(__doc__)
