import json
import sys
import types

import pytest

from shorts_maker import transcript as T


def test_parse_srt_words_are_interpolated_inside_each_cue(srt_file):
    t = T.load_transcript(srt_file)
    assert len(t["segments"]) == 3
    seg = t["segments"][0]
    assert seg["text"] == "Why did nobody warn you about this mistake?"
    assert [w["word"] for w in seg["words"]][:3] == ["Why", "did", "nobody"]
    assert seg["words"][0]["start"] == pytest.approx(0.5, abs=0.01)
    assert seg["words"][-1]["end"] == pytest.approx(4.0, abs=0.01)
    words = T.words_of(t)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:])), "words must never overlap"


def test_parse_vtt_with_header_ids_settings_tags_and_short_timestamps():
    vtt = """WEBVTT

NOTE this block is ignored

intro
00:01.000 --> 00:03.500 align:start position:0%
<c.colorE5E5E5>Hello</c> <00:00:01.800><c>brave new</c> world [Music]

2
00:00:04.000 --> 00:00:05.000
- (applause) Thanks &amp; goodbye
"""
    t = T.parse_cues(vtt)
    assert [s["text"] for s in t["segments"]] == ["Hello brave new world", "Thanks & goodbye"]
    assert t["segments"][0]["start"] == pytest.approx(1.0, abs=0.01)


def test_overlapping_cues_are_made_monotonic():
    srt = "1\n00:00:00,000 --> 00:00:03,000\nfirst line here\n\n2\n00:00:02,000 --> 00:00:05,000\nsecond line here\n"
    words = T.words_of(T.parse_cues(srt))
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:]))


def test_invalid_subtitle_file_is_rejected(tmp_path):
    bad = tmp_path / "x.srt"
    bad.write_text("this is not a subtitle file", encoding="utf-8")
    with pytest.raises(ValueError):
        T.load_transcript(bad)
    notes = tmp_path / "notes.txt"
    notes.write_text("x")
    with pytest.raises(ValueError, match="Unsupported"):
        T.load_transcript(notes)
    with pytest.raises(FileNotFoundError):
        T.load_transcript(tmp_path / "missing.srt")


def test_interpolate_words_covers_the_span_in_order():
    words = T.interpolate_words("a much longer word, short.", 10.0, 14.0)
    assert [w["word"] for w in words] == ["a", "much", "longer", "word,", "short."]
    assert words[0]["start"] == pytest.approx(10.0)
    assert words[-1]["end"] == pytest.approx(14.0, abs=0.01)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:]))
    assert T.interpolate_words("   ", 0, 1) == []


def test_json_roundtrip_and_whisper_style_input(tmp_path):
    data = {
        "language": "en",
        "segments": [
            {"start": 0, "end": 2, "text": "no words key here"},
            {"start": 2, "end": 4, "text": "x", "words": [{"text": "hand", "start": 2.0, "end": 2.5}]},
        ],
    }
    t = T.normalize(data)
    assert len(t["segments"][0]["words"]) == 4  # interpolated
    assert t["segments"][1]["words"][0]["word"] == "hand"
    path = tmp_path / "t.json"
    T.save_transcript(t, path)
    assert T.load_transcript(path) == t
    with pytest.raises(ValueError):
        T.normalize({"segments": []})


# ---- Whisper wrapper, exercised with a stand-in for faster-whisper (the real model needs a download)
class _FakeWord:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class _FakeSegment:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words


def _install_fake_whisper(monkeypatch, segments):
    calls = {}

    class FakeModel:
        def __init__(self, size, device, compute_type):
            calls["init"] = (size, device, compute_type)

        def transcribe(self, path, **kwargs):
            calls["transcribe"] = (path, kwargs)
            return iter(segments), types.SimpleNamespace(language="en", duration=10.0)

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    monkeypatch.setattr(T, "_cuda_available", lambda: False)
    return calls


def test_whisper_wrapper_converts_segments_and_requests_word_timestamps(monkeypatch):
    segs = [
        _FakeSegment(0.0, 2.0, " Hello world.", [_FakeWord(" Hello", 0.0, 0.8), _FakeWord(" world.", 0.9, 1.7)]),
        _FakeSegment(2.0, 4.0, " No words here", None),  # falls back to interpolation
    ]
    calls = _install_fake_whisper(monkeypatch, segs)
    t = T.transcribe_whisper("video.mp4", model_size="base", language="en", progress=False)
    assert calls["init"] == ("base", "cpu", "int8")
    kwargs = calls["transcribe"][1]
    assert kwargs["word_timestamps"] is True and kwargs["vad_filter"] is True and kwargs["language"] == "en"
    assert t["language"] == "en" and t["duration"] == 10.0
    assert [w["word"] for w in t["segments"][0]["words"]] == ["Hello", "world."]
    assert [w["word"] for w in t["segments"][1]["words"]] == ["No", "words", "here"]


def test_whisper_wrapper_reports_silence(monkeypatch):
    _install_fake_whisper(monkeypatch, [])
    with pytest.raises(RuntimeError, match="no speech"):
        T.transcribe_whisper("video.mp4", progress=False)


def test_get_transcript_prefers_import_then_cache_and_only_then_whisper(tmp_path, srt_file, monkeypatch):
    work = tmp_path / "work"
    imported = T.get_transcript("video.mp4", work, srt_file)
    assert (work / "transcript.json").is_file()

    def boom(*a, **k):
        raise AssertionError("Whisper must not run when a cached transcript exists")

    monkeypatch.setattr(T, "transcribe_whisper", boom)
    assert T.get_transcript("video.mp4", work) == json.loads((work / "transcript.json").read_text())
    assert len(imported["segments"]) == 3

    monkeypatch.setattr(T, "transcribe_whisper", lambda *a, **k: {"language": "en", "duration": 1, "segments": []})
    T.get_transcript("video.mp4", work, force=True)  # --force bypasses the cache
