#!/usr/bin/env python3
"""
BARNABY THE MENDER - 9:16 short, rendered from the storyboard.

Reads the 10 AI keyframes + Itx/build/audio_mix.wav and produces a
1080x1920 / 30 fps H.264 reel: per-scene camera moves (Ken Burns with pan,
tilt, handheld shake, impact shake), film-look grade, bloom, grain, vignette,
animated on-screen text with hand-drawn vector icons, dust motes, crossfades,
a hard cut + flash on the shatter, and a 2.5 s end card (the 10 scenes
themselves sit exactly on 0-60 s as specified).

Usage: python render_barnaby.py [--preview N]
"""
import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ------------------------------------------------------------------- config
ROOT = os.environ.get("BARNABY_ROOT", "/home/user/Itx/Itx")
ASSETS = os.path.join(ROOT, "assets")
BUILD = os.path.join(ROOT, "build")
OUT_DIR = os.environ.get("BARNABY_OUT", "/home/user/Itx/output")
AUDIO = os.path.join(BUILD, "audio_mix.wav")
FINAL = os.path.join(OUT_DIR, "barnaby_the_mender_9x16.mp4")

W, H, FPS = 1080, 1920, 30
MASTER_W = 1152                      # working master width (source is 768 wide)
STORY_END = 60.0
END_TOTAL = 62.5                     # + end card
FADE = 0.38                          # dissolve length at scene cuts

FONT_DIR = None
try:
    import matplotlib
    FONT_DIR = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
except Exception:
    pass
def font_path(name):
    return os.path.join(FONT_DIR, name)

BOLD = font_path("DejaVuSans-Bold.ttf")
DISP = font_path("DejaVuSansDisplay.ttf")
SERIF = font_path("DejaVuSerif-Bold.ttf")
MONO = font_path("DejaVuSansMono.ttf")

rng = np.random.default_rng(11)

# --------------------------------------------------------------- scene spec
# s = magnification (1.0 shows the whole master). pan = normalised drift of the
# crop centre, 0 = centred, +/-0.5 = frame edge.
SCENES = [
    dict(n=1, t0=0.0, t1=3.0, img="scene01.png", text="The Mistake", icon="heartbreak",
         t_in=0.30, t_out=2.95, s0=1.10, s1=1.44, pan=(0.0, 0.06, 0.0, -0.05),
         grade=dict(sat=.82, con=1.16, temp=-.07, gain=.93, gam=1.05, vig=.62, bloom=.10),
         cut="fade_in"),
    dict(n=2, t0=3.0, t1=10.0, img="scene02.png", text="Barnaby the Mender", icon=None,
         t_in=3.55, t_out=7.3, s0=1.20, s1=1.10, pan=(-0.20, 0.03, 0.22, -0.02),
         grade=dict(sat=1.14, con=1.05, temp=.075, gain=1.03, gam=.98, vig=.34, bloom=.18),
         dust=26),
    dict(n=3, t0=10.0, t1=18.0, img="scene03.png", text="One slip...", icon=None,
         t_in=11.0, t_out=14.6, s0=1.05, s1=1.34, pan=(-0.05, .10, .10, -.14),
         grade=dict(sat=.92, con=1.12, temp=.01, gain=.99, gam=1.0, vig=.44, bloom=.08),
         tilt=-2.6, shake=dict(amp=7.0, f=13.0, ramp=6.5), cut="hard"),
    dict(n=4, t0=18.0, t1=25.0, img="scene04.png", text="Gone.", icon="tear",
         t_in=19.0, t_out=22.3, s0=1.26, s1=1.09, pan=(0.0, -.10, 0.0, .06),
         grade=dict(sat=.66, con=1.13, temp=-.06, gain=.90, gam=1.06, vig=.55, bloom=.12),
         shake=dict(amp=26.0, f=17.0, decay=3.6)),
    dict(n=5, t0=25.0, t1=32.0, img="scene05.png", text="Look outside", icon="eye",
         t_in=26.0, t_out=29.6, s0=1.06, s1=1.30, pan=(0.0, .05, .02, -.12),
         grade=dict(sat=.94, con=1.10, temp=-.03, gain=.97, gam=1.04, vig=.52, bloom=.16),
         dust=16),
    dict(n=6, t0=32.0, t1=40.0, img="scene06.png", text="Time to act!", icon=None,
         t_in=32.6, t_out=36.4, s0=1.24, s1=1.06, pan=(-.06, .08, .06, -.06),
         grade=dict(sat=1.06, con=1.09, temp=.03, gain=1.0, gam=1.0, vig=.36, bloom=.10),
         shake=dict(amp=9.0, f=9.5, ramp=2.2), tilt_jitter=1.3),
    dict(n=7, t0=40.0, t1=48.0, img="scene07.png", text="So gentle...", icon=None,
         t_in=41.2, t_out=44.8, s0=1.17, s1=1.28, pan=(.02, -.03, -.03, .04),
         grade=dict(sat=1.10, con=1.04, temp=.05, gain=1.01, gam=.99, vig=.31, bloom=.26),
         shake=dict(amp=2.2, f=1.1, ramp=.5)),
    dict(n=8, t0=48.0, t1=52.0, img="scene08.png", text="Free!", icon="butterfly",
         t_in=48.55, t_out=51.9, s0=1.10, s1=1.26, pan=(0.0, .02, 0.0, -.04),
         grade=dict(sat=1.20, con=1.02, temp=.07, gain=1.06, gam=.97, vig=.27, bloom=.62),
         flare=True),
    dict(n=9, t0=52.0, t1=57.0, img="scene09.png", text="New Art", icon="palette",
         t_in=52.6, t_out=55.9, s0=1.34, s1=1.09, pan=(0.0, 0.0, 0.0, 0.0),
         grade=dict(sat=1.18, con=1.07, temp=.04, gain=1.02, gam=.99, vig=.36, bloom=.24),
         roll=3.4),
    dict(n=10, t0=57.0, t1=60.0, img="scene10.png", text="Create Beauty.", icon="sparkle",
         t_in=57.5, t_out=60.6, s0=1.10, s1=1.03, pan=(.02, .0, -.03, -.05),
         grade=dict(sat=1.13, con=1.04, temp=.08, gain=1.0, gam=.99, vig=.34, bloom=.42),
         dust=22, flare=True),
]

# ------------------------------------------------------------- master frames
def load_master(scene):
    im = Image.open(os.path.join(ASSETS, scene["img"])).convert("RGB")
    w, h = im.size
    target = w / (9 / 16)
    if h > target:                                   # trim top/bottom
        y0 = (h - int(target)) // 2
        im = im.crop((0, y0, w, y0 + int(target)))
    elif h < target:
        x0 = (w - int(h * 9 / 16)) // 2
        im = im.crop((x0, 0, x0 + int(h * 9 / 16), h))
    m_h = int(round(MASTER_W * h / w))
    im = im.resize((MASTER_W, m_h), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2.4, percent=125, threshold=2))
    # keep a little extra height margin for vertical drift
    if im.size[1] < int(MASTER_W * 1920 / 1080) + 8:
        pad = int(MASTER_W * 1920 / 1080) + 8 - im.size[1]
        canvas = Image.new("RGB", (im.size[0], im.size[1] + pad), (6, 6, 8))
        canvas.paste(im, (0, 0))
        im = canvas
    return np.asarray(im, dtype=np.uint8)


MASTERS = {s["n"]: load_master(s) for s in SCENES}
MH, MW = MASTERS[1].shape[:2]

# ---------------------------------------------------- shared fx (per frame #)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
cx, cy = W / 2, H * 0.47
r = np.sqrt(((xx - cx) / (W * .62)) ** 2 + ((yy - cy) / (H * .60)) ** 2)
GRAIN = [(rng.standard_normal((H, W)).astype(np.float32) * 5.0) for _ in range(6)]


def vignette_map(strength):
    return np.clip(1.0 - strength * (r ** 2.3), 0.0, 1.0)[..., None].astype(np.float32)


VIG_CACHE = {}

# ------------------------------------------------------------------ camera
def scene_params(sc, t):
    """interpolated camera state at absolute time t (u may run past 1 for dissolves)"""
    u = (t - sc["t0"]) / max(1e-6, sc["t1"] - sc["t0"])
    ue = np.clip(u, 0, 1)
    e = ue * ue * (3 - 2 * ue)                       # smoothstep easing
    s = sc["s0"] + (sc["s1"] - sc["s0"]) * e
    p = sc["pan"]
    px = p[0] + (p[2] - p[0]) * e
    py = p[1] + (p[3] - p[1]) * e
    return s, px, py, u


def crop_frame(sc, t):
    s, px, py, u = scene_params(sc, t)
    cw = int(round(MW / s))
    chh = int(round(cw * H / W))
    if chh > MH:
        chh = MH
        cw = int(round(chh * W / H))
    slack_x, slack_y = MW - cw, MH - chh
    x = int(round(slack_x / 2 + px * slack_x))
    y = int(round(slack_y / 2 + py * slack_y))
    # camera shake
    sh = sc.get("shake")
    if sh:
        if sh.get("decay"):
            amp = sh["amp"] * math.exp(-max(0.0, t - sc["t0"]) * sh["decay"])
        else:
            ramp = sh.get("ramp", 1.0)
            amp = sh["amp"] * min(1.0, (t - sc["t0"]) / ramp) * (1.0 if u < .98 else max(0.0, 1 - (u - .98) * 40))
        if amp > 0.05:
            f = sh["f"]
            x += int(round(amp * math.sin(2 * math.pi * f * t + 0.7) +
                           0.45 * amp * math.sin(2 * math.pi * f * 1.7 * t + 2.1)))
            y += int(round(amp * 0.75 * math.sin(2 * math.pi * f * 0.83 * t + 1.9) +
                           0.4 * amp * math.sin(2 * math.pi * f * 2.3 * t)))
    x = max(0, min(slack_x, x))
    y = max(0, min(slack_y, y))
    arr = MASTERS[sc["n"]][y:y + chh, x:x + cw]
    im = Image.fromarray(arr).resize((W, H), Image.BICUBIC)
    # tilt / handheld rotation
    ang = 0.0
    if sc.get("tilt"):
        ang += sc["tilt"] * min(1.0, np.clip(u, 0, 1) * 1.6)
    if sc.get("tilt_jitter"):
        ang += sc["tilt_jitter"] * math.sin(2 * math.pi * 0.9 * t + 1.0) + 0.4 * sc["tilt_jitter"] * math.sin(2 * math.pi * 2.7 * t)
    if sc.get("roll"):
        ang += sc["roll"] * (e := np.clip(u, 0, 1) ** 1.4)
    if abs(ang) > 0.05:
        im = im.rotate(ang, resample=Image.BILINEAR, fillcolor=(0, 0, 0))
    return np.asarray(im, dtype=np.float32) / 255.0


# -------------------------------------------------------------------- grade
def grade(f, g, t):
    out = f
    temp = g.get("temp", 0.0)
    if temp:
        out = out * np.array([1 + temp, 1.0, 1 - temp], dtype=np.float32)
    out = np.clip(out, 0, 1)
    lum = out[..., :1] * .2126 + out[..., 1:2] * .7152 + out[..., 2:3] * .0722
    sat = g.get("sat", 1.0)
    out = lum + (out - lum) * sat
    con = g.get("con", 1.0)
    if con != 1.0:
        out = np.clip((out - .5) * con + .5, 0, 1)
    if g.get("gam", 1.0) != 1.0:
        out = np.clip(out, 0, 1) ** g["gam"]
    out = out * g.get("gain", 1.0)
    v = g.get("vig", .3)
    if v not in VIG_CACHE:
        VIG_CACHE[v] = vignette_map(v)
    out = out * VIG_CACHE[v]
    return np.clip(out, 0, 1)


def add_bloom(f, amount):
    if amount <= 0.01:
        return f
    small = Image.fromarray((np.clip(f, 0, 1) * 255).astype(np.uint8)).resize((W // 8, H // 8), Image.BILINEAR)
    hi = np.asarray(small, dtype=np.float32) / 255.0
    hi = np.clip(hi - 0.62, 0, 1)
    hi = np.asarray(Image.fromarray((hi * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5)),
                    dtype=np.float32) / 255.0
    hi = np.asarray(Image.fromarray((hi * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR),
                    dtype=np.float32) / 255.0
    return np.clip(f + hi * amount, 0, 1)


# ------------------------------------------------------------------- vector
def draw_heartbreak(d, cx0, cy0, s, col):
    def heart(ox, oy, rot):
        pts = []
        for a in np.linspace(0, 2 * np.pi, 60):
            x = 16 * np.sin(a) ** 3
            y = 13 * np.cos(a) - 5 * np.cos(2 * a) - 2 * np.cos(3 * a) - np.cos(4 * a)
            xr = x * math.cos(rot) - y * math.sin(rot)
            yr = x * math.sin(rot) + y * math.cos(rot)
            pts.append((cx0 + ox + xr * s / 34, cy0 + oy - yr * s / 34))
        return pts
    d.polygon(heart(-s * .17, 0, -.22), fill=col)
    d.polygon(heart(s * .17, s * .04, .22), fill=col)
    d.line([(cx0, cy0 - s * .48), (cx0 - s * .07, cy0 - s * .12), (cx0 + s * .09, cy0 + s * .16),
            (cx0 - s * .04, cy0 + s * .48)], fill=(20, 8, 12, 220), width=max(2, int(s * .055)))


def draw_tear(d, cx0, cy0, s, col):
    pts = []
    for a in np.linspace(0, 2 * np.pi, 60):
        x = np.sin(a) * 0.62
        y = -np.cos(a) * (0.55 + 0.5 * (1 + np.cos(a)) / 2 * 0.6)
        pts.append((cx0 + x * s, cy0 + y * s))
    d.polygon(pts, fill=col)


def draw_butterfly(d, cx0, cy0, s, col):
    for sgn in (-1, 1):
        d.ellipse([cx0 + sgn * .05 * s - .52 * s, cy0 - .46 * s, cx0 + sgn * .05 * s + .52 * s, cy0 + .10 * s], fill=col)
        d.ellipse([cx0 + sgn * .04 * s - .40 * s, cy0 + .02 * s, cx0 + sgn * .04 * s + .40 * s, cy0 + .52 * s], fill=col)
    d.rounded_rectangle([cx0 - .05 * s, cy0 - .34 * s, cx0 + .05 * s, cy0 + .36 * s], radius=.05 * s, fill=col)
    for sgn in (-1, 1):
        d.line([(cx0, cy0 - .33 * s), (cx0 + sgn * .18 * s, cy0 - .55 * s)], fill=col, width=max(1, int(s * .045)))


def draw_eye(d, cx0, cy0, s, col):
    d.ellipse([cx0 - .55 * s, cy0 - .30 * s, cx0 + .55 * s, cy0 + .30 * s], outline=col, width=max(2, int(s * .09)))
    d.ellipse([cx0 - .16 * s, cy0 - .16 * s, cx0 + .16 * s, cy0 + .16 * s], fill=col)


def draw_palette(d, cx0, cy0, s, col):
    d.ellipse([cx0 - .55 * s, cy0 - .45 * s, cx0 + .55 * s, cy0 + .45 * s], fill=col)
    for i, (ox, oy) in enumerate([(-.28, -.14), (0, -.26), (.26, -.12), (-.3, .12)]):
        d.ellipse([cx0 + ox * s - .07 * s, cy0 + oy * s - .07 * s, cx0 + ox * s + .07 * s, cy0 + oy * s + .07 * s],
                  fill=(255, 255, 255, 255))
    d.ellipse([cx0 + .14 * s, cy0 + .06 * s, cx0 + .40 * s, cy0 + .32 * s], fill=(0, 0, 0, 0))


def draw_sparkle(d, cx0, cy0, s, col):
    def star(sc, off=0.0):
        pts = []
        for i in range(8):
            a = off + i * np.pi / 4
            rad = sc * s if i % 2 == 0 else sc * s * .34
            pts.append((cx0 + math.cos(a) * rad, cy0 + math.sin(a) * rad))
        d.polygon(pts, fill=col)
    star(1.0)
    star(.42, .25)
    for ox, oy in [(-.62, .38), (.55, -.5)]:
        star(.30, 0.0) if False else d.line([(cx0 + ox * s - .12 * s, cy0 + oy * s), (cx0 + ox * s + .12 * s, cy0 + oy * s)], fill=col, width=max(1, int(s * .06)))


ICON_FN = dict(heartbreak=draw_heartbreak, tear=draw_tear, butterfly=draw_butterfly,
               eye=draw_eye, palette=draw_palette, sparkle=draw_sparkle)


# ------------------------------------------------------------- text overlays
def measure(draw, txt, fnt, tracking):
    total = 0
    for c in txt:
        total += draw.textlength(c, font=fnt) + tracking
    return total - tracking


def build_text_layer(sc):
    """Pre-render this scene's title card, cropped to a small RGBA patch + box."""
    txt = sc.get("text")
    if not txt:
        return None
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = 92
    fnt = ImageFont.truetype(BOLD, size)
    tracking = 3.0
    max_w = W - 260
    while measure(d, txt, fnt, tracking) > max_w and size > 44:
        size -= 4
        fnt = ImageFont.truetype(BOLD, size)
    icon = sc.get("icon")
    icon_s = size * 0.72
    gap = icon_s * 1.55 if icon else 0
    tw = measure(d, txt, fnt, tracking)
    total_w = tw + gap
    x = (W - total_w) / 2
    y = int(H * 0.132)
    warm = (255, 226, 178, 255)
    white = (255, 252, 246, 255)
    # soft dark scrim for legibility over bright / busy plates
    bx0, by0 = x - 96, y - 66
    bx1, by1 = x + total_w + 96, y + size * 1.62
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(scrim).rounded_rectangle([bx0, by0, bx1, by1], radius=int((by1 - by0) * .34),
                                            fill=(7, 6, 10, 105))
    layer = Image.alpha_composite(layer, scrim.filter(ImageFilter.GaussianBlur(22)))
    # text drop shadow
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    sx = x
    if icon:
        ICON_FN[icon](ds, sx + icon_s / 2, y + size * 0.52, icon_s, (0, 0, 0, 160))
        sx += gap
    ds.text((sx + 4, y + 8), txt, font=fnt, fill=(0, 0, 0, 175))
    layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(layer)
    sx = x
    if icon:
        ICON_FN[icon](d, sx + icon_s / 2, y + size * 0.52, icon_s, tuple(list(warm[:3]) + [255]))
        sx += gap
    for c in txt:
        d.text((sx + 2, y + 3), c, font=fnt, fill=(10, 8, 6, 120))
        d.text((sx, y), c, font=fnt, fill=white, stroke_width=3, stroke_fill=(24, 16, 10, 240))
        sx += d.textlength(c, font=fnt) + tracking
    # underline flourish
    uy = y + size * 1.30
    uw = min(360.0, total_w * 0.6)
    d.rounded_rectangle([(W - uw) / 2, uy, (W + uw) / 2, uy + 7], radius=4, fill=tuple(list(warm[:3]) + [200]))
    # crop to the inked area (with margin) so compositing per frame is cheap
    bb = layer.getbbox() or (0, 0, W, H)
    pad = 8
    bb = (max(0, bb[0] - pad), max(0, bb[1] - pad), min(W, bb[2] + pad), min(H, bb[3] + pad))
    return layer.crop(bb), bb


TEXT_LAYER = {sc["n"]: build_text_layer(sc) for sc in SCENES}


def text_alpha(sc, t):
    i0, o1 = sc["t_in"], sc["t_out"]
    if t < i0 or t > o1:
        return 0.0
    a = min(1.0, (t - i0) / 0.30, (o1 - t) / 0.34)
    return float(np.clip(a, 0, 1))


# ------------------------------------------------------------------ particles
Q = 4                                     # FX work at 1/Q resolution, then upscale
QW, QH = W // Q, H // Q


def make_dust(count, seed):
    r2 = np.random.default_rng(seed)
    return [(r2.uniform(0, QW), r2.uniform(0, QH), r2.uniform(0.7, 2.3),
             r2.uniform(4, 16), r2.uniform(0, 6.28), r2.uniform(.15, .55)) for _ in range(count)]


DUST = {sc["n"]: make_dust(sc["dust"], sc["n"] * 37) for sc in SCENES if sc.get("dust")}


def dust_layer(sc, t):
    """drifting motes - drawn small, blurred, upscaled (fast + free softening)"""
    parts = DUST.get(sc["n"])
    if not parts:
        return None
    lay = Image.new("RGBA", (QW, QH), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for (x0, y0, rad, sp, ph, br) in parts:
        x = (x0 + QW * 0.03 * math.sin(2 * math.pi * 0.06 * sp * t + ph)) % QW
        y = (y0 - sp * t * 1.5) % QH
        tw = 0.55 + 0.45 * math.sin(2 * math.pi * (0.4 + sp * 0.05) * t + ph * 2)
        a = int(255 * br * tw * 0.62)
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(255, 240, 210, a))
    lay = lay.filter(ImageFilter.GaussianBlur(0.8))
    return lay.resize((W, H), Image.BILINEAR)


def flare_layer(t, k=1.0):
    lay = Image.new("RGBA", (QW, QH), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    fx = QW * (0.30 + 0.34 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.07 * t)))
    fy = QH * (0.30 + 0.10 * math.sin(2 * math.pi * 0.05 * t + 1))
    rad = QW * 0.31
    d.ellipse([fx - rad, fy - rad * .55, fx + rad, fy + rad * .55], fill=(255, 232, 190, int(52 * k)))
    d.ellipse([fx - rad * .4, fy - rad * .22, fx + rad * .4, fy + rad * .22], fill=(255, 246, 224, int(46 * k)))
    lay = lay.filter(ImageFilter.GaussianBlur(9))
    return lay.resize((W, H), Image.BILINEAR)


# ---------------------------------------------------------------- end card
END_CARD = dict(t0=60.0, t1=62.5,
                title="BARNABY", sub="the mender of broken things")


def render_end_card(t, u):
    bg = np.zeros((H, W, 3), dtype=np.float32)
    g = np.clip(1.0 - r * 0.72, 0, 1) ** 1.8
    bg[..., 0] = (0.055 + 0.075 * g)
    bg[..., 1] = (0.040 + 0.050 * g)
    bg[..., 2] = (0.052 + 0.048 * g)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    a = int(255 * min(1.0, u * 2.6))
    draw_butterfly(d, W / 2, H * 0.40, 120, (255, 208, 150, a))
    f1 = ImageFont.truetype(BOLD, 128)
    f2 = ImageFont.truetype(SERIF, 42)
    ttl = END_CARD["title"]
    w1 = d.textlength(ttl, font=f1)
    d.text(((W - w1) / 2 + 3, H * .50 + 3), ttl, font=f1, fill=(0, 0, 0, a))
    d.text(((W - w1) / 2, H * .50), ttl, font=f1, fill=(255, 248, 236, a))
    sub = END_CARD["sub"]
    w2 = d.textlength(sub, font=f2)
    a2 = int(255 * min(1.0, max(0.0, u * 2.6 - 0.35)))
    d.text(((W - w2) / 2, H * .50 + 172), sub, font=f2, fill=(255, 224, 184, a2))
    d.line([(W / 2 - 150, H * .50 + 130), (W / 2 + 150, H * .50 + 130)], fill=(255, 210, 160, a2), width=3)
    frame = (bg * 255).astype(np.uint8)
    out = Image.fromarray(frame).convert("RGBA")
    out = Image.alpha_composite(out, lay)
    arr = np.asarray(out.convert("RGB"), dtype=np.float32) / 255.0
    return arr


# ------------------------------------------------------------------- frames
def scene_at(t):
    """index of the scene active at time t (len(SCENES) == end card)."""
    for i, s in enumerate(SCENES):
        if t < s["t1"] - 1e-9:
            return i
    return len(SCENES)


def render_frame(t):
    i = scene_at(t)
    if i >= len(SCENES):                                   # end card
        return render_end_card_layer(t)
    sc = SCENES[i]
    # dissolve window centred on the cut
    if i > 0:
        prev = SCENES[i - 1]
        hard = sc.get("cut") == "hard" or prev.get("cut") == "hard" or prev.get("cut") == "fade_in"
        if not hard and abs(t - sc["t0"]) < FADE / 2:
            k = (t - (sc["t0"] - FADE / 2)) / FADE
            k = float(np.clip(k, 0, 1))
            k = k * k * (3 - 2 * k)
            return compose(prev, t) * (1 - k) + compose(sc, t) * k
    return compose(sc, t)


def compose(sc, t):
    if sc["n"] == 99:
        return np.zeros((H, W, 3), np.float32)
    f = crop_frame(sc, t)
    f = grade(f, sc["grade"], t)
    f = add_bloom(f, sc["grade"].get("bloom", 0))
    # impact flash right after the shatter cut
    if sc["n"] == 4:
        dt = t - sc["t0"]
        if dt < 0.20:
            f = np.clip(f + (1 - dt / 0.20) * 0.75, 0, 1)
    f = np.clip(f, 0, 1)
    out = Image.fromarray((f * 255).astype(np.uint8)).convert("RGBA")
    dl = dust_layer(sc, t)
    if dl is not None:
        out = Image.alpha_composite(out, dl)
    if sc.get("flare"):
        out = Image.alpha_composite(out, flare_layer(t, .9 if sc["n"] == 8 else .55))
    ta = text_alpha(sc, t)
    if ta > 0.001 and TEXT_LAYER[sc["n"]] is not None:
        patch, bb = TEXT_LAYER[sc["n"]]
        rise = int((1 - ta) * 24)
        p2 = patch.copy()
        p2.putalpha(patch.getchannel("A").point(lambda v: int(v * ta)))
        out.paste(p2, (bb[0], bb[1] + rise), p2)
    # HUD: chapter marker + progress bar
    d = ImageDraw.Draw(out, "RGBA")
    fm = ImageFont.truetype(MONO, 30)
    lab = f"{sc['n']:02d} / 10"
    d.text((56, 66), lab, font=fm, fill=(255, 255, 255, 96))
    d.rounded_rectangle([52, 60, 52 + 30 + d.textlength(lab, font=fm), 108], radius=10, outline=(255, 255, 255, 60), width=2)
    pw = W * min(1.0, t / STORY_END)
    d.rectangle([0, H - 6, W, H], fill=(255, 255, 255, 26))
    d.rectangle([0, H - 6, pw, H], fill=(255, 226, 180, 150))
    arr = np.asarray(out.convert("RGB"), dtype=np.float32) / 255.0
    # grain
    arr = arr + GRAIN[int(t * FPS) % len(GRAIN)][..., None] / 255.0
    # global fades
    ga = 1.0
    if sc.get("cut") == "fade_in":
        ga = min(ga, np.clip((t - sc["t0"]) / 0.55, 0, 1))
    if t > STORY_END - 0.55 and t < STORY_END + 0.05:
        ga = min(ga, np.clip((STORY_END + 0.05 - t) / 0.6, 0, 1))
    arr = arr * ga
    return np.clip(arr, 0, 1)


def render_end_card_layer(t):
    u = np.clip((t - END_CARD["t0"]) / (END_CARD["t1"] - END_CARD["t0"]), 0, 1)
    f = render_end_card(t, u)
    f = np.clip(f, 0, 1)
    f = f * (1 - max(0.0, (u - 0.75) / 0.25))          # final fade out
    return f


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=int, default=0, help="render N sample stills only")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--out", default=FINAL)
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.preview:
        ts = np.linspace(0, END_TOTAL, args.preview + 1)[1:]
        for i, t in enumerate(ts, 1):
            fr = (render_frame(float(t)) * 255).astype(np.uint8)
            p = os.path.join(BUILD, f"preview_{i:02d}_{t:.1f}s.png")
            Image.fromarray(fr).save(p, optimize=True)
            print("wrote", p)
        return

    total = int(round(END_TOTAL * FPS))
    cmd = [FFMPEG, "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{W}x{H}",
           "-pix_fmt", "rgb24", "-r", str(FPS), "-i", "-"]
    if not args.no_audio and os.path.exists(AUDIO):
        cmd += ["-i", AUDIO, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
    else:
        print("WARNING: no audio track", file=sys.stderr)
    cmd += ["-an"] if args.no_audio or not os.path.exists(AUDIO) else []
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-movflags", "+faststart", "-shortest", args.out]
    print("ffmpeg:", " ".join(cmd[-8:]), flush=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    import time
    t0 = time.time()
    for i in range(total):
        t = i / FPS
        fr = (render_frame(t) * 255).astype(np.uint8)
        proc.stdin.write(fr.tobytes())
        if i % 60 == 0:
            el = time.time() - t0
            print(f"frame {i}/{total}  t={t:5.1f}s  {i / max(el,1e-6):5.1f} fps  "
                  f"eta {((total - i) / max(i / max(el, 1e-6), .1)):5.0f}s", flush=True)
    proc.stdin.close()
    err = proc.stderr.read().decode()[-1500:]
    proc.wait()
    print("ffmpeg exit", proc.returncode)
    if proc.returncode:
        print(err, file=sys.stderr)
        sys.exit(1)
    print("done ->", args.out, "in", round(time.time() - t0, 1), "s")


try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"

if __name__ == "__main__":
    main()
