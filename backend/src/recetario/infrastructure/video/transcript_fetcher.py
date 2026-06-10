"""Video transcript fetcher (implements the VideoTranscriptFetcher port).

Captions-first, no ASR: we ask yt-dlp for a video's existing subtitles (manual
first, then auto-generated), download the chosen track, and flatten it to plain
text for the LLM to extract a recipe from. If a video has no captions at all we
raise `TranscriptError` — audio transcription is a deferred fallback.

The yt-dlp metadata call and the subtitle HTTP fetch are the only network steps;
all selection and caption-format parsing live in module-level pure functions
(`pick_subtitle_track`, `parse_vtt`, `parse_json3`, `caption_to_text`) so they are
unit-tested against fixtures with no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from recetario.application.ports import TranscriptError

# Manual captions are human-written and far cleaner than auto-generated ones, so
# they win; English variants are preferred but we fall back to whatever exists.
_PREFERRED_LANGS = ("en", "en-us", "en-gb", "en-orig")
# Caption container formats we can parse, best first.
_FORMAT_PRIORITY = ("json3", "srv3", "vtt")

_VTT_TAG_RE = re.compile(r"<[^>]+>")  # inline timing/style tags: <00:00:01.000>, <c>

# A recipe video's transcript runs a few tens of KB. Anything far past this is a
# malformed or non-caption payload; cap it so one bad fetch can't balloon the LLM
# bill (200k chars ≈ 50k tokens ≈ a few cents, vs. a 636k-token / ~$1.91 blowout
# when a watch-page HTML body was once flattened as if it were captions).
_MAX_TRANSCRIPT_CHARS = 200_000


@dataclass(frozen=True)
class SubtitleTrack:
    url: str
    ext: str


def _lang_rank(lang: str) -> int:
    base = lang.lower()
    for rank, pref in enumerate(_PREFERRED_LANGS):
        if base == pref or base.startswith(pref):
            return rank
    return len(_PREFERRED_LANGS)


def _format_rank(ext: str) -> int:
    try:
        return _FORMAT_PRIORITY.index(ext)
    except ValueError:
        return len(_FORMAT_PRIORITY)


def pick_subtitle_track(
    subtitles: dict[str, Any] | None,
    automatic: dict[str, Any] | None,
) -> SubtitleTrack | None:
    """Choose the best caption track from a yt-dlp info dict.

    Prefers manual subtitles over auto-generated, English over other languages,
    and a parseable container format. Returns the chosen track or ``None`` when
    no usable track exists.
    """
    # Manual first: if any manual track exists we never fall through to auto.
    for source in (subtitles or {}, automatic or {}):
        best_key: tuple[int, int, str] | None = None
        best_track: SubtitleTrack | None = None
        for lang, formats in source.items():
            if not isinstance(formats, list):
                continue
            for fmt in formats:
                if not isinstance(fmt, dict):
                    continue
                url = fmt.get("url")
                ext = fmt.get("ext", "")
                if not url:
                    continue
                key = (_lang_rank(lang), _format_rank(ext), lang)
                if best_key is None or key < best_key:
                    best_key = key
                    best_track = SubtitleTrack(url=url, ext=ext)
        if best_track is not None:
            return best_track
    return None


def _collapse(lines: list[str]) -> str:
    """Join caption lines, dropping blanks and consecutive duplicates.

    Auto-captions repeat each phrase as the rolling window advances, so naive
    concatenation triples the text; deduping adjacent identical lines fixes it.
    """
    out: list[str] = []
    for line in lines:
        line = line.strip()
        if line and (not out or out[-1] != line):
            out.append(line)
    return "\n".join(out)


def parse_vtt(content: str) -> str:
    """Flatten a WebVTT track to plain text (drop headers, timestamps, tags)."""
    content = content.lstrip("﻿")  # drop a leading UTF-8 BOM if present
    # A real WebVTT file must begin with the "WEBVTT" signature. Reject anything
    # else: an expired/403'd caption URL can return an HTML error or player page,
    # and blindly flattening that as "captions" ships megabytes of markup to the LLM.
    if not content.lstrip().upper().startswith("WEBVTT"):
        raise TranscriptError(
            "Caption track was not valid WebVTT (the URL returned non-caption content)."
        )
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or "-->" in line:
            continue
        if line.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION", "KIND", "LANGUAGE")):
            continue
        if line.isdigit():  # cue index
            continue
        lines.append(_VTT_TAG_RE.sub("", line))
    return _collapse(lines)


def parse_json3(content: str) -> str:
    """Flatten a YouTube json3/srv3 caption payload to plain text."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranscriptError(f"Could not parse json3 captions: {exc}") from exc
    lines: list[str] = []
    for event in data.get("events", []):
        segs = event.get("segs") if isinstance(event, dict) else None
        if not isinstance(segs, list):
            continue
        text = "".join(seg.get("utf8", "") for seg in segs if isinstance(seg, dict))
        if text.strip():
            lines.append(text.replace("\n", " "))
    return _collapse(lines)


def caption_to_text(content: str, ext: str) -> str:
    """Dispatch caption parsing by container format, capping pathological sizes."""
    text = parse_json3(content) if ext in ("json3", "srv3") else parse_vtt(content)
    # Backstop the cost: even a well-formed but extreme transcript is truncated so
    # it can never run up an outsized LLM bill. Validation above already rejects
    # non-caption payloads; this guards the rare genuinely-huge caption track.
    if len(text) > _MAX_TRANSCRIPT_CHARS:
        text = text[:_MAX_TRANSCRIPT_CHARS]
    return text


# Browser-like header so subtitle CDNs don't 403 the default agent.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class YtDlpTranscriptFetcher:
    """Pulls existing captions from a video URL via yt-dlp (no audio download)."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def fetch_transcript(self, url: str) -> str:
        # Lazy imports: the deps are only needed when actually fetching a video
        # (tests inject a fake fetcher and never reach this path).
        try:
            import httpx
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - import guard
            raise TranscriptError(
                "yt-dlp is not installed; run `pip install yt-dlp`."
            ) from exc

        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # noqa: BLE001 - yt-dlp raises many error types
            raise TranscriptError(f"Could not read video {url}: {exc}") from exc

        track = pick_subtitle_track(
            info.get("subtitles"), info.get("automatic_captions")
        )
        if track is None:
            raise TranscriptError(
                "This video has no captions to import from. "
                "(Audio transcription is not supported yet.)"
            )

        try:
            resp = httpx.get(
                track.url,
                follow_redirects=True,
                timeout=self._timeout,
                headers={"User-Agent": _BROWSER_UA},
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise TranscriptError(f"Could not download captions for {url}: {exc}") from exc

        # A caption CDN that's expired or rate-limited can answer 200 with an HTML
        # page instead of the track; reject it before it reaches the parser.
        if "html" in resp.headers.get("content-type", "").lower():
            raise TranscriptError(
                f"Caption URL for {url} returned a web page, not a caption track."
            )

        transcript = caption_to_text(resp.text, track.ext)
        if not transcript.strip():
            raise TranscriptError("The video's captions were empty after parsing.")
        return transcript
