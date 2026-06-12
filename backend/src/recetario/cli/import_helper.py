"""Recipe-import helper CLI (Architecture v2, step 4).

A one-shot command-line tool that does the one thing the TS core can't do well in
JavaScript: turn a URL, a video, or a captured page into a *structured draft
recipe*. It is **pure extraction** — it never touches storage. It reads a source,
runs the deterministic `recipe-scrapers`/`yt-dlp` path (plus an optional Claude
pass to parse ingredient lines), and prints a JSON draft to stdout. The desktop
app spawns this as a Tauri sidecar, parses that JSON, and writes the recipe to the
flat-file store through the TS `RecipeRepository`. That keeps a single data path:
the helper proposes, the TS core persists.

Design notes:
- **No database, no USDA, no macros.** The packaged app's macro workflow is manual
  per-serving entry, so we deliberately drop any nutrition the scraper found and
  leave macros blank for the user to fill in. Output keys are camelCase to map
  straight onto the TS `Recipe` shape.
- **Keys are optional for the common case.** A well-structured page (schema.org /
  JSON-LD) imports with no API key. The Anthropic key (read from
  ``~/.recetario/.env`` via the shared Settings loader) unlocks the LLM fallback
  for messy pages, ingredient-line structuring, and video transcripts.
- **Exit contract:** success → JSON on stdout, exit 0. Any failure → a one-line,
  user-facing message on stderr, exit 1. The desktop side surfaces stderr verbatim.

Subcommands::

    recetario-helper from-url   <url>
    recetario-helper from-video <url>
    recetario-helper from-html  --url <url> [--html-file PATH]   # else stdin
    recetario-helper serve                                       # persistent stdio

The desktop app uses ``serve``: spawn once, keep warm, and send newline-delimited
JSON requests on stdin — ``{"id": N, "command": "from-url", "url": "..."}`` — each
answered by one JSON line on stdout. This amortizes the (one-time) interpreter +
recipe-scrapers import over the whole session, so only the first import is slow.
The loop exits on stdin EOF, which happens automatically when the app quits (its
end of the pipe closes), so no separate lifecycle/watchdog is needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from recetario.application.dto import RecipeInput
from recetario.application.ports.ingestion import ExtractError, ScrapeError
from recetario.infrastructure.config import get_settings
from recetario.infrastructure.llm.recipe_extractor import AnthropicRecipeExtractor
from recetario.infrastructure.scraping.recipe_scraper import (
    RecipeScrapersAdapter,
    html_to_text,
)
from recetario.infrastructure.video.transcript_fetcher import YtDlpTranscriptFetcher

# Shown when a path needs the LLM (messy page / video) but no key is configured.
_NO_KEY_WEB = (
    "Couldn't read this page automatically, and no Anthropic API key is set to fall "
    "back on. Add a key in Settings (returns in a later step) or enter the recipe by "
    "hand with + New recipe."
)
_NO_KEY_VIDEO = (
    "Importing from a video needs an Anthropic API key to read the transcript. Add a "
    "key in Settings (returns in a later step), or enter the recipe by hand."
)


def _extractor_or_none() -> AnthropicRecipeExtractor | None:
    """Build the Claude extractor if a key is configured, else None.

    Absence of a key is not an error: deterministic scraping still works for
    well-structured pages. The LLM is only required for fallbacks and video.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    return AnthropicRecipeExtractor(
        settings.anthropic_api_key,
        model=settings.anthropic_model,
        structuring_model=settings.anthropic_structuring_model,
    )


def _maybe_structure(
    draft: RecipeInput, extractor: AnthropicRecipeExtractor | None
) -> RecipeInput:
    """Best-effort LLM pass to split raw ingredient lines into quantity/unit/name.

    The deterministic scraper yields whole ingredient strings; structuring makes
    them clean enough for shopping-list aggregation. Skipped without a key, and a
    failure falls back to the unstructured draft rather than failing the import.
    """
    if extractor is None or not draft.ingredients:
        return draft
    try:
        return extractor.structure(draft)
    except ExtractError:
        return draft


def produce_from_url(url: str) -> RecipeInput:
    """Deterministic scrape first (free, no key); LLM fallback for messy pages."""
    scraper = RecipeScrapersAdapter()
    extractor = _extractor_or_none()
    try:
        return _maybe_structure(scraper.scrape(url), extractor)
    except ScrapeError as scrape_error:
        if extractor is None:
            raise ScrapeError(_NO_KEY_WEB) from scrape_error
        return extractor.extract_from_web(scraper.fetch_page_text(url), source_url=url)


def produce_from_html(html: str, url: str) -> RecipeInput:
    """Parse caller-supplied (already-rendered) page HTML — no network fetch.

    Mirrors `produce_from_url` but starts from HTML the in-app capture browser
    handed back, so Cloudflare-style JS challenges are already cleared.
    """
    scraper = RecipeScrapersAdapter()
    extractor = _extractor_or_none()
    try:
        return _maybe_structure(scraper.parse_html(html, url), extractor)
    except ScrapeError as scrape_error:
        if extractor is None:
            raise ScrapeError(_NO_KEY_WEB) from scrape_error
        return extractor.extract_from_web(html_to_text(html), source_url=url)


def produce_from_video(url: str) -> RecipeInput:
    """Pull captions (yt-dlp) and have Claude structure them into a recipe."""
    extractor = _extractor_or_none()
    if extractor is None:
        raise ScrapeError(_NO_KEY_VIDEO)
    transcript = YtDlpTranscriptFetcher().fetch_transcript(url)
    return extractor.extract_from_transcript(transcript, source_url=url)


def draft_to_payload(draft: RecipeInput, *, source_type: str) -> dict[str, Any]:
    """Serialize a draft into the camelCase JSON the TS `Recipe` mapper expects.

    Macros and USDA fields are intentionally omitted — imported recipes arrive
    with blank macros for manual per-serving entry.
    """
    return {
        "title": draft.title,
        "description": draft.description,
        "servings": draft.servings,
        "sourceUrl": draft.source_url or None,
        "sourceType": source_type,
        "instructionsMd": draft.instructions_md,
        "ingredients": [
            {
                "name": ing.name,
                "quantity": None if ing.quantity is None else str(ing.quantity),
                "unit": ing.unit,
                "rawText": ing.raw_text,
                "notes": ing.notes,
                "category": ing.category,
            }
            for ing in draft.ingredients
        ],
        "tags": list(draft.tags),
    }


def handle_request(req: dict[str, Any]) -> dict[str, Any]:
    """Process one persistent-mode request into a JSON-serializable response.

    Returns ``{"id", "ok": True, "recipe": {...}}`` on success or
    ``{"id", "ok": False, "error": "..."}`` on a clean failure. Never raises —
    the serve loop must survive a bad import and stay warm for the next one.
    """
    rid = req.get("id")
    command = req.get("command")
    try:
        if command == "from-url":
            payload = draft_to_payload(produce_from_url(req["url"]), source_type="web")
        elif command == "from-video":
            payload = draft_to_payload(produce_from_video(req["url"]), source_type="video")
        elif command == "from-html":
            draft = produce_from_html(req["html"], req["url"])
            payload = draft_to_payload(draft, source_type="web")
        elif command == "ping":
            return {"id": rid, "ok": True, "recipe": None}
        else:
            return {"id": rid, "ok": False, "error": f"Unknown command: {command!r}"}
    except (ScrapeError, ExtractError) as exc:
        return {"id": rid, "ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - keep the worker alive on any failure
        return {"id": rid, "ok": False, "error": f"Import failed: {exc}"}
    return {"id": rid, "ok": True, "recipe": payload}


def serve(stdin=None, stdout=None) -> int:
    """Persistent worker: read NDJSON requests on stdin, write NDJSON responses.

    One request and one response per line. Exits 0 on EOF (the app closed its end
    of the pipe — i.e. quit), or on a broken stdout pipe. Each request is isolated
    so a single failure can't take the warm process down.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            response = {"id": None, "ok": False, "error": "Malformed request (not JSON)."}
        else:
            response = handle_request(req)
        try:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
        except BrokenPipeError:  # pragma: no cover - app went away mid-response
            return 0
    return 0


def _read_html(args: argparse.Namespace) -> str:
    """Captured HTML comes from --html-file (preferred, avoids arg-length limits)
    or stdin. It can be multiple megabytes, so it is never passed as an argument."""
    if args.html_file:
        with open(args.html_file, encoding="utf-8") as handle:
            return handle.read()
    return sys.stdin.read()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recetario-helper",
        description="Extract a structured draft recipe from a URL, video, or page HTML.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_url = sub.add_parser("from-url", help="Import from a recipe web page URL.")
    p_url.add_argument("url")

    p_video = sub.add_parser("from-video", help="Import from a video URL (captions).")
    p_video.add_argument("url")

    p_html = sub.add_parser(
        "from-html", help="Import from already-rendered page HTML (capture browser)."
    )
    p_html.add_argument("--url", required=True, help="Original page URL (for metadata).")
    p_html.add_argument(
        "--html-file",
        default=None,
        help="Path to a UTF-8 HTML file. If omitted, HTML is read from stdin.",
    )

    sub.add_parser(
        "serve",
        help="Persistent worker: NDJSON requests on stdin, responses on stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "serve":
        return serve()
    try:
        if args.command == "from-url":
            payload = draft_to_payload(produce_from_url(args.url), source_type="web")
        elif args.command == "from-video":
            payload = draft_to_payload(produce_from_video(args.url), source_type="video")
        elif args.command == "from-html":
            draft = produce_from_html(_read_html(args), args.url)
            payload = draft_to_payload(draft, source_type="web")
        else:  # pragma: no cover - argparse enforces a valid subcommand
            raise SystemExit(2)
    except (ScrapeError, ExtractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - any failure is a clean user-facing error
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
