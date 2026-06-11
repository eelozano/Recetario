"""Video transcript fetcher (implements the VideoTranscriptFetcher port).

Captions-first, no ASR: we ask yt-dlp for a video's existing subtitles (manual
first, then auto-generated), download the chosen track, and flatten it to plain
text for the LLM to extract a recipe from. If a video has no captions at all we
raise `TranscriptError` — audio transcription is a deferred fallback.

The yt-dlp metadata call and the subtitle HTTP fetch are the only network steps;
all selection and caption-format parsing live in module-level pure functions
(`rank_subtitle_tracks`, `parse_vtt`, `parse_json3`, `parse_srv1`,
`caption_to_text`) so they are unit-tested against fixtures with no network.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

from recetario.application.ports import TranscriptError, TranscriptRateLimitedError

# Manual captions are human-written and far cleaner than auto-generated ones, so
# they win; English variants are preferred but we fall back to whatever exists.
_PREFERRED_LANGS = ("en", "en-us", "en-gb", "en-orig")
# Caption container formats we have a parser for, best first. Selection is
# restricted to this set: yt-dlp also lists pseudo-subtitles like `live_chat`
# (ext "json", URL = the watch page itself) and formats we can't parse
# (ttml/srt); picking live_chat once flattened 1.4MB of page HTML into a
# $1.91 LLM call (#62/#64).
_FORMAT_PRIORITY = ("json3", "srv1", "srv3", "vtt")
# How many candidate tracks to try before giving up: enough to route around a
# few bad URLs without hammering the caption CDN across 150+ auto languages.
_MAX_TRACK_ATTEMPTS = 4

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


def rank_subtitle_tracks(
    subtitles: dict[str, Any] | None,
    automatic: dict[str, Any] | None,
) -> list[SubtitleTrack]:
    """Rank every usable caption track from a yt-dlp info dict, best first.

    Only tracks in a parseable container format are candidates — this is what
    drops `live_chat` and other pseudo-subtitles. Manual subtitles outrank
    auto-generated, English outranks other languages, and cleaner machine
    formats outrank cue-text ones. Returning the whole ranking (rather than a
    single winner) lets the fetcher fall through to the next candidate when a
    track's URL fails validation, so one bad URL doesn't doom the import.
    """
    ranked: list[tuple[tuple[int, int, int, str], SubtitleTrack]] = []
    seen: set[str] = set()
    for source_rank, source in enumerate((subtitles or {}, automatic or {})):
        for lang, formats in source.items():
            if not isinstance(formats, list):
                continue
            for fmt in formats:
                if not isinstance(fmt, dict):
                    continue
                url = fmt.get("url")
                ext = fmt.get("ext", "")
                if not url or ext not in _FORMAT_PRIORITY or url in seen:
                    continue
                seen.add(url)
                key = (source_rank, _lang_rank(lang), _format_rank(ext), lang)
                ranked.append((key, SubtitleTrack(url=url, ext=ext)))
    ranked.sort(key=lambda item: item[0])
    return [track for _, track in ranked]


def pick_subtitle_track(
    subtitles: dict[str, Any] | None,
    automatic: dict[str, Any] | None,
) -> SubtitleTrack | None:
    """The single best caption track, or ``None`` when no usable track exists."""
    tracks = rank_subtitle_tracks(subtitles, automatic)
    return tracks[0] if tracks else None


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


def parse_srv1(content: str) -> str:
    """Flatten a YouTube srv1 caption payload to plain text.

    srv1 is a minimal XML format: ``<transcript><text start dur>…</text>…``.
    YouTube double-escapes entities in it (``&amp;#39;``), so the text needs one
    more unescape pass after XML parsing.
    """
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise TranscriptError(f"Could not parse srv1 captions: {exc}") from exc
    lines: list[str] = []
    for node in root.iter("text"):
        text = html.unescape("".join(node.itertext()))
        if text.strip():
            lines.append(text.replace("\n", " "))
    return _collapse(lines)


def caption_to_text(content: str, ext: str) -> str:
    """Dispatch caption parsing by container format, capping pathological sizes."""
    if ext in ("json3", "srv3"):
        text = parse_json3(content)
    elif ext == "srv1":
        text = parse_srv1(content)
    else:
        text = parse_vtt(content)
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

        tracks = rank_subtitle_tracks(
            info.get("subtitles"), info.get("automatic_captions")
        )
        if not tracks:
            raise TranscriptError(
                "This video has no captions to import from. "
                "(Audio transcription is not supported yet.)"
            )

        # Try candidates best-first: a single track whose URL has expired or
        # answers with an HTML page shouldn't doom the import when the same
        # captions exist in another format or language.
        last_error: TranscriptError | None = None
        for track in tracks[:_MAX_TRACK_ATTEMPTS]:
            try:
                transcript = caption_to_text(self._download(track.url), track.ext)
                if not transcript.strip():
                    raise TranscriptError("The video's captions were empty after parsing.")
                return transcript
            except TranscriptRateLimitedError:
                # A 429 is endpoint-wide: every sibling track hits the same host,
                # so trying more only deepens YouTube's throttle. Stop now and
                # surface a wait-and-retry message instead of hammering.
                raise
            except TranscriptError as exc:
                last_error = exc
        raise TranscriptError(f"Could not download captions for {url}: {last_error}")

    def _download(self, track_url: str) -> str:
        """Fetch one caption track, raising ``TranscriptError`` on anything unusable."""
        import httpx

        try:
            resp = httpx.get(
                track_url,
                follow_redirects=True,
                timeout=self._timeout,
                headers={"User-Agent": _BROWSER_UA},
            )
            # YouTube throttles the timedtext endpoint per-IP/video, and it trips
            # easily on repeated imports of the same video. Translate it into a
            # clear, actionable message — and a distinct type so the caller stops
            # retrying sibling tracks (which only deepens the throttle).
            if resp.status_code == 429:
                raise TranscriptRateLimitedError(
                    "YouTube is rate-limiting caption downloads for this video "
                    "right now (HTTP 429). This is temporary — wait a few minutes "
                    "before trying again (repeated retries make it last longer)."
                )
            resp.raise_for_status()
        except TranscriptError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TranscriptError(f"Could not download captions: {exc}") from exc

        # A caption CDN that's expired or rate-limited can answer 200 with an HTML
        # page instead of the track; reject it before it reaches the parser.
        if "html" in resp.headers.get("content-type", "").lower():
            raise TranscriptError(
                "Caption URL returned a web page, not a caption track."
            )
        return resp.text
