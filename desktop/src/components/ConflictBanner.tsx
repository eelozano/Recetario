import { useCallback, useEffect, useState } from "react";
import { scanConflicts, resolveConflict, type ConflictGroup } from "../data/conflicts";

interface Props {
  /** Bump to re-scan (e.g. after a focus refresh or a mutation). */
  reloadKey?: number;
  /** Called after a conflict is resolved, so the parent can refresh its lists. */
  onResolved: () => void;
}

/**
 * Sync-conflict banner (#51, part 2). When a folder-sync tool has dropped a
 * duplicate recipe file (a "conflicted copy"), the repository would otherwise
 * load whichever it found first and silently hide the other edit. This surfaces
 * each conflicted recipe and lets the user keep one copy — the rest are deleted.
 * Renders nothing when the data folder is clean.
 */
export function ConflictBanner({ reloadKey, onResolved }: Props) {
  const [groups, setGroups] = useState<ConflictGroup[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rescan = useCallback(async () => {
    try {
      setGroups(await scanConflicts());
      setError(null);
    } catch {
      // A scan failure shouldn't break the app — just show nothing this round.
      setGroups([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const found = await scanConflicts();
        if (active) setGroups(found);
      } catch {
        if (active) setGroups([]);
      }
    })();
    return () => {
      active = false;
    };
  }, [reloadKey]);

  async function keep(group: ConflictGroup, keepName: string) {
    if (busyKey) return;
    setBusyKey(group.key);
    setError(null);
    try {
      const drop = group.files.map((f) => f.name).filter((n) => n !== keepName);
      await resolveConflict(drop);
      await rescan();
      onResolved();
    } catch {
      setError("Could not resolve the conflict. The files may be in use by a sync app.");
    } finally {
      setBusyKey(null);
    }
  }

  if (groups.length === 0) return null;

  return (
    <div className="conflicts" role="alert">
      <div className="conflicts__head">
        <strong>
          {groups.length === 1
            ? "1 recipe has a sync conflict"
            : `${groups.length} recipes have sync conflicts`}
        </strong>
        <p className="muted">
          A folder-sync app left more than one copy of these recipes. Keep the one you
          want — the others will be deleted.
        </p>
      </div>
      {error && <p className="error">{error}</p>}
      <ul className="conflicts__list">
        {groups.map((group) => (
          <li key={group.key} className="conflicts__group">
            <div className="conflicts__title">
              {group.files.find((f) => f.title)?.title ?? "Untitled recipe"}
            </div>
            <ul className="conflicts__copies">
              {group.files.map((file, i) => (
                <li key={file.name} className="conflicts__copy">
                  <div className="conflicts__copy-info">
                    <span className="conflicts__copy-name">{file.name}</span>
                    <span className="muted conflicts__copy-meta">
                      {file.suffixed ? "conflicted copy · " : i === 0 ? "most recent · " : ""}
                      {formatWhen(file.updatedAt)}
                    </span>
                  </div>
                  <button
                    className="btn btn--small"
                    onClick={() => keep(group, file.name)}
                    disabled={busyKey === group.key}
                  >
                    {busyKey === group.key ? "Resolving…" : "Keep this"}
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Human-friendly "edited <date>" from an ISO timestamp, or a fallback. */
function formatWhen(updatedAt: string | null): string {
  if (!updatedAt) return "no timestamp";
  const d = new Date(updatedAt);
  if (Number.isNaN(d.getTime())) return "no timestamp";
  return `edited ${d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })}`;
}
