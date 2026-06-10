import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { importFromHtml, importFromVideo } from "../data/import";

interface Props {
  /** Called with the new recipe's id once an import finishes. */
  onImported: (recipeId: string) => void;
}

/** Hosts whose URLs we route to the video (caption) importer rather than the
 * web-page scraper. Everything else is treated as a web page. */
const VIDEO_HOST = /(^|\.)(youtube\.com|youtu\.be|vimeo\.com|tiktok\.com|instagram\.com)$/i;

function isVideoUrl(raw: string): boolean {
  try {
    return VIDEO_HOST.test(new URL(raw).hostname);
  } catch {
    return false;
  }
}

/** Payload shape emitted by the capture browser's injected script (see lib.rs). */
interface CaptureEvent {
  url: string;
  html: string;
}

/**
 * Import box (browser-first). A web URL opens in an in-app browser window: the
 * page renders as a real browser — clearing paywalls/Cloudflare with the user's
 * own session — and the injected "Import this recipe" button hands the rendered
 * HTML back via a `recipe-html-captured` event, which we import through the
 * `recetario-helper` sidecar (recipe-scrapers + a Haiku pass to structure the
 * ingredients). Video links can't be captured from a DOM, so they still go
 * straight to the sidecar's caption/transcript path.
 */
export function ImportRecipe({ onImported }: Props) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Guard against overlapping imports (e.g. a capture firing mid-import).
  const inFlight = useRef(false);

  async function run(task: () => Promise<string>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setOpened(false);
    setError(null);
    try {
      const id = await task();
      setUrl("");
      onImported(id);
    } catch (e) {
      // Tauri plugin calls can reject with a plain string, so stringify rather
      // than collapse everything to a vague "try again".
      const message = e instanceof Error ? e.message : String(e);
      setError(message || "Import failed. Please try again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  // Listen for HTML handed back by the in-app capture browser.
  useEffect(() => {
    const unlisten = listen<CaptureEvent>("recipe-html-captured", (event) => {
      const { html, url: captured } = event.payload;
      if (html) void run(() => importFromHtml(html, captured));
    });
    return () => {
      void unlisten.then((off) => off());
    };
    // run/onImported are stable enough for this one-time subscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || busy) return;
    // Video → caption path (no DOM to capture). Web → open in the browser.
    if (isVideoUrl(trimmed)) {
      void run(() => importFromVideo(trimmed));
    } else {
      void openInBrowser(trimmed);
    }
  }

  async function openInBrowser(rawUrl: string) {
    const trimmed = rawUrl.trim();
    if (!trimmed || busy) return;
    setError(null);
    try {
      await invoke("open_recipe_capture", { url: trimmed });
      setOpened(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open the page.");
    }
  }

  const isVideo = url.trim() !== "" && isVideoUrl(url);

  return (
    <form className="import" onSubmit={submit}>
      <label className="import__label" htmlFor="import-url">
        Import from URL
      </label>
      <div className="import__row">
        <input
          id="import-url"
          type="url"
          className="import__input"
          placeholder="Paste a recipe or video link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
        />
        <button type="submit" className="btn btn--accent" disabled={busy || !url.trim()}>
          {busy ? "Importing…" : isVideo ? "Import" : "Open in browser"}
        </button>
      </div>
      {busy ? (
        <p className="muted import__hint">
          Reading the recipe… this can take a few seconds.
        </p>
      ) : opened ? (
        <p className="muted import__hint">
          Opened in a browser window — load the page, then click “Import this recipe” on it.
        </p>
      ) : !isVideo ? (
        <p className="muted import__hint">
          Opens the page in an in-app browser so paywalled and protected sites load
          with your own session; click “Import this recipe” to save it.
        </p>
      ) : null}
      {error && <p className="error import__error">{error}</p>}
    </form>
  );
}
