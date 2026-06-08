import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { importFromHtml, importFromUrl, importFromVideo } from "../data/import";

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
 * Import-from-URL box. A web/video URL goes straight to the `recetario-helper`
 * sidecar (recipe-scrapers / yt-dlp / Claude). For pages a server-side fetch
 * can't reach (Cloudflare etc.), "Open in browser" launches an in-app window;
 * once the user clicks the injected capture button, the rendered HTML comes back
 * via a `recipe-html-captured` event and is imported the same way.
 */
export function ImportRecipe({ onImported }: Props) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Guard against overlapping imports (e.g. a capture firing mid-import).
  const inFlight = useRef(false);

  async function run(task: () => Promise<string>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
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
    void run(() =>
      isVideoUrl(trimmed) ? importFromVideo(trimmed) : importFromUrl(trimmed),
    );
  }

  async function openInBrowser() {
    const trimmed = url.trim();
    if (!trimmed || busy) return;
    setError(null);
    try {
      await invoke("open_recipe_capture", { url: trimmed });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open the page.");
    }
  }

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
          {busy ? "Importing…" : "Import"}
        </button>
      </div>
      <button
        type="button"
        className="import__browser-link"
        onClick={openInBrowser}
        disabled={busy || !url.trim()}
        title="Open the page in an in-app browser, then click “Import this recipe”"
      >
        Page won't import? Open in browser →
      </button>
      {busy && (
        <p className="muted import__hint">
          Reading the recipe… this can take a few seconds for messy pages or videos.
        </p>
      )}
      {error && <p className="error import__error">{error}</p>}
    </form>
  );
}
