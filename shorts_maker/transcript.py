"""Transcripts: run Whisper locally, or import an existing SRT / VTT / JSON file.

Internal format (what ``transcript.json`` contains)::

    {
      "language": "en",
      "duration": 123.4,
      "segments": [
        {"start": 0.0, "end": 2.5, "text": "Hello there",
         "words": [{"word": "Hello", "start": 0.0, "end": 0.4}, ...]}
      ]
    }

Word timings are what drive the animated captions. Whisper gives real per-word
timings; for SRT/VTT files (e.g. exported from YouTube Studio) they are
interpolated inside each cue, which is accurate enough for 2-3 word captions.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

Transcript = Dict[str, Any]

_TS = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
_TIME_LINE = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}")
_MARKUP = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_ANNOTATION = re.compile(r"\[[^\]]*\]|\([^)]*\)")  # [Music], (applause), ...
_PAUSE_END = re.compile(r"[.,!?;:…]$")


# --------------------------------------------------------------------------- helpers
def _seconds(h: Optional[str], m: str, s: str, ms: str) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int((ms + "000")[:3]) / 1000.0


def interpolate_words(text: str, start: float, end: float) -> List[Dict[str, Any]]:
    """Spread the words of ``text`` over [start, end], weighted by length (+ a pause after punctuation)."""
    tokens = text.split()
    if not tokens:
        return []
    weights = [max(2, len(t)) + (4 if _PAUSE_END.search(t) else 0) for t in tokens]
    total = float(sum(weights))
    span = max(end - start, 0.05 * len(tokens))
    words, t = [], start
    for token, weight in zip(tokens, weights):
        dur = span * weight / total
        words.append({"word": token, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur
    return words


def _make_monotonic(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort by start and make sure words never overlap or run backwards."""
    words = sorted(words, key=lambda w: (w["start"], w["end"]))
    prev_end = 0.0
    for w in words:
        w["start"] = max(float(w["start"]), prev_end)
        w["end"] = max(float(w["end"]), w["start"] + 0.02)
        prev_end = w["end"]
    return words


def words_of(transcript: Transcript) -> List[Dict[str, Any]]:
    """All words of a transcript as one flat, time-ordered list."""
    words = [dict(w) for seg in transcript.get("segments", []) for w in seg.get("words", [])]
    return _make_monotonic(words)


# --------------------------------------------------------------------------- SRT / VTT
def _clean_cue_text(lines: List[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = html.unescape(_MARKUP.sub("", text))
    text = _ANNOTATION.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^[-\u2013\u2014]\s+", "", text)


def parse_cues(text: str) -> Transcript:
    """Parse SRT or WebVTT text into the internal transcript format."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    segments = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip("\n").split("\n")
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None:
            continue  # WEBVTT header, NOTE / STYLE blocks, stray numbers
        m = _TIME_LINE.match(lines[idx])
        if not m:
            continue
        g = m.groups()
        start, end = _seconds(*g[0:4]), _seconds(*g[4:8])
        cue = _clean_cue_text(lines[idx + 1 :])
        if not cue or end <= start:
            continue
        segments.append({"start": start, "end": end, "text": cue, "words": interpolate_words(cue, start, end)})
    if not segments:
        raise ValueError("No subtitle cues found - is this a valid .srt/.vtt file?")
    # YouTube auto-captions overlap; keep cues in order and non-overlapping
    all_words = _make_monotonic([w for s in segments for w in s["words"]])
    it = iter(all_words)
    for seg in segments:
        seg["words"] = [next(it) for _ in seg["words"]]
        seg["start"], seg["end"] = seg["words"][0]["start"], seg["words"][-1]["end"]
    return {"language": None, "duration": segments[-1]["end"], "segments": segments}


# --------------------------------------------------------------------------- JSON / load / save
def normalize(data: Any) -> Transcript:
    """Accept our own JSON, a Whisper-style JSON, or a bare list of segments."""
    segments_in = data.get("segments") if isinstance(data, dict) else data
    if not isinstance(segments_in, list) or not segments_in:
        raise ValueError("Transcript JSON needs a non-empty 'segments' list.")
    segments = []
    for seg in segments_in:
        start, end = float(seg["start"]), float(seg["end"])
        text = str(seg.get("text", "")).strip()
        raw_words = seg.get("words") or []
        words = [
            {
                "word": str(w.get("word", w.get("text", ""))).strip(),
                "start": float(w["start"]),
                "end": float(w["end"]),
            }
            for w in raw_words
            if str(w.get("word", w.get("text", ""))).strip()
        ]
        if not words:
            words = interpolate_words(text, start, end)
        if not text:
            text = " ".join(w["word"] for w in words)
        segments.append({"start": start, "end": end, "text": text, "words": words})
    meta = data if isinstance(data, dict) else {}
    return {
        "language": meta.get("language"),
        "duration": float(meta.get("duration") or segments[-1]["end"]),
        "segments": segments,
    }


def load_transcript(path) -> Transcript:
    """Load a transcript from .json, .srt or .vtt."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Transcript file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return normalize(json.loads(path.read_text(encoding="utf-8")))
    if suffix in {".srt", ".vtt"}:
        return parse_cues(path.read_text(encoding="utf-8-sig"))
    raise ValueError(f"Unsupported transcript format '{suffix}' (use .json, .srt or .vtt)")


def save_transcript(transcript: Transcript, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- Whisper
def _cuda_available() -> bool:
    try:
        import ctranslate2  # type: ignore

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def transcribe_whisper(
    media_path,
    model_size: str = "small",
    language: Optional[str] = None,
    device: str = "auto",
    compute_type: Optional[str] = None,
    beam_size: int = 1,
    progress: bool = True,
) -> Transcript:
    """Transcribe with faster-whisper, returning word-level timestamps.

    The model (~145 MB for ``base``, ~480 MB for ``small``) is downloaded from
    Hugging Face on first use, so this step needs an internet connection once.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed. Run: pip install faster-whisper") from exc

    if device == "auto":
        device = "cuda" if _cuda_available() else "cpu"
    if compute_type is None:
        compute_type = "float16" if device == "cuda" else "int8"

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(
        str(media_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=beam_size,
        condition_on_previous_text=False,  # avoids repetition loops on long videos
    )
    total = float(getattr(info, "duration", 0.0) or 0.0)
    segments: List[Dict[str, Any]] = []
    last_pct = -1
    for seg in segments_iter:
        words = [
            {"word": w.word.strip(), "start": float(w.start), "end": float(w.end)}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        text = seg.text.strip()
        if not words:
            words = interpolate_words(text, float(seg.start), float(seg.end))
        segments.append({"start": float(seg.start), "end": float(seg.end), "text": text, "words": words})
        if progress and total:
            pct = int(100 * min(float(seg.end), total) / total)
            if pct != last_pct and pct % 5 == 0:
                print(f"  transcribing... {pct}%", file=sys.stderr, flush=True)
                last_pct = pct
    if not segments:
        raise RuntimeError("Whisper found no speech in this video.")
    return {"language": getattr(info, "language", language), "duration": total or segments[-1]["end"], "segments": segments}


def get_transcript(
    media_path,
    work_dir,
    transcript_path=None,
    *,
    force: bool = False,
    model_size: str = "small",
    language: Optional[str] = None,
    device: str = "auto",
) -> Transcript:
    """Return the transcript for a video, using (in order): an imported file, the cache, or Whisper."""
    cache = Path(work_dir) / "transcript.json"
    if transcript_path:
        transcript = load_transcript(transcript_path)
        save_transcript(transcript, cache)
        return transcript
    if cache.is_file() and not force:
        return normalize(json.loads(cache.read_text(encoding="utf-8")))
    transcript = transcribe_whisper(media_path, model_size=model_size, language=language, device=device)
    save_transcript(transcript, cache)
    return transcript
