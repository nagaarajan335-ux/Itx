"""Story mode: word alignment, planning, sound design, and a tiny end-to-end render."""
import json
from pathlib import Path

import av
import numpy as np
import pytest
from PIL import Image

from shorts_maker import soundscape as sx
from shorts_maker import story as st
from shorts_maker.cli import main
from shorts_maker.media import MediaError, decode_audio, write_wav

REPO = Path(__file__).resolve().parent.parent
SMALL = dict(width=270, height=480, fps=15, preset="ultrafast", crf=30)


# --------------------------------------------------------------------------- helpers
def make_voice(path, bursts, sr=24000, tail=0.2):
    """A stand-in for a recorded line: harmonic 'syllables' with pauses between them."""
    t = np.arange(int((bursts[-1][1] + tail) * sr)) / sr
    x = np.zeros_like(t)
    for a, b in bursts:
        m = (t >= a) & (t < b)
        env = np.sin(np.pi * (t[m] - a) / (b - a)) ** 0.5
        f0 = 140 + 20 * np.sin(2 * np.pi * 3 * t[m])
        phase = 2 * np.pi * np.cumsum(f0) / sr
        x[m] = env * sum(np.sin(k * phase) / k for k in range(1, 8))
    write_wav(path, 0.4 * x / np.abs(x).max(), sr)


def smooth_picture(i, base, w=360, h=640):
    """Gradients and one block: cheap to encode, so two renders only differ where the content does."""
    y, x = np.mgrid[0:h, 0:w]
    arr = np.stack([base[c] + 30 * (x / w) - 20 * (y / h) + 12 * np.sin(2 * np.pi * (i + 1) * x / w) for c in range(3)], axis=-1)
    arr[h // 3: h // 2, w // 4: w // 2] += 40
    return arr.clip(0, 255).astype("uint8")


def make_story(root: Path, **overrides) -> Path:
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "voice").mkdir(exist_ok=True)
    for i, base in enumerate([(40, 70, 110), (110, 60, 50), (50, 100, 60)]):
        Image.fromarray(smooth_picture(i, base)).save(root / "images" / f"s{i}.jpg", quality=95)
    make_voice(root / "voice" / "a.wav", [(0.05, 0.7), (1.0, 1.9)])
    make_voice(root / "voice" / "b.wav", [(0.05, 0.9)])
    make_voice(root / "voice" / "w.wav", [(0.05, 0.5)])
    spec = {
        "title": "Test Story",
        "hook": "PART 1: TEST",
        "grain": 0,  # film grain is random per render; off so two renders can be compared pixel for pixel
        "scenes": [
            {"image": "images/s0.jpg", "duration": 1, "tension": 0.2, "motion": {"zoom": [1.0, 1.1], "flicker": 0.5},
             "lines": [{"audio": "voice/a.wav", "text": "Hello there, my good friend.", "pauses": {"0": 0.2}}]},
            {"image": "images/s1.jpg", "duration": 2, "tension": 0.5,
             "transition": {"type": "fade", "duration": 0.6, "align": "end"},
             "motion": {"zoom": [1.1, 1.3], "shake": 3},
             "lines": [{"audio": "voice/b.wav", "text": "It was nothing at all.", "at": 0.4}],
             "sfx": [{"type": "creak", "at": 0.1}, {"type": "click", "at": 1.2}, {"type": "heartbeat", "at": 0, "dur": 5}]},
            {"image": "images/s2.jpg", "duration": 2.5, "tension": 1.0,
             "lines": [{"audio": "voice/w.wav", "style": "whisper", "text": "Rajan...", "at": 0.4}],
             "sfx": [{"type": "dropout", "at": 0.0, "dur": 1.0}, {"type": "riser", "at": 0.8, "dur": 0.8},
                     {"type": "boom", "at": 1.5, "dur": 1.5}],
             "end_text": {"text": "PART 2?", "at": 1.5, "dim": 0.5}},
        ],
    }
    spec.update(overrides)
    path = root / "story.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def read_video(path):
    with av.open(str(path)) as c:
        v, a = c.streams.video[0], next((s for s in c.streams if s.type == "audio"), None)
        info = {"w": v.codec_context.width, "h": v.codec_context.height, "has_audio": a is not None,
                "vdur": float(v.duration * v.time_base), "adur": float(a.duration * a.time_base) if a else 0.0}
        frames = [f.to_ndarray(format="gray").astype(np.float32) for f in c.decode(v)]
    info["frames"] = frames
    return info


@pytest.fixture(scope="module")
def story_file(tmp_path_factory):
    return make_story(tmp_path_factory.mktemp("story"))


@pytest.fixture(scope="module")
def built(story_file, tmp_path_factory):
    out = tmp_path_factory.mktemp("story_out")
    summary = st.build_story(story_file, out, st.StoryOptions(**SMALL), log=lambda m: None)
    return summary, out


# --------------------------------------------------------------------------- words and pauses
def test_align_words_matches_phrases_to_pauses():
    words = st.align_words("Last night, I found a door.", [(0.0, 0.6), (1.0, 2.0)])
    assert [w["word"] for w in words] == ["Last", "night,", "I", "found", "a", "door."]
    assert words[1]["end"] == pytest.approx(0.6)  # "night," closes the first stretch of speech
    assert words[2]["start"] == pytest.approx(1.0)  # "I" opens the second
    assert words[-1]["end"] == pytest.approx(2.0)
    assert all(a["start"] <= a["end"] <= b["start"] + 1e-9 for a, b in zip(words, words[1:]))


def test_align_words_falls_back_to_even_spread_when_pauses_do_not_match():
    words = st.align_words("Last night, I found a door.", [(0.5, 3.5)])  # 2 phrases, 1 stretch of speech
    assert words[0]["start"] == pytest.approx(0.5) and words[-1]["end"] == pytest.approx(3.5)
    assert all(a["end"] == pytest.approx(b["start"]) for a, b in zip(words, words[1:]))
    assert st.align_words("", [(0, 1)]) == [] and st.align_words("hi", []) == []


def test_longer_words_get_more_time():
    short, long_ = st.align_words("a extraordinarily", [(0.0, 1.0)])
    assert long_["end"] - long_["start"] > 3 * (short["end"] - short["start"])


def test_insert_pauses_lengthens_only_the_chosen_gap():
    audio = np.zeros(3 * sx.SR, np.float32)
    out, spans = st._insert_pauses(audio, [(0.0, 1.0), (2.0, 3.0)], {0: 0.5})
    assert len(out) == len(audio) + int(0.5 * sx.SR)
    assert spans[0] == (0.0, 1.0) and spans[1] == pytest.approx((2.5, 3.5))
    same, spans2 = st._insert_pauses(audio, [(0.0, 1.0), (2.0, 3.0)], {5: 1.0})  # no such gap: untouched
    assert len(same) == len(audio) and spans2 == [(0.0, 1.0), (2.0, 3.0)]


# --------------------------------------------------------------------------- planning
def test_plan_stretches_scenes_to_fit_the_voice_and_lays_out_frames(story_file):
    spec = json.loads(story_file.read_text())
    plan = st.plan_story(spec, story_file.parent, st.StoryOptions(**SMALL))
    s0, s1, s2 = plan.scenes
    assert s0.dur > 1.0 and s0.lines[0].end + 0.5 <= s0.dur + 1e-6  # asked for 1 s, but the line is longer
    assert s1.start_frame == s0.frames and s2.start_frame == s0.frames + s1.frames
    assert plan.total_frames == s0.frames + s1.frames + s2.frames
    assert plan.total == pytest.approx(plan.total_frames / 15)
    assert s1.trans_type == "fade" and s1.head_frames == s1.trans_frames == 9  # 0.6 s at 15 fps, ending on the cut
    assert s0.stream_frames == s0.frames + 0 + st.STREAM_PAD  # next scene is "end" aligned: no overlap tail needed
    assert s1.stream_frames == 9 + s1.frames + st.STREAM_PAD
    assert s0.lines[0].words and s0.lines[0].words[0]["start"] >= s0.lines[0].at
    assert s2.lines[0].style == "whisper" and s2.lines[0].words == []
    assert [c.kind for c in s2.cues] == ["dropout", "riser", "boom"]
    assert s2.end_text["at"] == pytest.approx(s2.start + 1.5)


def test_negative_cue_times_count_back_from_the_end_of_the_scene(story_file):
    spec = json.loads(story_file.read_text())
    spec["scenes"][2]["sfx"] = [{"type": "boom", "at": -1.0}]
    plan = st.plan_story(spec, story_file.parent, st.StoryOptions(**SMALL))
    last = plan.scenes[2]
    assert last.cues[0].at == pytest.approx(last.start + last.dur - 1.0)


@pytest.mark.parametrize(
    "mutate, exc, match",
    [
        (lambda s: s.update(scenes=[]), ValueError, "scenes"),
        (lambda s: s["scenes"][1]["transition"].update(type="swirl"), ValueError, "transition"),
        (lambda s: s["scenes"][1]["transition"].update(align="middle"), ValueError, "align"),
        (lambda s: s["scenes"][0]["lines"][0].update(style="shout"), ValueError, "style"),
        (lambda s: s["scenes"][1]["sfx"].append({"type": "laser"}), ValueError, "sfx"),
        (lambda s: s["scenes"][0].update(image="images/nope.jpg"), MediaError, "not found"),
        (lambda s: s["scenes"][0]["lines"][0].update(audio="voice/nope.wav"), MediaError, "not found"),
    ],
)
def test_plan_rejects_bad_scripts_with_a_clear_message(story_file, mutate, exc, match):
    spec = json.loads(story_file.read_text())
    mutate(spec)
    with pytest.raises(exc, match=match):
        st.plan_story(spec, story_file.parent, st.StoryOptions(**SMALL))


def test_the_shipped_story_still_plans_cleanly():
    folder = REPO / "stories" / "part-1-the-door"
    spec = json.loads((folder / "story.json").read_text(encoding="utf-8"))
    plan = st.plan_story(spec, folder, st.StoryOptions())
    assert len(plan.scenes) == 5 and 28.0 < plan.total < 31.0
    assert plan.hook and plan.scenes[-1].end_text["text"] == "PART 2?"
    spoken = [w["word"] for sc in plan.scenes for ln in sc.lines for w in ln.words]
    assert " ".join(spoken).startswith("I have lived in this apartment for six months.")
    assert " ".join(spoken).endswith("Then I heard someone whisper my name.")
    for sc in plan.scenes:  # every voice line sits inside its own scene
        for ln in sc.lines:
            assert sc.start <= ln.at and ln.end <= sc.start + sc.dur + 1e-6


# --------------------------------------------------------------------------- sound design
def test_speech_spans_find_each_burst(tmp_path):
    make_voice(tmp_path / "v.wav", [(0.1, 0.6), (1.0, 1.8)], sr=48000)
    spans = sx.speech_spans(decode_audio(tmp_path / "v.wav"))
    assert len(spans) == 2
    assert spans[0][0] == pytest.approx(0.1, abs=0.1) and spans[1][1] == pytest.approx(1.8, abs=0.1)


def test_whisperise_changes_the_waveform_but_keeps_the_rhythm(tmp_path):
    make_voice(tmp_path / "v.wav", [(0.1, 0.6), (1.0, 1.8)], sr=48000)
    x = decode_audio(tmp_path / "v.wav")
    w = sx.whisperise(x)
    assert len(w) == len(x) and np.isfinite(w).all()
    assert abs(np.corrcoef(x, w)[0, 1]) < 0.3  # phases were thrown away: not the same waveform
    env = lambda a: np.sqrt(np.convolve(a * a, np.ones(480) / 480, "same"))  # 10 ms RMS
    assert np.corrcoef(env(x), env(w))[0, 1] > 0.8  # but the words still start and stop together


def test_limiter_never_exceeds_the_ceiling_and_leaves_quiet_audio_alone():
    rng = np.random.default_rng(0)
    loud = (rng.standard_normal((sx.SR, 2)) * 0.8).astype(np.float32)
    assert np.abs(sx.limit(loud, 0.4)).max() <= 0.4 + 1e-6
    quiet = (rng.standard_normal((sx.SR, 2)) * 0.05).astype(np.float32)
    np.testing.assert_allclose(sx.limit(quiet, 0.4), quiet, atol=1e-6)


def test_narrator_chain_levels_speech_to_the_target(tmp_path):
    make_voice(tmp_path / "v.wav", [(0.1, 0.8), (1.2, 2.0)], sr=48000)
    audio, spans = sx.trim_to_speech(decode_audio(tmp_path / "v.wav"))
    out = sx.level_to(sx.narrator(audio), -20.0, spans)
    assert sx.active_level_db(out, spans) == pytest.approx(-20.0, abs=0.2)
    assert np.isfinite(out).all()


def test_dropout_curve_goes_quiet_inside_the_hole_only():
    t = np.arange(10 * 1000) / 1000.0
    g = sx.dropout_curve([(4.0, 2.0, 0.3)], t, floor=0.05)
    assert g[2000] == pytest.approx(1.0) and g[5000] == pytest.approx(0.05) and g[8000] == pytest.approx(1.0)


def test_sources_are_finite_and_peak_normalised():
    rng = np.random.default_rng(1)
    for x in (sx.heartbeat(3, 60, 100), sx.riser(1, rng), sx.boom(1, rng), sx.creak(1, rng), sx.click(rng), sx.whoosh(1, rng)):
        assert np.isfinite(x).all() and np.abs(x).max() == pytest.approx(1.0, abs=1e-4)
    d = sx.drone(2, rng)
    assert d.shape == (2 * sx.SR, 2) and sx.rms(d) == pytest.approx(1.0, abs=0.05)


def test_master_lands_on_the_target_loudness_without_clipping(tmp_path):
    rng = np.random.default_rng(2)
    t = np.arange(6 * sx.SR) / sx.SR
    tone = 0.05 * np.sin(2 * np.pi * 220 * t) * (1 + np.sin(2 * np.pi * 0.7 * t)) + 0.01 * rng.standard_normal(len(t))
    out, info = st.master(np.stack([tone, tone], axis=1).astype(np.float32), tmp_path)
    assert info["lufs"] == pytest.approx(st.TARGET_LUFS, abs=0.5)
    assert np.abs(out).max() <= sx.db(st.PEAK_CEILING_DB) + 1e-4


# --------------------------------------------------------------------------- full render
def test_story_render_has_exact_frame_count_matching_audio_and_no_black_frames(built, story_file):
    summary, _ = built
    v = read_video(summary["file"])
    plan = st.plan_story(json.loads(story_file.read_text()), story_file.parent, st.StoryOptions(**SMALL))
    assert (v["w"], v["h"]) == (270, 480) and v["has_audio"]
    assert len(v["frames"]) == plan.total_frames  # no frame lost or added at any scene join
    assert v["vdur"] == pytest.approx(v["adur"], abs=0.03)  # picture and sound end together
    assert v["vdur"] == pytest.approx(plan.total, abs=0.05)
    luma = [f.mean() for f in v["frames"]]
    body = luma[12:-10]  # skip the fade in and out
    assert min(body) > 8  # the cut between scenes must not flash black
    assert summary["lufs"] == pytest.approx(st.TARGET_LUFS, abs=0.5) and summary["true_peak"] < -1.0


def test_story_render_burns_in_captions_hook_and_end_card(built, story_file, tmp_path):
    summary, _ = built
    plan = st.plan_story(json.loads(story_file.read_text()), story_file.parent, st.StoryOptions(**SMALL))
    plain = st.build_story(story_file, tmp_path, st.StoryOptions(**SMALL, captions=False), log=lambda m: None)
    a, b = read_video(summary["file"])["frames"], read_video(plain["file"])["frames"]
    fps = 15
    frame = lambda t: int(t * fps)

    def diff(t, rows):  # how different the captioned and caption-free renders are in a band of rows
        return float(np.abs(a[frame(t)][rows] - b[frame(t)][rows]).mean())

    word = plan.scenes[0].lines[0].words[1]  # while a word is spoken, the caption band must differ...
    assert diff((word["start"] + word["end"]) / 2, slice(290, 350)) > 3.0
    assert diff((word["start"] + word["end"]) / 2, slice(0, 120)) < 1.5  # ...and nothing else on screen does
    # the hook banner is a title, not a caption: it is in both renders, in the top part of the picture
    assert diff(1.5, slice(40, 110)) < 1.5 and a[frame(1.5)][40:110].max() > 200
    # the end card dims the picture and writes big white text, with or without captions
    scene = plan.scenes[2]
    early, late = frame(scene.start + 0.2), frame(scene.end_text["at"] + 0.4)
    assert a[late].mean() < 0.8 * a[early].mean()
    assert a[late][270:350].max() > 200 and diff(scene.end_text["at"] + 0.4, slice(0, 480)) < 1.5


def test_story_cli_end_to_end_and_errors(story_file, tmp_path, capsys):
    out = tmp_path / "cli_out"
    args = ["story", str(story_file), "--out", str(out), "--size", "270x480", "--fps", "15", "--preset", "ultrafast",
            "--crf", "30", "--preview", "2"]
    assert main(args) == 0
    made = list(out.glob("*.mp4"))
    assert len(made) == 1 and read_video(made[0])["vdur"] == pytest.approx(2.0, abs=0.1)
    err = capsys.readouterr().err
    assert "synthetic" in err  # the disclosure reminder is printed
    assert main(["story", str(tmp_path / "missing.json")]) == 2
    assert "not found" in capsys.readouterr().err
    assert main(["story", str(story_file), "--size", "big"]) == 2
    assert "--size" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    assert main(["story", str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().err
