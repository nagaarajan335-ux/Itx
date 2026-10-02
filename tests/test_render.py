import json

import av
import numpy as np
import pytest

from shorts_maker import render as R
from shorts_maker.cli import main
from shorts_maker.media import MediaError, MediaInfo, probe
from shorts_maker.transcript import load_transcript

FAST = dict(preset="ultrafast", crf=30)


def info(w=1280, h=720, audio=True, dur=16.0):
    return MediaInfo(duration=dur, width=w, height=h, fps=25.0, has_audio=audio)


def streams(path):
    with av.open(str(path)) as c:
        v = c.streams.video[0]
        a = next((s for s in c.streams if s.type == "audio"), None)
        return {
            "w": v.codec_context.width, "h": v.codec_context.height, "vcodec": v.codec_context.name,
            "acodec": a.codec_context.name if a else None, "duration": float(c.duration) / av.time_base,
            "fps": float(v.average_rate),
        }


def frame_at(path, t):
    with av.open(str(path)) as c:
        v = c.streams.video[0]
        c.seek(int(t / v.time_base), stream=v)
        for frame in c.decode(v):
            if frame.time is not None and frame.time >= t - 1e-3:
                return frame.to_ndarray(format="rgb24")


def bright_pixels(img, y0, y1):
    band = img[y0:y1].astype(int)
    return int(((band[:, :, 0] > 245) & (band[:, :, 1] > 245) & (band[:, :, 2] > 245)).sum())


# ----------------------------------------------------------------------------- pure functions
def test_snap_clip_keeps_words_whole_and_trims_dead_air():
    ws = [{"word": "a", "start": 1.0, "end": 1.4}, {"word": "b", "start": 1.5, "end": 2.0}, {"word": "c", "start": 2.1, "end": 2.6}]
    assert R.snap_clip(1.2, 2.3, ws, 10)[0] == 1.0  # cut was inside "a" -> include all of it
    assert R.snap_clip(0.5, 2.3, ws, 10)[0] == 1.0  # silence before the first word is dropped
    assert R.snap_clip(0.0, 2.3, ws, 10)[0] == 0.0  # too far away to snap
    assert R.snap_clip(1.0, 2.3, ws, 10)[1] == 2.6  # cut was inside "c" -> finish the word
    assert R.snap_clip(1.0, 5.0, ws, 10)[1] == 5.0
    assert R.snap_clip(1.0, 50.0, ws, 10)[1] == 10  # never past the end of the video
    assert R.snap_clip(1.2, 2.0, [], 10) == (1.2, 2.0)


def test_plan_layout_for_widescreen_square_and_vertical_sources():
    opts = R.RenderOptions()
    blur = R.plan_layout(info(), opts)
    assert (blur["layout"], blur["fg_h"], blur["top"]) == ("blur", 608, 525)
    assert blur["caption_y"] >= blur["top"] + blur["fg_h"] + 100, "captions sit below the video"
    assert blur["hook_y"] < blur["top"], "hook sits above the video"

    square = R.plan_layout(info(1080, 1080), opts)
    assert square["caption_y"] <= int(1920 * 0.70), "captions must stay out of the bottom UI zone"

    crop = R.plan_layout(info(), R.RenderOptions(layout="crop"), focus=0.0)
    assert (crop["x"], crop["y"], crop["sh"]) == (0, 0, 1920)
    assert R.plan_layout(info(), R.RenderOptions(layout="crop"), focus=1.0)["x"] == crop["sw"] - 1080

    for vertical in (info(720, 1280), info(1080, 2400)):
        plan = R.plan_layout(vertical, opts)  # even if "blur" was requested
        assert plan["layout"] == "crop" and plan["sw"] >= 1080 and plan["sh"] >= 1920


def test_description_links_back_to_the_exact_moment():
    d = R.build_description({}, "Hook line", 125.7, "https://youtu.be/abc123", "Credit: me", "#shorts #demo")
    assert d.startswith("Hook line")
    assert "https://youtu.be/abc123?t=125s" in d and "Credit: me" in d and d.endswith("#shorts #demo")
    assert "Watch" not in R.build_description({}, "Hook", 1, None, None, "")


# ----------------------------------------------------------------------------- real renders
def test_probe_reports_display_size_and_streams(source_video, silent_video):
    i = probe(source_video)
    assert (i.width, i.height, i.has_audio) == (1280, 720, True) and i.duration == pytest.approx(16, abs=0.3)
    assert probe(silent_video).has_audio is False
    with pytest.raises(MediaError):
        probe(source_video.parent / "nope.mp4")


def test_blur_layout_outputs_1080x1920_h264_aac(tmp_path, source_video, fake_words):
    out = tmp_path / "o.mp4"
    meta = R.render_clip(source_video, {"start": 1.0, "end": 7.0, "hook": "Hook text"}, fake_words, out,
                         R.RenderOptions(**FAST), probe(source_video))
    s = streams(out)
    assert (s["w"], s["h"], s["vcodec"], s["acodec"]) == (1080, 1920, "h264", "aac")
    assert s["fps"] == pytest.approx(30, abs=0.1)
    assert s["duration"] == pytest.approx(meta["duration"], abs=0.25)
    assert 6.0 <= meta["duration"] <= 7.5  # 6 s of content + lead-in and tail


def test_captions_and_hook_are_really_burned_into_the_pixels(tmp_path, source_video, fake_words):
    base = dict(clip={"start": 1.0, "end": 7.0, "hook": "Hook text"}, words=fake_words, i=probe(source_video))
    with_caps, without = tmp_path / "with.mp4", tmp_path / "without.mp4"
    R.render_clip(source_video, base["clip"], fake_words, with_caps, R.RenderOptions(**FAST), base["i"])
    R.render_clip(source_video, base["clip"], fake_words, without, R.RenderOptions(captions=False, hook=False, **FAST), base["i"])
    f_with, f_without = frame_at(with_caps, 3.0), frame_at(without, 3.0)
    caption_band = (1150, 1350)
    assert bright_pixels(f_with, *caption_band) > 800 + bright_pixels(f_without, *caption_band)
    # the hook banner is yellow-on-dark text near the top during the first seconds
    hook_with, hook_without = frame_at(with_caps, 1.0), frame_at(without, 1.0)
    assert np.abs(hook_with[150:500].astype(int) - hook_without[150:500].astype(int)).mean() > 5
    # ...and gone again afterwards
    late_with, late_without = frame_at(with_caps, 5.0), frame_at(without, 5.0)
    assert np.abs(late_with[150:450].astype(int) - late_without[150:450].astype(int)).mean() < 2


def test_crop_layout_fills_the_screen_and_focus_moves_the_window(tmp_path, source_video):
    a, b = tmp_path / "left.mp4", tmp_path / "right.mp4"
    opts = R.RenderOptions(layout="crop", captions=False, hook=False, **FAST)
    R.render_clip(source_video, {"start": 1, "end": 4, "focus": 0.0}, [], a, opts, probe(source_video))
    R.render_clip(source_video, {"start": 1, "end": 4, "focus": 1.0}, [], b, opts, probe(source_video))
    assert streams(a)["w"] == 1080 and streams(a)["h"] == 1920
    fa, fb = frame_at(a, 1.5), frame_at(b, 1.5)
    assert np.abs(fa.astype(int) - fb.astype(int)).mean() > 20, "different focus must show different parts of the frame"


def test_portrait_and_silent_sources_are_handled(tmp_path, portrait_video, silent_video):
    p = tmp_path / "p.mp4"
    R.render_clip(portrait_video, {"start": 0.5, "end": 4}, [], p, R.RenderOptions(captions=False, hook=False, **FAST), probe(portrait_video))
    assert (streams(p)["w"], streams(p)["h"]) == (1080, 1920)

    s = tmp_path / "s.mp4"
    R.render_clip(silent_video, {"start": 0.5, "end": 4}, [], s, R.RenderOptions(captions=False, hook=False, **FAST), probe(silent_video))
    assert streams(s)["acodec"] is None and streams(s)["h"] == 1920


def test_audio_is_normalised_towards_minus_14_lufs(tmp_path, source_video):
    out = tmp_path / "loud.mp4"
    R.render_clip(source_video, {"start": 1, "end": 8}, [], out, R.RenderOptions(captions=False, hook=False, **FAST), probe(source_video))
    proc = R.run_ffmpeg(["-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"], loglevel="info")
    text = proc.stderr.decode()
    integrated = float(text.rsplit("I:", 1)[1].split("LUFS")[0])
    assert -16.0 < integrated < -12.0, f"integrated loudness was {integrated} LUFS"


def test_clip_shorter_than_a_second_is_rejected(tmp_path, source_video):
    with pytest.raises(MediaError):
        R.render_clip(source_video, {"start": 2.0, "end": 2.1}, [], tmp_path / "x.mp4",
                      R.RenderOptions(lead_in=0, tail=0, **FAST), probe(source_video))


# ----------------------------------------------------------------------------- batch + CLI
def test_render_all_writes_files_and_a_report(tmp_path, source_video, srt_file):
    clips = [{"start": 0.5, "end": 9.0, "hook": "Why did nobody warn you?", "title": "The mistake nobody warns you about"}]
    results = R.render_all(source_video, clips, load_transcript(srt_file), tmp_path / "out", R.RenderOptions(**FAST),
                           source_url="https://www.youtube.com/watch?v=abc123", credit="Credit line", log=lambda m: None)
    assert (tmp_path / "out" / results[0]["file"]).is_file()
    report = json.loads((tmp_path / "out" / "shorts.json").read_text())
    assert report["shorts"][0]["title"] == "The mistake nobody warns you about"
    assert "&t=" in report["shorts"][0]["description"] and "Credit line" in report["shorts"][0]["description"]
    assert "## 1. The mistake nobody warns you about" in (tmp_path / "out" / "shorts.md").read_text()

    with pytest.raises(ValueError, match="only"):
        R.render_all(source_video, [{"start": 99, "end": 120}], None, tmp_path / "o2", R.RenderOptions(**FAST), log=lambda m: None)


def test_cli_run_end_to_end_from_subtitles(tmp_path, source_video, srt_file, capsys):
    code = main(["run", str(source_video), "--transcript", str(srt_file), "--work", str(tmp_path / "w"),
                 "--out", str(tmp_path / "o"), "--count", "1", "--min-len", "6", "--max-len", "14", "--preset", "ultrafast", "--crf", "30"])
    assert code == 0
    mp4s = list((tmp_path / "o").glob("short_01_*.mp4"))
    assert len(mp4s) == 1 and streams(mp4s[0])["h"] == 1920
    clips = json.loads((tmp_path / "w" / "clips.json").read_text())["clips"]
    assert len(clips) == 1 and 6 <= clips[0]["end"] - clips[0]["start"] <= 14
    assert "Reminder" in capsys.readouterr().err


def test_cli_suggest_then_render_uses_the_edited_clips_file(tmp_path, source_video, srt_file):
    work, out = tmp_path / "w", tmp_path / "o"
    assert main(["suggest", str(source_video), "--transcript", str(srt_file), "--work", str(work), "--count", "2",
                 "--min-len", "5", "--max-len", "10", "--no-audio-analysis"]) == 0
    path = work / "clips.json"
    data = json.loads(path.read_text())
    data["clips"] = [{"start": 4.2, "end": 9.0, "hook": "Edited by hand", "title": "Hand picked"}]
    path.write_text(json.dumps(data))
    assert main(["render", str(source_video), "--work", str(work), "--out", str(out), "--layout", "crop",
                 "--preset", "ultrafast", "--crf", "30", "--no-hook"]) == 0
    assert [p.name for p in out.glob("*.mp4")] == ["short_01_hand-picked.mp4"]


def test_cli_reports_problems_with_exit_code_2(tmp_path, source_video, capsys):
    assert main(["run", str(tmp_path / "missing.mp4")]) == 2
    assert "Video not found" in capsys.readouterr().err
    bad = tmp_path / "clips.json"
    bad.write_text(json.dumps({"clips": [{"start": 5, "end": 2}]}))
    assert main(["render", str(source_video), "--clips", str(bad), "--no-captions", "--out", str(tmp_path / "o")]) == 2
    assert "needs numeric" in capsys.readouterr().err
    assert main(["render", str(source_video), "--clips", str(tmp_path / "none.json"), "--no-captions"]) == 2
