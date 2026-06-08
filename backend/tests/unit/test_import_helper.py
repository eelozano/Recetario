"""Unit tests for the recipe-import helper CLI (no network, no real LLM).

The CLI is pure extraction over the scraper/LLM/video adapters; here we stub those
adapters and assert the orchestration: deterministic-first, LLM fallback, the
no-key error paths, macros stripped from the JSON, and the stdout/exit contract.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.ports.ingestion import ExtractError, ScrapeError
from recetario.cli import import_helper
from recetario.domain.entities import SourceType


def _draft(**over) -> RecipeInput:
    base = dict(
        title="Pancakes",
        servings=4,
        source_url="https://example.com/p",
        source_type=SourceType.WEB,
        instructions_md="Mix.\nCook.",
        ingredients=[
            RecipeIngredientInput(
                name="flour", quantity=Decimal("2"), unit="cup", raw_text="2 cups flour"
            )
        ],
        # Macros the scraper might have found — must NOT survive into the payload.
        calories_per_serving=Decimal("250"),
        protein_per_serving=Decimal("6"),
    )
    base.update(over)
    return RecipeInput(**base)


# --- draft_to_payload --------------------------------------------------------


def test_payload_shape_is_camelcase_and_drops_macros():
    payload = import_helper.draft_to_payload(_draft(), source_type="web")

    assert payload["title"] == "Pancakes"
    assert payload["servings"] == 4
    assert payload["sourceType"] == "web"
    assert payload["instructionsMd"] == "Mix.\nCook."
    # Decimal quantities serialize as strings (Decimal on the TS wire).
    assert payload["ingredients"] == [
        {
            "name": "flour",
            "quantity": "2",
            "unit": "cup",
            "rawText": "2 cups flour",
            "notes": None,
        }
    ]
    # No macro keys leak through — imports arrive blank for manual entry.
    assert not any("calorie" in k.lower() or "protein" in k.lower() for k in payload)


def test_payload_null_quantity_stays_null():
    draft = _draft(ingredients=[RecipeIngredientInput(name="salt")])
    payload = import_helper.draft_to_payload(draft, source_type="web")
    assert payload["ingredients"][0]["quantity"] is None


# --- produce_from_url --------------------------------------------------------


class _FakeScraper:
    def __init__(self, *, scrape_result=None, scrape_error=None, page_text="page text"):
        self._scrape_result = scrape_result
        self._scrape_error = scrape_error
        self._page_text = page_text
        self.fetch_called = False

    def scrape(self, url):
        if self._scrape_error is not None:
            raise self._scrape_error
        return self._scrape_result

    def fetch_page_text(self, url):
        self.fetch_called = True
        return self._page_text


def test_url_deterministic_no_key_skips_llm(monkeypatch):
    draft = _draft()
    fake = _FakeScraper(scrape_result=draft)
    monkeypatch.setattr(import_helper, "RecipeScrapersAdapter", lambda: fake)
    monkeypatch.setattr(import_helper, "_extractor_or_none", lambda: None)

    result = import_helper.produce_from_url("https://example.com/p")

    assert result is draft
    assert fake.fetch_called is False  # no fallback when the scrape succeeds


def test_url_structure_applied_when_key_present(monkeypatch):
    draft = _draft()
    structured = _draft(title="Pancakes (structured)")
    fake = _FakeScraper(scrape_result=draft)

    class _Extractor:
        def structure(self, d):
            return structured

    monkeypatch.setattr(import_helper, "RecipeScrapersAdapter", lambda: fake)
    monkeypatch.setattr(import_helper, "_extractor_or_none", lambda: _Extractor())

    result = import_helper.produce_from_url("https://example.com/p")
    assert result is structured


def test_url_structure_failure_falls_back_to_raw_draft(monkeypatch):
    draft = _draft()
    fake = _FakeScraper(scrape_result=draft)

    class _Extractor:
        def structure(self, d):
            raise ExtractError("nope")

    monkeypatch.setattr(import_helper, "RecipeScrapersAdapter", lambda: fake)
    monkeypatch.setattr(import_helper, "_extractor_or_none", lambda: _Extractor())

    assert import_helper.produce_from_url("https://example.com/p") is draft


def test_url_scrape_failure_without_key_raises_friendly(monkeypatch):
    fake = _FakeScraper(scrape_error=ScrapeError("unparseable"))
    monkeypatch.setattr(import_helper, "RecipeScrapersAdapter", lambda: fake)
    monkeypatch.setattr(import_helper, "_extractor_or_none", lambda: None)

    with pytest.raises(ScrapeError) as exc:
        import_helper.produce_from_url("https://example.com/p")
    assert "no Anthropic API key" in str(exc.value)


def test_url_scrape_failure_with_key_uses_web_extract(monkeypatch):
    extracted = _draft(title="From page text")
    fake = _FakeScraper(scrape_error=ScrapeError("unparseable"))

    class _Extractor:
        def extract_from_web(self, page_text, *, source_url):
            assert page_text == "page text"
            assert source_url == "https://example.com/p"
            return extracted

    monkeypatch.setattr(import_helper, "RecipeScrapersAdapter", lambda: fake)
    monkeypatch.setattr(import_helper, "_extractor_or_none", lambda: _Extractor())

    result = import_helper.produce_from_url("https://example.com/p")
    assert result is extracted
    assert fake.fetch_called is True


# --- produce_from_video ------------------------------------------------------


def test_video_without_key_raises_friendly(monkeypatch):
    monkeypatch.setattr(import_helper, "_extractor_or_none", lambda: None)
    with pytest.raises(ScrapeError) as exc:
        import_helper.produce_from_video("https://youtu.be/x")
    assert "needs an Anthropic API key" in str(exc.value)


def test_video_with_key_extracts_from_transcript(monkeypatch):
    extracted = _draft(title="From video", source_type=SourceType.VIDEO)

    class _Fetcher:
        def fetch_transcript(self, url):
            return "spoken transcript"

    class _Extractor:
        def extract_from_transcript(self, transcript, *, source_url):
            assert transcript == "spoken transcript"
            return extracted

    monkeypatch.setattr(import_helper, "YtDlpTranscriptFetcher", lambda: _Fetcher())
    monkeypatch.setattr(import_helper, "_extractor_or_none", lambda: _Extractor())

    assert import_helper.produce_from_video("https://youtu.be/x") is extracted


# --- main() stdout / exit contract -------------------------------------------


def test_main_from_html_prints_json_and_exits_zero(monkeypatch, tmp_path, capsys):
    html_file = tmp_path / "page.html"
    html_file.write_text("<html>...</html>", encoding="utf-8")

    captured_args = {}

    def _produce(html, url):
        captured_args["html"] = html
        captured_args["url"] = url
        return _draft(title="HTML import")

    monkeypatch.setattr(import_helper, "produce_from_html", _produce)

    code = import_helper.main(
        ["from-html", "--url", "https://example.com/p", "--html-file", str(html_file)]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["title"] == "HTML import"
    assert out["sourceType"] == "web"
    assert captured_args["html"] == "<html>...</html>"
    assert captured_args["url"] == "https://example.com/p"


def test_main_surfaces_scrape_error_on_stderr_with_exit_one(monkeypatch, capsys):
    def _boom(url):
        raise ScrapeError("could not read this page")

    monkeypatch.setattr(import_helper, "produce_from_url", _boom)
    code = import_helper.main(["from-url", "https://example.com/p"])
    assert code == 1
    err = capsys.readouterr().err
    assert "could not read this page" in err


def test_main_video_source_type(monkeypatch, capsys):
    monkeypatch.setattr(
        import_helper, "produce_from_video", lambda url: _draft(source_type=SourceType.VIDEO)
    )
    code = import_helper.main(["from-video", "https://youtu.be/x"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["sourceType"] == "video"


# --- serve (persistent worker) -----------------------------------------------


def test_serve_handles_requests_and_exits_on_eof(monkeypatch):
    import io

    monkeypatch.setattr(import_helper, "produce_from_url", lambda url: _draft(title=url))
    monkeypatch.setattr(
        import_helper, "produce_from_html", lambda html, url: _draft(title=f"html:{html}")
    )
    stdin = io.StringIO(
        json.dumps({"id": 1, "command": "from-url", "url": "A"})
        + "\n"
        + "\n"  # blank line ignored
        + json.dumps({"id": 2, "command": "from-html", "url": "u", "html": "<b>"})
        + "\n"
    )
    stdout = io.StringIO()
    code = import_helper.serve(stdin=stdin, stdout=stdout)

    assert code == 0  # clean EOF exit
    lines = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
    assert lines[0] == {"id": 1, "ok": True, "recipe": lines[0]["recipe"]}
    assert lines[0]["recipe"]["title"] == "A"
    assert lines[1]["id"] == 2 and lines[1]["recipe"]["title"] == "html:<b>"


def test_serve_isolates_failures_and_stays_warm(monkeypatch):
    import io

    def _boom(url):
        raise ScrapeError("nope")

    monkeypatch.setattr(import_helper, "produce_from_url", _boom)
    stdin = io.StringIO(
        "not json\n"
        + json.dumps({"id": 7, "command": "from-url", "url": "A"})
        + "\n"
        + json.dumps({"id": 8, "command": "ping"})
        + "\n"
    )
    stdout = io.StringIO()
    import_helper.serve(stdin=stdin, stdout=stdout)

    lines = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
    assert lines[0]["ok"] is False and "Malformed" in lines[0]["error"]
    assert lines[1] == {"id": 7, "ok": False, "error": "nope"}
    # The worker survived a bad request and a failed import to answer the ping.
    assert lines[2] == {"id": 8, "ok": True, "recipe": None}
