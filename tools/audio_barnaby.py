#!/usr/bin/env python3
"""
Barnaby the Mender - full audio build (voiceover + original score + SFX).

Everything is synthesised with numpy/scipy (no external music samples), so the
result is royalty-free. Output: Itx/build/audio_mix.wav (48 kHz stereo float).

Timeline matches the storyboard exactly (scenes at 0-3-10-18-25-32-40-48-52-57-60s).
"""
import os
import sys
import wave
import numpy as np
from scipy.signal import butter, filtfilt, resample_poly, fftconvolve

SR = 48000
N = int(round(62.5 * SR))          # 60s story + 2.5s optional end card
rng = np.random.default_rng(7)

BUILD = os.environ.get("BARNABY_BUILD", "/home/user/Itx/Itx/build")
VO_DIR = os.path.join(BUILD, "vo")
OUT = os.path.join(BUILD, "audio_mix.wav")

# ---------------------------------------------------------------- scene table
# (index, start, end, vo_file)
SCENES = [
    (1, 0.0, 3.0, "vo01.wav"),
    (2, 3.0, 10.0, "vo02.wav"),
    (3, 10.0, 18.0, "vo03.wav"),
    (4, 18.0, 25.0, "vo04.wav"),
    (5, 25.0, 32.0, "vo05.wav"),
    (6, 32.0, 40.0, "vo06.wav"),
    (7, 40.0, 48.0, "vo07.wav"),
    (8, 48.0, 52.0, "vo08.wav"),
    (9, 52.0, 57.0, "vo09.wav"),
    (10, 57.0, 60.0, "vo10.wav"),
]
VO_START_OFFSET = [0.10, 3.35, 10.9, 18.6, 25.5, 32.5, 41.0, 48.4, 52.3, 57.2]

A = np.zeros((N, 2), dtype=np.float64)   # music + sfx bus
t_all = np.arange(N) / SR


def place(buf, start_s, sig):
    """Add a mono (n,) or stereo (n,2) signal into buf at a given time."""
    i0 = int(round(start_s * SR))
    if i0 >= N:
        return
    sig = np.asarray(sig)
    if sig.ndim == 1:
        sig = np.repeat(sig[:, None], buf.shape[1], axis=1)
    elif sig.shape[-1] != buf.shape[1] and sig.shape[0] == buf.shape[1]:
        sig = sig.T
    i1 = min(N, i0 + sig.shape[0])
    buf[i0:i1] += sig[: i1 - i0]
    return i1


def env_ad(n, attack, decay, curve=3.0):
    """attack/decay envelope, lengths in samples."""
    e = np.zeros(n)
    a = min(attack, n)
    if a > 0:
        e[:a] = (np.linspace(0, 1, a) ** 1.2)
    tail = np.ones(n - a)
    if decay > 0:
        tail = np.exp(-np.linspace(0, 1, n - a) * curve)
    e[a:] = tail
    return e


def tone(freq, dur, timbre="pad", amp=1.0, vibrato=0.0, detune=0.0):
    """Additive synth voice with per-timbre harmonic stack + matching envelope."""
    n = int(dur * SR)
    tt = np.arange(n) / SR
    profiles = {
        # (harmonic amplitudes, decay exponent per partial, attack, decay_curve)
        "pad":     ([1, .55, .35, .2, .12], 1.1, int(.55 * SR), 1.0),
        "strings": ([1, .7, .5, .38, .28, .18], 1.3, int(.35 * SR), 1.2),
        "pluck":   ([1, .8, .55, .35, .2, .1], 2.6, 40, 4.0),
        "piano":   ([1, .5, .32, .22, .12, .07], 2.1, 25, 3.4),
        "bell":    ([1, .0, .55, .0, .32, .0, .12], 2.4, 12, 3.0),
        "bass":    ([1, .5, .25, .1], .8, int(.12 * SR), 1.0),
        "brass":   ([1, .85, .6, .45, .3, .18], 1.4, int(.05 * SR), 1.8),
        "air":     ([1, .4, .15, .05], 1.6, int(.25 * SR), 1.4),
    }
    hamps, hdecay, atk, dcurve = profiles[timbre]
    y = np.zeros(n)
    # vibrato as proper frequency modulation (shared across partials)
    ph_vib = np.zeros(n)
    if vibrato:
        f_vib, depth = 5.3, vibrato * freq / 5.3
        ph_vib = depth * np.sin(2 * np.pi * f_vib * tt + rng.uniform(0, 6.28))
    for k, a in enumerate(hamps, start=1):
        if a <= 0:
            continue
        f = freq * k * (1 + detune)
        if k > 1:
            f *= (1 + 0.0012 * (k - 1))          # slight inharmonicity
        ph = 2 * np.pi * f * tt + k * 0.35 + ph_vib * k
        part_decay = max(1, int(n / (1 + hdecay * (k - 1) * 1.6)))
        part = np.zeros(n)
        m = np.minimum(n, part_decay)
        part[:m] = np.exp(-np.linspace(0, 1, m) * 4.0 * hdecay)
        y += a * part * np.sin(ph)
    y *= env_ad(n, atk, n - atk, dcurve)
    return y * amp


def noise(dur, f_lo=200, f_hi=None, amp=1.0, shape="exp", curve=4.0, order=4):
    """Filtered noise burst."""
    n = max(1, int(dur * SR))
    x = rng.standard_normal(n)
    nyq = SR / 2
    f_lo = max(20.0, min(f_lo, nyq * .98))
    if f_hi is not None:
        f_hi = min(f_hi, nyq * .98)
        if f_hi > f_lo * 1.05:
            b, a = butter(order, [f_lo / nyq, f_hi / nyq], btype="band")
        else:
            b, a = butter(order, f_lo / nyq, btype="high")
    else:
        b, a = butter(order, f_lo / nyq, btype="high")
    x = filtfilt(b, a, x)
    if shape == "exp":
        x *= np.exp(-np.linspace(0, 1, n) * curve)
    elif shape == "updown":
        x *= np.sin(np.linspace(0, np.pi, n)) ** 2
    return x * amp


def addsig(base, sig):
    """Add a signal into base, clipping to base's length."""
    m = min(len(base), len(sig))
    base[:m] += np.asarray(sig)[:m]
    return base


def pan(sig, p):
    """Constant-power pan: p = -1 (left) .. +1 (right)."""
    th = (np.clip(p, -1, 1) + 1) * np.pi / 4
    return np.stack([sig * np.cos(th), sig * np.sin(th)], axis=1)


def note_at(freq, t, dur, timbre, amp, p=0.0, vib=0.0):
    y = tone(freq, dur, timbre, amp, vibrato=vib)
    place(A, t, pan(y, p))


Nf = {  # note name -> frequency
    "Bb1": 58.27, "Eb2": 77.78, "Ab2": 103.83, "Bb2": 116.54, "Db3": 138.59,
    "Eb3": 155.56, "Ab3": 207.65, "Bb3": 233.08, "Db4": 277.18, "Eb4": 311.13,
    "Ab4": 415.30, "Bb4": 466.16, "Eb5": 622.25, "Ab5": 830.61, "Bb5": 932.33, "C2": 65.41, "D2": 73.42, "E2": 82.41, "F2": 87.31, "G2": 98.00,
    "A2": 110.0, "B2": 123.47, "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61,
    "G3": 196.0, "A3": 220.0, "B3": 246.94, "C4": 261.63, "D4": 293.66, "E4": 329.63,
    "F4": 349.23, "G4": 392.0, "A4": 440.0, "B4": 493.88, "C5": 523.25, "D5": 587.33,
    "E5": 659.25, "F5": 698.46, "G5": 783.99, "A5": 880.0, "B5": 987.77, "C6": 1046.5,
    "E6": 1318.5, "G6": 1568.0, "C7": 2093.0,
}


def ch(name):
    return [Nf[n] for n in name.split("+")]


# ============================================================== 1. THE STING
# Scene 1 (0-3s): dark, tense sting + glass crack
low = tone(41.2, 3.0, "bass", 0.55)
place(A, 0.0, np.stack([low, low], axis=1) * .5)
for nm, t, amp in [("G2", 0.0, .30), ("A2", 0.0, .26)]:      # dissonant minor-2 hit
    y = tone(Nf[nm] * 2, 1.5, "brass", amp)
    place(A, 0.0, np.stack([y, y], axis=1) * .5)
riser = noise(2.4, 300, 5000, 0.05, shape="updown")
place(A, 0.55, pan(riser, -0.2))
# sharp glass crack
nc = int(0.85 * SR)
crack = np.zeros(nc)
addsig(crack, noise(0.32, 2600, 12000, 0.55, curve=9))
for f in (3100, 4700, 6300, 8100, 9700):
    addsig(crack, 0.20 * tone(f, 0.85, "bell", 1.0))
place(A, 0.62, pan(crack, 0.15))

# =========================================================== 2. WARM ACOUSTIC
# Scene 2 (3-10s): nostalgic fingerpicked G major, 72 bpm
bpm = 72.0
beat = 60.0 / bpm
prog = ["G3+B3+D4", "E3+G3+B3", "C4+E4+G4", "D4+F4+A4"]
start, end = 3.0, 10.0
t = start
i = 0
while t < end - 0.35:
    cn = ch(prog[i % 4])
    for k, f in enumerate(cn):
        note_at(f, t + k * 0.028, 2.2, "pluck", 0.115 * (1 - k * 0.12), p=-0.35 + 0.35 * k)
    note_at(cn[0] / 2, t, 2.4, "bass", 0.10)
    # gentle high octave doubling for shimmer
    note_at(cn[2] * 2, t + beat, 1.6, "pluck", 0.035, p=0.4)
    t += beat * 2
    i += 1
padv = tone(Nf["G3"], end - start, "pad", 0.055)
place(A, start, np.stack([padv * .9, padv * 1.0], axis=1))
padv2 = tone(Nf["B3"], end - start, "pad", 0.038)
place(A, start, np.stack([padv2 * 1.0, padv2 * .9], axis=1))
# cloth-on-glass polishing texture
for k, tt in enumerate(np.arange(3.6, 9.4, 0.62)):
    sw = noise(0.42, 900, 5200, 0.030, shape="updown")
    place(A, tt, pan(sw, -0.5 if k % 2 else 0.5))

# ================================================= 3. THE SLIP (music stops)
# Scene 3 (10-18s): hard music stop at 10.0, air whoosh, gasp
# long accelerating whoosh as the butterfly falls
who = noise(3.4, 180, 4200, 0.16, shape="updown", order=2)
b, a = butter(2, [120 / (SR / 2), 900 / (SR / 2)], btype="band")
who = who + 0.7 * filtfilt(b, a, noise(3.4, 120, 900, 0.14, shape="updown", order=2))
place(A, 12.2, pan(who, -0.15))
tail = noise(1.1, 600, 7000, 0.09, shape="updown")
place(A, 16.4, pan(tail, 0.25))
# gasp: quick inhale
gasp = filtfilt(*butter(3, [420 / (SR / 2), 2600 / (SR / 2)], btype="band"),
               rng.standard_normal(int(0.5 * SR)))
gasp *= np.hanning(len(gasp)) * 0.16
place(A, 16.9, pan(gasp, 0.0))
# a lone, detuned high piano note hanging in the air
note_at(Nf["E5"], 15.6, 2.2, "piano", 0.07, p=0.2)

# ================================================== 4. THE CRASH + SAD PIANO
# Scene 4 (18-25s): impact, then sparse sad piano single notes
nch = int(1.6 * SR)
crash = np.zeros(nch)
addsig(crash, noise(0.9, 1500, 15000, 0.62, curve=6))
addsig(crash, filtfilt(*butter(2, [60 / (SR / 2), 220 / (SR / 2)], btype="band"), rng.standard_normal(int(0.6 * SR))) * np.exp(-np.linspace(0, 1, int(0.6 * SR)) * 5) * 0.5)
for f in (2400, 3300, 4200, 5100, 6600, 7900, 9400, 11200):
    addsig(crash, 0.13 * tone(f * rng.uniform(0.9, 1.15), 1.5, "bell", 1.0))
place(A, 18.0, pan(crash, 0.05))
# shimmering scatter
place(A, 18.12, pan(noise(1.5, 3000, 13000, 0.11, curve=5.5), 0.45))
sad = [("A2+E3", 19.0), ("F2+C3", 20.4), ("C3+G3", 21.9), ("G2+D3", 23.4)]
for nm, tt in sad:
    for k, f in enumerate(ch(nm)):
        note_at(f, tt, 3.0, "piano", 0.16 if k == 0 else 0.115, p=-0.25 + 0.25 * k)
note_at(Nf["A4"], 22.4, 2.6, "piano", 0.075, p=0.3)
padv = tone(Nf["A2"] * 2, 6.6, "pad", 0.05)
place(A, 18.4, np.stack([padv, padv * .85], axis=1))

# ================================================ 5. SPARK OF HOPE (window)
# Scene 5 (25-32s): wind chime, slow hopeful piano melody over pad
for k, (f, tt) in enumerate([(Nf["E6"], 25.6), (Nf["C6"], 25.85), (Nf["G6"], 26.1),
                             (Nf["D5"], 26.35), (Nf["C6"], 26.7)]):
    place(A, tt, pan(0.075 * tone(f, 2.2, "bell"), -0.55 + 0.28 * k))
hope = [("C4+E4", 26.6), ("G4+B4", 28.2), ("A4+C5", 29.8), ("E5", 31.0)]
for nm, tt in hope:
    for k, f in enumerate(ch(nm)):
        note_at(f, tt, 2.6, "piano", 0.13, p=-0.2 + 0.4 * k)
hpad1 = tone(Nf["C3"], 7.0, "pad", 0.062)
hpad2 = tone(Nf["E3"], 7.0, "pad", 0.05)
hpad3 = tone(Nf["G3"], 7.0, "pad", 0.042)
place(A, 25.0, np.stack([hpad1, hpad1 * .9], axis=1))
place(A, 25.0, np.stack([hpad2 * .9, hpad2], axis=1))
place(A, 25.0, np.stack([hpad3, hpad3 * .9], axis=1))
# faint wing struggle: airy flutter outside
flut = noise(6.4, 1200, 6500, 0.030)
flut *= 0.5 + 0.5 * (np.sin(2 * np.pi * 7.2 * np.arange(len(flut)) / SR) ** 8)
place(A, 25.4, pan(flut, 0.55))

# ============================================== 6. URGENT (tempo + strings)
# Scene 6 (32-40s): 144 bpm string ostinato, pulses, rising tension
bpm6 = 144.0
e8 = 60.0 / bpm6 / 2
ost = ["A3+C4+E4", "F3+A3+C4", "G3+B3+D4", "E3+G3+B3"]
t = 32.0
i = 0
while t < 40.0 - 0.2:
    cn = ch(ost[i % 4])
    accent = 0.085 if i % 2 == 0 else 0.058
    for k, f in enumerate(cn):
        note_at(f * 2, t, 0.42, "strings", accent * (1 - k * 0.15), p=-0.3 + 0.3 * k)
    if i % 4 == 0:
        note_at(cn[0] / 2, t, 1.5, "bass", 0.14)
    t += e8
    i += 1
# footsteps + fabric rustle
step_t = 32.35
k = 0
while step_t < 37.2:
    th = filtfilt(*butter(2, 240 / (SR / 2)), rng.standard_normal(int(0.12 * SR)))
    th *= np.exp(-np.linspace(0, 1, len(th)) * 7) * 0.30
    place(A, step_t, pan(th, -0.25 if k % 2 == 0 else 0.25))
    ru = noise(0.14, 1800, 7000, 0.055, shape="updown")
    place(A, step_t + 0.02, pan(ru, 0.3 if k % 2 == 0 else -0.3))
    step_t += 0.275
    k += 1
# riser into scene 7
place(A, 36.6, pan(noise(3.3, 200, 6000, 0.075, shape="updown", order=2), 0.0))
sw = tone(Nf["E3"], 3.2, "strings", 0.075)
place(A, 36.8, np.stack([sw, sw], axis=1))

# ============================================ 7. SWELL (emotional peak) / 8
# Scene 7-8 (40-52s): swelling orchestral, silk snaps, chime, big resolution
swell_chords = [(Nf["F2"], 40.0), (Nf["C3"], 40.0), (Nf["F3"], 40.0), (Nf["A3"], 40.0),
                (Nf["Bb2"], 42.0), (Nf["F3"], 42.0), (Nf["Bb3"], 42.0), (Nf["D4"], 42.0),
                (Nf["C3"], 44.0), (Nf["E3"], 44.0), (Nf["G3"], 44.0), (Nf["C4"], 44.0),
                (Nf["D3"], 46.0), (Nf["A3"], 46.0), (Nf["D4"], 46.0), (Nf["F4"], 46.0)]
for f, tt in swell_chords:
    dur = 48.0 - tt if tt < 48 else 52.5 - tt
    g = 0.085 * (1 + 0.5 * (tt - 40.0) / 8.0)
    note_at(f, tt, max(1.0, dur), "strings", g, p=-0.4 + 0.8 * ((f / 100) % 1))
# melodic line above
line = [("D5", 41.0), ("E5", 42.0), ("F5", 43.0), ("G5", 44.0), ("E5", 45.5),
        ("F5", 46.5), ("G5", 47.2), ("A5", 48.3), ("C6", 49.0), ("B5", 49.9), ("G5", 50.6)]
for nm, tt in line:
    note_at(Nf[nm], tt, 2.0, "strings", 0.085, p=0.15)
# delicate silk snaps
for tt, pp in [(40.9, -0.4), (42.6, 0.35), (44.3, -0.2)]:
    snap = noise(0.05, 2200, 9000, 0.30, curve=16)
    place(A, tt, pan(snap, pp))
# wing flutter freeing itself
wf = noise(2.2, 900, 5200, 0.055)
wf *= 0.35 + 0.65 * (np.sin(2 * np.pi * 11.0 * np.arange(len(wf)) / SR) ** 6)
place(A, 43.0, pan(wf, 0.45))
# peak swell + sparkle for "She was free" (48s)
peak = [Nf[n] for n in ("C3", "G3", "C4", "E4", "G4")]
for f in peak:
    note_at(f, 48.0, 4.2, "bell", 0.075, p=rng.uniform(-.5, .5))
place(A, 48.0, pan(noise(2.2, 4000, 14000, 0.07, shape="updown"), 0.0))
mag = [("C6", 48.8), ("E6", 49.0), ("G6", 49.2), ("C7", 49.45), ("E6", 50.4)]
for nm, tt in mag:
    place(A, tt, pan(0.075 * tone(Nf[nm], 2.6, "bell"), rng.uniform(-.4, .4)))
# airy pad under the nose-on-glass moment
air1 = tone(Nf["C4"], 4.6, "air", 0.05)
place(A, 47.8, np.stack([air1 * .9, air1], axis=1))

# ======================================== 9. RESOLVING (mosaic) / 10. FADE
# Scene 9 (52-57s): calm resolving melody, rhythmic glass clinks
res = [("D3+G3+B3", 52.0), ("C3+E3+G3+C4", 53.6), ("A2+E3+A3", 55.0), ("G2+D3+G3", 56.0)]
for nm, tt in res:
    for k, f in enumerate(ch(nm)):
        note_at(f, tt, 2.4, "piano", 0.12, p=-0.4 + 0.4 * k)
        note_at(f, tt, 1.6, "pluck", 0.05, p=0.4 - 0.4 * k)
mel9 = [("B4", 52.4), ("D5", 53.2), ("C5", 54.0), ("G4", 54.9), ("A4", 55.6), ("B4", 56.3)]
for nm, tt in mel9:
    note_at(Nf[nm], tt, 1.6, "pluck", 0.075, p=0.1)
clink_pat = [(52.4, -0.35, 5200), (52.9, 0.3, 6800), (53.5, -0.1, 4400),
             (54.1, 0.4, 7600), (54.6, -0.3, 5900), (55.3, 0.2, 4900),
             (55.9, -0.2, 8200), (56.4, 0.35, 6100)]
for tt, pp, f in clink_pat:
    ncl = int(0.55 * SR)
    c = np.zeros(ncl)
    addsig(c, 0.085 * tone(f * rng.uniform(0.94, 1.06), 0.55, "bell"))
    addsig(c[: int(0.03 * SR)], noise(0.03, 3000, 11000, 0.10))
    place(A, tt, pan(c, pp))

# Scene 10 (57-60s): gentle fade out, final piano note
final = [("F2+C3+F3+A3", 57.0), ("G2+D3+G3+B3", 58.2), ("C3+E3+G3+C4", 59.2)]
for nm, tt in final:
    for k, f in enumerate(ch(nm)):
        note_at(f, tt, 3.6, "piano", 0.115, p=-0.35 + 0.35 * k)
        note_at(f, tt, 3.0, "pad", 0.05, p=0.35 - 0.35 * k)
note_at(Nf["C6"], 59.3, 3.0, "bell", 0.06, p=0.2)
note_at(Nf["C2"], 60.2, 2.2, "piano", 0.13)
note_at(Nf["E4"], 60.2, 2.0, "piano", 0.05, p=0.3)
# long tail fading into the end card
tail_env = np.linspace(1, 0, N - int(60.0 * SR)) ** 1.6
for c2 in range(2):
    A[int(60.0 * SR):, c2] *= tail_env

# ==================================================== 3. MIX: space + duck
def make_ir(dur_s, decay, lp):
    n = int(dur_s * SR)
    x = rng.standard_normal(n) * np.exp(-np.linspace(0, 1, n) * decay)
    b, a = butter(2, lp / (SR / 2), btype="low")
    x = filtfilt(b, a, x)
    x[0] *= 0.4
    return x / (np.sqrt(np.sum(x ** 2)) + 1e-9) * 0.55


ir_room = make_ir(0.85, 6.0, 7000)
ir_hall = make_ir(2.4, 3.2, 5200)

music_wet = fftconvolve(A, ir_hall[:, None], mode="full")[:N] * 0.34
A = A + music_wet

# --- voiceover: resample 24k -> 48k, gentle presence lift, slapback + room
vo = np.zeros((N, 2))
for (idx, s0, s1, fn), off in zip(SCENES, VO_START_OFFSET):
    path = os.path.join(VO_DIR, fn)
    if not os.path.exists(path):
        print("missing", path)
        continue
    with wave.open(path) as w:
        nch, sw, fr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if nch > 1:
        d = d.reshape(-1, nch).mean(axis=1)
    g = np.gcd(SR, fr)
    d = resample_poly(d, SR // g, fr // g)
    b, a = butter(2, 95 / (SR / 2), btype="high")
    d = filtfilt(b, a, d)
    # de-ess-ish: tame 6-9k harshness
    hs = filtfilt(*butter(2, [6000 / (SR / 2), 9500 / (SR / 2)], btype="band"), d)
    d = d - 0.25 * hs
    # soft presence lift for narration clarity
    ps = filtfilt(*butter(2, [2200 / (SR / 2), 4200 / (SR / 2)], btype="band"), d)
    d = d + 0.18 * ps
    d = fftconvolve(d, make_ir(0.45, 9.0, 6500), mode="full")[: len(d)] * 0.9 + d
    d = np.clip(d, -1, 1)
    place(vo, off, np.stack([d, d], axis=1))
    print(f"vo{idx:02d} at {off:.2f}s dur {len(d)/SR:.2f}s  (scene {s0:.0f}-{s1:.0f}s)")

# --- duck the music under narration (fast attack, slow release)
from scipy.ndimage import uniform_filter1d
env = np.abs(vo).max(axis=1)
env = uniform_filter1d(env, int(0.06 * SR))
ref = np.percentile(env, 99.7)
env = np.clip(env / (0.55 * ref + 1e-9), 0, 1)
env = uniform_filter1d(env, int(0.28 * SR))
duck = 1.0 - 0.55 * env
A *= duck[:, None]

mix = A * 0.62 + vo * 1.05
# gentle glue: tanh soft clip + low-shelf warmth
mix = np.tanh(mix * 1.15) / np.tanh(1.15)
_b, _a = butter(1, 9000 / (SR / 2), btype="high")
hi = np.stack([filtfilt(_b, _a, mix[:, c], axis=0) for c in range(mix.shape[1])], axis=1)
mix = mix - 0.22 * hi
mix *= 0.95 / (np.abs(mix).max() + 1e-9)
print("peak", round(float(np.abs(mix).max()), 3), "rms", round(float(np.sqrt((mix ** 2).mean())), 4))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
pcm = (mix * 32767).astype(np.int16)
with wave.open(OUT, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", OUT, round(N / SR, 2), "s")
