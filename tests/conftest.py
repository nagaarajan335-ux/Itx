"""Shared fixtures. All media is generated with ffmpeg on the fly - no binary assets in the repo."""
import pytest

from shorts_maker.media import find_ffmpeg, run_ffmpeg


def _make_video(path, size="1280x720", seconds=16, audio=True):
    args = ["-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=44100:duration={seconds}"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac", "-shortest"] if audio else ["-an"]
    run_ffmpeg(args + [path])
    return path


@pytest.fixture(scope="session", autouse=True)
def _need_ffmpeg():
    try:
        find_ffmpeg()
    except Exception:  # pragma: no cover
        pytest.skip("ffmpeg is not available", allow_module_level=True)


@pytest.fixture(scope="session")
def source_video(tmp_path_factory):
    return _make_video(tmp_path_factory.mktemp("media") / "src.mp4")


@pytest.fixture(scope="session")
def portrait_video(tmp_path_factory):
    return _make_video(tmp_path_factory.mktemp("media") / "portrait.mp4", size="720x1280", seconds=8)


@pytest.fixture(scope="session")
def silent_video(tmp_path_factory):
    return _make_video(tmp_path_factory.mktemp("media") / "silent.mp4", seconds=8, audio=False)


@pytest.fixture()
def fake_words():
    """A word every half second from t=0.5 to t=15: 'one', 'two', ..."""
    names = "one two three four five six seven eight nine ten".split()
    return [
        {"word": names[i % 10] + ("." if i % 6 == 5 else ""), "start": 0.5 + i * 0.5, "end": 0.5 + i * 0.5 + 0.42}
        for i in range(30)
    ]


SRT_SAMPLE = """1
00:00:00,500 --> 00:00:04,000
Why did nobody warn you about this mistake?

2
00:00:04,200 --> 00:00:09,000
Three years ago I lost everything because I ignored one simple rule.

3
00:00:09,300 --> 00:00:13,500
Honestly, it was the scariest week of my life!
"""


@pytest.fixture()
def srt_file(tmp_path):
    p = tmp_path / "sample.srt"
    p.write_text(SRT_SAMPLE, encoding="utf-8")
    return p
