import re

import pytest

from shorts_maker import captions as C
from shorts_maker.render import DEFAULT_FONT


def words(texts, start=1.0, dur=0.4, gap=0.1):
    out, t = [], start
    for text in texts:
        out.append({"word": text, "start": t, "end": t + dur})
        t += dur + gap
    return out


def test_ass_colour_is_bgr_and_validated():
    assert C.ass_color("FFD400") == "&H0000D4FF"
    assert C.ass_color("#ff0000") == "&H000000FF"
    assert C.ass_color("000000", 0x80) == "&H80000000"
    with pytest.raises(ValueError):
        C.ass_color("yellow")


def test_ass_time_format():
    assert C.ass_time(0) == "0:00:00.00"
    assert C.ass_time(61.234) == "0:01:01.23"
    assert C.ass_time(3725.5) == "1:02:05.50"
    assert C.ass_time(-3) == "0:00:00.00"


def test_chunking_respects_word_limit_punctuation_and_pauses():
    chunks = C.chunk_words(words(["a", "b", "c", "d", "e"]), max_words=3, max_chars=40)
    assert [[w["word"] for w in c] for c in chunks] == [["a", "b", "c"], ["d", "e"]]

    chunks = C.chunk_words(words(["so", "yes.", "next", "one"]), max_words=3, max_chars=40)
    assert [[w["word"] for w in c] for c in chunks] == [["so", "yes."], ["next", "one"]]

    spaced = words(["x", "y"]) + words(["z"], start=5.0)  # 3 s pause before z
    assert [[w["word"] for w in c] for c in C.chunk_words(spaced, 3, 40)] == [["x", "y"], ["z"]]

    long = C.chunk_words(words(["extraordinary", "circumstances", "arise"]), max_words=3, max_chars=20)
    assert max(len(c) for c in long) < 3  # char budget splits it even under the word limit


def test_one_event_per_word_each_highlighting_exactly_that_word():
    ws = words(["why", "did", "nobody", "tell", "you"])
    style = C.CaptionStyle(font_path=str(DEFAULT_FONT))
    events = C.build_events(ws, style, cx=540, cy=1300, clip_len=10)
    assert len(events) == len(ws)
    hi = C.ass_color(style.highlight)
    for ev, w in zip(events, ws):
        assert ev.count(f"\\1c{hi}") == 1
        assert re.search(rf"\{{\\1c{re.escape(hi)}\}}{w['word'].upper()}\{{", ev)
        assert "\\an5\\pos(540,1300)" in ev


def test_event_times_are_ordered_contiguous_in_a_caption_and_inside_the_clip():
    ws = words(["one", "two", "three", "four", "five", "six"], start=0.5)
    events = C.build_events(ws, C.CaptionStyle(), cx=540, cy=1300, clip_len=4.0)
    spans = []
    for ev in events:
        m = re.match(r"Dialogue: 0,(\d+:\d\d:\d\d\.\d\d),(\d+:\d\d:\d\d\.\d\d),", ev)
        to_s = lambda ts: sum(float(x) * k for x, k in zip(ts.split(":"), (3600, 60, 1)))
        spans.append((to_s(m.group(1)), to_s(m.group(2))))
    assert all(s < e for s, e in spans)
    assert all(e <= 4.0 + 1e-6 for _, e in spans)
    assert all(a[1] <= b[0] + 0.011 for a, b in zip(spans, spans[1:])), "events must not overlap"
    # words inside one caption chunk follow each other without a flicker gap
    assert spans[0][1] == pytest.approx(spans[1][0], abs=0.011)


def test_text_that_is_too_wide_is_wrapped_or_shrunk_instead_of_overflowing():
    style = C.CaptionStyle(font_path=str(DEFAULT_FONT), max_chars=80, words_per_caption=4)
    wide = C.build_events(words(["INTERNATIONALLY", "RECOGNISED", "PROFESSIONALS"]), style, cx=540, cy=1300, clip_len=10)
    assert all("\\N" in ev for ev in wide), "three long words should go on two lines"

    giant = C.build_events(words(["PNEUMONOULTRAMICROSCOPICSILICOVOLCANO"]), style, cx=540, cy=1300, clip_len=10)
    size = int(re.search(r"\\fs(\d+)", giant[0]).group(1))
    assert size < style.font_size, "a single huge word must shrink to fit the frame"

    m = C.TextMeasurer(str(DEFAULT_FONT))
    assert m.width("HELLO WORLD", 104) < style.safe_width


def test_markup_characters_in_speech_cannot_inject_ass_tags():
    ev = C.build_events(words(["{\\an8}hello", "wor\\Nld}"]), C.CaptionStyle(), cx=540, cy=1300, clip_len=5)
    text = "".join(re.sub(r"\{[^}]*\}", "", e.split(",,", 1)[1]) for e in ev)
    assert "an8" in text.lower() and "\\" not in text.replace("\\h", "").replace("\\N", "")
    assert all(e.count("{") == e.count("}") for e in ev)


def test_write_ass_file_has_script_info_styles_captions_and_hook(tmp_path):
    out = tmp_path / "c.ass"
    n = C.write_ass(
        out, words(["hello", "world"]), C.CaptionStyle(), width=1080, height=1920, clip_len=6.0,
        caption_y=1300, hook="Why did nobody warn you about this mistake?", hook_y=340,
    )
    text = out.read_text(encoding="utf-8")
    assert n == 3  # two words + the hook
    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert "Style: Caption,Poppins ExtraBold" in text and "Style: Hook," in text
    hook_line = [ln for ln in text.splitlines() if ",Hook," in ln][0]
    assert "\\fad(" in hook_line and "\\N" in hook_line and "0:00:03.20" in hook_line


def test_wrap_hook_limits_lines_and_uppercases():
    wrapped = C.wrap_hook("a very long hook line that keeps going and going well past three lines of text", width=20)
    assert wrapped.count("\\N") <= 2
    assert wrapped == wrapped.upper()
    assert C.wrap_hook("") == ""
