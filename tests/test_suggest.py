import numpy as np
import pytest

from shorts_maker import suggest as S

FILLER = [
    "and then we kind of went over there",
    "so the thing is it was fine for a while",
    "they said that it would be done later on",
    "we looked at some of the other options too",
]
HOT = [
    "Why did nobody warn you about this terrible mistake?",
    "I lost everything and it was the scariest night of my life!",
    "You will never believe what happened next, it was insane.",
    "Nobody told me the truth about the secret rule!",
    "That one mistake destroyed my whole business.",
]


def build_transcript(total=600.0, hot_start=300.0, sentence_len=4.0):
    """Filler sentences everywhere except a block of punchy ones starting at hot_start."""
    words, t, i = [], 0.0, 0
    while t < total:
        hot = hot_start <= t < hot_start + 45
        text = HOT[int((t - hot_start) // sentence_len) % len(HOT)] if hot else FILLER[i % len(FILLER)]
        i += 1
        toks = text.split()
        per = (sentence_len - 0.4) / len(toks)
        for k, tok in enumerate(toks):
            words.append({"word": tok, "start": t + k * per, "end": t + (k + 1) * per - 0.02})
        t += sentence_len
    seg = {"start": 0, "end": t, "text": "", "words": words}
    return {"language": "en", "duration": t, "segments": [seg]}


def test_hook_scoring_prefers_questions_and_curiosity_over_weak_openings():
    strong = S.hook_score("Why did nobody warn you about this terrible mistake?")
    plain = S.hook_score("We walked to the shop on Tuesday.")
    weak = S.hook_score("and then we kind of went over there")
    assert strong > plain > weak
    assert 0.0 <= weak <= strong <= 1.0
    assert S.hook_score("") == 0.0


def test_make_hook_shortens_long_sentences_cleanly():
    assert S.make_hook("Short and sweet.") == "Short and sweet"
    long = "When I first started the company, nobody believed that we could ever make it work at all"
    hook = S.make_hook(long, max_chars=40)
    assert len(hook) <= 41 and not hook.endswith(" ")
    assert S.make_hook("x " * 100, max_chars=20).endswith("\u2026")


def test_selects_the_punchy_stretch_and_respects_length_and_overlap():
    t = build_transcript()
    clips = S.suggest_clips(t, count=3, min_len=25, max_len=58)
    assert 1 <= len(clips) <= 3
    best = max(clips, key=lambda c: c["score"])
    assert 295 <= best["start"] <= 330, f"expected the hot block (~300s), got {best['start']}"
    assert best["hook"].lower().startswith(("why", "i lost", "you will", "nobody"))
    for c in clips:
        assert 25 <= c["end"] - c["start"] <= 58
    for a, b in zip(clips, clips[1:]):
        assert a["end"] <= b["start"], "clips must not overlap and are listed chronologically"


def test_clips_start_and_end_on_sentence_boundaries():
    t = build_transcript()
    sent_starts = {round(s.start, 2) for s in S.build_sentences(S.words_of(t))}
    sent_ends = {round(s.end, 2) for s in S.build_sentences(S.words_of(t))}
    for c in S.suggest_clips(t, count=4):
        assert round(c["start"], 2) in sent_starts
        assert round(c["end"], 2) in sent_ends


def test_loud_stretch_wins_when_the_text_is_uniform():
    t = build_transcript(hot_start=10_000)  # no punchy text at all
    bins = int(600 / 0.5)
    energy = np.full(bins, -35.0)
    energy[int(420 / 0.5) : int(470 / 0.5)] = -18.0  # a loud stretch at 420-470s
    energy += np.random.default_rng(0).normal(0, 0.5, bins)
    clips = S.suggest_clips(t, count=1, energy=energy)
    assert 410 <= clips[0]["start"] <= 450
    assert "energy" in clips[0]["signals"]


def test_short_transcripts_degrade_gracefully():
    tiny = build_transcript(total=12.0, hot_start=0)
    clips = S.suggest_clips(tiny, count=3, min_len=25, max_len=58)
    assert len(clips) == 1 and clips[0]["end"] - clips[0]["start"] >= 5
    assert S.suggest_clips({"segments": []}, count=3) == []
    assert S.suggest_clips(build_transcript(total=3.0, hot_start=0), count=3) == []


def test_audio_energy_matches_the_audio_track(source_video):
    energy = S.audio_energy(source_video, bin_s=0.5)
    assert 28 <= len(energy) <= 33  # 16 s of audio
    assert -30 < energy.mean() < -10  # a 330 Hz tone: steady, clearly audible
    assert energy.std() < 1.0
