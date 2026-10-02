"""Small helpers shared by the CLI and renderer."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def slugify(text: str, max_len: int = 40, fallback: str = "clip") -> str:
    """ASCII, filesystem-safe slug. Falls back for scripts that have no ASCII form."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    text = text[:max_len].strip("-")
    return text or fallback


def fmt_ts(seconds: float) -> str:
    """12.5 -> '0:12', 3725 -> '1:02:05'."""
    total = int(round(max(0.0, seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def with_timestamp(url: str, seconds: float) -> str:
    """Append a start-time parameter to a YouTube URL so viewers land on the right moment.

    Non-YouTube URLs are returned unchanged.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not (host.endswith("youtube.com") or host.endswith("youtu.be")):
        return url
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "t"]
    query.append(("t", f"{int(max(0, seconds))}s"))
    return urlunparse(parsed._replace(query=urlencode(query)))
