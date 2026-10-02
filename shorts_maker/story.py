"""Build a finished vertical story video from stills, voice clips and a small JSON script.

You supply the pictures and the recorded lines (from any text-to-speech tool or your own voice);
this module does the rest: slow camera moves, dissolves, word-by-word captions, an original
synthesised sound bed (see ``soundscape.py``), loudness mastering and the final H.264/AAC export.

``story.json`` (paths are relative to the file)::

    {
      "title": "Part 1 - The Door",
      "hook": "PART 1: THE DOOR",                       # banner shown for the first seconds
      "style": {"highlight": "FF3B3B"},                 # optional caption colours
      "grain": 5,                                       # film grain strength, 0 = none
      "scenes": [
        {"image": "images/hall.jpg",
         "duration": 6,                                 # minimum; stretches to fit the voice
         "tension": 0.2,                                # 0..1, how loud the drone is here
         "motion": {"zoom": [1.0, 1.15], "center": [[0.5, 0.5], [0.5, 0.45]], "shake": 0, "flicker": 0},
         "transition": {"type": "fade", "duration": 1.2, "align": "end"},   # how we arrive here (default: cut)
         "lines": [{"audio": "voice/a.wav", "text": "I have lived here for six months.", "at": 0.7},
                   {"audio": "voice/b.wav", "text": "Then I heard a sound.", "gap": 0.5}],
         "sfx": [{"type": "creak", "at": 0.2, "gain": -12}],
         "end_text": {"text": "PART 2?", "at": 2.4, "dim": 0.5}}
      ]
    }
"""
from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from . import soundscape as sx
from .captions import CaptionStyle, ass_color, ass_time, write_ass
from .media import MediaError, decode_audio, run_ffmpeg, write_wav
from .render import DEFAULT_FONT, font_family_name
from .util import slugify

PLAY_W, PLAY_H = 1080, 1920  # captions are laid out on this canvas whatever the output size is
CAPTION_Y = 1290  # inside the area that YouTube's buttons and title do not cover
HOOK_Y = 330
END_Y = 1250
GHOST_Y = 1400  # whispered words: lower, over the darker part of the picture
NARRATOR_DB = -20.0  # average level of spoken words before mastering
WHISPER_DB = -25.0
TARGET_LUFS = -15.0
PEAK_CEILING_DB = -2.0  # sample peak after the limiter (about -1.5 dBTP)
STREAM_PAD = 2  # extra frames at the end of every scene stream (see plan_story)

CUE_KINDS = {"creak", "click", "whoosh", "riser", "heartbeat", "boom", "dropout"}
TRANSITIONS = {"fade"}  # cross-dissolve; anything else is a hard cut
_ALIGN = {"start": 0.0, "center": 0.5, "end": 1.0}
_PHRASE_END = re.compile(r"[,;:.!?\u2026]$")


@dataclass
class StoryOptions:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 23
    preset: str = "medium"
    captions: bool = True
    sound: bool = True  # False: narration only, no drone / heartbeat / effects
    font_path: Optional[str] = None
    seed: int = 7
    preview: Optional[float] = None  # render only the first N seconds (quick look)


@dataclass
class Line:
    text: str
    style: str  # "narrator" | "whisper"
    at: float  # absolute start of the (silence-trimmed) clip, seconds
    audio: np.ndarray  # processed mono at soundscape.SR
    spans: List[Tuple[float, float]]  # speech spans relative to ``at``
    words: List[Dict[str, Any]]  # absolute word times

    @property
    def end(self) -> float:
        return self.at + len(self.audio) / sx.SR


@dataclass
class Cue:
    kind: str
    at: float
    params: Dict[str, Any]


@dataclass
class Scene:
    index: int
    image: Path
    start: float
    dur: float
    start_frame: int
    frames: int
    motion: Dict[str, Any]
    tension: float
    lines: List[Line]
    cues: List[Cue]
    end_text: Optional[Dict[str, Any]]
    trans_type: str = "cut"
    trans_frames: int = 0
    head_frames: int = 0  # frames this scene is shown before its nominal start (dissolve that ends on the cut)
    stream_frames: int = 0


@dataclass
class Plan:
    title: str
    hook: Optional[str]
    scenes: List[Scene]
    total: float
    fps: int
    style: Dict[str, Any] = field(default_factory=dict)
    grain: float = 5.0

    @property
    def total_frames(self) -> int:
        return int(round(self.total * self.fps))


# --------------------------------------------------------------------------- words
def _weight(word: str) -> float:
    letters = re.sub(r"[^A-Za-z']", "", word)
    vowels = len(re.findall(r"[aeiouy]+", letters.lower()))
    return 0.7 * max(1, vowels) + 0.12 * len(letters) + 0.25


def _phrases(words: List[str]) -> List[List[str]]:
    out: List[List[str]] = []
    cur: List[str] = []
    for w in words:
        cur.append(w)
        if _PHRASE_END.search(w):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def align_words(text: str, spans: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
    """Give every word of ``text`` a start/end time inside the clip's speech spans.

    Text is split into phrases at punctuation. When the number of phrases equals the number of
    audible stretches (a pause at every comma/full stop) they are matched one to one; otherwise
    the words are spread over the whole speech. Within a phrase, time is shared out by word length.
    """
    words = text.split()
    if not words or not spans:
        return []
    phrases = _phrases(words)
    if len(phrases) != len(spans):
        phrases, spans = [words], [(spans[0][0], spans[-1][1])]
    out: List[Dict[str, Any]] = []
    for phrase, (a, b) in zip(phrases, spans):
        weights = [_weight(w) for w in phrase]
        total = sum(weights)
        t = a
        for token, wt in zip(phrase, weights):
            d = (b - a) * wt / total
            out.append({"word": token, "start": t, "end": t + d})
            t += d
    return out


def _insert_pauses(audio: np.ndarray, spans, pauses: Dict[int, float]):
    """Lengthen the silence after speech span k by ``pauses[k]`` seconds (for pacing)."""
    cuts = sorted(
        ((spans[k][1] + spans[k + 1][0]) / 2.0, extra)
        for k, extra in pauses.items()
        if 0 <= k < len(spans) - 1 and extra > 0
    )
    pieces, last = [], 0
    for t, extra in cuts:
        i = int(t * sx.SR)
        pieces += [audio[last:i], np.zeros(int(extra * sx.SR), np.float32)]
        last = i
    pieces.append(audio[last:])
    shifted = [(a + sum(e for t, e in cuts if t <= a + 1e-6), b + sum(e for t, e in cuts if t <= a + 1e-6)) for a, b in spans]
    return np.concatenate(pieces).astype(np.float32), shifted


# --------------------------------------------------------------------------- planning
def _file(base: Path, rel: Any, what: str) -> Path:
    if not rel:
        raise ValueError(f"{what}: path missing in story.json")
    p = (base / str(rel)).expanduser()
    if not p.is_file():
        raise MediaError(f"{what}: file not found: {p}")
    return p


def load_line(base: Path, spec: Dict[str, Any], at: float) -> Line:
    path = _file(base, spec.get("audio"), "voice line")
    text = str(spec.get("text") or "").strip()
    style = str(spec.get("style") or "narrator")
    if style not in ("narrator", "whisper"):
        raise ValueError(f"Unknown line style {style!r} (use 'narrator' or 'whisper')")
    raw = decode_audio(path, sx.SR)
    audio, spans = sx.trim_to_speech(raw)
    if not spans:
        raise MediaError(f"No speech found in {path}")
    pauses = {int(k): float(v) for k, v in (spec.get("pauses") or {}).items()}
    if pauses:
        audio, spans = _insert_pauses(audio, spans, pauses)
    words = [dict(w, start=w["start"] + at, end=w["end"] + at) for w in align_words(text, spans)] if style == "narrator" else []
    if style == "whisper":
        audio = sx.level_to(sx.whisperise(audio), WHISPER_DB + float(spec.get("gain_db", 0.0)), spans)
    else:
        audio = sx.level_to(sx.narrator(audio), NARRATOR_DB + float(spec.get("gain_db", 0.0)), spans)
    return Line(text=text, style=style, at=at, audio=audio, spans=spans, words=words)


def plan_story(spec: Dict[str, Any], base: Path, opts: StoryOptions) -> Plan:
    specs = spec.get("scenes")
    if not isinstance(specs, list) or not specs:
        raise ValueError("story.json needs a non-empty 'scenes' list")
    fps = opts.fps
    scenes: List[Scene] = []
    start_frame = 0
    for i, sc in enumerate(specs):
        image = _file(base, sc.get("image"), f"scene {i + 1} image")
        start = start_frame / fps
        lead, tail = float(sc.get("lead", 0.6)), float(sc.get("tail", 0.6))
        lines: List[Line] = []
        prev_end: Optional[float] = None
        for ln in sc.get("lines") or []:
            at_rel = ln.get("at")
            if at_rel is None:
                at_rel = lead if prev_end is None else prev_end + float(ln.get("gap", 0.45))
            line = load_line(base, ln, start + float(at_rel))
            lines.append(line)
            prev_end = float(at_rel) + len(line.audio) / sx.SR
        need = prev_end + tail if prev_end is not None else 0.0
        dur = max(float(sc.get("duration", 0.0)), need, 1.0 / fps)
        frames = max(1, math.ceil(dur * fps - 1e-6))
        dur = frames / fps

        tr = sc.get("transition") or {}
        ttype = "cut" if i == 0 else str(tr.get("type", "cut"))
        if ttype != "cut" and ttype not in TRANSITIONS:
            raise ValueError(f"scene {i + 1}: unknown transition {ttype!r} (use cut or fade)")
        trans_frames = head = 0
        if ttype != "cut":
            trans_frames = max(2, int(round(float(tr.get("duration", 0.5)) * fps)))
            align = str(tr.get("align", "start"))
            if align not in _ALIGN:
                raise ValueError(f"scene {i + 1}: transition align must be start, center or end")
            head = int(round(_ALIGN[align] * trans_frames))
            if scenes and head > scenes[-1].frames + scenes[-1].head_frames:
                raise ValueError(f"scene {i + 1}: the transition is longer than the scene before it")

        cues: List[Cue] = []
        for c in sc.get("sfx") or []:
            kind = c.get("type")
            if kind not in CUE_KINDS:
                raise ValueError(f"scene {i + 1}: unknown sfx type {kind!r} (use {', '.join(sorted(CUE_KINDS))})")
            at = float(c.get("at", 0.0))
            cues.append(Cue(kind, start + (at if at >= 0 else dur + at), {k: v for k, v in c.items() if k not in ("type", "at")}))

        end_text = None
        if sc.get("end_text"):
            et = dict(sc["end_text"])
            at = float(et.get("at", 0.0))
            et["at"] = start + (at if at >= 0 else dur + at)
            end_text = et

        scenes.append(
            Scene(
                index=i, image=image, start=start, dur=dur, start_frame=start_frame, frames=frames,
                motion=dict(sc.get("motion") or {}), tension=float(sc.get("tension", min(1.0, 0.2 + 0.2 * i))),
                lines=lines, cues=cues, end_text=end_text, trans_type=ttype, trans_frames=trans_frames, head_frames=head,
            )
        )
        start_frame += frames

    for i, sc in enumerate(scenes):
        nxt = scenes[i + 1] if i + 1 < len(scenes) else None
        # +STREAM_PAD: ffmpeg's overlay drops a stream's final frame, so run each stream a little long;
        # the next scene is drawn opaquely over those frames (and the last one runs past the end).
        sc.stream_frames = sc.head_frames + sc.frames + ((nxt.trans_frames - nxt.head_frames) if nxt else 0) + STREAM_PAD
    hook = str(spec.get("hook") or "").strip() or None
    return Plan(
        title=str(spec.get("title") or "story"), hook=hook, scenes=scenes,
        total=start_frame / fps, fps=fps, style=dict(spec.get("style") or {}), grain=float(spec.get("grain", 5.0)),
    )


# --------------------------------------------------------------------------- sound
def _render_cue(cue: Cue, rng, hall: np.ndarray) -> Tuple[np.ndarray, float]:
    p = cue.params
    gain = sx.db(float(p.get("gain", -12.0)))
    pan = float(p.get("pan", 0.0))
    kind = cue.kind
    if kind == "creak":
        x = sx.creak(float(p.get("dur", 1.5)), rng)
    elif kind == "click":
        x = sx.click(rng)
    elif kind == "whoosh":
        x = sx.whoosh(float(p.get("dur", 1.6)), rng)
    elif kind == "riser":
        x = sx.riser(float(p.get("dur", 2.0)), rng)
    elif kind == "heartbeat":
        bpm = [float(v) for v in p.get("bpm", [64, 90])]
        x = sx.heartbeat(float(p.get("dur", 10.0)), bpm[0], bpm[-1], rng)
    else:  # boom: dry hit plus a long dark room
        b = sx.boom(float(p.get("dur", 2.4)), rng)
        wet = sx.convolve(b, hall) * sx.db(-6.0)
        wet[: len(b)] += np.stack([b, b], axis=1)
        return wet * gain, 0.0
    return x * gain, pan


def build_soundtrack(plan: Plan, opts: StoryOptions) -> np.ndarray:
    """Stereo float mix of voices, whispers, drone, heartbeat and effects (not yet mastered)."""
    n = int(round(plan.total * sx.SR))
    t = np.arange(n) / sx.SR
    rng = np.random.default_rng(opts.seed)
    mix = np.zeros((n, 2), np.float32)
    voice = np.zeros(n, np.float32)
    room, hall = sx.make_ir(0.8, rng), sx.make_ir(2.6, rng, predelay=0.03)

    for sc in plan.scenes:
        for ln in sc.lines:
            if ln.style == "whisper":  # near, a long dark tail, and a far echo off to the right
                sx.add_at(mix, ln.audio, ln.at, gain=sx.db(-4.0), pan=-0.15)
                sx.add_at(mix, sx.convolve(ln.audio, hall), ln.at, gain=sx.db(-5.0))
                echo = sx.lowpass(ln.audio, 3200.0, 2)
                sx.add_at(mix, echo, ln.at + 0.65, gain=sx.db(-9.0), pan=0.55)
                sx.add_at(mix, sx.convolve(echo, hall), ln.at + 0.65, gain=sx.db(-8.0))
            else:
                sx.add_at(mix, ln.audio, ln.at)
                sx.add_at(mix, sx.convolve(ln.audio, room), ln.at, gain=sx.db(-16.0))  # a touch of room
                sx.add_at(voice, ln.audio, ln.at)

    if opts.sound:
        pts = [(sc.start, sc.tension) for sc in plan.scenes] + [(plan.total, plan.scenes[-1].tension)]
        level = np.power(10.0, (-37.0 + 10.0 * sx.curve(pts, t)) / 20.0)
        holes = sx.dropout_curve(
            [(c.at, float(c.params.get("dur", 1.0)), float(c.params.get("fade", 0.3)))
             for sc in plan.scenes for c in sc.cues if c.kind == "dropout"], t)
        duck = sx.duck_curve(voice, -7.0)
        mix += (sx.drone(plan.total, rng) * (level * duck * holes)[:, None]).astype(np.float32)
        mix += (sx.room_tone(plan.total, rng) * (sx.db(-50.0) * holes)[:, None]).astype(np.float32)
        for sc in plan.scenes:
            for c in sc.cues:
                if c.kind != "dropout":
                    x, pan = _render_cue(c, rng, hall)
                    sx.add_at(mix, x, c.at, pan=pan)
    return mix


def measure_integrated(path: Path) -> Tuple[float, float]:
    """Integrated loudness (LUFS) and true peak (dBTP) of an audio file, via ffmpeg's loudnorm analysis."""
    proc = run_ffmpeg(
        ["-i", path, "-vn", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], loglevel="info"
    )
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr.decode("utf-8", "replace"), re.S)
    if not match:
        raise MediaError("Could not measure loudness of the soundtrack")
    vals = json.loads(match.group(0))
    return float(vals["input_i"]), float(vals["input_tp"])


def master(mix: np.ndarray, tmp: Path) -> Tuple[np.ndarray, Dict[str, float]]:
    """Gain to TARGET_LUFS, then a look-ahead limiter; re-measured so the result lands within ~0.3 LU."""
    wav = tmp / "premaster.wav"
    write_wav(wav, mix)
    loud, _ = measure_integrated(wav)
    if loud < -60:  # silent: nothing to normalise
        return mix, {"lufs": loud, "true_peak": -99.0, "gain_db": 0.0, "limiter_db": 0.0}
    gain_db = TARGET_LUFS - loud
    ceiling = sx.db(PEAK_CEILING_DB)
    out = sx.limit(mix * sx.db(gain_db), ceiling)
    lufs = tp = 0.0
    for _ in range(3):
        write_wav(wav, out)
        lufs, tp = measure_integrated(wav)
        if abs(lufs - TARGET_LUFS) <= 0.3:
            break
        gain_db += TARGET_LUFS - lufs
        out = sx.limit(mix * sx.db(gain_db), ceiling)
    reduction = sx.to_db(float(np.abs(mix * sx.db(gain_db)).max())) - sx.to_db(float(np.abs(out).max()))
    return out, {"lufs": lufs, "true_peak": tp, "gain_db": gain_db, "limiter_db": max(0.0, reduction)}


# --------------------------------------------------------------------------- captions
def _ass_text(text: str) -> str:
    return text.replace("\\", "").replace("{", "").replace("}", "").replace("...", "\u2026").strip()


def build_ass(plan: Plan, opts: StoryOptions, tmp: Path) -> int:
    """Write captions.ass (and a fonts/ folder next to it); returns the number of events."""
    font_src = Path(opts.font_path) if opts.font_path else DEFAULT_FONT
    if not font_src.is_file():
        raise MediaError(f"Font file not found: {font_src}")
    (tmp / "fonts").mkdir(exist_ok=True)
    shutil.copy(font_src, tmp / "fonts" / font_src.name)

    kw: Dict[str, Any] = {}
    for key in ("highlight", "primary", "outline_color", "hook_box", "hook_text"):
        if key in plan.style:
            ass_color(str(plan.style[key]))
            kw[key] = str(plan.style[key])
    for key in ("font_size", "words_per_caption", "max_chars", "hook_font_size"):
        if key in plan.style:
            kw[key] = int(plan.style[key])
    if "uppercase" in plan.style:
        kw["uppercase"] = bool(plan.style["uppercase"])
    style = CaptionStyle(font_path=str(font_src), font_name=font_family_name(font_src), **kw)

    words = [w for sc in plan.scenes for ln in sc.lines for w in ln.words] if opts.captions else []
    extra: List[str] = []
    under: List[str] = []
    cx = PLAY_W // 2
    for sc in plan.scenes:
        if opts.captions:
            for ln in sc.lines:
                if ln.style == "whisper" and ln.text:  # ghostly, lower-case, fades in and out
                    t0, t1 = ln.at + ln.spans[0][0] - 0.05, ln.at + ln.spans[-1][1] + 0.9
                    extra.append(
                        f"Dialogue: 1,{ass_time(t0)},{ass_time(t1)},Caption,,0,0,0,,"
                        f"{{\\an5\\pos({cx},{GHOST_Y})\\fs124\\1c&HF0F0F0&\\bord7\\blur2\\fad(250,700)}}{_ass_text(ln.text)}"
                    )
        et = sc.end_text
        if et:
            t0, t1 = float(et["at"]), plan.total
            grow = int(max(0.2, t1 - t0) * 1000)
            txt = _ass_text(str(et.get("text", "")))
            dim = float(et.get("dim", 0.0))
            if dim > 0:
                alpha = int(round((1.0 - min(1.0, dim)) * 255))
                under.append(
                    f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},Caption,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H000000&"
                    f"\\alpha&HFF&\\t(0,600,\\alpha&H{alpha:02X}&)\\p1}}m 0 0 l {PLAY_W} 0 {PLAY_W} {PLAY_H} 0 {PLAY_H}{{\\p0}}"
                )
            pop = f"\\fscx94\\fscy94\\t(0,{grow},\\fscx106\\fscy106)"
            extra.append(  # black halo underneath keeps the text readable on any picture
                f"Dialogue: 2,{ass_time(t0)},{ass_time(t1)},Caption,,0,0,0,,{{\\an5\\pos({cx},{END_Y})\\fs190\\bord24\\shad0"
                f"\\blur9\\1c&H000000&\\3c&H000000&\\fad(120,0){pop}}}{txt}"
            )
            extra.append(
                f"Dialogue: 3,{ass_time(t0)},{ass_time(t1)},Caption,,0,0,0,,{{\\an5\\pos({cx},{END_Y})\\fs190\\bord6\\shad0"
                f"\\1c&HFFFFFF&\\3c&H1414D0&\\fad(120,0){pop}}}{txt}"
            )
    return write_ass(
        tmp / "captions.ass", words, style, width=PLAY_W, height=PLAY_H, clip_len=plan.total,
        caption_y=CAPTION_Y, hook=plan.hook, hook_y=HOOK_Y, extra_events=extra, underlay_events=under,
    )


# --------------------------------------------------------------------------- pictures
def prescale(image: Path, out: Path, width: int, height: int) -> None:
    """Cover-fit the picture to twice the output size (so camera moves stay smooth) and save as PNG."""
    from PIL import Image, ImageOps

    with Image.open(image) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = 2 * width, 2 * height
        scale = max(w / im.width, h / im.height)
        im = im.resize((max(w, int(round(im.width * scale))), max(h, int(round(im.height * scale)))), Image.LANCZOS)
        left, top = (im.width - w) // 2, (im.height - h) // 2
        im.crop((left, top, left + w, top + h)).save(out, "PNG", compress_level=1)


def _ease(kind: str, p: str) -> str:
    if kind == "linear":
        return p
    if kind == "in":
        return f"pow({p},2.2)"
    if kind == "out":
        return f"(1-pow(1-{p},2))"
    return f"(3*pow({p},2)-2*pow({p},3))"


def scene_filter(i: int, sc: Scene, opts: StoryOptions) -> str:
    """One scene: a slow push/pan (zoompan) with optional hand-held shake and a failing-light flicker.

    The stream is moved to its place on the timeline in whole frames (its timebase is 1/fps after the
    fps filter), so nothing depends on floating-point seconds and frames can never drift or drop.
    """
    m, n = sc.motion, sc.stream_frames
    z0, z1 = (float(v) for v in (m.get("zoom") or [1.0, 1.12]))
    center = m.get("center") or [[0.5, 0.5], [0.5, 0.5]]
    (cx0, cy0), (cx1, cy1) = center[0], center[-1]
    p = f"min(on/{max(n - 1, 1)},1)"
    zoom = f"{z0}+({z1}-{z0})*{_ease(str(m.get('ease', 'smooth')), p)}"
    shake = float(m.get("shake", 0.0)) * 2.0  # the picture is twice the output size
    sh_x = f"+{shake:.2f}*(sin(on*0.83)+0.6*sin(on*2.1+1.3))" if shake else ""
    sh_y = f"+{shake:.2f}*(sin(on*0.67+0.5)+0.6*sin(on*1.9+2.4))" if shake else ""
    x = f"({cx0}+({cx1}-{cx0})*{p})*iw-iw/zoom/2{sh_x}"
    y = f"({cy0}+({cy1}-{cy0})*{p})*ih-ih/zoom/2{sh_y}"
    flick = float(m.get("flicker", 0.0))
    eq = f",eq=brightness='-0.30*{flick}*gt(sin(t*2.3+{i})*sin(t*5.1+1),0.5)*gt(sin(t*83),0)':eval=frame" if flick else ""
    arrive = (  # dissolve in: fade the picture's alpha up over the scene before it
        f",format=yuva420p,fade=t=in:s=0:n={sc.trans_frames}:alpha=1" if sc.trans_frames > 0 else ",format=yuv420p"
    )
    return (
        f"[{i}:v]scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={n}:s={opts.width}x{opts.height}:fps={opts.fps},"
        f"unsharp=5:5:0.5:5:5:0.0{eq},setsar=1,fps={opts.fps},settb=1/{opts.fps}{arrive},"
        f"setpts=PTS+{sc.start_frame - sc.head_frames}[v{i}]"
    )


def video_graph(plan: Plan, opts: StoryOptions, ass: bool) -> str:
    """Every scene is laid over a black base of exactly the right length (no concat/xfade joins)."""
    n = len(plan.scenes)
    parts = [scene_filter(i, sc, opts) for i, sc in enumerate(plan.scenes)]
    base_secs = (plan.total_frames - 0.5) / plan.fps  # half a frame short of the next frame boundary
    parts.append(f"color=c=black:s={opts.width}x{opts.height}:r={plan.fps}:d={base_secs:.5f},format=yuv420p[b0]")
    for i in range(n):
        parts.append(f"[b{i}][v{i}]overlay=eof_action=pass:format=auto[b{i + 1}]")
    tail = "vignette=angle=PI/4.5"
    if plan.grain > 0:
        tail += f",noise=alls={plan.grain:g}:allf=t"
    if ass:
        tail += ",ass=captions.ass:fontsdir=fonts"
    fade_in, fade_out = int(round(0.6 * plan.fps)), int(round(0.55 * plan.fps))
    tail += f",fade=t=in:s=0:n={fade_in},fade=t=out:s={max(0, plan.total_frames - fade_out)}:n={fade_out},format=yuv420p"
    parts.append(f"[b{n}]{tail}[v]")
    return ";".join(parts)


# --------------------------------------------------------------------------- the whole thing
def build_story(spec_path, out_dir, opts: Optional[StoryOptions] = None, log: Callable[[str], None] = print) -> Dict[str, Any]:
    opts = opts or StoryOptions()
    spec_path = Path(spec_path).resolve()
    if not spec_path.is_file():
        raise FileNotFoundError(f"Story file not found: {spec_path}")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{spec_path.name} is not valid JSON: {exc}") from exc
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    plan = plan_story(spec, spec_path.parent, opts)
    log(f"Planned {len(plan.scenes)} scenes, {plan.total:.1f}s:")
    for sc in plan.scenes:
        log(f"  scene {sc.index + 1}: {sc.start:5.1f}s - {sc.start + sc.dur:5.1f}s  {sc.image.name}  ({len(sc.lines)} voice lines)")

    out_path = (out_dir / f"{slugify(plan.title, 60, 'story')}.mp4").resolve()
    with tempfile.TemporaryDirectory(prefix="story_") as tmp_name:
        tmp = Path(tmp_name)
        log("Mixing sound...")
        mix, loud = master(build_soundtrack(plan, opts), tmp)
        wav = tmp / "soundtrack.wav"
        write_wav(wav, mix)
        log(f"  {loud['lufs']:.1f} LUFS, {loud['true_peak']:.1f} dBTP (limiter took up to {loud['limiter_db']:.1f} dB)")

        use_ass = opts.captions or bool(plan.hook) or any(sc.end_text for sc in plan.scenes)
        if use_ass:
            build_ass(plan, opts, tmp)
        for i, sc in enumerate(plan.scenes):
            prescale(sc.image, tmp / f"scene{i}.png", opts.width, opts.height)

        graph = video_graph(plan, opts, use_ass)
        n = len(plan.scenes)
        graph += f";[{n}:a]aresample=48000,afade=t=in:st=0:d=0.04,afade=t=out:st={max(0.0, plan.total - 0.7):.3f}:d=0.7[a]"
        cmd: List[Any] = ["-y"]
        for i in range(n):
            cmd += ["-i", tmp / f"scene{i}.png"]
        length = min(plan.total, opts.preview) if opts.preview else plan.total
        cmd += ["-i", wav, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", f"{length:.3f}"]
        cmd += [
            "-c:v", "libx264", "-preset", opts.preset, "-crf", opts.crf, "-maxrate", "10M", "-bufsize", "20M",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", opts.fps, "-g", opts.fps * 2,
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-map_metadata", "-1", "-map_chapters", "-1", out_path,
        ]
        log("Rendering video...")
        run_ffmpeg(cmd, cwd=tmp)

    size_mb = out_path.stat().st_size / 1e6
    log(f"Done in {time.time() - t0:.0f}s: {out_path} ({plan.total:.1f}s, {size_mb:.1f} MB)")
    return {
        "file": str(out_path), "duration": round(plan.total, 2), "size_mb": round(size_mb, 2),
        "lufs": round(loud["lufs"], 1), "true_peak": round(loud["true_peak"], 1),
        "scenes": [{"start": round(s.start, 2), "end": round(s.start + s.dur, 2), "image": s.image.name} for s in plan.scenes],
    }
