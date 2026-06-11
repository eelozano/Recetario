"""Unit tests for video caption parsing + track selection (no network)."""

from __future__ import annotations

import json

import pytest

from recetario.application.ports import TranscriptError, TranscriptRateLimitedError
from recetario.infrastructure.video import (
    YtDlpTranscriptFetcher,
    caption_to_text,
    parse_json3,
    parse_srv1,
    parse_vtt,
    pick_subtitle_track,
    rank_subtitle_tracks,
)

_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
Welcome back to the channel.

1
00:00:02.000 --> 00:00:04.500 align:start position:0%
Today we're making <00:00:03.000><c>garlic soup</c>.

00:00:04.500 --> 00:00:06.000
Today we're making garlic soup.
"""


def test_parse_vtt_strips_headers_timestamps_tags_and_dedupes():
    text = parse_vtt(_VTT)
    lines = text.splitlines()
    assert lines == [
        "Welcome back to the channel.",
        "Today we're making garlic soup.",
    ]
    # Inline timing tags and the duplicated rolling-window line are gone.
    assert "<c>" not in text
    assert "-->" not in text


def test_parse_json3_concatenates_segments_and_dedupes():
    payload = json.dumps(
        {
            "events": [
                {"segs": [{"utf8": "Add "}, {"utf8": "two cloves"}]},
                {"segs": [{"utf8": "of garlic."}]},
                {"segs": [{"utf8": "of garlic."}]},  # duplicate rolling caption
                {"foo": "no segs"},
            ]
        }
    )
    text = parse_json3(payload)
    assert text.splitlines() == ["Add two cloves", "of garlic."]


def test_parse_json3_raises_on_bad_json():
    with pytest.raises(TranscriptError):
        parse_json3("{not json")


def test_caption_to_text_dispatches_by_ext():
    assert caption_to_text(_VTT, "vtt").startswith("Welcome back")
    j3 = json.dumps({"events": [{"segs": [{"utf8": "hi"}]}]})
    assert caption_to_text(j3, "json3") == "hi"
    assert caption_to_text(j3, "srv3") == "hi"


def test_pick_track_prefers_manual_english_and_parseable_format():
    subtitles = {
        "fr": [{"ext": "vtt", "url": "fr-vtt"}],
        "en": [
            {"ext": "ttml", "url": "en-ttml"},
            {"ext": "json3", "url": "en-json3"},
        ],
    }
    automatic = {"en": [{"ext": "json3", "url": "auto-json3"}]}
    track = pick_subtitle_track(subtitles, automatic)
    assert track is not None
    # Manual English json3 wins over auto and over the ttml format.
    assert track.url == "en-json3"
    assert track.ext == "json3"


def test_pick_track_falls_back_to_automatic_when_no_manual():
    track = pick_subtitle_track({}, {"en": [{"ext": "vtt", "url": "auto-en"}]})
    assert track is not None
    assert track.url == "auto-en"


def test_pick_track_returns_none_without_captions():
    assert pick_subtitle_track(None, None) is None
    assert pick_subtitle_track({}, {}) is None


def test_pick_track_never_selects_live_chat():
    # The rjqWCSuUjcE shape (#62/#64): the only *manual* "subtitle" is the
    # live_chat pseudo-track (ext "json", URL = the watch page), while the real
    # transcript lives in the auto-captions. live_chat must never win.
    subtitles = {"live_chat": [{"ext": "json", "url": "watch-page-html"}]}
    automatic = {"en": [{"ext": "json3", "url": "auto-en-json3"}]}
    track = pick_subtitle_track(subtitles, automatic)
    assert track is not None
    assert track.url == "auto-en-json3"


def test_pick_track_returns_none_when_only_live_chat():
    subtitles = {"live_chat": [{"ext": "json", "url": "watch-page-html"}]}
    assert pick_subtitle_track(subtitles, {}) is None


def test_rank_tracks_orders_source_then_language_then_format():
    subtitles = {"fr": [{"ext": "vtt", "url": "manual-fr-vtt"}]}
    automatic = {
        "en": [
            {"ext": "vtt", "url": "auto-en-vtt"},
            {"ext": "json3", "url": "auto-en-json3"},
            {"ext": "ttml", "url": "auto-en-ttml"},  # unparseable: excluded
        ],
        "de": [{"ext": "json3", "url": "auto-de-json3"}],
    }
    urls = [t.url for t in rank_subtitle_tracks(subtitles, automatic)]
    # Manual (any language) outranks auto; then English; then format priority.
    assert urls == ["manual-fr-vtt", "auto-en-json3", "auto-en-vtt", "auto-de-json3"]


def test_parse_vtt_rejects_non_caption_page_html():
    # An expired/403'd caption URL can answer 200 with the watch-page HTML/JS;
    # flattening that as "captions" once shipped 636k tokens (~$1.91) to the LLM.
    page = (
        'window.WIZ_global_data = {"AfY8Hf":false};\n'
        "window.ytcfg.set('EMERGENCY_BASE_URL', '/error_204');\n"
        "window.onerror=function(msg,url,line){};"
    )
    with pytest.raises(TranscriptError):
        parse_vtt(page)


def test_parse_vtt_accepts_bom_prefixed_signature():
    text = parse_vtt("﻿WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello there.\n")
    assert text == "Hello there."


def test_caption_to_text_caps_oversized_transcript():
    from recetario.infrastructure.video.transcript_fetcher import _MAX_TRANSCRIPT_CHARS

    huge = "word " * 60_000  # ~300k chars of valid caption text, over the cap
    vtt = f"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n{huge}\n"
    text = caption_to_text(vtt, "vtt")
    assert len(text) == _MAX_TRANSCRIPT_CHARS


_SRV1 = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<transcript>"
    '<text start="0" dur="2.1">Welcome back to the channel.</text>'
    '<text start="2.1" dur="3">Today we&amp;#39;re making garlic soup.</text>'
    '<text start="5.1" dur="1">   </text>'
    "</transcript>"
)


def test_parse_srv1_flattens_and_unescapes():
    text = parse_srv1(_SRV1)
    assert text.splitlines() == [
        "Welcome back to the channel.",
        # The double-escaped &amp;#39; resolves all the way to an apostrophe.
        "Today we're making garlic soup.",
    ]


def test_parse_srv1_rejects_non_xml():
    with pytest.raises(TranscriptError):
        parse_srv1("window.WIZ_global_data = {};")


def test_caption_to_text_dispatches_srv1():
    assert caption_to_text(_SRV1, "srv1").startswith("Welcome back")


def test_fetch_transcript_falls_through_to_next_track(monkeypatch):
    # First-ranked track 404s/expires; the import must succeed off the second.
    import yt_dlp

    info = {
        "subtitles": {},
        "automatic_captions": {
            "en": [
                {"ext": "json3", "url": "u-json3"},
                {"ext": "vtt", "url": "u-vtt"},
            ]
        },
    }

    class _FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return info

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)

    fetcher = YtDlpTranscriptFetcher()
    attempted: list[str] = []

    def fake_download(track_url: str) -> str:
        attempted.append(track_url)
        if track_url == "u-json3":
            raise TranscriptError("expired URL")
        return "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello there.\n"

    monkeypatch.setattr(fetcher, "_download", fake_download)

    assert fetcher.fetch_transcript("https://example.com/watch?v=x") == "Hello there."
    assert attempted == ["u-json3", "u-vtt"]


def test_fetch_transcript_surfaces_last_error_when_all_tracks_fail(monkeypatch):
    import yt_dlp

    info = {
        "subtitles": {},
        "automatic_captions": {"en": [{"ext": "json3", "url": "u-json3"}]},
    }

    class _FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return info

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)

    fetcher = YtDlpTranscriptFetcher()

    def failing_download(track_url: str) -> str:
        raise TranscriptError("expired URL")

    monkeypatch.setattr(fetcher, "_download", failing_download)

    with pytest.raises(TranscriptError, match="expired URL"):
        fetcher.fetch_transcript("https://example.com/watch?v=x")


def test_fetch_transcript_short_circuits_on_rate_limit(monkeypatch):
    # A 429 is endpoint-wide: every sibling track hits the same throttled host,
    # so the fetcher must stop after the first rather than fire more requests.
    import yt_dlp

    info = {
        "subtitles": {},
        "automatic_captions": {
            "en": [
                {"ext": "json3", "url": "u-json3"},
                {"ext": "vtt", "url": "u-vtt"},
                {"ext": "srv1", "url": "u-srv1"},
            ]
        },
    }

    class _FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return info

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)

    fetcher = YtDlpTranscriptFetcher()
    attempted: list[str] = []

    def rate_limited_download(track_url: str) -> str:
        attempted.append(track_url)
        raise TranscriptRateLimitedError("YouTube is rate-limiting…")

    monkeypatch.setattr(fetcher, "_download", rate_limited_download)

    with pytest.raises(TranscriptRateLimitedError):
        fetcher.fetch_transcript("https://example.com/watch?v=x")
    # Only the first track was attempted — no hammering the throttled endpoint.
    assert attempted == ["u-json3"]
