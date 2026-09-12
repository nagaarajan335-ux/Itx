# Barnaby the Mender — production notes

Vertical 9:16 short built from the 10-scene storyboard. Everything is generated
in-repo: AI keyframes + a Python render pipeline (no external video tool).

## Deliverables

| File | What |
|---|---|
| `output/barnaby_the_mender_9x16.mp4` | 1080x1920, 30 fps, H.264 + AAC, 62.5 s |
| `Itx/assets/scene01..10.png` | 768x1376 AI keyframes (one per scene) |
| `Itx/build/audio_mix.wav` | 48 kHz stereo master: narration + score + SFX |

The 10 scenes sit exactly on the storyboard timings (0-3-10-18-25-32-40-48-52-57-60 s).
Frames 60.0-62.5 s are an optional end card — delete that tail for a hard 60 s cut.

## Re-render

```bash
python3 -m venv .venv && .venv/bin/pip install numpy pillow scipy matplotlib imageio-ffmpeg
.venv/bin/python Itx/tools/audio_barnaby.py       # score + SFX + VO mix
.venv/bin/python Itx/tools/render_barnaby.py      # ~4 fps, ~8 min on 2 cores
```

`render_barnaby.py --preview 14` dumps stills instead of video (fast layout checks).
Voiceover clips are separate per scene (`Itx/build/vo/voNN.wav`) so lines can be
re-voiced individually; their positions are the `VO_START_OFFSET` table in
`audio_barnaby.py`.

## What the renderer does

Per scene, driven by the `SCENES` table (`t0/t1`, image, text, camera, grade, fx):

* **Camera** — magnification + pan interpolated with smoothstep easing (Ken Burns),
  so each shot matches its storyboard direction: macro push-in (1), slow pan right (2),
  Dutch-angle lunge with shake (3), pull-back on the floor (4), creep toward the
  window (5), handheld jitter (6), held-breath close-up (7), gentle push (8),
  top-down roll-out (9), static wide (10).
* **Grade** — per-scene saturation / contrast / temperature / gamma / vignette, so the
  warm attic cools and desaturates at the shatter and blooms again for the release.
* **Look** — bloom on highlights, film grain, dust motes, drifting lens flare,
  impact flash + decaying camera shake on the crash, cross-dissolves on every cut
  except the shatter (hard cut at 18 s).
* **Titles** — the storyboard's on-screen text, letter-spaced DejaVu Sans Bold over a
  soft scrim, with hand-drawn vector icons standing in for the emoji (a real colour
  emoji font isn't available in this sandbox): broken heart, tear, eye, butterfly,
  palette, sparkle. Plus a chapter marker and a progress bar.

## Audio

Synthesised with numpy/scipy (nothing licensed, nothing fetched): a mood-following
score (tense sting -> acoustic G-major nostalgia -> dead air on the fall -> sparse
A-minor piano -> hopeful motif -> 144 bpm string ostinato -> orchestral swell ->
resolving C major fade), plus designed SFX (glass crack, whoosh, gasp, shatter, wind
chime, footsteps, silk snaps, wing flutter, magical chime, rhythmic glass clinks),
hall reverb, and sidechain ducking so the narration always sits on top.

## Tweaks worth knowing

* `FADE` — dissolve length; `MASTER_W` — working resolution (raise it if you feed in
  larger keyframes, then zoom ranges can go deeper).
* `s0/s1` + `pan` per scene — zoom depth and drift; `shake=dict(amp,f,decay)` — impact.
* `--no-audio`, `--out path.mp4` on the CLI.
