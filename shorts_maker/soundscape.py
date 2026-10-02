"""Original sound design for story videos, synthesised with numpy (no samples, no licences).

Every building block returns a float32 array at ``SR`` Hz. ``story.py`` combines them: a low,
dissonant drone and room tone as the bed, a heartbeat, a few one-shot effects, a ghostly
"whisperised" voice and a gently compressed narrator that stays well above all of it.

Nothing here needs a sound library, so there is no music licence to worry about when you publish.
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

SR = 48000
TAU = 2.0 * math.pi


# --------------------------------------------------------------------------- basics
def db(x: float) -> float:
    """Decibels -> linear gain."""
    return float(10.0 ** (x / 20.0))


def to_db(x: float) -> float:
    return float(20.0 * math.log10(max(float(x), 1e-12)))


def rms(x) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def normalize_peak(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    return x.astype(np.float32) if m < 1e-12 else (x * (peak / m)).astype(np.float32)


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


# --------------------------------------------------------------------------- filters
def _fft_apply(x: np.ndarray, response: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """Zero-phase frequency-domain filter (zero padded so nothing wraps around)."""
    n = len(x)
    if n == 0:
        return np.asarray(x, dtype=np.float32)
    size = n + 8192
    spec = np.fft.rfft(np.asarray(x, dtype=np.float64), size)
    freqs = np.fft.rfftfreq(size, 1.0 / SR)
    return np.fft.irfft(spec * response(freqs), size)[:n].astype(np.float32)


def lowpass(x: np.ndarray, fc: float, order: int = 2) -> np.ndarray:
    return _fft_apply(x, lambda f: 1.0 / np.sqrt(1.0 + (f / fc) ** (2 * order)))


def highpass(x: np.ndarray, fc: float, order: int = 2) -> np.ndarray:
    return _fft_apply(x, lambda f: 1.0 / np.sqrt(1.0 + (fc / np.maximum(f, 1e-3)) ** (2 * order)))


def bandpass(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    return highpass(lowpass(x, hi, order), lo, order)


def peak_eq(x: np.ndarray, f0: float, gain_db: float, octaves: float = 1.0) -> np.ndarray:
    """Smooth bell-shaped boost/cut centred on ``f0`` Hz, ``octaves`` wide (one sigma)."""
    g = 10.0 ** (gain_db / 20.0)

    def response(f):
        d = np.log2(np.maximum(f, 1.0) / f0)
        return 1.0 + (g - 1.0) * np.exp(-0.5 * (d / octaves) ** 2)

    return _fft_apply(x, response)


# --------------------------------------------------------------------------- noise and space
def white(n: int, rng) -> np.ndarray:
    return rng.standard_normal(n).astype(np.float32)


def pink(n: int, rng) -> np.ndarray:
    x = _fft_apply(white(n, rng), lambda f: 1.0 / np.sqrt(np.maximum(f, 30.0) / 30.0))
    return (x / (rms(x) + 1e-12)).astype(np.float32)


def make_ir(rt60: float, rng, predelay: float = 0.012, damp_hz: float = 6000.0, dark_hz: float = 1400.0) -> np.ndarray:
    """Stereo, unit-energy impulse response: decaying noise that gets darker as it fades."""
    n = int(rt60 * 1.15 * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.9078 * t / rt60)
    mix = smoothstep(t / (0.7 * rt60))
    chans = []
    for _ in range(2):
        raw = white(n, rng) * env
        bright, dark = lowpass(raw, damp_hz, 1), lowpass(raw, dark_hz, 2)
        chans.append(((1.0 - mix) * bright + mix * dark).astype(np.float32))
    ir = np.concatenate([np.zeros((int(predelay * SR), 2), np.float32), np.stack(chans, axis=1)])
    return (ir / np.sqrt((ir.astype(np.float64) ** 2).sum(axis=0, keepdims=True))).astype(np.float32)


def convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """Mono signal convolved with a stereo impulse response -> stereo, len(x) + len(ir) - 1 samples."""
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(np.asarray(x, dtype=np.float64), size)
    out = [np.fft.irfft(spec * np.fft.rfft(ir[:, c].astype(np.float64), size), size)[:n] for c in range(ir.shape[1])]
    return np.stack(out, axis=1).astype(np.float32)


# --------------------------------------------------------------------------- dynamics
def envelope(x: np.ndarray, attack: float, release: float, rate: int = 1000) -> np.ndarray:
    """Peak envelope follower evaluated at ``rate`` Hz and interpolated back to the sample rate."""
    blk = SR // rate
    nb = len(x) // blk + 1
    padded = np.zeros(nb * blk, np.float32)
    padded[: len(x)] = np.abs(x)
    peaks = padded.reshape(nb, blk).max(axis=1)
    a, r = math.exp(-1.0 / (attack * rate)), math.exp(-1.0 / (release * rate))
    out = np.empty(nb, np.float32)
    e = 0.0
    for i in range(nb):
        p = float(peaks[i])
        c = a if p > e else r
        e = c * e + (1.0 - c) * p
        out[i] = e
    return np.interp(np.arange(len(x)), (np.arange(nb) + 0.5) * blk, out).astype(np.float32)


def compress(x: np.ndarray, threshold_db: float = -27.0, ratio: float = 3.0, attack: float = 0.004, release: float = 0.12) -> np.ndarray:
    env_db = 20.0 * np.log10(envelope(x, attack, release) + 1e-9)
    over = np.maximum(env_db - threshold_db, 0.0)
    return (x * 10.0 ** (-over * (1.0 - 1.0 / ratio) / 20.0)).astype(np.float32)


def limit(x: np.ndarray, ceiling: float, lookahead: float = 0.004, release: float = 0.12, rate: int = 1000) -> np.ndarray:
    """Look-ahead peak limiter for mono or stereo arrays; the output never exceeds ``ceiling``."""
    peak = np.abs(x) if x.ndim == 1 else np.abs(x).max(axis=1)
    blk = SR // rate
    nb = len(peak) // blk + 1
    padded = np.zeros(nb * blk, np.float32)
    padded[: len(peak)] = peak
    block_peak = padded.reshape(nb, blk).max(axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(block_peak, 1e-9))
    w = int(round(lookahead * rate)) * 2 + 1
    need = sliding_window_view(np.pad(need, w // 2, constant_values=1.0), w).min(axis=1)
    rel = math.exp(-1.0 / (release * rate))
    gains = np.empty(nb, np.float64)
    cur = 1.0
    for i in range(nb):
        v = float(need[i])
        cur = v if v < cur else rel * cur + (1.0 - rel) * v
        gains[i] = cur
    g = np.interp(np.arange(len(peak)), (np.arange(nb) + 0.5) * blk, gains)
    y = x * (g if x.ndim == 1 else g[:, None])
    return np.clip(y, -ceiling, ceiling).astype(np.float32)


# --------------------------------------------------------------------------- voices
def speech_spans(x: np.ndarray, hop: float = 0.01, floor_db: float = 26.0, min_gap: float = 0.14, min_len: float = 0.05):
    """(start, end) seconds of each stretch of speech; pauses shorter than ``min_gap`` are bridged."""
    blk = int(SR * hop)
    n = len(x) // blk
    if n < 3:
        return []
    frames = np.asarray(x[: n * blk], dtype=np.float64).reshape(n, blk)
    level = 20.0 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    active = level > (np.percentile(level, 95) - floor_db)
    runs: List[List[int]] = []
    i = 0
    while i < n:
        if active[i]:
            j = i
            while j + 1 < n and active[j + 1]:
                j += 1
            runs.append([i, j + 1])
            i = j + 1
        else:
            i += 1
    merged: List[List[int]] = []
    for r in runs:
        if merged and (r[0] - merged[-1][1]) * hop < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a * hop, b * hop) for a, b in merged if (b - a) * hop >= min_len]


def trim_to_speech(x: np.ndarray, pad_before: float = 0.03, pad_after: float = 0.12):
    """Cut leading/trailing silence; returns (audio, spans relative to the new start)."""
    spans = speech_spans(x)
    if not spans:
        return x, []
    a = max(0.0, spans[0][0] - pad_before)
    b = min(len(x) / SR, spans[-1][1] + pad_after)
    return x[int(a * SR): int(b * SR)], [(s - a, e - a) for s, e in spans]


def active_level_db(x: np.ndarray, spans) -> float:
    if not spans:
        return to_db(rms(x))
    return to_db(rms(np.concatenate([x[int(a * SR): int(b * SR)] for a, b in spans])))


def level_to(x: np.ndarray, target_db: float, spans) -> np.ndarray:
    """Scale so the speech itself (not the pauses) averages ``target_db`` dBFS RMS."""
    return (x * db(target_db - active_level_db(x, spans))).astype(np.float32)


def narrator(x: np.ndarray) -> np.ndarray:
    """Gentle clean-up for a spoken line: rumble filter, a little body and presence, light compression."""
    x = highpass(x, 85.0, 2)
    x = peak_eq(x, 190.0, 1.5, 0.8)
    x = peak_eq(x, 3200.0, 2.0, 1.0)
    return compress(x, threshold_db=-27.0, ratio=3.0, attack=0.004, release=0.12)


def whisperise(x: np.ndarray, n_fft: int = 1024, hop: int = 256, seed: int = 3) -> np.ndarray:
    """Turn speech into breathy whisper: keep each frame's spectrum, throw away its phase."""
    rng = np.random.default_rng(seed)
    win = np.hanning(n_fft + 1)[:-1]
    padded = np.concatenate([np.zeros(n_fft), np.asarray(x, dtype=np.float64), np.zeros(2 * n_fft)])
    frames = 1 + (len(padded) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    mag = np.abs(np.fft.rfft(padded[idx] * win, axis=1))
    phase = rng.uniform(0.0, TAU, mag.shape)
    phase[:, 0] = 0.0
    phase[:, -1] = 0.0
    synth = np.fft.irfft(mag * np.exp(1j * phase), n=n_fft, axis=1) * win
    out = np.zeros(len(padded))
    norm = np.zeros(len(padded))
    np.add.at(out, idx, synth)
    np.add.at(norm, idx, np.broadcast_to(win ** 2, idx.shape))
    out /= np.maximum(norm, 1e-6)
    return highpass(out[n_fft: n_fft + len(x)].astype(np.float32), 260.0, 2)


# --------------------------------------------------------------------------- sources
def drone(dur: float, rng) -> np.ndarray:
    """Stereo bed of slowly breathing partials, a semitone apart so they beat against each other (unit RMS)."""
    n = int(round(dur * SR))
    t = np.arange(n, dtype=np.float64) / SR
    partials = (
        (55.00, 1.00, 0.050), (58.27, 0.80, 0.071), (110.0, 0.55, 0.043), (116.5, 0.50, 0.059),
        (164.8, 0.22, 0.083), (174.6, 0.18, 0.067), (220.0, 0.10, 0.037),
    )
    out = np.zeros((n, 2), np.float64)
    for k, (freq, amp, lfo) in enumerate(partials):
        for ch in range(2):
            detune = 1.0 + (0.0006 if ch else -0.0006) * (k + 1)
            swell = 0.65 + 0.35 * np.sin(TAU * lfo * t + rng.uniform(0.0, TAU))
            out[:, ch] += amp * swell * np.sin(TAU * freq * detune * t + rng.uniform(0.0, TAU))
    for ch in range(2):
        out[:, ch] = lowpass(out[:, ch], 700.0, 2)
    return (out / (rms(out) + 1e-12)).astype(np.float32)


def room_tone(dur: float, rng) -> np.ndarray:
    """Quiet, dark air in an empty flat (stereo, unit RMS)."""
    n = int(round(dur * SR))
    out = np.stack([lowpass(pink(n, rng), 650.0, 2) for _ in range(2)], axis=1)
    return (out / (rms(out) + 1e-12)).astype(np.float32)


def heartbeat(dur: float, bpm0: float, bpm1: float, rng=None) -> np.ndarray:
    """Lub-dub thumps whose rate climbs from ``bpm0`` to ``bpm1`` (mono, peak 1)."""
    n = int(round(dur * SR))
    out = np.zeros(n, np.float32)
    beat = 0.0
    while beat < dur:
        bpm = bpm0 + (bpm1 - bpm0) * (beat / dur)
        period = 60.0 / max(bpm, 20.0)
        for offset, freq, amp, tau in ((0.0, 62.0, 1.0, 0.055), (min(0.30, 0.36 * period), 52.0, 0.7, 0.05)):
            i0 = int((beat + offset) * SR)
            if i0 >= n:
                continue
            tt = np.arange(min(int(0.4 * SR), n - i0)) / SR
            thump = np.sin(TAU * freq * tt) * (1.0 - np.exp(-tt / 0.004)) * np.exp(-tt / tau)
            thump += 0.35 * np.sin(TAU * 2.0 * freq * tt) * np.exp(-tt / (0.6 * tau))
            thump += 0.12 * np.sin(TAU * 3.1 * freq * tt) * np.exp(-tt / 0.02)  # a little knock for phone speakers
            out[i0: i0 + len(tt)] += (amp * thump).astype(np.float32)
        beat += period
    return normalize_peak(out)


def riser(dur: float, rng) -> np.ndarray:
    """Noise that brightens and swells (mono, peak 1)."""
    n = int(round(dur * SR))
    t = np.arange(n) / SR
    cutoffs = (180.0, 360.0, 720.0, 1440.0, 2880.0, 5760.0)
    noise = white(n, rng)
    pos = (t / dur) * (len(cutoffs) - 1)
    out = np.zeros(n, np.float32)
    for k, fc in enumerate(cutoffs):
        out += lowpass(noise, fc, 2) * np.clip(1.0 - np.abs(pos - k), 0.0, 1.0).astype(np.float32)
    return normalize_peak(out * ((t / dur) ** 2.2).astype(np.float32))


def boom(dur: float, rng) -> np.ndarray:
    """Low impact with a falling pitch and a short noise burst (mono, peak 1)."""
    n = int(round(dur * SR))
    t = np.arange(n) / SR
    freq = 38.0 + 62.0 * np.exp(-t / 0.25)
    body = np.sin(TAU * np.cumsum(freq) / SR) * np.exp(-t / 0.55)
    mid = (np.sin(TAU * 110.0 * t) + 0.6 * np.sin(TAU * 165.0 * t)) * np.exp(-t / 0.28) * 0.5  # audible on small speakers
    burst = lowpass(white(n, rng), 1400.0, 2) * np.exp(-t / 0.12) * 0.6
    return normalize_peak((body + mid + burst).astype(np.float32))


def creak(dur: float, rng) -> np.ndarray:
    """A hinge: an irregular stick-slip pulse train ringing through two resonances (mono, peak 1)."""
    n = int(round(dur * SR))
    t = np.arange(n) / SR
    wobble = np.interp(t, np.linspace(0.0, dur, 14), rng.uniform(-16.0, 16.0, 14))
    f0 = 105.0 + 90.0 * (t / dur) ** 0.8 + wobble
    phase = np.cumsum(f0) / SR
    pulses = np.diff(np.floor(phase), prepend=0.0) > 0
    impulses = pulses * (0.55 + 0.45 * rng.random(n))
    kt = np.arange(int(0.012 * SR)) / SR
    kernel = np.exp(-kt / 0.0035) * np.sin(TAU * 1100.0 * kt) + 0.6 * np.exp(-kt / 0.0025) * np.sin(TAU * 2300.0 * kt)
    sig = np.convolve(impulses, kernel)[:n]
    chatter = np.interp(t, np.linspace(0.0, dur, 10), rng.uniform(0.25, 1.0, 10))
    shape = chatter * np.sin(np.pi * np.clip(t / dur, 0.0, 1.0)) ** 0.6
    return normalize_peak(bandpass((sig * shape).astype(np.float32), 350.0, 4800.0, 2))


def click(rng) -> np.ndarray:
    """A small metallic tick (a doorknob being touched), mono, peak 1."""
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    tick = highpass(white(n, rng), 1500.0, 2) * np.exp(-t / 0.004)
    ring = 0.3 * (np.sin(TAU * 2150.0 * t) * np.exp(-t / 0.03) + 0.6 * np.sin(TAU * 3380.0 * t) * np.exp(-t / 0.022))
    thud = 0.5 * np.sin(TAU * 140.0 * t) * np.exp(-t / 0.02)
    return normalize_peak((0.8 * tick + ring + thud).astype(np.float32))


def whoosh(dur: float, rng, lo: float = 180.0, hi: float = 1500.0) -> np.ndarray:
    """A breath of moving air (mono, peak 1)."""
    n = int(round(dur * SR))
    t = np.arange(n) / SR
    return normalize_peak(bandpass(white(n, rng), lo, hi, 2) * (np.sin(np.pi * np.clip(t / dur, 0.0, 1.0)) ** 2))


# --------------------------------------------------------------------------- mixing helpers
def add_at(dest: np.ndarray, src: np.ndarray, t: float, gain: float = 1.0, pan: float = 0.0) -> None:
    """Add ``src`` into ``dest`` starting at ``t`` seconds. Mono sources are panned (-1 left .. +1 right)."""
    if dest.ndim == 2 and src.ndim == 1:
        angle = (pan + 1.0) * math.pi / 4.0
        src = np.stack([src * math.cos(angle), src * math.sin(angle)], axis=1) * math.sqrt(2.0)
    start = int(round(t * SR))
    s0, d0 = max(0, -start), max(0, start)
    m = min(len(src) - s0, len(dest) - d0)
    if m > 0:
        dest[d0: d0 + m] += (src[s0: s0 + m] * gain).astype(np.float32)


def curve(points: Sequence[Tuple[float, float]], t: np.ndarray) -> np.ndarray:
    """Piecewise-linear value over time from (seconds, value) points."""
    pts = sorted(points)
    return np.interp(t, [p[0] for p in pts], [p[1] for p in pts]).astype(np.float32)


def duck_curve(voice: np.ndarray, depth_db: float = -7.0, attack: float = 0.05, release: float = 0.45) -> np.ndarray:
    """Gain (<= 1) that dips under the voice so the bed never fights the narrator."""
    env = envelope(voice, attack, release)
    loud = env[env > 1e-3]
    ref = float(np.percentile(loud, 90)) if loud.size else 1.0
    return (1.0 - (1.0 - db(depth_db)) * np.clip(env / max(ref, 1e-6), 0.0, 1.0)).astype(np.float32)


def dropout_curve(holes: Sequence[Tuple[float, float, float]], t: np.ndarray, floor: float = 0.03) -> np.ndarray:
    """Gain that drops to ``floor`` for each (start, length, fade) hole - dread is mostly silence."""
    gain = np.ones(len(t), np.float32)
    for start, length, fade in holes:
        pts = [(start - fade, 1.0), (start, floor), (start + length, floor), (start + length + fade, 1.0)]
        gain *= curve(pts, t)
    return gain
