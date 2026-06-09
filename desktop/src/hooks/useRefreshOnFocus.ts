import { useEffect, useRef } from "react";

/**
 * Live FS refresh (#51): re-read the data folder when the window regains focus
 * or becomes visible again — the moment a folder-sync tool (iCloud Drive,
 * Dropbox, Google Drive, …) is most likely to have landed background changes
 * while the app was inactive.
 *
 * Poll-on-focus rather than a native `fs.watch`: cloud-sync folders use dataless
 * placeholder files that often don't emit reliable FS events, so a focus poll is
 * both simpler (no native deps/permissions) and more dependable for this exact
 * case. It only misses changes made while the app is already in the foreground,
 * which a sync client rarely does unobserved.
 *
 * `focus` and `visibilitychange` fire near-simultaneously when switching back to
 * the app, and rapid alt-tabbing can fire repeatedly; the throttle collapses
 * those into a single refresh so the lists don't thrash.
 */
export function useRefreshOnFocus(onRefresh: () => void, throttleMs = 1000): void {
  // Keep the latest callback without re-subscribing the listeners each render.
  const callback = useRef(onRefresh);
  callback.current = onRefresh;
  const lastFiredAt = useRef(0);

  useEffect(() => {
    const fire = () => {
      // visibilitychange also fires on the way out — only refresh when visible.
      if (document.visibilityState === "hidden") return;
      const now = Date.now();
      if (now - lastFiredAt.current < throttleMs) return;
      lastFiredAt.current = now;
      callback.current();
    };

    window.addEventListener("focus", fire);
    document.addEventListener("visibilitychange", fire);
    return () => {
      window.removeEventListener("focus", fire);
      document.removeEventListener("visibilitychange", fire);
    };
  }, [throttleMs]);
}
