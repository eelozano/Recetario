import { useEffect, useRef, useState } from "react";
import { api, type IngestionJob } from "../api/client";

interface Props {
  /** Called with the new recipe's id once an import finishes successfully. */
  onImported: (recipeId: number) => void;
}

// Give up polling after this long (LLM video extraction can take ~a minute).
const POLL_INTERVAL_MS = 1200;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

function isTerminal(job: IngestionJob): boolean {
  return job.status === "succeeded" || job.status === "failed";
}

/**
 * "Import from URL" box. Starts an ingestion job (web page or video), then polls
 * the job until it reaches a terminal state, surfacing progress and any error.
 * On success it hands the new recipe id up so the app can open its draft.
 */
export function ImportRecipe({ onImported }: Props) {
  const [url, setUrl] = useState("");
  const [job, setJob] = useState<IngestionJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  // Keep the latest callback without re-arming the poll effect.
  const onImportedRef = useRef(onImported);
  onImportedRef.current = onImported;
  const startedAt = useRef(0);

  const polling = job != null && !isTerminal(job);
  const busy = starting || polling;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || busy) return;
    setError(null);
    setJob(null);
    setStarting(true);
    const { data, error: apiError } = await api.POST("/ingestion/jobs", {
      body: { url: trimmed },
    });
    setStarting(false);
    if (apiError || !data) {
      setError("Could not start the import. Is the API running?");
      return;
    }
    startedAt.current = Date.now();
    setJob(data);
  }

  // Poll the job while it's still running. Each setJob re-arms this effect.
  useEffect(() => {
    if (job == null || isTerminal(job)) return;
    let active = true;
    const timer = setTimeout(async () => {
      if (Date.now() - startedAt.current > POLL_TIMEOUT_MS) {
        if (active) setError("Import is taking too long — giving up.");
        if (active) setJob(null);
        return;
      }
      const { data, error: apiError } = await api.GET("/ingestion/jobs/{job_id}", {
        params: { path: { job_id: job.id } },
      });
      if (!active) return;
      if (apiError || !data) {
        setError("Lost contact with the import job.");
        setJob(null);
        return;
      }
      setJob(data);
      if (data.status === "succeeded" && data.result_recipe_id != null) {
        setUrl("");
        onImportedRef.current(data.result_recipe_id);
      } else if (data.status === "failed") {
        setError(data.error ?? "Import failed.");
      }
    }, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [job]);

  const succeeded = job?.status === "succeeded";
  const progress = job?.progress ?? (starting ? 5 : 0);

  return (
    <form className="import" onSubmit={submit}>
      <label className="import__label" htmlFor="import-url">
        Import from URL
      </label>
      <div className="import__row">
        <input
          id="import-url"
          className="import__input"
          type="url"
          inputMode="url"
          placeholder="Recipe page or video link…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
        />
        <button className="btn btn--accent" type="submit" disabled={busy || !url.trim()}>
          {busy ? "Importing…" : "Import"}
        </button>
      </div>

      {busy && (
        <div className="import__status" role="status">
          <div className="progress">
            <div className="progress__bar" style={{ width: `${Math.max(progress, 5)}%` }} />
          </div>
          <span className="muted">
            {job?.input_type === "video" ? "Reading video captions…" : "Fetching recipe…"}
          </span>
        </div>
      )}

      {succeeded && !busy && <p className="import__ok">Imported ✓ — review the draft →</p>}
      {error && <p className="error import__error">{error}</p>}
    </form>
  );
}
