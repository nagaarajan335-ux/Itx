"""Command line interface:  python -m shorts_maker <command> VIDEO [options]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from . import __version__
from .captions import CaptionStyle, ass_color
from .media import MediaError, probe
from .render import RenderOptions, render_all
from .suggest import audio_energy, suggest_clips
from .transcript import get_transcript, words_of
from .util import fmt_ts, slugify

RESPONSIBLE_USE = (
    "Only use videos you own or have permission to reuse. Many creators forbid re-uploading their audio or "
    "animation; doing so leads to Content ID claims and copyright strikes."
)


# --------------------------------------------------------------------------- argument parsing
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shorts_maker",
        description="Turn a long video you own into captioned, vertical YouTube Shorts. " + RESPONSIBLE_USE,
    )
    parser.add_argument("--version", action="version", version=f"shorts_maker {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("video", help="path to the long video file")
    common.add_argument("--work", help="working folder for transcript / clips.json (default: work/<video name>)")

    tx = argparse.ArgumentParser(add_help=False)
    g = tx.add_argument_group("transcription")
    g.add_argument("--transcript", help="use an existing .srt / .vtt / .json instead of running Whisper")
    g.add_argument("--model", default="small", help="Whisper model: tiny, base, small, medium, large-v3 (default: small)")
    g.add_argument("--language", help="spoken language code, e.g. en, ms, ta (default: auto-detect)")
    g.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    g.add_argument("--force", action="store_true", help="ignore the cached transcript and transcribe again")

    sg = argparse.ArgumentParser(add_help=False)
    g = sg.add_argument_group("clip selection")
    g.add_argument("--count", type=int, default=8, help="how many Shorts to suggest (default: 8)")
    g.add_argument("--min-len", type=float, default=25.0, help="shortest Short in seconds (default: 25)")
    g.add_argument("--max-len", type=float, default=58.0, help="longest Short in seconds (default: 58)")
    g.add_argument("--no-audio-analysis", action="store_true", help="skip the loudness analysis (faster)")

    rd = argparse.ArgumentParser(add_help=False)
    g = rd.add_argument_group("rendering")
    g.add_argument("--out", help="output folder (default: output/<video name>)")
    g.add_argument("--layout", choices=["blur", "crop"], default="blur",
                   help="blur: whole frame over a blurred backdrop (default); crop: fill the screen")
    g.add_argument("--no-captions", action="store_true", help="do not burn in word-by-word captions")
    g.add_argument("--no-hook", action="store_true", help="do not show the hook banner at the top")
    g.add_argument("--words-per-caption", type=int, default=3)
    g.add_argument("--no-uppercase", action="store_true", help="keep the original letter case in captions")
    g.add_argument("--highlight", default="FFD400", help="colour of the spoken word, hex RGB (default: FFD400)")
    g.add_argument("--font", help="TTF/OTF font for captions (needed for scripts such as Tamil, Chinese, Arabic)")
    g.add_argument("--fps", type=int, default=30)
    g.add_argument("--crf", type=int, default=21, help="x264 quality, lower = better/larger (default: 21)")
    g.add_argument("--preset", default="veryfast", help="x264 speed preset (default: veryfast)")
    g.add_argument("--no-loudnorm", action="store_true", help="do not normalise loudness to -14 LUFS")
    g.add_argument("--source-url", help="URL of the full video; added to every description with a timestamp")
    g.add_argument("--credit", help="credit / licence line added to every description")
    g.add_argument("--hashtags", default="#shorts", help="hashtags appended to every description")

    sub.add_parser("transcribe", parents=[common, tx], help="create transcript.json (Whisper or imported subtitles)")
    sub.add_parser("suggest", parents=[common, tx, sg], help="find the best moments and write an editable clips.json")
    p = sub.add_parser("render", parents=[common, tx, rd], help="render the Shorts listed in clips.json")
    p.add_argument("--clips", help="clips file (default: <work>/clips.json)")
    sub.add_parser("run", parents=[common, tx, sg, rd], help="transcribe, pick moments and render, in one go")
    return parser


# --------------------------------------------------------------------------- helpers
def _paths(args) -> "tuple[Path, Path, Path]":
    video = Path(args.video).expanduser()
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")
    stem = slugify(video.stem, 60, "video")
    work = Path(args.work) if args.work else Path("work") / stem
    out = Path(args.out) if getattr(args, "out", None) else Path("output") / stem
    return video.resolve(), work, out


def _transcript(args, video: Path, work: Path):
    return get_transcript(
        video, work, args.transcript, force=args.force, model_size=args.model, language=args.language, device=args.device
    )


def _render_options(args) -> RenderOptions:
    ass_color(args.highlight)  # fail early on a bad colour
    style = CaptionStyle(
        words_per_caption=max(1, args.words_per_caption), uppercase=not args.no_uppercase, highlight=args.highlight
    )
    return RenderOptions(
        layout=args.layout, fps=args.fps, crf=args.crf, preset=args.preset, captions=not args.no_captions,
        hook=not args.no_hook, normalize_audio=not args.no_loudnorm, font_path=args.font, style=style,
    )


def load_clips(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    clips = data.get("clips") if isinstance(data, dict) else data
    if not isinstance(clips, list) or not clips:
        raise ValueError(f"{path} has no clips. Run the 'suggest' command first or add some by hand.")
    for i, clip in enumerate(clips, 1):
        try:
            ok = float(clip["end"]) > float(clip["start"]) >= 0
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok:
            raise ValueError(f"Clip {i} in {path} needs numeric 'start' and 'end' (seconds) with end > start.")
    return clips


def _print_clips(clips: List[Dict[str, Any]]) -> None:
    print(f"\n  {'#':>2}  {'start':>8}  {'end':>8}  {'len':>4}  {'score':>5}  hook")
    for i, c in enumerate(clips, 1):
        print(
            f"  {i:>2}  {fmt_ts(c['start']):>8}  {fmt_ts(c['end']):>8}  {c['end'] - c['start']:>3.0f}s  "
            f"{c.get('score', 0):>5.2f}  {c.get('hook', '')}"
        )


def _suggest(args, video: Path, work: Path) -> List[Dict[str, Any]]:
    transcript = _transcript(args, video, work)
    print(f"Transcript: {len(words_of(transcript))} words, language {transcript.get('language') or 'unknown'}")
    energy = None
    if not args.no_audio_analysis:
        print("Analysing loudness...")
        energy = audio_energy(video)
    clips = suggest_clips(
        transcript, count=args.count, min_len=args.min_len, max_len=args.max_len, energy=energy
    )
    if not clips:
        raise ValueError("No suitable moments found. Try a lower --min-len, or check the transcript.")
    clips_path = work / "clips.json"
    clips_path.parent.mkdir(parents=True, exist_ok=True)
    clips_path.write_text(json.dumps({"source": str(video), "clips": clips}, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_clips(clips)
    print(f"\nSaved {clips_path} - edit start/end/hook/title there if you like, then run 'render'.")
    return clips


def _render(args, video: Path, work: Path, out: Path, clips: List[Dict[str, Any]]) -> None:
    transcript = None if args.no_captions else _transcript(args, video, work)
    results = render_all(
        video, clips, transcript, out, _render_options(args),
        source_url=args.source_url, credit=args.credit, hashtags=args.hashtags,
        log=lambda m: print(m, flush=True),
    )
    print(f"\nDone: {len(results)} Shorts in {out}/  (titles and descriptions: {out / 'shorts.md'})")


# --------------------------------------------------------------------------- commands
def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        video, work, out = _paths(args)
        print(f"Reminder: {RESPONSIBLE_USE}\n", file=sys.stderr)
        if args.command == "transcribe":
            t = _transcript(args, video, work)
            print(f"Wrote {work / 'transcript.json'} ({len(words_of(t))} words, {t.get('duration', 0):.0f}s)")
        elif args.command == "suggest":
            _suggest(args, video, work)
        elif args.command == "render":
            clips = load_clips(Path(args.clips) if args.clips else work / "clips.json")
            _render(args, video, work, out, clips)
        elif args.command == "run":
            info = probe(video)
            print(f"{video.name}: {info.width}x{info.height}, {fmt_ts(info.duration)}")
            _render(args, video, work, out, _suggest(args, video, work))
        return 0
    except (MediaError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
