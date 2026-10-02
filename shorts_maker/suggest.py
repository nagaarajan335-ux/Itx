"""Heuristic selection of Short-worthy moments from a transcript.

This is a *first pass*, not an oracle. It looks for windows that

* open with a strong hook (a question, a bold claim, curiosity words - not "and then we...")
* are emotionally dense (intense words, ! and ?), at a lively speaking pace
* are loud / dynamic compared with the rest of the video (needs the audio track)
* start and end on sentence boundaries and fit the target length

and returns the best non-overlapping ones. The word lists are English; for other
languages the structural signals (questions, pace, loudness, completeness) still
work. Always skim the result and edit ``clips.json`` before rendering - picking
moments is the part that still benefits most from a human eye.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .transcript import Transcript, words_of

_END = re.compile(r"[.!?\u2026][\"'\u201d\u2019)\]]*$")
_ABBREV = {"mr.", "mrs.", "ms.", "dr.", "prof.", "vs.", "etc.", "e.g.", "i.e.", "st.", "jr.", "sr."}

HOOK_WORDS = frozenset(
    """secret secrets never worst best biggest shocking shocked insane crazy unbelievable truth nobody
    mistake mistakes warning dangerous scary terrifying impossible million billion free hack trick hidden
    exposed banned illegal fail failed wrong lie lies stop finally suddenly everything nothing why how
    wait listen imagine guess real actually rule rules reason reasons problem proven simple easy fast
    instantly literally honestly seriously changed ruined destroyed mystery weird strange""".split()
)
INTENSE_WORDS = frozenset(
    """love hate fear afraid angry furious amazing incredible terrible horrible awful disgusting hilarious
    funny scream screamed cry cried died dead death kill killed blood panic shock nightmare miracle genius
    stupid idiot wow omg god hell damn crazy insane unbelievable terrifying scary huge massive brutal""".split()
)
QUESTION_STARTS = frozenset(
    "why how what who when where which did do does have has can could would should is are was were will".split()
)
WEAK_STARTS = frozenset(
    "and but so because or then which also anyway well um uh yeah okay ok cause though plus like".split()
)
PRONOUN_STARTS = frozenset("he she it they them this that those these his her their".split())
YOU_WORDS = frozenset({"you", "your", "you're", "you've", "you'll", "youre"})


# --------------------------------------------------------------------------- sentences
@dataclass
class Sentence:
    start: float
    end: float
    text: str
    first: str  # first token, lower-case
    n_words: int
    intense: int
    excl: int
    ques: int
    inner_gap: float  # seconds of silence (beyond 1s) between words inside the sentence
    terminal: bool  # ends with . ! ? ...
    hook: float


def _tokens(words: List[Dict[str, Any]]) -> List[str]:
    toks = (re.sub(r"[^a-z0-9']", "", str(w["word"]).lower()) for w in words)
    return [t for t in toks if t]


def hook_score(text: str) -> float:
    """0..1: how well does this sentence work as the opening line of a Short?"""
    toks = _tokens([{"word": t} for t in text.split()])
    if not toks:
        return 0.0
    score = 0.35
    if text.rstrip().endswith("?"):
        score += 0.25
        if toks[0] in QUESTION_STARTS:
            score += 0.05
    score += min(0.30, 0.10 * sum(t in HOOK_WORDS for t in toks))
    if any(t in YOU_WORDS for t in toks):
        score += 0.08
    if re.search(r"\d", text):
        score += 0.06
    if toks[0] in WEAK_STARTS:
        score -= 0.30
    elif toks[0] in PRONOUN_STARTS:
        score -= 0.12
    if len(toks) < 4:
        score -= 0.15
    elif len(toks) > 28:
        score -= 0.15
    return float(min(1.0, max(0.0, score)))


def _make_sentence(ws: List[Dict[str, Any]]) -> Sentence:
    text = " ".join(str(w["word"]) for w in ws)
    toks = _tokens(ws)
    gap = sum(max(0.0, ws[k + 1]["start"] - ws[k]["end"] - 1.0) for k in range(len(ws) - 1))
    return Sentence(
        start=float(ws[0]["start"]),
        end=float(ws[-1]["end"]),
        text=text,
        first=toks[0] if toks else "",
        n_words=len(ws),
        intense=sum(t in INTENSE_WORDS for t in toks),
        excl=text.count("!"),
        ques=text.count("?"),
        inner_gap=gap,
        terminal=bool(_END.search(text)),
        hook=hook_score(text),
    )


def build_sentences(words: List[Dict[str, Any]], max_gap: float = 0.9, max_words: int = 60) -> List[Sentence]:
    """Group words into sentences (punctuation, long pauses, or a word cap end a sentence)."""
    sentences: List[Sentence] = []
    cur: List[Dict[str, Any]] = []
    for i, w in enumerate(words):
        cur.append(w)
        text = str(w["word"])
        ended = bool(_END.search(text)) and text.lower() not in _ABBREV
        gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 0.0
        if ended or gap > max_gap or len(cur) >= max_words:
            sentences.append(_make_sentence(cur))
            cur = []
    if cur:
        sentences.append(_make_sentence(cur))
    return sentences


# --------------------------------------------------------------------------- audio energy
def audio_energy(media_path, bin_s: float = 0.5, sample_rate: int = 16000) -> np.ndarray:
    """Loudness (dBFS RMS) per ``bin_s`` seconds of the audio track, decoded with PyAV."""
    import av

    per_bin = int(sample_rate * bin_s)
    out: List[float] = []
    pending: List[np.ndarray] = []
    pending_len = 0

    def drain(final: bool = False) -> None:
        nonlocal pending, pending_len
        if not pending:
            return
        buf = np.concatenate(pending)
        usable = (len(buf) // per_bin) * per_bin
        if usable:
            chunks = buf[:usable].reshape(-1, per_bin)
            rms = np.sqrt(np.mean(chunks**2, axis=1)) + 1e-9
            out.extend((20 * np.log10(rms)).tolist())
        rest = buf[usable:]
        pending, pending_len = ([rest], len(rest)) if len(rest) and not final else ([], 0)

    with av.open(str(media_path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.zeros(0)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        for frame in container.decode(stream):
            for rf in resampler.resample(frame):
                arr = rf.to_ndarray().reshape(-1).astype(np.float32) / 32768.0
                pending.append(arr)
                pending_len += len(arr)
            if pending_len >= per_bin * 64:
                drain()
    drain(final=True)
    return np.asarray(out, dtype=np.float64)


# --------------------------------------------------------------------------- selection
def make_hook(text: str, max_chars: int = 64) -> str:
    """Shorten a sentence into an on-screen hook line."""
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= max_chars:
        return t.rstrip(".,;:")
    clause = re.split(r"[,;:\u2014\u2013]\s|\s-\s", t)[0].strip()
    if 18 <= len(clause) <= max_chars:
        return clause
    return t[:max_chars].rsplit(" ", 1)[0].rstrip(",;:-") + "\u2026"


def _rank_norm(x: np.ndarray) -> np.ndarray:
    if len(x) < 2:
        return np.full(len(x), 0.5)
    return np.argsort(np.argsort(x)).astype(np.float64) / (len(x) - 1)


def _prefix(values) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.asarray(values, dtype=np.float64))])


def suggest_clips(
    transcript: Transcript,
    *,
    count: int = 8,
    min_len: float = 25.0,
    max_len: float = 58.0,
    energy: Optional[np.ndarray] = None,
    energy_bin: float = 0.5,
    min_gap: float = 3.0,
) -> List[Dict[str, Any]]:
    """Pick up to ``count`` non-overlapping windows, returned in chronological order."""
    words = words_of(transcript)
    sents = build_sentences(words)
    n = len(sents)
    if n == 0:
        return []

    starts = np.array([s.start for s in sents])
    ends = np.array([s.end for s in sents])

    # candidate windows: sentence i .. sentence j with min_len <= duration <= max_len
    ci_list, cj_list = [], []
    for i in range(n):
        jmin = int(np.searchsorted(ends, starts[i] + min_len, side="left"))
        jmax = int(np.searchsorted(ends, starts[i] + max_len, side="right")) - 1
        for j in range(max(jmin, i), min(jmax, n - 1) + 1):
            ci_list.append(i)
            cj_list.append(j)
    if not ci_list:  # transcript shorter than min_len: offer the whole thing, capped at max_len
        j = int(np.searchsorted(ends, starts[0] + max_len, side="right")) - 1
        if ends[max(j, 0)] - starts[0] < 5.0:
            return []
        ci_list, cj_list = [0], [max(j, 0)]
    ci, cj = np.array(ci_list), np.array(cj_list)
    cs, ce = starts[ci], ends[cj]
    dur = np.maximum(ce - cs, 1e-3)

    # window sums via prefix sums
    p_words = _prefix([s.n_words for s in sents])
    p_int = _prefix([s.intense for s in sents])
    p_exc = _prefix([s.excl for s in sents])
    p_que = _prefix([s.ques for s in sents])
    p_inner = _prefix([s.inner_gap for s in sents])
    gaps_between = [max(0.0, starts[k + 1] - ends[k] - 1.0) for k in range(n - 1)] + [0.0]
    p_between = _prefix(gaps_between)

    nw = p_words[cj + 1] - p_words[ci]
    wps = nw / dur
    density = ((p_int[cj + 1] - p_int[ci]) + 0.6 * (p_exc[cj + 1] - p_exc[ci]) + 0.4 * (p_que[cj + 1] - p_que[ci])) / (
        dur / 10.0
    )
    emotion = 1.0 - np.exp(-density / 1.5)
    pace = np.interp(wps, [1.2, 2.2, 3.4, 4.8], [0.0, 1.0, 1.0, 0.0])
    lo = max(min_len, 0.6 * max_len)
    length = np.where(dur >= lo, 1.0, 0.4 + 0.6 * (dur - min_len) / max(lo - min_len, 1e-6))
    complete = np.where(np.array([s.terminal for s in sents])[cj], 1.0, 0.4)
    hook = np.array([s.hook for s in sents])[ci]
    silence = np.minimum(0.25, ((p_between[cj] - p_between[ci]) + (p_inner[cj + 1] - p_inner[ci])) / dur)

    parts = {"hook": hook, "emotion": emotion, "pace": pace, "length": length, "complete": complete}
    weights = {"hook": 0.32, "emotion": 0.22, "pace": 0.16, "length": 0.12, "complete": 0.10}

    if energy is not None and len(energy) > 4:
        a = np.clip((cs / energy_bin).astype(int), 0, len(energy) - 1)
        b = np.clip(np.ceil(ce / energy_bin).astype(int), a + 1, len(energy))
        p1, p2 = _prefix(energy), _prefix(energy**2)
        mean = (p1[b] - p1[a]) / (b - a)
        std = np.sqrt(np.maximum((p2[b] - p2[a]) / (b - a) - mean**2, 0.0))
        parts["energy"] = 0.6 * _rank_norm(mean) + 0.4 * _rank_norm(std)
        weights["energy"] = 0.14

    score = sum(weights[k] * parts[k] for k in weights) / sum(weights.values()) - silence

    chosen: List[int] = []
    for idx in np.argsort(-score):
        s, e = cs[idx], ce[idx]
        if any(s < ce[o] + min_gap and e > cs[o] - min_gap for o in chosen):
            continue
        chosen.append(int(idx))
        if len(chosen) >= count:
            break

    clips = []
    for rank, idx in enumerate(chosen, 1):
        first = sents[int(ci[idx])]
        last = sents[int(cj[idx])]
        hook_line = make_hook(first.text)
        clips.append(
            {
                "start": round(float(cs[idx]), 2),
                "end": round(float(ce[idx]), 2),
                "hook": hook_line,
                "title": hook_line[:1].upper() + hook_line[1:],
                "score": round(float(score[idx]), 3),
                "rank": rank,
                "signals": {k: round(float(v[idx]), 2) for k, v in parts.items()},
                "preview": " ".join(s.text for s in sents[int(ci[idx]) : int(cj[idx]) + 1])[:220],
                "ends_with": last.text[-60:],
            }
        )
    clips.sort(key=lambda c: c["start"])
    return clips
