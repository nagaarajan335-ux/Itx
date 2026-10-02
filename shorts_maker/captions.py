"""Word-by-word animated captions and a hook banner, written as an ASS subtitle file.

ffmpeg's ``ass`` filter (libass) burns the result into the video. Every spoken word
becomes its own subtitle event that shows the whole 2-3 word caption with the
*current* word highlighted - the karaoke look used by most viral Shorts.
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

Word = Dict[str, Any]

# Words are separated by a space plus a hard space: with a thick outline a single space looks like no gap.
WORD_SEP = "  "  # what we measure with
ASS_SEP = " \\h"  # what we emit

_BREAK_PUNCT = re.compile(r"[.!?;:,\u2026]$")
_TRAILING_SOFT = re.compile(r"[,;:]+$")


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    """'FFD400' / '#FFD400' -> ASS colour '&H0000D4FF' (BGR, alpha 00 = opaque)."""
    h = hex_rgb.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"Colour must be 6 hex digits like FFD400, got {hex_rgb!r}")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


@dataclass
class CaptionStyle:
    font_name: str = "Poppins ExtraBold"
    font_path: Optional[str] = None  # used only to measure text so captions never overflow the frame
    font_size: int = 104  # ASS size: ~74 px em for Poppins on a 1080 px wide canvas
    primary: str = "FFFFFF"
    highlight: str = "FFD400"
    outline_color: str = "000000"
    outline: float = 8.0
    shadow: float = 3.0
    words_per_caption: int = 3
    max_chars: int = 20
    uppercase: bool = True
    safe_width: int = 940  # widest caption line in px (1080 canvas minus margins and outline)
    hook_font_size: int = 72
    hook_box: str = "FFD400"
    hook_text: str = "111111"
    hook_secs: float = 3.2


# --------------------------------------------------------------------------- measuring
class TextMeasurer:
    """Approximate rendered text width, matching libass' font-size convention.

    libass scales the font so that (ascent + descent) equals the ASS font size, so the
    em size is ``font_size / ((ascent + descent) / em)``.
    """

    def __init__(self, font_path: Optional[str]):
        self._font = None
        self.cell = 1.4
        if font_path:
            try:
                from PIL import ImageFont

                self._font = ImageFont.truetype(str(font_path), 100)
                ascent, descent = self._font.getmetrics()
                self.cell = (ascent + descent) / 100.0
            except Exception:
                self._font = None

    def width(self, text: str, font_size: float) -> float:
        em = font_size / self.cell
        if self._font is None:
            return len(text) * em * 0.65
        return self._font.getlength(text) * em / 100.0


# --------------------------------------------------------------------------- chunking
def chunk_words(words: Sequence[Word], max_words: int = 3, max_chars: int = 20, max_gap: float = 0.5) -> List[List[Word]]:
    """Group words into short on-screen captions, breaking at punctuation and pauses."""
    chunks: List[List[Word]] = []
    cur: List[Word] = []
    for w in words:
        if cur:
            chars = sum(len(str(x["word"])) for x in cur) + len(cur)
            if (
                len(cur) >= max_words
                or chars + len(str(w["word"])) > max_chars
                or w["start"] - cur[-1]["end"] > max_gap
            ):
                chunks.append(cur)
                cur = []
        cur.append(w)
        if _BREAK_PUNCT.search(str(w["word"])):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def _display(word: str, uppercase: bool) -> str:
    text = word.replace("\\", "").replace("{", "").replace("}", "").strip()
    text = _TRAILING_SOFT.sub("", text)
    return text.upper() if uppercase else text


def _layout(texts: List[str], measurer: TextMeasurer, base: int, safe_w: int) -> Tuple[Optional[int], int]:
    """Decide where to break a caption into two lines and whether the font must shrink."""
    if measurer.width(WORD_SEP.join(texts), base) <= safe_w:
        return None, base
    brk, widest = None, measurer.width(WORD_SEP.join(texts), base)
    if len(texts) > 1:
        best = None
        for k in range(1, len(texts)):
            w = max(measurer.width(WORD_SEP.join(texts[:k]), base), measurer.width(WORD_SEP.join(texts[k:]), base))
            if best is None or w < best[0]:
                best = (w, k)
        widest, brk = best  # type: ignore[misc]
        if widest <= safe_w:
            return brk, base
    return brk, int(max(base * 0.55, base * safe_w / widest))


# --------------------------------------------------------------------------- ASS
def _header(width: int, height: int, style: CaptionStyle, hook_font: Optional[str] = None) -> str:
    cap = (
        f"Style: Caption,{style.font_name},{style.font_size},{ass_color(style.primary)},{ass_color(style.primary)},"
        f"{ass_color(style.outline_color)},{ass_color('000000', 0x70)},0,0,0,0,100,100,0,0,1,"
        f"{style.outline:g},{style.shadow:g},5,40,40,40,1"
    )
    hook = (
        f"Style: Hook,{hook_font or style.font_name},{style.hook_font_size},{ass_color(style.hook_text)},"
        f"{ass_color(style.hook_text)},{ass_color(style.hook_box)},{ass_color('000000', 0x80)},0,0,0,0,100,100,0,0,3,"
        f"18,0,5,60,60,40,1"
    )
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        f"MarginR, MarginV, Encoding\n{cap}\n{hook}\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def build_events(
    words: Sequence[Word],
    style: CaptionStyle,
    *,
    cx: int,
    cy: int,
    clip_len: float,
) -> List[str]:
    """One Dialogue line per spoken word; times are relative to the clip start."""
    measurer = TextMeasurer(style.font_path)
    hi, base = ass_color(style.highlight), ass_color(style.primary)
    chunks = chunk_words(words, style.words_per_caption, style.max_chars)
    events: List[str] = []
    lead = 0.04  # have the caption up a hair before its first word is spoken
    prev_end = 0.0
    for ci, chunk in enumerate(chunks):
        texts = [_display(str(w["word"]), style.uppercase) for w in chunk]
        keep = [(w, t) for w, t in zip(chunk, texts) if t]
        if not keep:
            continue
        chunk, texts = [k[0] for k in keep], [k[1] for k in keep]
        brk, fs = _layout(texts, measurer, style.font_size, style.safe_width)
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else None
        for k, w in enumerate(chunk):
            start = float(w["start"]) - (lead if k == 0 else 0.0)
            start = max(0.0, start, prev_end)  # never overlap the previous caption
            if k + 1 < len(chunk):
                end = float(chunk[k + 1]["start"])
            else:
                end = float(w["end"]) + 0.25
                if next_start is not None:
                    end = min(end, float(next_start) - lead)  # leave room for the next caption's lead-in
            end = min(end, clip_len)
            if end - start < 0.05:
                end = min(clip_len, start + 0.05)
            if end <= start:
                continue
            prev_end = end
            pieces = []
            for idx, t in enumerate(texts):
                if brk is not None and idx == brk:
                    pieces.append("\\N")
                elif idx > 0:
                    pieces.append(ASS_SEP)
                pieces.append(f"{{\\1c{hi}}}{t}{{\\1c{base}}}" if idx == k else t)
            pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
            size = f"\\fs{fs}" if fs != style.font_size else ""
            tag = f"{{\\an5\\pos({cx},{cy}){size}}}"
            events.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{tag}{pop}{''.join(pieces)}"
            )
    return events


def wrap_hook(text: str, width: int = 24, max_lines: int = 3) -> str:
    """Wrap hook text into at most ``max_lines`` lines (ASS line break = ``\\N``)."""
    text = re.sub(r"\s+", " ", text.replace("\\", "").replace("{", "").replace("}", "")).strip().upper()
    lines = textwrap.wrap(text, width=width) or [""]
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]
        if len(lines[-1]) > width + 6:
            lines[-1] = lines[-1][: width + 3].rsplit(" ", 1)[0] + "\u2026"
    return "\\N".join(lines)


def write_ass(
    path,
    words: Sequence[Word],
    style: CaptionStyle,
    *,
    width: int,
    height: int,
    clip_len: float,
    caption_y: int,
    hook: Optional[str] = None,
    hook_y: int = 300,
    hook_font_name: Optional[str] = None,
    extra_events: Sequence[str] = (),
    underlay_events: Sequence[str] = (),
) -> int:
    """Write the .ass file; returns the number of events written.

    ``extra_events`` / ``underlay_events`` are ready-made ``Dialogue:`` lines (used by story videos for
    end cards and screen dimming); underlay events are listed first so they are drawn beneath the captions.
    """
    events = list(underlay_events)
    if words:
        events += build_events(words, style, cx=width // 2, cy=caption_y, clip_len=clip_len)
    if hook:
        end = min(style.hook_secs, clip_len)
        events.append(
            f"Dialogue: 1,{ass_time(0)},{ass_time(end)},Hook,,0,0,0,,"
            f"{{\\an5\\pos({width // 2},{hook_y})\\fad(180,250)}}{wrap_hook(hook)}"
        )
    events += list(extra_events)
    Path(path).write_text(_header(width, height, style, hook_font_name) + "\n".join(events) + "\n", encoding="utf-8")
    return len(events)
