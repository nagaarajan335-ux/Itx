"""Cut a clip, reframe it to 9:16, burn in captions, normalise loudness, export."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .captions import CaptionStyle, write_ass
from .media import MediaError, MediaInfo, probe, run_ffmpeg
from .transcript import Transcript, words_of
from .util import fmt_ts, slugify, with_timestamp

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
DEFAULT_FONT = FONT_DIR / "Poppins-ExtraBold.ttf"

LOUDNESS_TARGET = "I=-14:TP=-1.5:LRA=11"  # YouTube normalises playback to about -14 LUFS


@dataclass
class RenderOptions:
    layout: str = "blur"  # "blur": whole frame over a blurred backdrop | "crop": fill the screen
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 21
    preset: str = "veryfast"
    lead_in: float = 0.15  # seconds of room before the first word
    tail: float = 0.45  # seconds after the last word
    video_pos: float = 0.40  # blur layout: where the video sits (0 = top, 1 = bottom of the free space)
    normalize_audio: bool = True
    captions: bool = True
    hook: bool = True
    font_path: Optional[str] = None
    style: CaptionStyle = field(default_factory=CaptionStyle)


# --------------------------------------------------------------------------- geometry
def snap_clip(start: float, end: float, words: List[Dict[str, Any]], duration: float, max_shift: float = 0.8):
    """Nudge the cut points so no word is chopped in half and there is no dead air at the start."""
    if words:
        for w in words:
            if w["end"] > start:
                if abs(w["start"] - start) <= max_shift:
                    start = w["start"]
                break
        for w in reversed(words):
            if w["start"] < end:
                if w["end"] > end and w["end"] - end <= max_shift:
                    end = w["end"]
                break
    start = max(0.0, start)
    if duration:
        end = min(end, duration)
    return start, end


def plan_layout(info: MediaInfo, opts: RenderOptions, focus: float = 0.5) -> Dict[str, Any]:
    """Pixel positions for the chosen layout (all numbers are for the output canvas)."""
    W, H = opts.width, opts.height
    layout = "crop" if info.aspect <= 0.7 else opts.layout  # already vertical: just fill the screen
    if layout == "blur":
        fg_h = int(round(W / info.aspect / 2.0)) * 2
        top = int(round(max(0, H - fg_h) * opts.video_pos))
        return {
            "layout": "blur",
            "fg_h": fg_h,
            "top": top,
            "caption_y": min(max(int(H * 0.64), top + fg_h + 115), int(H * 0.70)),
            "hook_y": max(310, (230 + top - 40) // 2),
        }
    if info.aspect >= W / H:  # wider than 9:16: scale to full height, slide a window sideways
        sw, sh = int(round(H * info.aspect)), H
        x, y = int(round((sw - W) * min(1.0, max(0.0, focus)))), 0
    else:  # taller than 9:16: scale to full width, crop top/bottom evenly
        sw, sh = W, int(round(W / info.aspect))
        x, y = 0, (sh - H) // 2
    return {"layout": "crop", "sw": sw, "sh": sh, "x": x, "y": y, "caption_y": int(H * 0.64), "hook_y": 360}


def build_filtergraph(plan: Dict[str, Any], opts: RenderOptions, *, ass: bool) -> str:
    W, H = opts.width, opts.height
    pre = f"fps={opts.fps},scale=trunc(iw*sar):ih,setsar=1"
    burn = ",ass=captions.ass:fontsdir=fonts" if ass else ""
    if plan["layout"] == "blur":
        bw, bh = W // 4, H // 4  # blur a small copy, then scale up: fast and just as soft
        return (
            f"[0:v]{pre},split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
            f"gblur=sigma=5:steps=2,scale={W}:{H}:flags=bicubic,eq=brightness=-0.12:saturation=1.25[bg];"
            f"[fgsrc]scale={W}:{plan['fg_h']}:flags=lanczos[fg];"
            f"[bg][fg]overlay=x=0:y={plan['top']}:format=auto{burn},format=yuv420p[v]"
        )
    return (
        f"[0:v]{pre},scale={plan['sw']}:{plan['sh']}:flags=lanczos,"
        f"crop={W}:{H}:{plan['x']}:{plan['y']}{burn},format=yuv420p[v]"
    )


# --------------------------------------------------------------------------- audio
def measure_loudness(source: Path, start: float, dur: float) -> Optional[str]:
    """First loudnorm pass; returns the second-pass filter string (linear, accurate) or None."""
    proc = run_ffmpeg(
        ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", source, "-vn",
         "-af", f"loudnorm={LOUDNESS_TARGET}:print_format=json", "-f", "null", "-"],
        loglevel="info",
    )
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr.decode("utf-8", "replace"), re.S)
    if not match:
        return None
    try:
        m = json.loads(match.group(0))
        vals = {k: float(m[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, KeyError):
        return None
    if vals["input_i"] < -60:  # effectively silent: nothing sensible to normalise
        return None
    return (
        f"loudnorm={LOUDNESS_TARGET}:measured_I={vals['input_i']}:measured_TP={vals['input_tp']}:"
        f"measured_LRA={vals['input_lra']}:measured_thresh={vals['input_thresh']}:"
        f"offset={vals['target_offset']}:linear=true"
    )


def audio_graph(dur: float, loudnorm: Optional[str]) -> str:
    chain = ([loudnorm] if loudnorm else []) + [
        "aresample=48000",
        "afade=t=in:st=0:d=0.05",
        f"afade=t=out:st={max(0.0, dur - 0.30):.3f}:d=0.30",
    ]
    return "[0:a]" + ",".join(chain) + "[a]"


# --------------------------------------------------------------------------- one clip
def font_family_name(path) -> str:
    """Name libass should use to find this font file."""
    try:
        from PIL import ImageFont

        family, style = ImageFont.truetype(str(path), 20).getname()
    except Exception:
        return Path(path).stem.replace("-", " ")
    if style and style.lower() not in {"regular", "normal", "book", "roman"}:
        return f"{family} {style}"
    return family


def render_clip(
    source,
    clip: Dict[str, Any],
    words: List[Dict[str, Any]],
    out_path,
    opts: RenderOptions,
    info: MediaInfo,
) -> Dict[str, Any]:
    source, out_path = Path(source).resolve(), Path(out_path).resolve()
    start, end = snap_clip(float(clip["start"]), float(clip["end"]), words, info.duration)
    s0 = max(0.0, start - opts.lead_in)
    e0 = end + opts.tail if not info.duration else min(info.duration, end + opts.tail)
    dur = e0 - s0
    if dur < 1.0:
        raise MediaError(f"Clip {fmt_ts(start)}-{fmt_ts(end)} is shorter than 1 second.")

    plan = plan_layout(info, opts, focus=float(clip.get("focus", 0.5)))
    hook_text = str(clip.get("hook") or "").strip() if opts.hook else ""
    clip_words = [
        {"word": w["word"], "start": max(0.0, w["start"] - s0), "end": min(dur, w["end"] - s0)}
        for w in words
        if w["end"] > s0 and w["start"] < e0
    ]
    use_ass = (opts.captions and bool(clip_words)) or bool(hook_text)

    with tempfile.TemporaryDirectory(prefix="shorts_") as tmp_name:
        tmp = Path(tmp_name)
        if use_ass:
            font_src = Path(opts.font_path) if opts.font_path else DEFAULT_FONT
            if not font_src.is_file():
                raise MediaError(f"Font file not found: {font_src}")
            (tmp / "fonts").mkdir()
            shutil.copy(font_src, tmp / "fonts" / font_src.name)
            style = replace(opts.style, font_path=str(font_src), font_name=font_family_name(font_src))
            write_ass(
                tmp / "captions.ass",
                clip_words if opts.captions else [],
                style,
                width=opts.width,
                height=opts.height,
                clip_len=dur,
                caption_y=plan["caption_y"],
                hook=hook_text or None,
                hook_y=plan["hook_y"],
            )

        graph = build_filtergraph(plan, opts, ass=use_ass)
        cmd: List[Any] = ["-y", "-ss", f"{s0:.3f}", "-t", f"{dur:.3f}", "-i", source]
        if info.has_audio:
            loud = measure_loudness(source, s0, dur) if opts.normalize_audio else None
            graph += ";" + audio_graph(dur, loud)
        cmd += ["-filter_complex", graph, "-map", "[v]"]
        cmd += ["-map", "[a]"] if info.has_audio else ["-an"]
        cmd += [
            "-c:v", "libx264", "-preset", opts.preset, "-crf", opts.crf, "-maxrate", "12M", "-bufsize", "24M",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-g", opts.fps * 2, "-movflags", "+faststart",
        ]
        if info.has_audio:
            cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
        cmd += ["-map_metadata", "-1", "-map_chapters", "-1", out_path]
        run_ffmpeg(cmd, cwd=tmp)

    return {
        "source_start": round(start, 2),
        "source_end": round(end, 2),
        "duration": round(dur, 2),
        "layout": plan["layout"],
        "size_mb": round(out_path.stat().st_size / 1e6, 2),
    }


# --------------------------------------------------------------------------- batch + report
def build_description(
    clip: Dict[str, Any], hook: str, start: float, source_url: Optional[str], credit: Optional[str], hashtags: str
) -> str:
    lines = [str(clip.get("description") or hook).strip()]
    if source_url:
        lines += ["", "Watch the full video: " + with_timestamp(source_url, start)]
    if credit:
        lines += ["", credit.strip()]
    if hashtags:
        lines += ["", hashtags.strip()]
    return "\n".join(lines).strip()


def write_report(out_dir: Path, source: Path, results: List[Dict[str, Any]]) -> None:
    (out_dir / "shorts.json").write_text(
        json.dumps({"source": str(source), "shorts": results}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = [f"# Shorts from `{source.name}`", ""]
    for r in results:
        md += [
            f"## {r['index']}. {r['title']}",
            "",
            f"- File: `{r['file']}`",
            f"- Source moment: {fmt_ts(r['source_start'])} - {fmt_ts(r['source_end'])}  ({r['duration']:.0f}s short, {r['size_mb']} MB)",
            "",
            "**Description**",
            "",
            "```",
            r["description"],
            "```",
            "",
        ]
    (out_dir / "shorts.md").write_text("\n".join(md), encoding="utf-8")


def render_all(
    source,
    clips: List[Dict[str, Any]],
    transcript: Optional[Transcript],
    out_dir,
    opts: RenderOptions,
    *,
    source_url: Optional[str] = None,
    credit: Optional[str] = None,
    hashtags: str = "#shorts",
    log: Callable[[str], None] = print,
) -> List[Dict[str, Any]]:
    source, out_dir = Path(source).resolve(), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(source)
    words = words_of(transcript) if transcript else []
    results: List[Dict[str, Any]] = []
    for n, clip in enumerate(clips, 1):
        if float(clip["start"]) >= info.duration > 0:
            raise ValueError(f"Clip {n} starts at {clip['start']}s but the video is only {info.duration:.1f}s long.")
        hook = str(clip.get("hook") or "").strip()
        title = str(clip.get("title") or hook or f"{source.stem} part {n}").strip()[:100]
        name = f"short_{n:02d}_{slugify(title)}.mp4"
        t0 = time.time()
        log(f"[{n}/{len(clips)}] {fmt_ts(clip['start'])} - {fmt_ts(clip['end'])}  ->  {name}")
        meta = render_clip(source, clip, words, out_dir / name, opts, info)
        results.append(
            {
                "index": n,
                "file": name,
                "title": title,
                "description": build_description(clip, hook, meta["source_start"], source_url, credit, hashtags),
                **meta,
            }
        )
        log(f"      {meta['duration']:.0f}s, {meta['size_mb']} MB, rendered in {time.time() - t0:.0f}s")
    write_report(out_dir, source, results)
    return results
