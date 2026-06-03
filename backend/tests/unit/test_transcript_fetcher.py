"""Unit tests for video caption parsing + track selection (no network)."""

from __future__ import annotations

import json

import pytest

from recetario.application.ports import TranscriptError
from recetario.infrastructure.video import (
    caption_to_text,
    parse_json3,
    parse_vtt,
    pick_subtitle_track,
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
